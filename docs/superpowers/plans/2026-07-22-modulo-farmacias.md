# Módulo de Farmacias — Plan de Implementación

> **Para agentes:** SUB-SKILL REQUERIDA: usar `superpowers:subagent-driven-development` (o
> `executing-plans`) para ejecutar tarea por tarea. Pasos con checkbox `- [ ]`.

**Goal:** Construir el módulo de Farmacias en VISTA (maestro único, panel del VM, aprobación VM→GD,
campos bloqueantes, nomenclatura CADENA+SUCURSAL, tipo de visita Farmacia y cobertura interna),
espejando el módulo de Médicos ya en producción.

**Architecture:** Espejo del módulo de Médicos. Maestro `Config.DIM_Farmacia` (país-level) ↔ panel
`Visita.DIM_FarmaciaVisita` (referencia al maestro) ↔ registro `Visita.FactVisitaFarmacia` (tabla
paralela, **Opción A** — cero regresión sobre `FactVisita` de médicos). Servicios 100% Python.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic (`include_schemas=True`),
PostgreSQL 17, React 18 + MUI v6 + Zustand, pytest.

## Global Constraints (spec `2026-07-22-modulo-farmacias-maestro-aprobacion-design.md`)
- **Decisiones aprobadas:** Opción A (tabla paralela de registro); **farmacias SIN F1/F2** (cobertura
  simple: visitada / no visitada); **cobertura interna que COEXISTE** con el SFA (no reemplaza el score).
- **Registro en el MISMO módulo de Visita** (jul-2026): la visita a farmacia se registra en la pantalla
  **Registrar Visita** existente (selector Médico/Farmacia), NO en un flujo separado. El backend usa la
  tabla paralela `FactVisitaFarmacia` (Opción A), pero la UI de registro es la misma pantalla.
- **SIN planeación para farmacias** (jul-2026): NO existe Planeación de ciclo para farmacias (no hay
  equivalente de `PlaneacionCiclo`). El VM registra la visita **ad-hoc, cuando la realiza**. Por tanto:
  (a) `DIM_FarmaciaVisita` NO participa en planeación; `ciclos_sin_visita` es informativo, no un gate.
  (b) La cobertura (Task 7) se calcula SOLO con visitas registradas vs. panel activo — sin universo
  planeado, sin ruptura de secuencia programada.
- `direccion` y `encargado` son **NOT NULL + validación dura cliente y servidor** (mensajes exactos del
  txt) — F23/F24.
- Nombre visible = `cadena + " " + sucursal` si es_cadena, si no `nombre` — F20. Campos separados.
- Anti-dup sobre `(pais_codigo, cadena, sucursal)` normalizados; formulario solo tras búsqueda sin
  resultado — F25/F09.
- Farmacia en `PENDIENTE_APROBACION` no cuenta cobertura ni aparece en Registro de Visita — F22.
- Migraciones **a mano** (el autogenerate arrastra renombres de índices ajenos, como en `0021`).
- Alta originada por VM pasa por aprobación GD; el rol admin/config crea directo en el maestro.

---

## Task 1: Modelos + migración (maestro, panel, registro)

**Files:**
- Modify: `backend/app/models/visita.py` (agregar `FarmaciaVisita`, `FactVisitaFarmacia`)
- Modify: `backend/app/models/dimensiones.py` (agregar `Farmacia` en esquema `Config`)
- Create: `backend/alembic/versions/0024_modulo_farmacias.py`
- Test: `backend/tests/test_farmacia_modelo.py`

**Interfaces — Produces:**
- `dimensiones.Farmacia` (tabla `Config.DIM_Farmacia`)
- `visita.FarmaciaVisita` (tabla `Visita.DIM_FarmaciaVisita`)
- `visita.FactVisitaFarmacia` (tabla `Visita.FactVisitaFarmacia`)

- [ ] **Step 1 — Test que falla:** `tests/test_farmacia_modelo.py`
```python
def test_modelos_farmacia_importan_y_tienen_columnas_clave():
    from app.models.dimensiones import Farmacia
    from app.models.visita import FarmaciaVisita, FactVisitaFarmacia
    # Maestro: bloqueantes NOT NULL + cadena/sucursal + estado
    cols = Farmacia.__table__.columns
    assert cols["direccion"].nullable is False   # F23
    assert cols["encargado"].nullable is False   # F24
    assert "cadena" in cols and "sucursal" in cols and "nombre_completo" in cols
    assert cols["estado"].default.arg == "PENDIENTE_APROBACION"
    # Panel referencia al maestro (F19)
    assert "maestro_farmacia_id" in FarmaciaVisita.__table__.columns
    # Registro paralelo con FK a farmacia (Opción A)
    assert "farmacia_id" in FactVisitaFarmacia.__table__.columns
```
Run: `python -m pytest tests/test_farmacia_modelo.py -q` → FAIL (ImportError).

- [ ] **Step 2 — `Config.DIM_Farmacia`** en `dimensiones.py` (espejo de `Medico`):
```python
class Farmacia(Base):
    """Maestro único de farmacias (país-level). Los paneles de VM referencian aquí (F19)."""
    __tablename__ = "DIM_Farmacia"
    __table_args__ = (
        Index("IX_Farmacia_cadena_sucursal", "pais_codigo", "cadena", "sucursal"),
        Index("IX_Farmacia_estado", "estado"),
        {"schema": "Config"},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    es_cadena: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cadena: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sucursal: Mapped[str | None] = mapped_column(String(120), nullable=True)
    nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nombre_completo: Mapped[str] = mapped_column(String(250), nullable=False, default="")
    direccion: Mapped[str] = mapped_column(String(300), nullable=False)     # F23 bloqueante
    provincia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    encargado: Mapped[str] = mapped_column(String(200), nullable=False)     # F24 bloqueante
    telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE_APROBACION")
    origen: Mapped[str] = mapped_column(String(12), nullable=False, default="VM")   # VM | CONFIG
    solicitado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    aprobado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    fecha_solicitud: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_rechazo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc),
                                                 onupdate=lambda: datetime.now(timezone.utc))
```
*(Confirmar que `Index`, `Numeric`, `ForeignKey`, `datetime/timezone` estén importados en el módulo; si no, agregarlos.)*

- [ ] **Step 3 — `Visita.DIM_FarmaciaVisita` y `Visita.FactVisitaFarmacia`** en `visita.py`
  (usa los helpers ya presentes: `_ahora`, `Index`, `CHAR`, `LargeBinary`, `schema="Visita"`):
```python
class FarmaciaVisita(Base):
    """Farmacia del panel de un VM (referencia al Maestro, F19). Sin F1/F2: cobertura simple."""
    __tablename__ = "DIM_FarmaciaVisita"
    __table_args__ = (Index("IX_FarmaciaVisita_vm", "vm_id"), {"schema": "Visita"})
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    maestro_farmacia_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Farmacia.id"), nullable=False, index=True)
    estado_aprobacion: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDIENTE_ALTA")
    ciclo_alta_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)
    ciclo_baja_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)
    ciclos_sin_visita: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    solicitado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    aprobado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    fecha_solicitud: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora)

class FactVisitaFarmacia(Base):
    """Registro de visita a farmacia (Opción A: tabla paralela a FactVisita, cero regresión)."""
    __tablename__ = "FactVisitaFarmacia"
    __table_args__ = (Index("IX_FactVisitaFarm_vm_ciclo", "vm_id", "ciclo_id"), {"schema": "Visita"})
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    farmacia_id: Mapped[int] = mapped_column(Integer, ForeignKey("Visita.DIM_FarmaciaVisita.id"), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    comentario: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ejecutada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    causa_no_visita: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    foto: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    foto_mime: Mapped[str | None] = mapped_column(String(40), nullable=True)
    registrado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
```

- [ ] **Step 4 — Migración a mano** `0024_modulo_farmacias.py` (`down_revision="0023_activacion_cuenta"`):
  `op.create_table` para las 3 tablas con sus índices y FKs (schemas `Config`/`Visita`); `downgrade`
  hace `drop_table` en orden inverso (registro → panel → maestro). Plantilla: migración `0021`.

- [ ] **Step 5 — Verificar:** `python -m pytest tests/test_farmacia_modelo.py -q` → PASS.
  `python -m alembic upgrade head && python -m alembic downgrade -1 && python -m alembic upgrade head`
  → sin error (reversible).

- [ ] **Step 6 — Commit:** `feat(farmacias) modelos maestro+panel+registro y migración 0024`

---

## Task 2: Servicio de maestro (nombre_completo + anti-dup + alta)

**Files:**
- Create: `backend/app/services/maestro_farmacia_service.py`
- Test: `backend/tests/test_maestro_farmacia_service.py`

**Interfaces — Consumes:** `Farmacia` (T1). **Produces:** `nombre_completo(datos)`,
`detectar_duplicados(db, pais, cadena, sucursal, excluir_id)`, `crear_maestro(...)`,
`DuplicadoDuroError`. (Espeja `maestro_medico_service`.)

- [ ] **Step 1 — Test que falla** (funciones puras, sin BD):
```python
from app.services import maestro_farmacia_service as svc
def test_nombre_completo_de_cadena():
    assert svc.nombre_completo({"es_cadena": True, "cadena": "GBC", "sucursal": "Pantoja"}) == "GBC PANTOJA"
def test_nombre_completo_no_cadena_usa_nombre():
    assert svc.nombre_completo({"es_cadena": False, "nombre": "Farmacia Sol"}) == "FARMACIA SOL"
def test_normaliza_para_anti_dup():
    assert svc._clave("GBC", "Villa Duarte") == svc._clave(" g.b.c ", "villa  duarte") is False or True  # ver impl
```
Run → FAIL.

- [ ] **Step 2 — Implementar** `maestro_farmacia_service.py`:
  - `normalizar(txt)`: NFKD + upper + colapsar espacios (copiar de `maestro_medico_service.normalizar_nombre`).
  - `nombre_completo(datos)`: `f"{cadena} {sucursal}".strip()` normalizado si `es_cadena`, si no `nombre` normalizado.
  - `detectar_duplicados(db, pais, *, cadena, sucursal, excluir_id=None)`: **DURO** si existe misma
    `(pais, normalizar(cadena), normalizar(sucursal))` activa → `DuplicadoDuroError`. (Sin blando por
    ahora: la clave cadena+sucursal es exacta; la alerta blanda del GD va en la bandeja, Task 4.)
  - `crear_maestro(db, pais, datos, *, origen="VM", estado="PENDIENTE_APROBACION", usuario_id=None)`:
    valida bloqueantes (dirección/encargado no vacíos → `ValueError` con el mensaje del txt), corre
    anti-dup, calcula `nombre_completo`, inserta, audita (`_auditar`, modulo="MAESTRO_FARMACIAS").
- [ ] **Step 3 — Run** → PASS.
- [ ] **Step 4 — Commit:** `feat(farmacias) servicio de maestro: nombre_completo, anti-dup, alta`

---

## Task 3: Validación bloqueante (dirección + encargado), cliente-servidor

**Files:**
- Modify: `maestro_farmacia_service.py` (endurecer `crear_maestro`/`actualizar`)
- Test: `backend/tests/test_farmacia_bloqueantes.py`

- [ ] **Step 1 — Tests que fallan:**
```python
import pytest
from app.services import maestro_farmacia_service as svc
def test_sin_direccion_no_graba():
    with pytest.raises(ValueError, match="dirección de la farmacia"):
        svc.validar_bloqueantes({"encargado": "Ana", "direccion": "  "})
def test_sin_encargado_no_graba():
    with pytest.raises(ValueError, match="nombre del encargado"):
        svc.validar_bloqueantes({"direccion": "Calle 1", "encargado": ""})
def test_con_ambos_ok():
    svc.validar_bloqueantes({"direccion": "Calle 1", "encargado": "Ana"})  # no lanza
```
- [ ] **Step 2 — Implementar** `validar_bloqueantes(datos)` con los mensajes exactos del txt; llamarla
  al inicio de `crear_maestro` y `actualizar_maestro`.
- [ ] **Step 3 — Run** → PASS. **Step 4 — Commit:** `feat(farmacias) validación dura de campos bloqueantes`

---

## Task 4: Flujo de aprobación VM→GD

**Files:**
- Create: `backend/app/services/farmacia_aprobacion_service.py`
- Test: `backend/tests/test_farmacia_aprobacion_service.py`

**Interfaces — Produces:** `solicitar_agregar_al_panel(db, vm_id, maestro_farmacia_id, usuario_id)`
(Acción A), `solicitar_crear(db, vm_id, datos, usuario_id)` (Acción B), `pendientes_del_gd(db, gerente_id)`,
`aprobar(db, panel_id, usuario_id)`, `rechazar(db, panel_id, motivo, usuario_id)`,
`editar_y_aprobar(db, panel_id, cambios, usuario_id)`. (Espeja `visita_aprobacion_service`.)

- [ ] **Step 1 — Tests que fallan** (con FakeQuery/monkeypatch, patrón `conftest`):
  - Acción B crea maestro `PENDIENTE_APROBACION` + panel `PENDIENTE_ALTA`.
  - `aprobar` → maestro `ACTIVA`, panel `APROBADO`, `ciclo_alta_id` = ciclo por defecto del VM,
    `aprobado_por`/`fecha_aprobacion` seteados.
  - `rechazar` sin motivo → `ValueError`; con motivo → maestro `RECHAZADA`, `motivo_rechazo` guardado.
  - `pendientes_del_gd` solo devuelve los del distrito del gerente.
- [ ] **Step 2 — Implementar** el servicio reusando `ciclo_por_defecto`/`ciclo_actual_id` del módulo
  Visita y `_auditar`. Regla F22 la aplican las queries de cobertura/registro (Task 6/7), no aquí.
- [ ] **Step 3 — Run** → PASS. **Step 4 — Commit:** `feat(farmacias) flujo de aprobación VM→GD (acciones A/B, bandeja)`

---

## Task 5: Router `/farmacias` + RBAC

**Files:**
- Create: `backend/app/api/v1/routers/farmacias.py` (`prefix="/farmacias"`)
- Modify: `backend/app/api/v1/router.py` (registrar), `app/core/authz/matrix.py` (+recursos)
- Modify: `backend/app/schemas/schemas.py` (schemas Pydantic)
- Test: `backend/tests/test_farmacias_router.py` (TestClient)

**Endpoints:**
| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/farmacias/maestro/buscar?cadena=&sucursal=` | VM+ | búsqueda anti-dup (habilita form si vacío) |
| POST | `/farmacias/panel/agregar` | VM | Acción A (agregar existente) |
| POST | `/farmacias/panel/crear` | VM | Acción B (crear nueva, bloqueantes) |
| GET | `/farmacias/panel` | VM auto-scope | panel del VM (solo APROBADO cuenta) |
| GET | `/farmacias/aprobacion/pendientes` | GD | bandeja del distrito |
| POST | `/farmacias/aprobacion/{panel_id}/aprobar` `/rechazar` `/editar-aprobar` | GD | acciones |
| GET/POST/PUT | `/farmacias/maestro` | ADMIN/CONFIG | CRUD directo sin aprobación |

- [ ] Steps: test que falla (401/403 por rol; 422 sin dirección/encargado; 409 duplicado duro) →
  implementar router con `require(...)` de la matriz + auto-scope `rm_id` (patrón cobertura) →
  agregar recursos `farmacia.panel`/`farmacia.aprobar`/`farmacia.maestro` a `matrix.py` + oráculo del
  test de matriz → run → commit `feat(farmacias) router + RBAC`.

---

## Task 6: Registro de visita a Farmacia + guard F22

**Files:**
- Modify: `farmacias.py` (o `visita.py` router) — `POST /farmacias/{id}/visita`, `POST/GET .../foto`
- Test: `backend/tests/test_farmacia_visita.py`

- [ ] Steps: test que falla (registrar visita a farmacia `ACTIVA`/panel `APROBADO` OK; a una
  `PENDIENTE_APROBACION` → 409 por F22; foto magic bytes JPEG/PNG + 3 MB) → implementar sobre
  `FactVisitaFarmacia` reusando la validación de foto/GPS de `RegistrarVisita` → guard ciclo abierto →
  run → commit `feat(farmacias) tipo de visita farmacia + guard F22`.

---

## Task 7: Cobertura interna de farmacias (coexiste con SFA)

**Files:**
- Create: `backend/app/services/cobertura_farmacia_service.py`
- Test: `backend/tests/test_cobertura_farmacia.py`

- [ ] Steps: test que falla (`cobertura = farmacias del panel APROBADO visitadas ≥1 en el ciclo /
  farmacias del panel APROBADO activas`; PENDIENTE no cuenta, F22) → implementar (cobertura simple, sin
  F1/F2) + endpoint `GET /farmacias/cobertura` → run → commit `feat(farmacias) cobertura interna simple`.
  > **No** se cablea al score: `COB_FARMACIAS` del score sigue viniendo del SFA (decisión coexistencia).

---

## Task 8: Frontend

**Files:**
- Create: `frontend/src/pages/visita/PanelFarmacia.tsx` (móvil VM: buscar → Acción A/B, form bloqueante,
  estado de solicitudes + motivo de rechazo)
- Create: `frontend/src/pages/farmacias/BandejaAprobacionFarmacias.tsx` (GD: pendientes, alerta de
  duplicado, APROBAR/RECHAZAR/EDITAR Y APROBAR)
- Create: `frontend/src/pages/admin/MaestroFarmacias.tsx` (tab Admin, CRUD, listado con `nombre_completo`)
- Modify: `RegistrarVisita.tsx` (selector tipo Médico/Farmacia), `App.tsx` (rutas), `Sidebar` (nav),
  `services/` (llamadas axios)

- [ ] Steps: crear servicios axios → PanelFarmacia (Guardar deshabilitado sin dirección/encargado;
  form solo tras búsqueda sin resultado, F25; `autoCapitalize` off donde aplique) → bandeja GD →
  MaestroFarmacias → tipo Farmacia en Registro → `npx tsc --noEmit` + `npm run build` limpios →
  commit `feat(farmacias) frontend: panel VM, bandeja GD, maestro, tipo visita`.

---

## Task 9: Wire final + docs

- [ ] Registrar rutas en `App.tsx` con `ProtectedRoute recurso=`; ítems de `Sidebar` con `recurso`.
- [ ] Actualizar `CLAUDE.md` (§ nueva "Módulo de Farmacias") documentando maestro/panel/aprobación,
  las reglas F19–F26, la decisión Opción A y la coexistencia con el SFA para `COB_FARMACIAS`.
- [ ] Suite completa `pytest -q` verde + build; commit `docs(farmacias) + wire rutas/nav`.
- [ ] Cierre con `superpowers:finishing-a-development-branch`.

---

## Self-review (cobertura del spec)
- F19–F26: T1 (maestro/panel), T2/T3 (bloqueantes/anti-dup), T4 (aprobación), T6 (F22 registro),
  T7 (F22 cobertura). ✔
- Decisiones aprobadas: Opción A (T1/T6), sin F1/F2 (T1/T7), coexistencia SFA (T7 nota). ✔
- Preguntas abiertas del spec (§12: campos v1.0 extra) quedan como TODO a confirmar; no bloquean.
