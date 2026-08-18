"""Bloqueante 1 (frontera por país) — RONDA 4: `cobertura_predictiva.py` nunca se enumeró.

Las rondas 1-3 acotaron la enumeración por ARCHIVO (`visita.py`) en vez de por SUPERFICIE DE
AUTORIZACIÓN. `cobertura_predictiva.py` —registrado y alcanzable— quedó fuera y tenía la forma
más literal del defecto: `pais_codigo` viajando crudo desde el cliente en lecturas, escrituras y
un **borrado destructivo** (`DELETE /cat/datos`), sin un solo `exigir_pais`.

Cada test usa el mismo patrón cruzado que `test_frontera_pais_bypass_scope_vm.py`: un usuario
ADMIN acotado a `{GT}` en `Security.FACT_UsuarioPais` intentando alcanzar una entidad de RD.
No es el falso verde de "el usuario no tenía países asignados": ese caso está aislado en su
propio test, que verifica lo CONTRARIO (sin filas → sin filtro → sigue pudiendo).

Necesita PostgreSQL real: ejercita consultas SQLAlchemy encadenadas de verdad, no dobles.
"""
import asyncio
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.routers import cobertura_predictiva as cp_router
from app.api.v1.routers import visita as visita_router
from app.core.config import settings
from app.db.database import Base
from app.models import dimensiones, usuario  # noqa: F401 — registran las tablas en Base.metadata
from app.models import visita as visita_models  # noqa: F401
from app.models import cat_models  # noqa: F401 — registra el esquema cat.*
from app.models.alcance import UsuarioPais
from app.models.cat_models import CatDimCiclo, CatDimPais
from app.models.dimensiones import Ciclo, Feriado, Linea, Pais, ParametroCobertura, RepresentanteMedico
from app.models.usuario import Rol, Usuario

BD_PRUEBA = "vista_test_frontera_pais_cobertura_predictiva"


def _url(nombre: str) -> str:
    return (f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_SERVER}:{settings.DB_PORT}/{nombre}")


@pytest.fixture(scope="module")
def motor():
    try:
        admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as cx:
            cx.execute(text(f"DROP DATABASE IF EXISTS {BD_PRUEBA} WITH (FORCE)"))
            cx.execute(text(f"CREATE DATABASE {BD_PRUEBA}"))
        admin.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sin PostgreSQL alcanzable para pruebas de integración: {exc}")
    eng = create_engine(_url(BD_PRUEBA))
    with eng.begin() as cx:
        for esquema in ("Config", "Security", "DW", "Audit", "ETL", "exam",
                        "Visita", "coaching", "cat", "stg", "formacion", "ext"):
            cx.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"'))
    Base.metadata.create_all(eng)
    with eng.begin() as cx:
        # `cat.DimCentroMedico` no tiene modelo ORM (solo la crea la migración baseline);
        # `visita_service._SQL_MEDICOS_CAT` la LEFT JOIN-ea, así que sin ella la importación
        # masiva reventaría por tabla inexistente y el test no probaría nada.
        cx.execute(text('CREATE TABLE IF NOT EXISTS "cat"."DimCentroMedico" ('
                        '"CentroMedicoKey" integer PRIMARY KEY, "CentroMedico" varchar(200))'))
    yield eng
    eng.dispose()
    admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as cx:
        cx.execute(text(f"DROP DATABASE IF EXISTS {BD_PRUEBA} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def db(motor):
    Sesion = sessionmaker(bind=motor)
    s = Sesion()
    for tabla in ('"Visita"."FactVisita"', '"Visita"."DIM_MedicoVisita"',
                  '"cat"."FactMedicoCategoriaSnapshot"', '"cat"."DimMedico"',
                  '"cat"."DimRepresentanteMedico"', '"cat"."DimCiclo"',
                  '"cat"."LoadBatch"', '"cat"."DimPais"',
                  '"Config"."DIM_Feriado"', '"Config"."DIM_ParametroCobertura"',
                  '"Config"."DIM_RM"', '"Config"."DIM_Ciclo"',
                  '"Config"."DIM_Linea"', '"Security"."FACT_UsuarioPais"',
                  '"Security"."DIM_Usuario"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """DO y GT con línea, ciclo, VM, meta de cobertura y feriado cada uno. Usuario ADMIN
    acotado a `{GT}`: GT es su país propio, RD el ajeno que no debe poder alcanzar."""
    db.add_all([Pais(codigo="DO", nombre="República Dominicana"),
                Pais(codigo="GT", nombre="Guatemala")])
    db.flush()

    linea_do = Linea(pais_codigo="DO", codigo="A", nombre="Línea DO")
    linea_gt = Linea(pais_codigo="GT", codigo="A", nombre="Línea GT")
    db.add_all([linea_do, linea_gt])
    db.flush()

    ciclo_do = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="C01-2026",
                     fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 28),
                     dias_laborables=20, cerrado=False, activo=True)
    ciclo_gt = Ciclo(pais_codigo="GT", anio=2026, numero=1, nombre="C01-2026",
                     fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 28),
                     dias_laborables=20, cerrado=False, activo=True)
    db.add_all([ciclo_do, ciclo_gt])
    db.flush()

    vm_do = RepresentanteMedico(pais_codigo="DO", linea_id=linea_do.id, codigo="VMDO1",
                                nombre="VM República Dominicana")
    vm_gt = RepresentanteMedico(pais_codigo="GT", linea_id=linea_gt.id, codigo="VMGT1",
                                nombre="VM Guatemala")
    db.add_all([vm_do, vm_gt])

    # Configuración de AMBOS países: lo que un usuario de GT no debe ver es lo de RD.
    db.add_all([
        ParametroCobertura(pais_codigo="DO", meta_cobertura=0.90, activo=True),
        ParametroCobertura(pais_codigo="GT", meta_cobertura=0.80, activo=True),
        Feriado(pais_codigo="DO", fecha=date(2026, 1, 6), nombre="Reyes RD", activo=True),
        Feriado(pais_codigo="GT", fecha=date(2026, 1, 6), nombre="Reyes GT", activo=True),
    ])

    # cat.* — el DELETE destructivo resuelve `PaisKey` desde cat.DimPais.
    ahora = datetime.now(timezone.utc)
    pais_cat_do = CatDimPais(codigo_pais="DO", nombre_pais="República Dominicana", activo=True,
                             fecha_carga_utc=ahora)
    pais_cat_gt = CatDimPais(codigo_pais="GT", nombre_pais="Guatemala", activo=True,
                             fecha_carga_utc=ahora)
    db.add_all([pais_cat_do, pais_cat_gt])
    db.flush()
    db.add_all([
        CatDimCiclo(pais_key=pais_cat_do.pais_key, codigo_ciclo="2026-01",
                    fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 28),
                    meta_cobertura_pct=0.90, activo=True,
                    fecha_carga_utc=datetime.now(timezone.utc)),
        CatDimCiclo(pais_key=pais_cat_gt.pais_key, codigo_ciclo="2026-01",
                    fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 28),
                    meta_cobertura_pct=0.80, activo=True,
                    fecha_carga_utc=datetime.now(timezone.utc)),
    ])

    usuario_gt = Usuario(username="cp_scope_gt", hashed_password="x",
                         nombre_completo="Gerente de Guatemala", rol=Rol.ADMIN)
    db.add(usuario_gt)
    db.flush()
    db.add(UsuarioPais(usuario_id=usuario_gt.id, pais_codigo="GT"))
    db.commit()

    return {"usuario_gt": usuario_gt, "ciclo_do": ciclo_do, "ciclo_gt": ciclo_gt,
            "vm_do": vm_do, "vm_gt": vm_gt, "linea_do": linea_do, "linea_gt": linea_gt,
            "pais_cat_do": pais_cat_do, "pais_cat_gt": pais_cat_gt}


def _403(fn, *a, **kw):
    with pytest.raises(HTTPException) as exc:
        fn(*a, **kw)
    assert exc.value.status_code == 403
    return exc.value


class _FakeUpload:
    filename = "datos.xlsx"

    async def read(self):
        return b""


# ═══════════════════════════════════════════════════════════════════════════════
# HALLAZGO #1 — DELETE /cat/datos: borrado destructivo cross-país (prioridad)
# ═══════════════════════════════════════════════════════════════════════════════

def test_reset_datos_cat_de_otro_pais_da_403(db, escenario):
    """EL HALLAZGO MÁS GRAVE DEL BARRIDO: un GERENTE_PRODUCTIVIDAD acotado a GT podía
    borrar los KPIs, visitas y target de RD — y con `incluir_dims=true`, también sus
    dimensiones. El guard corre ANTES de resolver `PaisKey` y de cualquier DELETE."""
    _403(cp_router.reset_datos_cat, pais_codigo="DO", ciclo_codigo=None, incluir_dims=True,
         _current_user=escenario["usuario_gt"], db=db)


def test_reset_datos_cat_del_propio_pais_si_funciona(db, escenario):
    """Compatibilidad: el mismo usuario borrando SU país (GT) sigue funcionando."""
    r = cp_router.reset_datos_cat(pais_codigo="GT", ciclo_codigo=None, incluir_dims=False,
                                  _current_user=escenario["usuario_gt"], db=db)
    assert r["ok"] is True and r["pais"] == "GT"


# ═══════════════════════════════════════════════════════════════════════════════
# HALLAZGOS #2, #3, #6 — escrituras con `pais_codigo` crudo
# ═══════════════════════════════════════════════════════════════════════════════

def test_upsert_parametro_de_otro_pais_da_403(db, escenario):
    """`body.pais_codigo` sin guard fijaba la meta de cobertura de otro país (altera su KPI).
    Activo en la UI (`CoberturaPredictivaAdmin.tsx`)."""
    body = cp_router.ParametroCoberturaIn(pais_codigo="DO", meta_cobertura=0.10)
    _403(cp_router.upsert_parametro, body=body, db=db, current_user=escenario["usuario_gt"])
    # Y la meta de RD quedó intacta.
    meta = db.query(ParametroCobertura).filter(ParametroCobertura.pais_codigo == "DO").one()
    assert float(meta.meta_cobertura) == 0.90


def test_crear_feriado_de_otro_pais_da_403(db, escenario):
    """Un feriado ajeno altera el cálculo de días hábiles (NETWORKDAYS) del otro país."""
    body = cp_router.FeriadoIn(pais_codigo="DO", fecha=date(2026, 2, 27), nombre="Independencia")
    _403(cp_router.crear_feriado, body=body, db=db, current_user=escenario["usuario_gt"])


def test_calcular_sp_de_otro_pais_da_403(db, escenario):
    """Escritura: materializa (borrando y recalculando) los KPIs del país indicado."""
    _403(cp_router.calcular_sp, ciclo_codigo="2026-01", pais_codigo="DO", fecha_corte=None,
         representante_key=None, linea=None, _current_user=escenario["usuario_gt"], db=db)


def test_cargar_excel_cat_de_otro_pais_da_403(db, escenario):
    """`pais_codigo` llega por Form; el guard corre antes de leer el archivo."""
    exc = None
    try:
        asyncio.run(cp_router.cargar_excel_cat(
            archivo=_FakeUpload(), pais_codigo="DO", ciclo_codigo=None,
            calcular_al_cargar=False, _current_user=escenario["usuario_gt"], db=db))
    except HTTPException as e:
        exc = e
    assert exc is not None and exc.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# HALLAZGO #7 — cargas masivas cuyo identificador es `ciclo_id` (Form)
# ═══════════════════════════════════════════════════════════════════════════════

def test_cargar_target_medicos_con_ciclo_de_otro_pais_da_403(db, escenario):
    exc = None
    try:
        asyncio.run(cp_router.cargar_target_medicos(
            ciclo_id=escenario["ciclo_do"].id, modo="PRODUCCION", archivo=_FakeUpload(),
            db=db, current_user=escenario["usuario_gt"]))
    except HTTPException as e:
        exc = e
    assert exc is not None and exc.status_code == 403


def test_cargar_visitas_con_ciclo_de_otro_pais_da_403(db, escenario):
    exc = None
    try:
        asyncio.run(cp_router.cargar_visitas(
            ciclo_id=escenario["ciclo_do"].id, modo="PRODUCCION", archivo=_FakeUpload(),
            db=db, current_user=escenario["usuario_gt"]))
    except HTTPException as e:
        exc = e
    assert exc is not None and exc.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# HALLAZGO #5 — lecturas cat.* con `pais_codigo` requerido pero sin guard
# ═══════════════════════════════════════════════════════════════════════════════

def test_dashboard_4dx_de_otro_pais_da_403(db, escenario):
    _403(cp_router.dashboard_4dx, ciclo_codigo="2026-01", pais_codigo="DO", fecha_corte=None,
         linea=None, gd=None, representante=None,
         _current_user=escenario["usuario_gt"], db=db)


def test_cobertura_por_categoria_de_otro_pais_da_403(db, escenario):
    _403(cp_router.cobertura_por_categoria, ciclo_codigo="2026-01", pais_codigo="DO",
         representante=None, gd=None, _current_user=escenario["usuario_gt"], db=db)


def test_listar_ciclos_cat_de_otro_pais_da_403(db, escenario):
    _403(cp_router.listar_ciclos_cat, pais_codigo="DO",
         _current_user=escenario["usuario_gt"], db=db)


def test_listar_ciclos_cat_sin_pais_aplica_el_piso(db, escenario):
    """`pais_codigo` opcional: omitirlo listaba los ciclos de TODOS los países. El arreglo
    no es exigirlo, es filtrar por `paises_visibles`."""
    r = cp_router.listar_ciclos_cat(pais_codigo=None, _current_user=escenario["usuario_gt"], db=db)
    assert {c["pais_codigo"] for c in r} == {"GT"}


# ═══════════════════════════════════════════════════════════════════════════════
# HALLAZGO #4 — lecturas con `pais_codigo` OPCIONAL: el arreglo es filtrar, no exigir
# ═══════════════════════════════════════════════════════════════════════════════

def test_listar_parametros_sin_pais_solo_devuelve_los_paises_visibles(db, escenario):
    r = cp_router.listar_parametros(pais_codigo=None, linea_id=None, ciclo_id=None,
                                    db=db, current_user=escenario["usuario_gt"])
    assert {p["pais_codigo"] for p in r} == {"GT"}


def test_listar_parametros_con_pais_de_otro_pais_da_403(db, escenario):
    _403(cp_router.listar_parametros, pais_codigo="DO", linea_id=None, ciclo_id=None,
         db=db, current_user=escenario["usuario_gt"])


def test_listar_feriados_sin_pais_solo_devuelve_los_paises_visibles(db, escenario):
    r = cp_router.listar_feriados(pais_codigo=None, desde=None, hasta=None,
                                  db=db, current_user=escenario["usuario_gt"])
    assert {f["pais_codigo"] for f in r} == {"GT"}
    assert "Reyes RD" not in {f["nombre"] for f in r}


def test_listar_feriados_con_pais_de_otro_pais_da_403(db, escenario):
    _403(cp_router.listar_feriados, pais_codigo="DO", desde=None, hasta=None,
         db=db, current_user=escenario["usuario_gt"])


# ═══════════════════════════════════════════════════════════════════════════════
# COMPATIBILIDAD — "sin filas = todos" (el pilar de la regla, spec §3)
# ═══════════════════════════════════════════════════════════════════════════════

def test_usuario_sin_paises_asignados_sigue_viendo_y_escribiendo_todo(db, escenario):
    """`None` (sin restricción) y `set()` (nada visible) son AMBOS falsy: si el código los
    evaluara como booleano, este test caería. Un usuario sin filas en `FACT_UsuarioPais`
    debe seguir viendo los dos países y pudiendo escribir sobre RD."""
    libre = Usuario(username="cp_admin_sin_paises", hashed_password="x",
                    nombre_completo="Admin sin países", rol=Rol.ADMIN)
    db.add(libre)
    db.commit()

    # Lectura sin `pais_codigo`: ve los DOS países, no solo uno.
    assert {p["pais_codigo"] for p in cp_router.listar_parametros(
        pais_codigo=None, linea_id=None, ciclo_id=None, db=db, current_user=libre)} == {"DO", "GT"}
    assert {f["pais_codigo"] for f in cp_router.listar_feriados(
        pais_codigo=None, desde=None, hasta=None, db=db, current_user=libre)} == {"DO", "GT"}
    assert {c["pais_codigo"] for c in cp_router.listar_ciclos_cat(
        pais_codigo=None, _current_user=libre, db=db)} == {"DO", "GT"}

    # Escritura sobre RD: sin 403.
    r = cp_router.upsert_parametro(
        body=cp_router.ParametroCoberturaIn(pais_codigo="DO", meta_cobertura=0.95),
        db=db, current_user=libre)
    assert r["accion"] == "actualizado"


# ═══════════════════════════════════════════════════════════════════════════════
# HALLAZGOS #8 y #9 — las dos rutas que quedaban abiertas en `visita.py`
# ═══════════════════════════════════════════════════════════════════════════════

def test_resumen_muestras_con_ciclo_de_otro_pais_da_403(db, escenario):
    """La tabla de la ronda 3 daba esta ruta por cubierta vía `_scope_vm`, pero recibe DOS
    identificadores y solo `vm_id` tenía piso. Sin `vm_id`, el servicio agregaba las
    muestras y metas de parrilla de todo el ciclo pedido, de cualquier país."""
    _403(visita_router.resumen_muestras, vm_id=None, ciclo_id=escenario["ciclo_do"].id,
         db=db, current_user=escenario["usuario_gt"])


def _sembrar_categorizacion(db, escenario):
    """Un médico en cat.* por cada país, colgado del VM correspondiente. Es la fuente que
    lee `importar_desde_categorizacion`."""
    from app.models.cat_models import (CatDimMedico, CatDimRepresentante, FactMedicoCategoriaSnapshot,
                                       LoadBatch)
    lote = LoadBatch(archivo_origen="prueba.xlsx", periodo="2026-01", estado="OK",
                     fecha_carga_utc=datetime.now(timezone.utc), usuario_carga="test")
    db.add(lote)
    db.flush()
    for pais_cat, vm, nombre in ((escenario["pais_cat_do"], escenario["vm_do"], "MEDICO SECRETO RD"),
                                 (escenario["pais_cat_gt"], escenario["vm_gt"], "MEDICO LEGITIMO GT")):
        med = CatDimMedico(pais_key=pais_cat.pais_key, nombre_medico=nombre, activo=True)
        rep = CatDimRepresentante(pais_key=pais_cat.pais_key, codigo_representante=vm.codigo,
                                  nombre_representante=vm.nombre, activo=True)
        db.add_all([med, rep])
        db.flush()
        db.add(FactMedicoCategoriaSnapshot(
            load_batch_key=lote.load_batch_key, row_number=1, periodo="2026-01",
            pais_key=pais_cat.pais_key, medico_key=med.medico_key,
            representante_key=rep.representante_key, categoria_calculada="A",
            estado_calculo="OK"))
    db.commit()


def test_importar_categorizacion_no_crea_medicos_de_otro_pais(db, escenario):
    """ESCRITURA MASIVA sin identificador de cliente: creaba médicos en los paneles de los
    VM de TODOS los países. Mismo criterio con el que se cerró `GET /cierre/historial`.
    Aquí el predicado es de lista, así que se verifica FILTRADO, no 403."""
    _sembrar_categorizacion(db, escenario)
    visita_router.importar_medicos_categorizacion(db=db, current_user=escenario["usuario_gt"])

    from app.models.visita import MedicoVisita
    creados = {(m.vm_id, m.nombre_completo) for m in db.query(MedicoVisita).all()}
    assert (escenario["vm_gt"].id, "MEDICO LEGITIMO GT") in creados
    assert escenario["vm_do"].id not in {vm for vm, _ in creados}


def test_importar_categorizacion_sin_paises_asignados_importa_todo(db, escenario):
    """Compatibilidad de la misma ruta: sin filas en `FACT_UsuarioPais` se importan los dos
    países — `permitidos is None` no debe confundirse con `set()`."""
    _sembrar_categorizacion(db, escenario)
    libre = Usuario(username="cp_import_sin_paises", hashed_password="x",
                    nombre_completo="Admin sin países", rol=Rol.ADMIN)
    db.add(libre)
    db.commit()
    visita_router.importar_medicos_categorizacion(db=db, current_user=libre)

    from app.models.visita import MedicoVisita
    vms = {m.vm_id for m in db.query(MedicoVisita).all()}
    assert {escenario["vm_do"].id, escenario["vm_gt"].id} <= vms
