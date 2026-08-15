"""El bypass que la revisión encontró: omitir `pais_codigo` y colar el país por
`ciclo_id` (o, en Regional, por no filtrar la lista de países candidatos).

`exigir_pais`/`PaisPermitido` (Tarea 3) solo validan el parámetro LITERAL. Pero
`DIM_Ciclo.pais_codigo` es NOT NULL: cada `ciclo_id` pertenece a un único país. Un
usuario con `FACT_UsuarioPais = {DO}` que pide `GET /ranking?ciclo_id=<ciclo de GT>`
(sin `pais_codigo`) pasaba el guard de endpoint sin problema — el guard nunca mira
`ciclo_id` — y la consulta interna sí resolvía por el país real del ciclo.

La corrección: `scope.paises_visibles(db, user)` se aplica como FILTRO DE PISO sobre
toda consulta a `FACT_RankingRM`/`DIM_Pais` en `ranking.py`, exista o no `pais_codigo`
en la query. Este archivo prueba ese piso con datos reales — necesita PostgreSQL,
igual que `test_alcance_scope.py`/`test_alcance_frontera_pais.py` (consultas
SQLAlchemy encadenadas de verdad, no dobles de prueba).
"""
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.routers import ranking as router_rk
from app.core.config import settings
from app.core.pagination import PaginationParams
from app.db.database import Base
from app.models import dimensiones, usuario  # noqa: F401 — registran las tablas en Base.metadata
from app.models.alcance import UsuarioPais
from app.models.dimensiones import Ciclo, Linea, Pais, RepresentanteMedico
from app.models.hechos import RankingRM
from app.models.usuario import Rol, Usuario

BD_PRUEBA = "vista_test_frontera_pais_bypass_ciclo"


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
        # Mismo motivo que `test_alcance_scope.py`: `Base.metadata` es compartido por todo
        # el proceso de pytest, así que hay que crear todos los esquemas conocidos.
        for esquema in ("Config", "Security", "DW", "Audit", "ETL", "exam",
                        "Visita", "coaching", "cat", "stg", "formacion", "ext"):
            cx.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"'))
    Base.metadata.create_all(eng)
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
    for tabla in ('"DW"."FACT_RankingRM"', '"Config"."DIM_RM"', '"Config"."DIM_Ciclo"',
                  '"Config"."DIM_Linea"', '"Security"."FACT_UsuarioPais"',
                  '"Security"."DIM_Usuario"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """DO y GT, cada uno con una línea, un RM elegible y una fila de ranking MENSUAL en
    un ciclo propio (numero=1, mismo año). Un usuario ADMIN restringido a `{DO}`."""
    do = Pais(codigo="DO", nombre="República Dominicana")
    gt = Pais(codigo="GT", nombre="Guatemala")
    db.add_all([do, gt])
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

    rm_do = RepresentanteMedico(pais_codigo="DO", linea_id=linea_do.id, codigo="RMDO1",
                                nombre="RM República Dominicana")
    rm_gt = RepresentanteMedico(pais_codigo="GT", linea_id=linea_gt.id, codigo="RMGT1",
                                nombre="RM Guatemala")
    db.add_all([rm_do, rm_gt])
    db.flush()

    rk_do = RankingRM(pais_codigo="DO", rm_id=rm_do.id, ciclo_id=ciclo_do.id,
                      tipo_ranking="MENSUAL", score_total=80, posicion_global=1, elegible=True)
    rk_gt = RankingRM(pais_codigo="GT", rm_id=rm_gt.id, ciclo_id=ciclo_gt.id,
                      tipo_ranking="MENSUAL", score_total=95, posicion_global=1, elegible=True)
    db.add_all([rk_do, rk_gt])
    db.flush()

    usuario_do = Usuario(username="scope_do", hashed_password="x",
                         nombre_completo="Gerente de RD", rol=Rol.ADMIN)
    db.add(usuario_do)
    db.flush()
    db.add(UsuarioPais(usuario_id=usuario_do.id, pais_codigo="DO"))
    db.commit()

    return {
        "usuario_do": usuario_do,
        "ciclo_do": ciclo_do, "ciclo_gt": ciclo_gt,
        "rm_do": rm_do, "rm_gt": rm_gt,
    }


def _get_ranking_bypass(db, current_user, ciclo_id):
    """Llama `get_ranking` como lo haría FastAPI, pero SIN mandar `pais_codigo`
    (el bypass: el cliente no lo manda, solo `ciclo_id` de otro país)."""
    return router_rk.get_ranking(
        pais_codigo=None, ciclo_id=ciclo_id, tipo="MENSUAL", top=None,
        params=PaginationParams(page=1, size=50), db=db, current_user=current_user,
    )


def test_omitir_pais_codigo_y_pedir_ciclo_de_otro_pais_no_filtra_nada(db, escenario):
    """EL TEST QUE REPRODUCE EL HALLAZGO CRITICAL: un usuario con `{DO}` que pide el
    ciclo de GT (sin `pais_codigo`) no debe recibir el ranking de GT."""
    r = _get_ranking_bypass(db, escenario["usuario_do"], escenario["ciclo_gt"].id)
    assert r["items"] == []
    assert r["total"] == 0


def test_omitir_pais_codigo_con_el_propio_ciclo_si_funciona(db, escenario):
    """Compatibilidad: el mismo usuario, pidiendo SU PROPIO ciclo (DO) sin `pais_codigo`,
    sigue viendo sus datos con normalidad — el piso no bloquea lo legítimo."""
    r = _get_ranking_bypass(db, escenario["usuario_do"], escenario["ciclo_do"].id)
    assert r["total"] == 1
    assert r["items"][0]["rm_id"] == escenario["rm_do"].id


def test_usuario_sin_paises_asignados_si_ve_el_ciclo_de_cualquier_pais(db, escenario):
    """Compatibilidad: sin filas en `FACT_UsuarioPais` (los 37 usuarios existentes),
    `permitidos` es `None` y el piso no se activa — sigue viendo cualquier país."""
    admin_sin_paises = Usuario(username="admin_sin_paises_bypass", hashed_password="x",
                               nombre_completo="Admin sin países", rol=Rol.ADMIN)
    db.add(admin_sin_paises)
    db.commit()
    r = _get_ranking_bypass(db, admin_sin_paises, escenario["ciclo_gt"].id)
    assert r["total"] == 1
    assert r["items"][0]["rm_id"] == escenario["rm_gt"].id


def test_ranking_regional_no_incluye_paises_fuera_del_alcance(db, escenario):
    """EL TEST QUE CIERRA EL SEGUNDO HALLAZGO CRITICAL: `/ranking/regional` no recibe
    `pais_codigo` (no hay nada que cablear con `PaisPermitido`), así que sin filtrar la
    lista de países candidatos por `paises_visibles` un usuario con `{DO}` vería también
    a los mejores representantes de Guatemala."""
    r = router_rk.get_ranking_regional(top=10, db=db, current_user=escenario["usuario_do"])
    rm_ids = {item["rm_id"] for item in r}
    assert escenario["rm_gt"].id not in rm_ids
    assert escenario["rm_do"].id in rm_ids


def test_ranking_regional_sin_paises_asignados_ve_todos(db, escenario):
    """Compatibilidad: sin filas en `FACT_UsuarioPais`, Regional sigue mostrando todos
    los países (comportamiento histórico, `permitidos is None`)."""
    admin_sin_paises = Usuario(username="admin_sin_paises_regional", hashed_password="x",
                               nombre_completo="Admin sin países", rol=Rol.ADMIN)
    db.add(admin_sin_paises)
    db.commit()
    r = router_rk.get_ranking_regional(top=10, db=db, current_user=admin_sin_paises)
    rm_ids = {item["rm_id"] for item in r}
    assert escenario["rm_do"].id in rm_ids
    assert escenario["rm_gt"].id in rm_ids
