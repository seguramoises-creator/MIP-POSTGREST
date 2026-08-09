# Médicos TOP — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar las tres reglas de Médicos TOP del §7.3 del requerimiento de Mallén: no publicar una planeación que omita un TOP, marcar los TOP sin visita/revisita, y recordar al representante con escalamiento al Gerente de Distrito.

**Architecture:** Una columna `es_top` en `Visita.DIM_MedicoVisita` poblada desde `ext.panelmedico.prioridad`; la validación al publicar vive en `visita_planeacion_service`; la marca en pantalla se deriva de lo que `visita_cobertura_service` ya calcula; y los avisos los produce un servicio nuevo (`visita_top_service`) que dispara un job diario de reconciliación de APScheduler, con una tabla de idempotencia para no reenviar.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, APScheduler, pytest contra PostgreSQL real, React 18 + TypeScript + MUI v6.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-09-medicos-top-design.md`. Ante duda, manda el spec.
- **Intérprete**: `backend/venv/Scripts/python.exe`. El `python` del PATH **no** tiene las dependencias.
- Los tests corren contra **PostgreSQL real** y se saltan (SKIPPED) si no hay servidor. SKIPPED es aceptable; FAILED/ERROR no.
- **Ausencia de dato = NO es TOP.** `es_top` es `Boolean NOT NULL default False`. Nunca nulo.
- **`es_top` se reafirma en cada integración**, como `activo` — es dato maestro del SFA, no algo que el representante edite.
- **El filtro de "cuenta en el ciclo" es `visita_aprobacion_service.cuenta_en_ciclo`, nunca `MedicoVisita.activo` a secas.** Con `activo` se exigiría planear médicos con alta pendiente o ya dados de baja.
- **El rótulo visible es "TOP", nunca "Prioridad"**: `ParrillaPromocional.prioridad` ya usa esa palabra con otro significado (orden de producto 1-N) en pantallas vecinas.
- **Días hábiles**: usar `cobertura_predictiva_service._networkdays` y `_feriados_pais` (respetan `DIM_Feriado`). **NO** usar `visita_cobertura_service._dias_habiles`, que ignora feriados y usa `date.today()` en vez de la hora local del país.
- **Ciclos cerrados no se procesan ni generan avisos.**
- **PROHIBIDO tocar** el esquema `ext` (`app/models/integracion_ext.py`, migración `0030`), `motor_calculo_service.py`, `recalculo_service.py`, `cobertura_predictiva_service.py` (solo se **importa** de él), `cobertura_farmacia_service.py`, y el motor de Score/indicadores. Este módulo no escribe una sola fila de `FACT_ResultadoIndicador`.
- **No se crean pantallas nuevas** ni se toca la matriz RBAC: los alcances `REG_OWN`/`R_TEAM` ya cubren el caso.
- Convenciones: modelos con `Mapped`/`mapped_column` (nunca `Column()`), `datetime.now(timezone.utc)` (nunca `utcnow()`), `from loguru import logger` (nunca `print()`), servicios reciben `db: Session` y no acceden a HTTP.
- Migración: la cadena usa ids legibles (`0033_mapeo_externo` es el head actual). La nueva es **`0034_medicos_top`** con `down_revision = "0033_mapeo_externo"`.

---

### Task 1: Migración, modelos y sincronización de `es_top`

**Files:**
- Create: `backend/alembic/versions/0034_medicos_top.py`
- Modify: `backend/app/models/visita.py` (columna en `MedicoVisita`, modelo `AvisoTopEnviado` nuevo)
- Modify: `backend/app/services/integracion_visitas_service.py` (poblar y reafirmar `es_top`)
- Test: `backend/tests/test_medicos_top.py`

**Interfaces:**
- Produces: `MedicoVisita.es_top: Mapped[bool]`; `AvisoTopEnviado` con campos `(id, vm_id, ciclo_id, medico_id, tipo_visita, tipo_aviso, fecha_envio)` y las constantes `AVISO_RECORDATORIO = "RECORDATORIO"` / `AVISO_ESCALAMIENTO = "ESCALAMIENTO"`.

- [ ] **Step 1: Escribir los tests**

Crear `backend/tests/test_medicos_top.py`. Copia el bloque de fixtures `motor`/`db` de `backend/tests/test_integracion_visitas.py` **tal cual**, cambiando `BD_PRUEBA = "vista_test_medicos_top"` y añadiendo `'"Visita"."AvisoTopEnviado"'`, `'"Visita"."PlaneacionEvento"'`, `'"Visita"."PlaneacionCiclo"'` y `'"Visita"."DIM_MedicoVisita"'` al **inicio** de la lista de limpieza (hijas antes que padres). Añade después:

```python
from app.models.visita import AvisoTopEnviado, MedicoVisita
from app.services import integracion_visitas_service as viz


def _panel_ext(db, medico="MD01", prioridad="TOP"):
    db.add(ExtPanelMedico(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026", rm_codigo="VM01",
        medico_codigo=medico, frecuencia_objetivo="F1", prioridad=prioridad,
        visitas_programadas=2, activo=True))
    db.flush()


def test_prioridad_top_marca_es_top(escenario):
    db = escenario["db"]
    _panel_ext(db, prioridad="TOP")
    db.commit()

    viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(MedicoVisita).one().es_top is True


def test_prioridad_regular_no_marca(escenario):
    db = escenario["db"]
    _panel_ext(db, prioridad="REGULAR")
    db.commit()

    viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(MedicoVisita).one().es_top is False


def test_prioridad_tolera_la_caja(escenario):
    """El origen ya ha demostrado mandar variaciones de caja."""
    db = escenario["db"]
    _panel_ext(db, prioridad="  top  ")
    db.commit()

    viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(MedicoVisita).one().es_top is True


def test_dejar_de_ser_top_se_reafirma(escenario):
    """El caso que distingue «reafirmar siempre» de «escribir solo al crear».

    Un médico que era TOP y llega como REGULAR en el siguiente lote debe
    quedar en False: es dato maestro del SFA, no una edición del representante.
    """
    db = escenario["db"]
    _panel_ext(db, prioridad="TOP")
    db.commit()
    viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()
    db.query(ExtPanelMedico).one().prioridad = "REGULAR"
    db.commit()

    viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(MedicoVisita).one().es_top is False


def test_medico_de_alta_manual_no_es_top(escenario):
    """Nunca pasa por `ext`: su default debe ser False, no nulo. Si fuera nulo
    y se tratara como TOP, bloquearía la publicación por una ficha que el
    representante creó a mano."""
    db = escenario["db"]
    m = MedicoVisita(vm_id=escenario["rm"].id, nombre_completo="DOCTOR MANUAL")
    db.add(m)
    db.commit()

    assert m.es_top is False
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_medicos_top.py -v`
Expected: FAIL con `ImportError: cannot import name 'AvisoTopEnviado'`.

- [ ] **Step 3: Añadir la columna y el modelo**

En `backend/app/models/visita.py`, dentro de `class MedicoVisita`, justo **después** de `categoria` (para que quede junto a los otros criterios de clasificación):

```python
    # Prioridad TOP del SFA de Mallén (`ext.panelmedico.prioridad`). NO es la
    # categoría A/B/C ni el potencial de prescripción: el §11.5 del requerimiento
    # avisa literalmente que "marcar TOP no es marcar categoría A" — son tres
    # criterios ortogonales que el contrato envía en tres columnas separadas.
    # Sin dato = NO es TOP (los médicos de alta manual nunca pasan por `ext`).
    es_top: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                         server_default=sa_text("false"))
```

Añade al principio del archivo, si no está: `from sqlalchemy import text as sa_text`. (`Boolean` ya está importado.)

Y al final del archivo, el modelo nuevo:

```python
AVISO_RECORDATORIO = "RECORDATORIO"
AVISO_ESCALAMIENTO = "ESCALAMIENTO"


class AvisoTopEnviado(Base):
    """Un aviso de médico TOP ya enviado. Existe para NO reenviarlo.

    El job de TOP es un cron diario de reconciliación: sin esta tabla mandaría
    el mismo correo cada mañana mientras la visita siguiera vencida. El proyecto
    no tenía ningún registro de notificaciones enviadas, así que se crea aquí.

    Append-only, como `PlaneacionEvento`: si el representante finalmente ejecuta
    la visita, el aviso ya enviado sigue siendo historia y no se borra.
    """
    __tablename__ = "AvisoTopEnviado"
    __table_args__ = (
        UniqueConstraint("vm_id", "ciclo_id", "medico_id", "tipo_visita", "tipo_aviso",
                         name="UQ_AvisoTop_clave"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    medico_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Visita.DIM_MedicoVisita.id"), nullable=False)
    tipo_visita: Mapped[str] = mapped_column(CHAR(1), nullable=False)      # V / R
    tipo_aviso: Mapped[str] = mapped_column(String(20), nullable=False)    # RECORDATORIO / ESCALAMIENTO
    fecha_envio: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_ahora)
```

Comprueba que `UniqueConstraint` esté en los imports de `sqlalchemy` del archivo; si no, añádelo.

- [ ] **Step 4: Escribir la migración**

Crear `backend/alembic/versions/0034_medicos_top.py`:

```python
"""Medicos TOP: es_top en el panel de visita + tabla de avisos enviados.

Revision ID: 0034_medicos_top
Revises: 0033_mapeo_externo
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0034_medicos_top"
down_revision: Union[str, Sequence[str], None] = "0033_mapeo_externo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOT NULL con server_default: la tabla tiene datos reales en produccion y
    # sin default el ALTER fallaria. `false` es la semantica correcta —
    # ausencia de dato = NO es TOP (ver spec §2).
    op.add_column(
        "DIM_MedicoVisita",
        sa.Column("es_top", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="Visita",
    )
    op.create_table(
        "AvisoTopEnviado",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vm_id", sa.Integer(), nullable=False),
        sa.Column("ciclo_id", sa.Integer(), nullable=False),
        sa.Column("medico_id", sa.Integer(), nullable=False),
        sa.Column("tipo_visita", sa.CHAR(length=1), nullable=False),
        sa.Column("tipo_aviso", sa.String(length=20), nullable=False),
        sa.Column("fecha_envio", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["vm_id"], ["Config.DIM_RM.id"]),
        sa.ForeignKeyConstraint(["ciclo_id"], ["Config.DIM_Ciclo.id"]),
        sa.ForeignKeyConstraint(["medico_id"], ["Visita.DIM_MedicoVisita.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vm_id", "ciclo_id", "medico_id", "tipo_visita", "tipo_aviso",
                            name="UQ_AvisoTop_clave"),
        schema="Visita",
    )


def downgrade() -> None:
    op.drop_table("AvisoTopEnviado", schema="Visita")
    op.drop_column("DIM_MedicoVisita", "es_top", schema="Visita")
```

- [ ] **Step 5: Aplicar y verificar la migración**

Run: `cd backend && ./venv/Scripts/python.exe -m alembic upgrade head`
Expected: aplica `0034_medicos_top` sin error.

Run: `cd backend && ./venv/Scripts/python.exe -m alembic current`
Expected: `0034_medicos_top (head)`

- [ ] **Step 6: Poblar `es_top` en la integración**

En `backend/app/services/integracion_visitas_service.py`, dentro de `integrar_panel_medico`, en el bloque que escribe `Visita.DIM_MedicoVisita`. Busca dónde se crea el `MedicoVisita` y dónde se reafirman sus campos tras `mapeo.resolver` (el mismo sitio donde hoy se reafirma `estado_aprobacion = "APROBADO"`).

Añade el helper junto a los demás del módulo:

```python
def _es_top(prioridad: str | None) -> bool:
    """`ext.panelmedico.prioridad` → booleano. Tolerante a la caja: el origen ya
    ha demostrado mandar variaciones."""
    return (prioridad or "").strip().upper() == "TOP"
```

En la creación del `MedicoVisita`, añade `es_top=_es_top(f.prioridad)`. Y **tras `mapeo.resolver`**, junto a la reafirmación de `estado_aprobacion`, añade:

```python
        # Se reafirma SIEMPRE, como `activo` y `estado_aprobacion`: la prioridad
        # es dato maestro del SFA. Un médico que pasa de TOP a REGULAR entre
        # ciclos tiene que dejar de serlo. (A diferencia de `nombre_completo`,
        # que solo se escribe al crear para no pisar correcciones del GD.)
        panel.es_top = _es_top(fila.prioridad)
```

Usa el nombre real de la variable del registro adoptado en ese bloque (no lo asumas: léelo).

- [ ] **Step 7: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_medicos_top.py -v`
Expected: 5 passed (o SKIPPED).

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_visitas.py -q`
Expected: sin regresiones.

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/0034_medicos_top.py backend/app/models/visita.py backend/app/services/integracion_visitas_service.py backend/tests/test_medicos_top.py
git commit -m "feat(top) es_top en el panel de visita y tabla de avisos enviados"
```

---

### Task 2: Regla 1 — no publicar una planeación que omita un TOP

**Files:**
- Modify: `backend/app/services/visita_planeacion_service.py`
- Modify: `backend/app/api/v1/routers/visita.py` (traducir la excepción a 409)
- Test: `backend/tests/test_medicos_top.py`

**Interfaces:**
- Consumes: `MedicoVisita.es_top` (Task 1).
- Produces: `TopSinPlanearError(Exception)`; `top_sin_planear(db, vm_id, ciclo_id) -> list[dict]` con `{"id": int, "nombre": str}`; `resumen_planeacion` gana las claves `top_sin_planear: list[dict]` y `top_sin_revisita: list[dict]`.

- [ ] **Step 1: Escribir los tests**

Añade a `backend/tests/test_medicos_top.py`:

```python
from app.models.visita import PlaneacionCiclo
from app.services import visita_planeacion_service as plan


def _medico(db, escenario, nombre, es_top, estado="APROBADO"):
    m = MedicoVisita(vm_id=escenario["rm"].id, nombre_completo=nombre,
                     es_top=es_top, estado_aprobacion=estado, activo=True)
    db.add(m)
    db.flush()
    return m


def _planear(db, escenario, medico, tipo="V", semana=1, dia="Lunes"):
    db.add(PlaneacionCiclo(vm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                           medico_id=medico.id, tipo_visita=tipo, semana=semana,
                           dia_semana=dia))
    db.flush()


def test_publicar_falla_si_falta_un_top(escenario):
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    otro = _medico(db, escenario, "DOCTOR NORMAL", False)
    _planear(db, escenario, otro)
    db.commit()

    with pytest.raises(plan.TopSinPlanearError) as exc:
        plan.publicar_planeacion(db, escenario["rm"].id, escenario["ciclo"].id, None)

    assert "DOCTOR TOP" in str(exc.value)
    assert top.id is not None


def test_publicar_ok_si_estan_todos_los_top(escenario):
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, top)
    db.commit()

    r = plan.publicar_planeacion(db, escenario["rm"].id, escenario["ciclo"].id, None)

    assert r["publicada"] is True


def test_un_top_con_alta_pendiente_no_bloquea(escenario):
    """El caso que distingue `cuenta_en_ciclo` de `activo`.

    Un TOP cuya alta el Gerente aún no aprobó NO cuenta en el ciclo: exigir
    planearlo dejaría al representante bloqueado sin poder hacer nada.
    """
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR PENDIENTE", True, estado="PENDIENTE_ALTA")
    otro = _medico(db, escenario, "DOCTOR NORMAL", False)
    _planear(db, escenario, otro)
    db.commit()

    r = plan.publicar_planeacion(db, escenario["rm"].id, escenario["ciclo"].id, None)

    assert r["publicada"] is True


def test_resumen_lista_los_top_sin_planear(escenario):
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR TOP", True)
    db.commit()

    r = plan.resumen_planeacion(db, escenario["rm"].id, escenario["ciclo"].id)

    assert [x["nombre"] for x in r["top_sin_planear"]] == ["DOCTOR TOP"]


def test_top_planeado_solo_con_vista_avisa_pero_no_bloquea(escenario):
    """§7.3 exige que el TOP esté «incluido» — con V basta para publicar.
    §3.4 dice que no puede terminar sin V y R, así que se avisa."""
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, top, tipo="V")
    db.commit()

    r = plan.resumen_planeacion(db, escenario["rm"].id, escenario["ciclo"].id)
    pub = plan.publicar_planeacion(db, escenario["rm"].id, escenario["ciclo"].id, None)

    assert [x["nombre"] for x in r["top_sin_revisita"]] == ["DOCTOR TOP"]
    assert pub["publicada"] is True


def test_guardar_borrador_nunca_se_bloquea_por_top(escenario):
    """El bloqueo es solo al publicar: el representante guarda cuantas veces quiera."""
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR TOP", True)
    otro = _medico(db, escenario, "DOCTOR NORMAL", False)
    db.commit()

    n = plan.guardar_planeacion(
        db, escenario["rm"].id, escenario["ciclo"].id,
        [PlaneacionItem(medico_id=otro.id, tipo_visita="V", semana=1, dia_semana="Lunes")],
        None)

    assert n == 1
```

Añade `from app.schemas.visita import PlaneacionItem` a los imports del test.

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_medicos_top.py -k "publicar or resumen or top_planeado or borrador" -v`
Expected: FAIL con `AttributeError: module ... has no attribute 'TopSinPlanearError'`.

- [ ] **Step 3: Implementar en el servicio de planeación**

En `backend/app/services/visita_planeacion_service.py`, junto a `PlaneacionPublicadaError`:

```python
class TopSinPlanearError(Exception):
    """La planeación omite médicos TOP. §7.3 del requerimiento de Mallén: al
    publicar, VISTA verifica que todos los TOP del panel estén incluidos y, si
    falta alguno, no permite publicar y muestra cuáles faltan."""
```

Y las funciones nuevas:

```python
def _medicos_del_ciclo(db: Session, vm_id: int, ciclo_id: int) -> list[MedicoVisita]:
    """Los médicos del panel que CUENTAN en el ciclo.

    Filtra por `cuenta_en_ciclo` y no por `activo` a secas: con `activo` se
    incluirían altas pendientes de aprobación y bajas ya efectivas, y se
    exigiría planear médicos sobre los que el representante no puede actuar.
    """
    from app.services.visita_aprobacion_service import ordenes_ciclo, cuenta_en_ciclo
    ordenes = ordenes_ciclo(db)
    ciclo_orden = ordenes.get(ciclo_id)
    medicos = db.query(MedicoVisita).filter(MedicoVisita.vm_id == vm_id).all()
    return [m for m in medicos if cuenta_en_ciclo(m, ciclo_orden, ordenes)]


def top_sin_planear(db: Session, vm_id: int, ciclo_id: int) -> list[dict]:
    """Médicos TOP del ciclo que no tienen NINGUNA fila en la planeación."""
    planeados = {p.medico_id for p in db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all()}
    return [{"id": m.id, "nombre": m.nombre_completo}
            for m in _medicos_del_ciclo(db, vm_id, ciclo_id)
            if m.es_top and m.id not in planeados]


def top_sin_revisita(db: Session, vm_id: int, ciclo_id: int) -> list[dict]:
    """TOP planeados pero sin Revisita. Se AVISA, no se bloquea: el §7.3 solo
    exige que estén «incluidos», pero el §3.4 dice que un TOP no puede terminar
    sin visita y revisita — planearlo solo con V es planear el incumplimiento."""
    plan_ = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all()
    planeados = {p.medico_id for p in plan_}
    con_revisita = {p.medico_id for p in plan_ if p.tipo_visita == "R"}
    return [{"id": m.id, "nombre": m.nombre_completo}
            for m in _medicos_del_ciclo(db, vm_id, ciclo_id)
            if m.es_top and m.id in planeados and m.id not in con_revisita]
```

En `publicar_planeacion`, **después** del guard `if n == 0:` y **antes** del `db.add(PlaneacionEvento(...))`:

```python
    faltantes = top_sin_planear(db, vm_id, ciclo_id)
    if faltantes:
        nombres = ", ".join(f["nombre"] for f in faltantes)
        raise TopSinPlanearError(
            f"No se puede publicar: faltan {len(faltantes)} médico(s) TOP en la "
            f"planeación del ciclo. Agrégalos y vuelve a intentarlo: {nombres}.")
```

En `resumen_planeacion`, antes del `return`, calcula las dos listas y añádelas al dict:

```python
    sin_planear = top_sin_planear(db, vm_id, ciclo_id)
    sin_revisita = top_sin_revisita(db, vm_id, ciclo_id)
```

y en el dict devuelto, junto a `"cat_a_sin_revisita"`:

```python
        "top_sin_planear": sin_planear,
        "top_sin_revisita": sin_revisita,
```

- [ ] **Step 4: Traducir la excepción a 409 en el router**

En `backend/app/api/v1/routers/visita.py`, en el endpoint `POST /visita/planeacion/publicar`, añade el `except` **antes** del que ya captura `PlaneacionPublicadaError` o junto a él, con el mismo patrón (409 = conflicto de estado, no 400: la planeación no está en condiciones de publicarse):

```python
    except planeacion_svc.TopSinPlanearError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
```

Usa el alias real con que ese router importa el servicio de planeación (léelo, no lo asumas).

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_medicos_top.py -v`
Expected: 11 passed (o SKIPPED).

Run: `cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/visita_planeacion_service.py backend/app/api/v1/routers/visita.py backend/tests/test_medicos_top.py
git commit -m "feat(top) bloquear la publicacion si la planeacion omite un medico TOP"
```

---

### Task 3: Regla 2 — marcar los TOP sin cubrir

**Files:**
- Modify: `backend/app/services/visita_cobertura_service.py`
- Test: `backend/tests/test_medicos_top.py`

**Interfaces:**
- Consumes: `MedicoVisita.es_top` (Task 1).
- Produces: `_cobertura_base` (y por tanto `resumen_cobertura`) devuelve `es_top: bool` dentro de cada ítem de `sin_visita` y `falta_revisita`, más dos listas nuevas de primer nivel: `top_sin_visita` y `top_falta_revisita`, con la misma forma que las existentes.

- [ ] **Step 1: Escribir los tests**

Añade a `backend/tests/test_medicos_top.py`:

```python
from app.models.visita import VisitaRegistro
from app.services import visita_cobertura_service as cob


def _visita_reg(db, escenario, medico, tipo="V"):
    db.add(VisitaRegistro(vm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                          medico_id=medico.id, tipo_visita=tipo, ejecutada=True,
                          fecha_hora=datetime(2026, 1, 15, 10, 0)))
    db.flush()


def test_top_sin_visita_sale_en_su_lista(escenario):
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR TOP", True)
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert [x["nombre"] for x in r["top_sin_visita"]] == ["DOCTOR TOP"]
    assert r["top_falta_revisita"] == []


def test_top_con_vista_sin_revisita(escenario):
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    _visita_reg(db, escenario, top, tipo="V")
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert r["top_sin_visita"] == []
    assert [x["nombre"] for x in r["top_falta_revisita"]] == ["DOCTOR TOP"]


def test_medico_normal_no_entra_en_las_listas_top(escenario):
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR NORMAL", False)
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert [x["nombre"] for x in r["sin_visita"]] == ["DOCTOR NORMAL"]
    assert r["top_sin_visita"] == []


def test_visita_no_ejecutada_no_cubre_al_top(escenario):
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    db.add(VisitaRegistro(vm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                          medico_id=top.id, tipo_visita="V", ejecutada=False,
                          fecha_hora=datetime(2026, 1, 15, 10, 0)))
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert [x["nombre"] for x in r["top_sin_visita"]] == ["DOCTOR TOP"]
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_medicos_top.py -k "top_sin_visita or top_con_vista or medico_normal or no_ejecutada" -v`
Expected: FAIL con `KeyError: 'top_sin_visita'`.

- [ ] **Step 3: Implementar**

En `backend/app/services/visita_cobertura_service.py`, dentro de `_cobertura_base`:

Añade `es_top` a los dos dicts que ya se construyen, y acumula las dos listas nuevas. El bucle queda así (las tres líneas nuevas van marcadas con el comentario):

```python
    sin_visita, falta_revisita = [], []
    top_sin_visita, top_falta_revisita = [], []   # TOP: §7.3 regla 2
    for m in medicos:
        d = mapa.get(m.id)
        vis = bool(d and (d["v"] or d["r"]))
        comp = bool(d and d["v"] and d["r"])
        c = cat.get(m.categoria)
        if c:
            c["total"] += 1
            if vis:
                c["visitados"] += 1
            if comp:
                c["completos"] += 1
        if vis:
            visitados += 1
        if comp:
            con_revisita += 1
        elif not vis:
            item = {"id": m.id, "nombre": m.nombre_completo, "categoria": m.categoria,
                    "especialidad_id": m.especialidad_id, "es_top": m.es_top}
            sin_visita.append(item)
            if m.es_top:
                top_sin_visita.append(item)
        if vis and not comp:  # solo Vista, falta Revisita
            item = {"id": m.id, "nombre": m.nombre_completo, "categoria": m.categoria,
                    "es_top": m.es_top}
            falta_revisita.append(item)
            if m.es_top:
                top_falta_revisita.append(item)
```

Y en el dict devuelto, junto a `"sin_visita"` y `"falta_revisita"`:

```python
        "top_sin_visita": top_sin_visita, "top_falta_revisita": top_falta_revisita,
```

Comprueba que `resumen_cobertura` propague las claves nuevas: si construye su respuesta copiando el dict de `_cobertura_base`, no hay nada más que hacer; si enumera claves una a una, añádelas.

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_medicos_top.py -v`
Expected: 15 passed (o SKIPPED).

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_visita_service.py tests/test_cobertura_farmacia.py -q`
Expected: sin regresiones.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/visita_cobertura_service.py backend/tests/test_medicos_top.py
git commit -m "feat(top) listas de medicos TOP sin visita y sin revisita en la cobertura"
```

---

### Task 4: El servicio de TOP — fechas y detección de vencidos

**Files:**
- Create: `backend/app/services/visita_top_service.py`
- Test: `backend/tests/test_medicos_top.py`

**Interfaces:**
- Consumes: `MedicoVisita.es_top`, `PlaneacionCiclo`, `VisitaRegistro`, `cobertura_predictiva_service._networkdays` y `_feriados_pais`.
- Produces:
  - `fecha_planeada(ciclo, semana, dia_semana) -> date | None`
  - `pct_ciclo_transcurrido(db, ciclo, hoy) -> int` (0-100)
  - `DIAS_SEMANA: dict[str, int]` (`"Lunes"` → 0 … `"Viernes"` → 4)
  - `pendientes_recordatorio(db, ciclo, hoy, dias_gracia) -> list[dict]` con `{"vm_id", "medico_id", "medico": str, "tipo_visita", "fecha_planeada"}`
  - `pendientes_escalamiento(db, ciclo) -> list[dict]` con la misma forma

- [ ] **Step 1: Escribir los tests**

Añade a `backend/tests/test_medicos_top.py`:

```python
from datetime import date
from app.services import visita_top_service as top


def test_fecha_planeada_semana_1_lunes(escenario):
    """El ciclo empieza el jueves 1-ene-2026. La semana 1 es la que CONTIENE
    fecha_inicio, así que su lunes es el 29-dic — anterior al ciclo. La fecha
    se acota a fecha_inicio: no se puede planear antes de que el ciclo empiece."""
    c = escenario["ciclo"]
    assert top.fecha_planeada(c, 1, "Lunes") == date(2026, 1, 1)


def test_fecha_planeada_semana_2_miercoles(escenario):
    """Lunes de la semana 1 = 29-dic-2025; semana 2 = +7 días = 5-ene;
    miércoles = +2 = 7-ene-2026."""
    c = escenario["ciclo"]
    assert top.fecha_planeada(c, 2, "Miércoles") == date(2026, 1, 7)


def test_fecha_planeada_se_acota_al_fin_del_ciclo(escenario):
    c = escenario["ciclo"]
    assert top.fecha_planeada(c, 40, "Viernes") == c.fecha_fin


def test_fecha_planeada_dia_irreconocible_es_none(escenario):
    """Un dato de planeación incompleto no debe generar un correo de reclamo."""
    c = escenario["ciclo"]
    assert top.fecha_planeada(c, 1, None) is None
    assert top.fecha_planeada(c, 1, "Cualquiera") is None


def test_recordatorio_respeta_los_dias_de_gracia(escenario):
    db = escenario["db"]
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")   # 1-ene-2026
    db.commit()

    # 2-ene: solo 1 día hábil transcurrido, con gracia de 2 no toca avisar
    assert top.pendientes_recordatorio(db, escenario["ciclo"], date(2026, 1, 2), 2) == []
    # 6-ene: ya pasaron 3 días hábiles desde el 2 (2, 5 y 6; el 3 y 4 son fin
    # de semana), así que supera la gracia de 2
    r = top.pendientes_recordatorio(db, escenario["ciclo"], date(2026, 1, 6), 2)
    assert [x["medico"] for x in r] == ["DOCTOR TOP"]


def test_recordatorio_no_incluye_lo_ya_visitado(escenario):
    db = escenario["db"]
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    _visita_reg(db, escenario, t, tipo="V")
    db.commit()

    assert top.pendientes_recordatorio(db, escenario["ciclo"], date(2026, 1, 20), 2) == []


def test_recordatorio_ignora_a_los_no_top(escenario):
    db = escenario["db"]
    n = _medico(db, escenario, "DOCTOR NORMAL", False)
    _planear(db, escenario, n, tipo="V", semana=1, dia="Lunes")
    db.commit()

    assert top.pendientes_recordatorio(db, escenario["ciclo"], date(2026, 1, 20), 2) == []


def test_pct_ciclo_transcurrido(escenario):
    """Ciclo 1-ene a 31-ene-2026: 22 días hábiles. Al 15-ene han pasado 11."""
    db = escenario["db"]
    assert top.pct_ciclo_transcurrido(db, escenario["ciclo"], date(2026, 1, 15)) == 50


def test_escalamiento_solo_para_top_sin_cubrir(escenario):
    db = escenario["db"]
    t = _medico(db, escenario, "DOCTOR TOP", True)
    cubierto = _medico(db, escenario, "DOCTOR CUBIERTO", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    _planear(db, escenario, cubierto, tipo="V", semana=1, dia="Lunes")
    _visita_reg(db, escenario, cubierto, tipo="V")
    db.commit()

    r = top.pendientes_escalamiento(db, escenario["ciclo"])

    assert [x["medico"] for x in r] == ["DOCTOR TOP"]
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_medicos_top.py -k "fecha_planeada or recordatorio or pct_ciclo or escalamiento" -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.visita_top_service'`.

- [ ] **Step 3: Implementar el servicio**

Crear `backend/app/services/visita_top_service.py`:

```python
"""Médicos TOP — detección de visitas vencidas y de TOP sin cubrir (§7.3 del
Requerimiento de Datos VISTA · Laboratorios Mallén v2).

POR QUÉ HAY QUE TRADUCIR FECHAS
--------------------------------
`Visita.PlaneacionCiclo` NO guarda fechas: guarda `semana` (1-4) y `dia_semana`
("Lunes".."Viernes", texto libre). Para saber si una visita programada venció hay
que derivar una fecha de calendario real, y ese traductor no existía.

La fecha planeada se deriva por CALENDARIO PURO: lunes de la semana que contiene
`fecha_inicio`, más (semana-1) semanas, más el desplazamiento del día. Los
feriados NO la mueven — si alguien planeó para un día que resultó feriado, la
fecha planeada sigue siendo esa. Los feriados entran al medir el VENCIMIENTO
posterior y el porcentaje del ciclo, que sí se cuentan en días hábiles.

DÍAS HÁBILES: SE USA EL CÁLCULO CORRECTO
-----------------------------------------
Se importa `_networkdays`/`_feriados_pais` de `cobertura_predictiva_service`,
que consultan `Config.DIM_Feriado`. NO se usa `visita_cobertura_service._dias_habiles`,
que solo excluye sábado y domingo e ignora los feriados.
"""
from datetime import date, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Ciclo
from app.models.visita import MedicoVisita, PlaneacionCiclo, VisitaRegistro

#: "Lunes" → 0 … "Viernes" → 4. Es el vocabulario que guarda `dia_semana`.
DIAS_SEMANA: dict[str, int] = {
    "Lunes": 0, "Martes": 1, "Miércoles": 2, "Miercoles": 2,
    "Jueves": 3, "Viernes": 4,
}


def fecha_planeada(ciclo: Ciclo, semana: int, dia_semana: str | None) -> date | None:
    """`(ciclo, semana, dia_semana)` → fecha de calendario, acotada al ciclo.

    Devuelve None si el día no es reconocible: un dato de planeación incompleto
    no debe generar un correo de reclamo al representante.
    """
    if not dia_semana:
        return None
    offset = DIAS_SEMANA.get(dia_semana.strip())
    if offset is None:
        logger.debug(f"dia_semana no reconocido en planeación: {dia_semana!r}")
        return None
    # Lunes de la semana que CONTIENE fecha_inicio.
    lunes_1 = ciclo.fecha_inicio - timedelta(days=ciclo.fecha_inicio.weekday())
    f = lunes_1 + timedelta(weeks=max(semana, 1) - 1, days=offset)
    # Acotada al ciclo: no se puede planear antes de que empiece ni después de
    # que termine.
    if f < ciclo.fecha_inicio:
        return ciclo.fecha_inicio
    if f > ciclo.fecha_fin:
        return ciclo.fecha_fin
    return f


def _feriados(db: Session, ciclo: Ciclo) -> set:
    from app.services.cobertura_predictiva_service import _feriados_pais
    return _feriados_pais(db, ciclo.pais_codigo, ciclo.fecha_inicio, ciclo.fecha_fin)


def _habiles(desde: date, hasta: date, feriados: set) -> int:
    from app.services.cobertura_predictiva_service import _networkdays
    return _networkdays(desde, hasta, feriados)


def pct_ciclo_transcurrido(db: Session, ciclo: Ciclo, hoy: date) -> int:
    """% de DÍAS HÁBILES del ciclo ya transcurridos (0-100), no días naturales."""
    feriados = _feriados(db, ciclo)
    total = _habiles(ciclo.fecha_inicio, ciclo.fecha_fin, feriados)
    if total <= 0:
        return 0
    corte = min(hoy, ciclo.fecha_fin)
    if corte < ciclo.fecha_inicio:
        return 0
    return round(_habiles(ciclo.fecha_inicio, corte, feriados) / total * 100)


def _ejecutadas(db: Session, ciclo_id: int) -> set[tuple[int, str]]:
    """`(medico_id, tipo_visita)` de las visitas EJECUTADAS del ciclo."""
    filas = (db.query(VisitaRegistro.medico_id, VisitaRegistro.tipo_visita)
             .filter(VisitaRegistro.ciclo_id == ciclo_id,
                     VisitaRegistro.ejecutada == True).all())  # noqa: E712
    return {(m, t) for m, t in filas}


def _plan_top(db: Session, ciclo_id: int) -> list[tuple[PlaneacionCiclo, MedicoVisita]]:
    """Filas de planeación del ciclo cuyo médico es TOP."""
    return (db.query(PlaneacionCiclo, MedicoVisita)
            .join(MedicoVisita, MedicoVisita.id == PlaneacionCiclo.medico_id)
            .filter(PlaneacionCiclo.ciclo_id == ciclo_id,
                    MedicoVisita.es_top == True).all())  # noqa: E712


def pendientes_recordatorio(db: Session, ciclo: Ciclo, hoy: date,
                            dias_gracia: int) -> list[dict]:
    """Visitas planeadas a un TOP cuya fecha venció hace >= `dias_gracia` días
    hábiles y que siguen sin ejecutarse."""
    ejecutadas = _ejecutadas(db, ciclo.id)
    feriados = _feriados(db, ciclo)
    salida = []
    for p, m in _plan_top(db, ciclo.id):
        if (m.id, p.tipo_visita) in ejecutadas:
            continue
        f = fecha_planeada(ciclo, p.semana, p.dia_semana)
        if f is None or f >= hoy:
            continue
        # Días hábiles transcurridos DESPUÉS de la fecha planeada.
        if _habiles(f + timedelta(days=1), hoy, feriados) < dias_gracia:
            continue
        salida.append({"vm_id": p.vm_id, "medico_id": m.id,
                       "medico": m.nombre_completo, "tipo_visita": p.tipo_visita,
                       "fecha_planeada": f})
    return salida


def pendientes_escalamiento(db: Session, ciclo: Ciclo) -> list[dict]:
    """Visitas planeadas a un TOP que siguen sin ejecutarse, sin mirar la fecha:
    quien decide el momento es el umbral de % del ciclo, que evalúa el job."""
    ejecutadas = _ejecutadas(db, ciclo.id)
    salida = []
    for p, m in _plan_top(db, ciclo.id):
        if (m.id, p.tipo_visita) in ejecutadas:
            continue
        salida.append({"vm_id": p.vm_id, "medico_id": m.id,
                       "medico": m.nombre_completo, "tipo_visita": p.tipo_visita,
                       "fecha_planeada": fecha_planeada(ciclo, p.semana, p.dia_semana)})
    return salida
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_medicos_top.py -v`
Expected: 24 passed (o SKIPPED).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/visita_top_service.py backend/tests/test_medicos_top.py
git commit -m "feat(top) traductor de fechas de planeacion y deteccion de TOP vencidos"
```

---

### Task 5: Regla 3 — notificaciones y job diario

**Files:**
- Modify: `backend/app/services/notification_service.py` (dos funciones nuevas)
- Modify: `backend/app/services/visita_top_service.py` (el orquestador del aviso)
- Modify: `backend/app/core/scheduler.py` (el job diario)
- Modify: `backend/app/main.py` (registrarlo al arrancar)
- Test: `backend/tests/test_medicos_top.py`

**Interfaces:**
- Consumes: `pendientes_recordatorio`, `pendientes_escalamiento`, `pct_ciclo_transcurrido` (Task 4); `AvisoTopEnviado`, `AVISO_RECORDATORIO`, `AVISO_ESCALAMIENTO` (Task 1); `config_service.obtener_int(db, clave, por_defecto)`.
- Produces:
  - `notification_service.notificar_top_pendiente(destinatario, nombre_rm, medicos) -> bool`
  - `notification_service.notificar_top_escalado(destinatario, nombre_gerente, por_representante) -> bool`
  - `visita_top_service.procesar_avisos(db, hoy=None) -> dict` con `{"recordatorios": int, "escalamientos": int}`
  - Claves de configuración: `top_dias_recordatorio` (default `2`), `top_pct_ciclo_escalamiento` (default `70`)

- [ ] **Step 1: Escribir los tests**

Añade a `backend/tests/test_medicos_top.py`:

```python
from app.models.visita import AVISO_ESCALAMIENTO, AVISO_RECORDATORIO


def test_procesar_avisos_registra_y_no_repite(escenario, monkeypatch):
    """El test que justifica la tabla `AvisoTopEnviado`: sin ella, el cron
    diario reenviaría el mismo correo cada mañana."""
    db = escenario["db"]
    enviados = []
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: (enviados.append(a) or True))
    escenario["rm"].email = "rm@ejemplo.com"
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    db.commit()

    r1 = top.procesar_avisos(db, hoy=date(2026, 1, 20))
    r2 = top.procesar_avisos(db, hoy=date(2026, 1, 20))

    assert r1["recordatorios"] == 1
    assert r2["recordatorios"] == 0          # no se repite
    assert len(enviados) == 1
    assert db.query(AvisoTopEnviado).filter_by(tipo_aviso=AVISO_RECORDATORIO).count() == 1


def test_no_registra_si_el_correo_no_salio(escenario, monkeypatch):
    """Marcar como enviado lo que no salió dejaría al representante sin aviso
    para siempre, en silencio."""
    db = escenario["db"]
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: False)
    escenario["rm"].email = "rm@ejemplo.com"
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    db.commit()

    r = top.procesar_avisos(db, hoy=date(2026, 1, 20))

    assert r["recordatorios"] == 0
    assert db.query(AvisoTopEnviado).count() == 0


def test_ciclo_cerrado_no_genera_avisos(escenario, monkeypatch):
    db = escenario["db"]
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: True)
    escenario["rm"].email = "rm@ejemplo.com"
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    escenario["ciclo"].cerrado = True
    db.commit()

    r = top.procesar_avisos(db, hoy=date(2026, 1, 20))

    assert r["recordatorios"] == 0
    assert db.query(AvisoTopEnviado).count() == 0


def test_escalamiento_solo_pasado_el_umbral(escenario, monkeypatch):
    db = escenario["db"]
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: True)
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_escalado",
        lambda *a, **k: True)
    escenario["rm"].email = "rm@ejemplo.com"
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    db.commit()

    # 15-ene = 50% del ciclo, por debajo del umbral de 70
    r_antes = top.procesar_avisos(db, hoy=date(2026, 1, 15))
    # 28-ene ya supera el 70%
    r_despues = top.procesar_avisos(db, hoy=date(2026, 1, 28))

    assert r_antes["escalamientos"] == 0
    assert r_despues["escalamientos"] == 1
    assert db.query(AvisoTopEnviado).filter_by(tipo_aviso=AVISO_ESCALAMIENTO).count() == 1


def test_representante_sin_gerente_no_tumba_el_job(escenario, monkeypatch):
    db = escenario["db"]
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: True)
    escenario["rm"].email = "rm@ejemplo.com"
    escenario["rm"].gerente_id = None
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    db.commit()

    r = top.procesar_avisos(db, hoy=date(2026, 1, 28))

    assert r["escalamientos"] == 0
    assert r["recordatorios"] == 1   # el recordatorio al RM sí sale
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_medicos_top.py -k "procesar_avisos or no_registra or ciclo_cerrado or umbral or sin_gerente" -v`
Expected: FAIL con `AttributeError: module ... has no attribute 'procesar_avisos'`.

- [ ] **Step 3: Añadir las dos notificaciones**

En `backend/app/services/notification_service.py`, al final, siguiendo el patrón de `notificar_medico_pendiente_aprobacion`:

```python
def notificar_top_pendiente(destinatario: str, nombre_rm: str,
                            medicos: list) -> bool:
    """Recuerda al representante que tiene visitas a médicos TOP vencidas sin
    ejecutar (§7.3 regla 3). Best-effort: nunca bloquea el job."""
    if not _habilitado() or not destinatario:
        return False
    filas = "".join(
        f"<li><strong>{m['medico']}</strong> — {'Revisita' if m['tipo_visita'] == 'R' else 'Visita'}"
        f" planeada para el {m['fecha_planeada'].strftime('%d/%m/%Y')}</li>"
        for m in medicos)
    cuerpo = f"""<html><body style="font-family:Arial,sans-serif;color:#333;">
  <h2 style="color:{_COLOR_TITULO};">Médicos TOP pendientes de visita</h2>
  <p>Hola <strong>{nombre_rm}</strong>, estas visitas a médicos <strong>TOP</strong>
     ya pasaron su fecha planeada y siguen sin registrarse:</p>
  <ul>{filas}</ul>
  <p>Los médicos TOP no pueden cerrar el ciclo sin visita y revisita. Entra a la
     plataforma para reprogramarlas o registrarlas.</p>
  {_pie_pagina()}
</body></html>"""
    return _enviar(destinatario, f"Médicos TOP pendientes ({len(medicos)})", cuerpo)


def notificar_top_escalado(destinatario: str, nombre_gerente: str,
                           por_representante: dict) -> bool:
    """Escala al Gerente de Distrito los médicos TOP que siguen sin cubrir con el
    ciclo ya avanzado (§7.3 regla 3). Best-effort."""
    if not _habilitado() or not destinatario:
        return False
    bloques = "".join(
        f"<h3 style=\"margin-bottom:4px;\">{rm}</h3><ul>"
        + "".join(f"<li><strong>{m['medico']}</strong> — "
                  f"{'Revisita' if m['tipo_visita'] == 'R' else 'Visita'}</li>"
                  for m in medicos)
        + "</ul>"
        for rm, medicos in por_representante.items())
    total = sum(len(v) for v in por_representante.values())
    cuerpo = f"""<html><body style="font-family:Arial,sans-serif;color:#333;">
  <h2 style="color:{_COLOR_TITULO};">Médicos TOP sin cubrir — requiere seguimiento</h2>
  <p>Hola <strong>{nombre_gerente}</strong>, el ciclo ya está avanzado y estos médicos
     <strong>TOP</strong> siguen sin visita registrada en su distrito:</p>
  {bloques}
  <p>Se avisó previamente a cada representante. Conviene revisarlo con ellos antes
     del cierre del ciclo.</p>
  {_pie_pagina()}
</body></html>"""
    return _enviar(destinatario, f"Médicos TOP sin cubrir ({total}) — seguimiento", cuerpo)
```

- [ ] **Step 4: Implementar el orquestador**

Añade al final de `backend/app/services/visita_top_service.py`:

```python
#: Claves de configuración (editables desde Administración, tabla de config en BD).
#: Los defaults son una posición razonable, NO una decisión del cliente: el
#: pendiente nº 8 del §10 del requerimiento sigue abierto con Mallén.
CFG_DIAS_RECORDATORIO = "top_dias_recordatorio"
CFG_PCT_ESCALAMIENTO = "top_pct_ciclo_escalamiento"
DIAS_RECORDATORIO_DEFAULT = 2
PCT_ESCALAMIENTO_DEFAULT = 70


def _ya_avisado(db: Session, ciclo_id: int, tipo_aviso: str) -> set[tuple]:
    from app.models.visita import AvisoTopEnviado
    filas = (db.query(AvisoTopEnviado.vm_id, AvisoTopEnviado.medico_id,
                      AvisoTopEnviado.tipo_visita)
             .filter(AvisoTopEnviado.ciclo_id == ciclo_id,
                     AvisoTopEnviado.tipo_aviso == tipo_aviso).all())
    return {(v, m, t) for v, m, t in filas}


def _marcar(db: Session, ciclo_id: int, items: list[dict], tipo_aviso: str) -> None:
    from app.models.visita import AvisoTopEnviado
    for it in items:
        db.add(AvisoTopEnviado(vm_id=it["vm_id"], ciclo_id=ciclo_id,
                               medico_id=it["medico_id"],
                               tipo_visita=it["tipo_visita"], tipo_aviso=tipo_aviso))


def procesar_avisos(db: Session, hoy: date | None = None) -> dict:
    """Recorre los ciclos ABIERTOS y manda lo que toque, una sola vez por caso.

    Es un cron de RECONCILIACIÓN, no un temporizador: cada corrida vuelve a
    preguntarle a la base qué está vencido. Por eso sobrevive a los reinicios
    del contenedor, a diferencia de un job agendado en memoria.
    """
    from app.models.dimensiones import Gerente, RepresentanteMedico
    from app.models.visita import AVISO_ESCALAMIENTO, AVISO_RECORDATORIO
    from app.services import config_service, notification_service

    hoy = hoy or date.today()
    dias_gracia = config_service.obtener_int(db, CFG_DIAS_RECORDATORIO,
                                             DIAS_RECORDATORIO_DEFAULT)
    pct_umbral = config_service.obtener_int(db, CFG_PCT_ESCALAMIENTO,
                                            PCT_ESCALAMIENTO_DEFAULT)
    n_rec = n_esc = 0

    # Ciclos CERRADOS no se procesan: son snapshots inmutables y nadie puede ya
    # actuar sobre ellos.
    for ciclo in db.query(Ciclo).filter(Ciclo.cerrado == False).all():  # noqa: E712
        # ── Recordatorio al representante ────────────────────────────────
        avisados = _ya_avisado(db, ciclo.id, AVISO_RECORDATORIO)
        pend = [p for p in pendientes_recordatorio(db, ciclo, hoy, dias_gracia)
                if (p["vm_id"], p["medico_id"], p["tipo_visita"]) not in avisados]
        por_vm: dict[int, list] = {}
        for p in pend:
            por_vm.setdefault(p["vm_id"], []).append(p)
        for vm_id, items in por_vm.items():
            rm = db.query(RepresentanteMedico).filter(
                RepresentanteMedico.id == vm_id).first()
            if rm is None or not rm.email:
                logger.warning(f"TOP: representante {vm_id} sin correo; no se avisa")
                continue
            if notification_service.notificar_top_pendiente(rm.email, rm.nombre, items):
                _marcar(db, ciclo.id, items, AVISO_RECORDATORIO)
                n_rec += len(items)

        # ── Escalamiento al Gerente de Distrito ──────────────────────────
        if pct_ciclo_transcurrido(db, ciclo, hoy) < pct_umbral:
            continue
        avisados_esc = _ya_avisado(db, ciclo.id, AVISO_ESCALAMIENTO)
        pend_esc = [p for p in pendientes_escalamiento(db, ciclo)
                    if (p["vm_id"], p["medico_id"], p["tipo_visita"]) not in avisados_esc]
        por_gerente: dict[int, dict] = {}
        for p in pend_esc:
            rm = db.query(RepresentanteMedico).filter(
                RepresentanteMedico.id == p["vm_id"]).first()
            if rm is None or rm.gerente_id is None:
                logger.warning(f"TOP: representante {p['vm_id']} sin gerente; no se escala")
                continue
            por_gerente.setdefault(rm.gerente_id, {}).setdefault(rm.nombre, []).append(p)
        for gerente_id, por_rm in por_gerente.items():
            g = db.query(Gerente).filter(Gerente.id == gerente_id).first()
            if g is None or not g.email:
                logger.warning(f"TOP: gerente {gerente_id} sin correo; no se escala")
                continue
            if notification_service.notificar_top_escalado(g.email, g.nombre, por_rm):
                planos = [x for lista in por_rm.values() for x in lista]
                _marcar(db, ciclo.id, planos, AVISO_ESCALAMIENTO)
                n_esc += len(planos)

    db.commit()
    logger.info(f"Avisos de médicos TOP: {n_rec} recordatorios, {n_esc} escalamientos")
    return {"recordatorios": n_rec, "escalamientos": n_esc}
```

- [ ] **Step 5: Registrar el job diario**

En `backend/app/core/scheduler.py`, al final:

```python
def _job_medicos_top() -> None:
    """Ejecuta los avisos de médicos TOP con su propia sesión de BD."""
    from app.db.database import SessionLocal
    from app.services import visita_top_service
    db = SessionLocal()
    try:
        visita_top_service.procesar_avisos(db)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Job de médicos TOP falló: {e}")
    finally:
        db.close()


def programar_medicos_top() -> None:
    """Cron diario de RECONCILIACIÓN de médicos TOP (§7.3 regla 3).

    Es un cron y no un temporizador por visita a propósito: el scheduler usa
    `MemoryJobStore`, así que cualquier reinicio del contenedor perdería los
    jobs agendados en silencio. Un cron se re-registra en cada arranque y cada
    corrida vuelve a preguntarle a la base qué está vencido.
    """
    try:
        get_scheduler().add_job(
            _job_medicos_top, "cron", hour=7, minute=0,
            id="medicos-top-diario", replace_existing=True, misfire_grace_time=3600)
        logger.info("Job diario de médicos TOP programado (07:00 UTC)")
    except Exception as e:  # noqa: BLE001
        logger.error(f"No se pudo programar el job de médicos TOP: {e}")
```

En `backend/app/main.py`, en el bloque del lifespan donde hoy se llama a `scheduler.iniciar()`, añade justo después:

```python
    scheduler.programar_medicos_top()
```

Usa el alias real con que `main.py` importa el scheduler (léelo, no lo asumas).

- [ ] **Step 6: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_medicos_top.py -v`
Expected: 29 passed (o SKIPPED).

Run: `cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print('OK')"`
Expected: `OK`

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: toda la suite en verde, sin regresiones.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/notification_service.py backend/app/services/visita_top_service.py backend/app/core/scheduler.py backend/app/main.py backend/tests/test_medicos_top.py
git commit -m "feat(top) recordatorio al representante y escalamiento al GD con cron diario"
```

---

### Task 6: Frontend — chip TOP y avisos

**Files:**
- Modify: `frontend/src/services/visita.service.ts` (tipos)
- Modify: `frontend/src/pages/visita/PlaneacionVisita.tsx`
- Modify: `frontend/src/pages/visita/PanelMedico.tsx`
- Modify: `frontend/src/pages/visita/CoberturaDashboard.tsx`

**Interfaces:**
- Consumes: `resumen_planeacion` devuelve `top_sin_planear` y `top_sin_revisita` (Task 2); `resumen_cobertura` devuelve `top_sin_visita` y `top_falta_revisita`, y cada ítem de `sin_visita`/`falta_revisita` trae `es_top` (Task 3); publicar responde **409** con el mensaje que nombra los médicos faltantes (Task 2).

- [ ] **Step 1: Añadir los tipos**

En `frontend/src/services/visita.service.ts`, añade a la interfaz del resumen de planeación:

```typescript
  top_sin_planear: { id: number; nombre: string }[];
  top_sin_revisita: { id: number; nombre: string }[];
```

Y a la del resumen de cobertura:

```typescript
  top_sin_visita: { id: number; nombre: string; categoria: string | null; es_top: boolean }[];
  top_falta_revisita: { id: number; nombre: string; categoria: string | null; es_top: boolean }[];
```

Añade `es_top: boolean` a los tipos de los ítems de `sin_visita` y `falta_revisita` que ya existen. Verifica los nombres reales de esas interfaces leyendo el archivo — no los inventes.

- [ ] **Step 2: Avisos en la pantalla de planeación**

En `frontend/src/pages/visita/PlaneacionVisita.tsx`, junto al `Alert` de "Cat. A sin Revisita" que ya existe:

```tsx
{!!resumen?.top_sin_planear?.length && (
  <Alert severity="error" sx={{ mb: 2 }}>
    No podrás publicar hasta incluir {resumen.top_sin_planear.length} médico(s){' '}
    <strong>TOP</strong>: {resumen.top_sin_planear.map((m) => m.nombre).join(', ')}.
  </Alert>
)}
{!!resumen?.top_sin_revisita?.length && (
  <Alert severity="warning" sx={{ mb: 2 }}>
    {resumen.top_sin_revisita.length} médico(s) <strong>TOP</strong> están planeados sin
    Revisita: {resumen.top_sin_revisita.map((m) => m.nombre).join(', ')}. Un TOP no debería
    cerrar el ciclo sin visita y revisita.
  </Alert>
)}
```

El primero es `error` y el segundo `warning` a propósito: uno impide publicar, el otro no.

Añade también el chip TOP en la columna "Médico" de la tabla, junto al `Chip` de "Visitado"/"Sin visitar" que ya existe:

```tsx
{m.es_top && <Chip label="TOP" size="small" color="error" sx={{ ml: 0.5, fontWeight: 700 }} />}
```

Esto exige que el listado de médicos traiga `es_top`. Si `visita_service.listar_medicos` (backend) no lo devuelve, añádelo ahí: es un campo más en el dict que ya construye, junto a `estado_visita`.

- [ ] **Step 3: Chip en Panel Médico y sección en Cobertura**

En `frontend/src/pages/visita/PanelMedico.tsx`, el mismo `Chip` junto al nombre del médico.

En `frontend/src/pages/visita/CoberturaDashboard.tsx`, una sección destacada antes de las de "Sin ninguna visita" y "falta Revisita" que ya existen:

```tsx
{(!!data?.top_sin_visita?.length || !!data?.top_falta_revisita?.length) && (
  <Alert severity="error" sx={{ mb: 2 }}>
    <strong>Médicos TOP sin cubrir:</strong>{' '}
    {data.top_sin_visita.length} sin ninguna visita
    {' · '}{data.top_falta_revisita.length} sin revisita.
    {' '}
    {[...data.top_sin_visita, ...data.top_falta_revisita].map((m) => m.nombre).join(', ')}
  </Alert>
)}
```

Y el chip TOP en las filas de las listas existentes, usando el `es_top` que ahora traen sus ítems.

- [ ] **Step 4: Verificar el build**

Run: `cd frontend && npm run build`
Expected: `tsc -b && vite build` termina con exit 0, sin errores de tipos.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/visita.service.ts frontend/src/pages/visita/PlaneacionVisita.tsx frontend/src/pages/visita/PanelMedico.tsx frontend/src/pages/visita/CoberturaDashboard.tsx backend/app/services/visita_service.py
git commit -m "feat(top) chip TOP y avisos de medicos TOP en planeacion, panel y cobertura"
```

---

## Verificación en vivo (tras Task 6, no es un commit)

Con un JWT de ADMIN, sobre datos sembrados a mano:

1. Marcar un médico como TOP (`UPDATE "Visita"."DIM_MedicoVisita" SET es_top = true WHERE id = ...`), dejarlo fuera de la planeación e intentar publicar → **409** con su nombre en el mensaje.
2. Incluirlo y publicar → funciona.
3. Marcar como TOP a un médico con `estado_aprobacion = 'PENDIENTE_ALTA'`, dejarlo fuera → **publica igual** (es la comprobación de `cuenta_en_ciclo`).
4. La pantalla de Planeación muestra el `Alert` rojo con los nombres antes de pulsar Publicar, y guardar en borrador sigue funcionando.
5. El dashboard de Cobertura muestra la sección de TOP sin cubrir y el chip TOP.
6. Disparar el job a mano y comprobar que crea filas en `Visita.AvisoTopEnviado`:
   `docker compose exec backend python -c "from app.db.database import SessionLocal; from app.services import visita_top_service as t; print(t.procesar_avisos(SessionLocal()))"`
7. Volver a dispararlo → devuelve `0` recordatorios y no crea filas nuevas.
8. Comprobar que el job quedó registrado al arrancar, en el log: `Job diario de médicos TOP programado (07:00 UTC)`.

---

## Self-Review

**1. Cobertura del spec:**
- §2 `es_top`, tabla elegida, booleano, sincronización que reafirma, ausencia = no TOP → Task 1 + 5 tests.
- §3 bloqueo al publicar con `cuenta_en_ciclo`, 409, aviso previo no bloqueante, TOP sin revisita que avisa y no bloquea → Task 2 + 6 tests.
- §4 listas de TOP sin cubrir y chip en las tres pantallas → Task 3 (backend) + Task 6 (frontend).
- §5.1 traductor de fechas, feriados solo en el vencimiento → Task 4 + 4 tests.
- §5.2 tabla de avisos e idempotencia → Task 1 (modelo) + Task 5 (uso) + test de doble corrida.
- §5.3 cron diario de reconciliación, ciclos cerrados excluidos → Task 5 + 2 tests.
- §5.4 los dos parámetros configurables con sus defaults → Task 5.
- §5.5 destinatarios por `RepresentanteMedico.email` / `Gerente.email`, best-effort, registro solo si el envío ocurrió → Task 5 + 2 tests.
- §7 fuera de alcance → respetado: sin pantallas nuevas, sin tocar RBAC, sin unificar los cálculos de días hábiles, sin arreglar el job de exámenes.

**2. Placeholder scan:** sin TBD/TODO. Tres puntos piden leer el nombre real antes de escribir (el alias del servicio de planeación en el router, el nombre de la variable del registro adoptado en `integrar_panel_medico`, y el alias del scheduler en `main.py`): son instrucciones de inspección deliberadas, no huecos — el plan no fija nombres que no verifiqué.

**3. Consistencia de tipos:** `top_sin_planear`/`top_sin_revisita` devuelven `{id, nombre}` en Task 2 y así se consumen en Task 6. `pendientes_recordatorio`/`pendientes_escalamiento` devuelven `{vm_id, medico_id, medico, tipo_visita, fecha_planeada}` en Task 4 y así los consume `procesar_avisos` y las plantillas de correo en Task 5. `AVISO_RECORDATORIO`/`AVISO_ESCALAMIENTO` se definen en Task 1 y se usan en Task 5. `es_top` es booleano en todas las capas.

**4. Riesgo conocido, mitigado:** el test de `pct_ciclo_transcurrido` depende de que el ciclo del fixture sea 1-ene a 31-ene-2026 (22 días hábiles, 11 al día 15). Si el fixture cambia de fechas, ese test hay que recalcularlo — queda dicho en su propio docstring.
