# Integración de Ventas (Mallén) — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrar `ext.factventa` a `DW.FACT_Ventas` y calcular el indicador `VENTAS`, cerrando además el circuito de ingresos del ROI del módulo de Visita.

**Architecture:** Un integrador nuevo en `integracion_visitas_service` que **agrega** el detalle por producto a una fila por `(país, ciclo, RM)`, con idempotencia por una entidad nueva de `MapeoExterno`; y el cálculo del indicador en `integracion_indicadores_service`, junto a los cuatro que ya existen y con sus mismas reglas.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, pytest contra PostgreSQL real.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-11-integracion-mallen-ventas-design.md`. Ante duda, manda el spec.
- **Intérprete**: `backend/venv/Scripts/python.exe`. El `python` del PATH **no** tiene dependencias.
- Tests contra **PostgreSQL real**; SKIPPED es aceptable, FAILED/ERROR no.
- **`resultado_real` de `VENTAS` va como FRACCIÓN 0-1**, nunca como porcentaje: `VENTAS` tiene `escala = 1` y el motor multiplica por 100. Escribir `88.0` daría puntuación perfecta.
- **El test del indicador DEBE atravesar `motor_calculo_service.completar_puntajes`** y afirmar sobre `puntos_obtenidos`. Afirmar solo sobre `resultado_real` es comparar el valor consigo mismo — el defecto que ya se coló una vez.
- **Sin cuota (nula o cero) NO se escribe la fila** del indicador, y se emite hallazgo `aviso`. Dividir por cero no es cumplimiento cero.
- **La cuota se SUMA**, pero si un `(rm, ciclo)` tiene más de una fila y **todas** traen la misma cuota, se emite hallazgo `aviso` (firma de un ERP que repite el total). **El cálculo no cambia.**
- **`linea_id` sale de `rm.linea_id`**, nunca del producto.
- **Entidad de mapeo NUEVA** (`ENT_VENTAS_RM_CICLO`): reutilizar otra corrompería el mapeo, porque `MapeoExterno` es único por `(entidad, país, código)` con un solo `id_interno`.
- **NO se toca `visita_costo_service`**: el supuesto bug del ROI mezclando países no existe — `DIM_Ciclo` tiene `pais_codigo` (ver §6 del spec).
- **PROHIBIDO tocar** el esquema `ext`, `motor_calculo_service.py`, `recalculo_service.py`, `cobertura_predictiva_service.py`, `cobertura_farmacia_service.py`. **Sin migración.**
- Convenciones: `logger` de loguru (nunca `print()`), servicios reciben `db: Session`.

---

### Task 1: El integrador de ventas

**Files:**
- Modify: `backend/app/services/integracion_visitas_service.py`
- Test: `backend/tests/test_integracion_ventas.py`

**Interfaces:**
- Consumes: `ConteoHecho`, `Hallazgo`, `SEVERIDAD_AVISO`/`SEVERIDAD_ERROR`, `_lote_habilitado`, `_resolver_estados_lotes`, `_cabe`, `_omitir_por_largo`, `_omitir_por_lote`, `_falta_ref`, `_refs`, `LARGO_CODIGO_EXTERNO` — todos ya en ese módulo.
- Produces: `ENT_VENTAS_RM_CICLO = "ventas_rm_ciclo"`; `integrar_ventas(db, pais_codigo, ciclo_codigo, hallazgos, estados_lote=None) -> ConteoHecho`; entrada `("factventa", integrar_ventas)` en `_INTEGRADORES` y en `_ORIGEN_CONTEO`.

- [ ] **Step 1: Escribir los tests**

Crear `backend/tests/test_integracion_ventas.py`. Copia el bloque de fixtures `motor`/`db`/`escenario` de `backend/tests/test_medicos_top.py` **tal cual**, cambiando `BD_PRUEBA = "vista_test_ventas"` y añadiendo `'"DW"."FACT_Ventas"'` al **inicio** de la lista de limpieza. Añade después:

```python
from decimal import Decimal
from app.models.hechos import Ventas
from app.models.integracion_ext import ExtFactVenta
from app.services import integracion_visitas_service as viz


def _venta(db, origen_id, valor, cuota, producto="P1", rm="VM01"):
    db.add(ExtFactVenta(
        lote_id=1001, origen_id=origen_id, pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo=rm, producto_codigo=producto,
        valor_venta=Decimal(str(valor)), cuota=Decimal(str(cuota))))
    db.flush()


def test_agrega_el_detalle_por_producto_en_una_fila(escenario):
    """FACT_Ventas es una fila por (pais, linea, RM, ciclo): el detalle por
    producto se suma, no se replica."""
    db = escenario["db"]
    _venta(db, "V-1", 100, 50, producto="P1")
    _venta(db, "V-2", 200, 50, producto="P2")
    _venta(db, "V-3", 300, 50, producto="P3")
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    v = db.query(Ventas).one()
    assert v.ventas_reales == Decimal("600.00")
    assert v.rm_id == escenario["rm"].id
    assert v.ciclo_id == escenario["ciclo"].id


def test_una_fila_sin_producto_se_agrega_igual(escenario):
    db = escenario["db"]
    _venta(db, "V-1", 100, 40, producto=None)
    _venta(db, "V-2", 50, 60, producto="P1")
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(Ventas).one().ventas_reales == Decimal("150.00")


def test_linea_id_sale_del_representante(escenario):
    """`DIM_Producto.linea_id` es nullable y el hecho puede no traer producto:
    la linea del RM es el unico origen fiable."""
    db = escenario["db"]
    _venta(db, "V-1", 100, 100, producto=None)
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(Ventas).one().linea_id == escenario["rm"].linea_id


def test_reintegrar_no_duplica_ni_dobla_los_ingresos(escenario):
    """El test que justifica el mapeo: FACT_Ventas NO tiene llave natural, y el
    ROI SUMA ventas_reales — duplicar seria inventar ingresos."""
    db = escenario["db"]
    _venta(db, "V-1", 500, 400)
    db.commit()
    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(Ventas).count() == 1
    assert db.query(Ventas).one().ventas_reales == Decimal("500.00")


def test_adopta_una_fila_legacy_sin_mapeo(escenario):
    """En produccion hay 9 filas cargadas por el Excel legacy, sin mapeo. Se
    ADOPTAN por clave natural en vez de duplicarse."""
    db = escenario["db"]
    legacy = Ventas(pais_codigo="DO", linea_id=escenario["rm"].linea_id,
                    rm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                    ventas_reales=Decimal("1.00"), cuota=Decimal("1.00"))
    db.add(legacy)
    db.commit()
    legacy_id = legacy.id
    _venta(db, "V-1", 900, 800)
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(Ventas).count() == 1
    v = db.query(Ventas).one()
    assert v.id == legacy_id                    # la misma fila, no una nueva
    assert v.ventas_reales == Decimal("900.00")


def test_cuotas_distintas_se_suman_sin_aviso(escenario):
    db = escenario["db"]
    _venta(db, "V-1", 100, 30)
    _venta(db, "V-2", 100, 70)
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(Ventas).one().cuota == Decimal("100.00")
    assert hallazgos == []


def test_cuotas_identicas_se_suman_pero_avisan(escenario):
    """La firma de un ERP que repite el total del RM en cada fila de producto.
    Se suma igual (decision del cliente) pero se avisa: si esa fuera la causa,
    la cuota quedaria multiplicada por el numero de productos y el
    cumplimiento de TODOS se desplomaria sin que nada lo delatara."""
    db = escenario["db"]
    _venta(db, "V-1", 100, 500, producto="P1")
    _venta(db, "V-2", 200, 500, producto="P2")
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(Ventas).one().cuota == Decimal("1000.00")   # se suma igual
    assert any(h.severidad == "aviso" and "cuota" in h.problema.lower()
               for h in hallazgos)


def test_una_sola_fila_nunca_dispara_el_aviso_de_cuota(escenario):
    db = escenario["db"]
    _venta(db, "V-1", 100, 500)
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert hallazgos == []


def test_lote_no_validado_no_entra(escenario):
    db = escenario["db"]
    _venta(db, "V-1", 100, 100)
    db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado = "RECHAZADO"
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(Ventas).count() == 0
    assert any(h.severidad == "error" for h in hallazgos)


def test_rm_sin_sincronizar_se_omite_y_el_resto_entra(escenario):
    db = escenario["db"]
    _venta(db, "V-1", 100, 100, rm="VM01")
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               nombre="Sin mapeo", activo=True))
    db.flush()
    _venta(db, "V-2", 999, 999, rm="VM99")
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(Ventas).count() == 1
    assert db.query(Ventas).one().ventas_reales == Decimal("100.00")
    assert any(h.severidad == "error" for h in hallazgos)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ventas.py -v`
Expected: FAIL con `AttributeError: module ... has no attribute 'integrar_ventas'`.

- [ ] **Step 3: Añadir la constante de entidad**

En `backend/app/services/integracion_visitas_service.py`, junto a las demás constantes de entidad:

```python
#: Entidad propia para la fila AGREGADA de `DW.FACT_Ventas`. Nueva y no
#: reutilizada, por lo mismo que las de los hechos de médico: `MapeoExterno` es
#: único por `(entidad, país, código)` con un solo `id_interno`, así que
#: compartirla haría que `resolver` buscara el id en la tabla equivocada.
#: Es además la ÚNICA idempotencia que tiene `FACT_Ventas`: esa tabla no lleva
#: ningún UNIQUE, y como el ROI suma `ventas_reales`, duplicar una fila
#: inventaría ingresos que nadie podría rastrear.
ENT_VENTAS_RM_CICLO = "ventas_rm_ciclo"
```

Y añade `ExtFactVenta` y `Ventas` a los imports del módulo (`from app.models.integracion_ext import ...` y `from app.models.hechos import Ventas`).

- [ ] **Step 4: Implementar el integrador**

Añádelo antes de `_INTEGRADORES`:

```python
def integrar_ventas(db: Session, pais_codigo: str, ciclo_codigo: str,
                    hallazgos: list,
                    estados_lote: dict[int, str] | None = None) -> ConteoHecho:
    """`ext.factventa` → `DW.FACT_Ventas`, AGREGANDO por (país, ciclo, RM).

    La granularidad no coincide: el contrato manda detalle (con `producto_codigo`
    opcional) y `FACT_Ventas` es una fila por país+línea+RM+ciclo, sin columna de
    producto. Se suma `valor_venta` y `cuota`; el detalle se descarta porque no
    hay dónde ponerlo y ningún consumidor lo pide.

    Alimenta dos cosas: el indicador VENTAS (vía `integracion_indicadores_service`)
    y los INGRESOS DEL ROI del módulo de Visita, que lee esta tabla — de ahí que
    duplicar una fila sea especialmente dañino.
    """
    conteo = ConteoHecho("factventa")
    filas = (db.query(ExtFactVenta)
             .filter(ExtFactVenta.pais_codigo == pais_codigo,
                     ExtFactVenta.ciclo_codigo == ciclo_codigo).all())
    conteo.en_ext = len(filas)
    if estados_lote is None:
        estados_lote = _resolver_estados_lotes(db, {f.lote_id for f in filas})

    # Agregación por RM. Se agrupa DESPUÉS de filtrar por lote: una fila de un
    # lote rechazado no debe sumar al total de nadie.
    por_rm: dict[str, list] = {}
    for fila in filas:
        if not _lote_habilitado(estados_lote, fila.lote_id):
            _omitir_por_lote(conteo, hallazgos, "factventa", fila.origen_id,
                             fila.lote_id, estados_lote)
            continue
        por_rm.setdefault(fila.rm_codigo, []).append(fila)

    for rm_codigo, grupo in sorted(por_rm.items()):
        clave = f"{ciclo_codigo}/{rm_codigo}"
        if not _cabe(clave, LARGO_CODIGO_EXTERNO):
            _omitir_por_largo(conteo, hallazgos, "factventa", clave,
                              "MapeoExterno.codigo_externo", LARGO_CODIGO_EXTERNO)
            continue
        ciclo_id, rm_id = _refs(db, pais_codigo, ciclo_codigo, rm_codigo)
        if ciclo_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factventa", clave, "el ciclo", ciclo_codigo)
            continue
        if rm_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factventa", clave, "el representante", rm_codigo)
            continue
        rm = db.query(RepresentanteMedico).filter(
            RepresentanteMedico.id == rm_id).first()
        if rm is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factventa", clave, "la ficha del representante",
                       rm_codigo)
            continue

        total_venta = sum((f.valor_venta or Decimal(0) for f in grupo), Decimal(0))
        total_cuota = sum((f.cuota or Decimal(0) for f in grupo), Decimal(0))

        # La cuota se SUMA (decisión del cliente), pero varias filas con la cuota
        # EXACTAMENTE igual son la firma de un ERP que repite el total del RM en
        # cada producto en vez de repartirlo. Sumarla ahí la multiplicaría por el
        # número de productos y hundiría el cumplimiento de todos sin que nada lo
        # delatara. No se corrige automáticamente —adivinar haría el número
        # impredecible—: se avisa.
        cuotas = {f.cuota for f in grupo}
        if len(grupo) > 1 and len(cuotas) == 1:
            hallazgos.append(Hallazgo(
                "factventa", clave,
                f"El representante «{rm_codigo}» trae {len(grupo)} filas con la "
                f"MISMA cuota ({next(iter(cuotas))}). Se sumaron, pero si el "
                f"origen repite la cuota total por producto en vez de "
                f"repartirla, el total quedaría multiplicado por "
                f"{len(grupo)}. Confirmar con el laboratorio.",
                SEVERIDAD_AVISO))

        def _buscar(cid=ciclo_id, rid=rm_id):
            return (db.query(Ventas)
                    .filter(Ventas.pais_codigo == pais_codigo,
                            Ventas.ciclo_id == cid, Ventas.rm_id == rid).first())

        def _crear(cid=ciclo_id, rid=rm_id, r=rm):
            nuevo = Ventas(pais_codigo=pais_codigo, linea_id=r.linea_id,
                           rm_id=rid, ciclo_id=cid,
                           ventas_reales=Decimal(0), cuota=Decimal(0))
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_VENTAS_RM_CICLO, pais_codigo, clave, Ventas, _buscar, _crear)
        registro.ventas_reales = total_venta
        registro.cuota = total_cuota
        registro.linea_id = rm.linea_id
        # `cumplimiento_pct` en 0-100 (criterio del ETL legacy, para no dejar la
        # tabla a medias). El Score NO lo usa: su camino es FACT_ResultadoIndicador.
        registro.cumplimiento_pct = (
            calcular_cumplimiento(total_venta, total_cuota) if total_cuota else None)
        conteo.anotar(resultado, grupo[0].lote_id)

    return conteo
```

Añade los imports que falten al módulo: `from decimal import Decimal`, `from app.models.dimensiones import RepresentanteMedico` y `from app.services.puntaje_service import calcular_cumplimiento`. Comprueba cuáles ya están antes de duplicarlos.

- [ ] **Step 5: Registrarlo en el orquestador**

En `_INTEGRADORES`, al final (las ventas no dependen de los otros hechos, pero el orden fija el de la respuesta):

```python
    ("factventa", integrar_ventas),
```

Y en `_ORIGEN_CONTEO`, para que `resumen_visitas` lo cuente:

```python
    "factventa": (
        ExtFactVenta, ENT_VENTAS_RM_CICLO,
        lambda m: func.concat(m.ciclo_codigo, "/", m.rm_codigo)),
```

**Ojo**: la lambda debe reconstruir en SQL **exactamente** la misma `codigo_externo` que le pasas a `mapeo.resolver` — si divergen, el resumen contará mal sin fallar.

- [ ] **Step 6: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ventas.py -v`
Expected: 10 passed (o SKIPPED).

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_visitas.py -q`
Expected: sin regresiones — el orquestador ahora corre un integrador más.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/integracion_visitas_service.py backend/tests/test_integracion_ventas.py
git commit -m "feat(integracion) integrar ventas de Mallen agregando por RM y ciclo"
```

---

### Task 2: El indicador `VENTAS`

**Files:**
- Modify: `backend/app/services/integracion_indicadores_service.py`
- Test: `backend/tests/test_integracion_ventas.py`

**Interfaces:**
- Consumes: `ExtFactVenta`; los helpers y el flujo de `calcular_indicadores` (gate de lote, guard de ciclo cerrado, patrón `candidatos`/`valores`, delete-then-insert acotado).
- Produces: constante `VENTAS = "VENTAS"` añadida a `CODIGOS`; helper `_cumplimiento_ventas(db, pais_codigo, ciclo_codigo, rm_codigo, lotes_integrables) -> Decimal | None`.

- [ ] **Step 1: Escribir los tests**

Añade a `backend/tests/test_integracion_ventas.py`:

```python
from app.models.dimensiones import Indicador
from app.models.hechos import ResultadoIndicador
from app.services import integracion_indicadores_service as ind
from app.services import motor_calculo_service


def _indicador_ventas(db):
    """VENTAS con escala=1 y ponderacion 15, igual que en produccion."""
    i = Indicador(pais_codigo="DO", codigo="VENTAS", nombre="Ventas vs Cuota",
                  modulo="RESULTADOS", tipo_periodo="MES", escala=1,
                  ponderacion_pct=15)
    db.add(i)
    db.flush()
    return i


def test_ventas_atraviesa_el_motor_y_puntua_bien(escenario):
    """EL test que faltó en el sub-proyecto 3: afirmar sobre `resultado_real`
    compara el valor consigo mismo. Lo que importa es qué PUNTOS salen al
    final, porque VENTAS tiene escala=1 y el motor multiplica por 100."""
    db = escenario["db"]
    _indicador_ventas(db)
    _venta(db, "V-1", 88, 100)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()
    motor_calculo_service.completar_puntajes(db, escenario["ciclo"].id, "DO")

    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").one())
    assert fila.resultado_real == Decimal("0.8800")      # FRACCION, no 88
    assert fila.resultado_porcentaje == Decimal("88.0000")
    assert fila.puntos_obtenidos == Decimal("13.2000")   # 88% de 15


def test_sobrecumplimiento_no_se_acota_en_el_dato_crudo(escenario):
    db = escenario["db"]
    _indicador_ventas(db)
    _venta(db, "V-1", 120, 100)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()
    motor_calculo_service.completar_puntajes(db, escenario["ciclo"].id, "DO")

    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").one())
    assert fila.resultado_real == Decimal("1.2000")       # crudo, sin acotar
    assert fila.resultado_porcentaje == Decimal("100.0000")  # el motor sí acota


def test_venta_negativa_no_baja_de_cero(escenario):
    db = escenario["db"]
    _indicador_ventas(db)
    _venta(db, "V-1", -50, 100)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").one())
    assert fila.resultado_real == Decimal("0.0000")


def test_sin_cuota_no_se_escribe_la_fila(escenario):
    """Dividir por cero no es cumplimiento cero: es ausencia de meta, y un 0
    penalizaria a un RM al que nadie le fijo cuota."""
    db = escenario["db"]
    _indicador_ventas(db)
    _venta(db, "V-1", 500, 0)
    db.commit()
    hallazgos = []

    ind.calcular_indicadores(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").count()) == 0
    assert any(h.severidad == "aviso" for h in hallazgos)


def test_sin_cuota_no_pisa_un_valor_anterior(escenario):
    """Al no escribirse, tampoco entra en el delete-then-insert: lo que hubiera
    cargado el Excel se conserva."""
    db = escenario["db"]
    i = _indicador_ventas(db)
    db.add(ResultadoIndicador(
        rm_id=escenario["rm"].id, pais_codigo="DO",
        linea_id=escenario["rm"].linea_id, ciclo_id=escenario["ciclo"].id,
        indicador_id=i.id, resultado_real=Decimal("0.9"), activo=True))
    _venta(db, "V-1", 500, 0)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").one())
    assert fila.resultado_real == Decimal("0.9000")   # intacto
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ventas.py -k "ventas_atraviesa or sobrecumplimiento or negativa or sin_cuota" -v`
Expected: FAIL — no se escribe ninguna fila de `VENTAS`.

- [ ] **Step 3: Implementar el cálculo**

En `backend/app/services/integracion_indicadores_service.py`, junto a los otros códigos:

```python
VENTAS = "VENTAS"
```

Añade `VENTAS` a la tupla `CODIGOS`, e `ExtFactVenta` a los imports de `integracion_ext`.

Y el helper, junto a los otros:

```python
def _cumplimiento_ventas(db: Session, pais_codigo: str, ciclo_codigo: str,
                         rm_codigo: str, lotes_integrables: list[int]
                         ) -> Decimal | None:
    """`SUM(valor_venta) / SUM(cuota)` del RM en el ciclo, como FRACCIÓN 0-1.

    Devuelve None —y por tanto NO se escribe la fila— cuando no hay cuota: sin
    meta no hay cumplimiento que medir, y un 0 penalizaría a un representante al
    que nadie se la fijó. Misma regla que el universo vacío de las coberturas.

    Se acota por abajo a 0 (una venta negativa por devoluciones no resta
    cumplimiento) pero NO por arriba: sobrecumplir debe verse en el dato crudo,
    y el motor ya acota a 100 al puntuar.
    """
    fila = (db.query(func.sum(ExtFactVenta.valor_venta),
                     func.sum(ExtFactVenta.cuota))
            .filter(ExtFactVenta.pais_codigo == pais_codigo,
                    ExtFactVenta.ciclo_codigo == ciclo_codigo,
                    ExtFactVenta.rm_codigo == rm_codigo,
                    ExtFactVenta.lote_id.in_(lotes_integrables)).one())
    venta, cuota = fila[0], fila[1]
    if cuota is None or Decimal(cuota) == 0:
        return None
    bruto = Decimal(venta or 0) / Decimal(cuota)
    return max(bruto, Decimal(0)).quantize(Decimal("0.0001"))
```

En `calcular_indicadores`, añade `VENTAS` al dict `candidatos` (para que herede el tratamiento de `None` → aviso + no escribir):

```python
            VENTAS: (_cumplimiento_ventas(db, pais_codigo, ciclo_codigo,
                                          rm_codigo, lotes_integrables),
                     "no tiene cuota de ventas cargada"),
```

Y en la consulta que arma el conjunto de RMs a procesar, añade los que solo tienen ventas — si no, un RM sin panel médico nunca llegaría a calcularse:

```python
    rms |= {f[0] for f in db.query(ExtFactVenta.rm_codigo)
            .filter(ExtFactVenta.pais_codigo == pais_codigo,
                    ExtFactVenta.ciclo_codigo == ciclo_codigo,
                    ExtFactVenta.lote_id.in_(lotes_integrables)).distinct()}
```

Lee cómo se construye hoy ese conjunto antes de escribir: el nombre de la variable y el filtro por lote deben coincidir con lo que ya hay.

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ventas.py -v`
Expected: 15 passed (o SKIPPED).

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_indicadores.py -q`
Expected: sin regresiones.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/integracion_indicadores_service.py backend/tests/test_integracion_ventas.py
git commit -m "feat(integracion) calcular el indicador VENTAS desde los hechos de Mallen"
```

---

### Task 3: Cerrar el circuito del ROI

**Files:**
- Test: `backend/tests/test_integracion_ventas.py`

**Interfaces:**
- Consumes: `integrar_ventas` (Task 1) y `visita_costo_service.roi`.
- Produces: nada de código — esta tarea **solo añade tests**. Es deliberado: fija por prueba la propiedad que el §7.2 pide ("ingresos del ROI") y la que retiró el falso hallazgo del §6 del spec.

- [ ] **Step 1: Escribir los tests**

Añade a `backend/tests/test_integracion_ventas.py`:

```python
from app.services import visita_costo_service


def test_las_ventas_integradas_alimentan_el_roi(escenario):
    """El §7.2 pide que Ventas alimente «los ingresos del ROI». Este test cierra
    el circuito Mallen -> FACT_Ventas -> ROI de punta a punta."""
    db = escenario["db"]
    _venta(db, "V-1", 700, 500)
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    r = visita_costo_service.roi(db, escenario["ciclo"].id, escenario["rm"].id)

    assert r["ingresos"] == 700.0


def test_el_roi_no_toma_ventas_de_otro_pais(escenario):
    """No prueba un arreglo: `DIM_Ciclo` YA lleva pais_codigo, asi que cada
    ciclo es de un solo pais y el ROI nunca pudo mezclar. Fija la propiedad
    para que nadie la rompa quitando el pais del ciclo."""
    db = escenario["db"]
    otro_pais = Pais(codigo="CR", nombre="Costa Rica")
    db.add(otro_pais)
    db.flush()
    otra_linea = Linea(pais_codigo="CR", codigo="CARD", nombre="Cardiologia")
    db.add(otra_linea)
    db.flush()
    otro_rm = RepresentanteMedico(pais_codigo="CR", linea_id=otra_linea.id,
                                  codigo="VM01", nombre="RM de CR")
    otro_ciclo = Ciclo(pais_codigo="CR", anio=2026, numero=1, nombre="Ciclo 1",
                       fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                       dias_laborables=20, cerrado=False)
    db.add_all([otro_rm, otro_ciclo])
    db.flush()
    db.add(Ventas(pais_codigo="CR", linea_id=otra_linea.id, rm_id=otro_rm.id,
                  ciclo_id=otro_ciclo.id, ventas_reales=Decimal("9999.00"),
                  cuota=Decimal("1.00")))
    _venta(db, "V-1", 700, 500)
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    r = visita_costo_service.roi(db, escenario["ciclo"].id, None)

    assert r["ingresos"] == 700.0        # las de CR no se cuelan
```

Añade `RepresentanteMedico` a los imports de `app.models.dimensiones` en el test si no estuviera ya.

- [ ] **Step 2: Correr los tests**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ventas.py -v`
Expected: 17 passed (o SKIPPED). **Estos dos deben pasar sin tocar código**: si alguno falla, el diagnóstico del §6 del spec era incorrecto y hay que parar y revisarlo, no "arreglar" el test.

- [ ] **Step 3: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: toda la suite en verde.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_integracion_ventas.py
git commit -m "test(integracion) fijar que las ventas integradas alimentan el ROI"
```

---

## Verificación en vivo (tras Task 3, no es un commit)

Con JWT de ADMIN, sembrando `ext.factventa` a mano:

1. Tres filas del mismo RM con productos distintos → `POST /integracion/visitas/integrar` devuelve el hecho `factventa` con `integrados: 1` (una fila, no tres).
2. `GET /integracion/visitas/resumen` cuenta bien `en_ext` (3) frente a `integradas` (1) — el JOIN de `_ORIGEN_CONTEO` reconstruye la clave correcta.
3. Integrar dos veces → `ventas_reales` **no se dobla** en `DW.FACT_Ventas`.
4. Dos filas con la misma cuota → el aviso aparece en la tabla de hallazgos de la pantalla.
5. El ROI del módulo de Visita muestra esos ingresos.
6. La pantalla `/integracion/lotes` muestra el hecho nuevo **sin tocar el frontend**: la tabla se pinta desde `resultado.hechos`, que es dinámico. Si no aparece, es que falta el registro en `_ORIGEN_CONTEO`.

---

## Self-Review

**1. Cobertura del spec:**
- §2 agregación por RM, `linea_id` del RM, producto descartado → Task 1 + 3 tests.
- §3 idempotencia con entidad nueva y adopción de las filas legacy → Task 1 + 2 tests.
- §4 cuota sumada con aviso si son idénticas → Task 1 + 3 tests (distintas, idénticas, una sola).
- §5 indicador como fracción 0-1, sin cuota no escribe, no pisa lo anterior → Task 2 + 5 tests, uno de ellos **atravesando `completar_puntajes`**.
- §6 el ROI no mezcla países (hallazgo retirado) → Task 3, 2 tests que **no cambian código**.
- §7 fuera de alcance → respetado: sin migración, sin tocar los servicios prohibidos, sin frontend.
- §8 los 18 puntos de verificación → repartidos entre las 3 tareas y la sección en vivo.

**2. Placeholder scan:** sin TBD/TODO. Tres puntos piden leer el código antes de escribir (los imports ya presentes en cada módulo, y cómo se construye hoy el conjunto de RMs): son instrucciones de inspección deliberadas, no huecos.

**3. Consistencia de tipos:** `ENT_VENTAS_RM_CICLO` se define en Task 1 y lo usa `_ORIGEN_CONTEO` en la misma tarea. `integrar_ventas` tiene la misma firma que los otros cuatro integradores, que es lo que `_INTEGRADORES` espera. `_cumplimiento_ventas` devuelve `Decimal | None`, que es justo lo que el dict `candidatos` de Task 2 sabe tratar. La clave `f"{ciclo_codigo}/{rm_codigo}"` es idéntica en el integrador y en la lambda SQL del resumen.

**4. Riesgo conocido:** el aviso de cuota idéntica es una heurística, no una verdad. Un representante con dos productos que legítimamente tengan la misma cuota lo dispararía. Es aceptable porque **avisa sin cambiar el número** — el coste de un falso positivo es un renglón en la pantalla; el de no avisar, un indicador hundido para todos sin explicación.
