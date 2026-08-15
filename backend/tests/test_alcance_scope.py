"""Resolución de alcance por línea y de países visibles.

El orden importa y es lo que estos tests fijan: el país se evalúa ANTES que el
alcance. Un Gerente de Marca de RD con alcance de línea ve su línea EN RD, no esa
línea en todos los países. Al revés, un usuario podría alcanzar operaciones de
países que no le corresponden con solo pertenecer a una línea homónima.

Necesita PostgreSQL real: `paises_visibles`/`lineas_de_usuario`/`rm_ids_visibles`
consultan `FACT_UsuarioPais`/`DIM_GerenteLinea`/`DIM_RM` con SQLAlchemy encadenado,
no con dobles de prueba.
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.authz.constantes import Alcance, alcance_min
from app.core.authz import scope
from app.db.database import Base
from app.models import dimensiones, usuario  # noqa: F401 — registran las tablas en Base.metadata
from app.models.alcance import GerenteLinea, UsuarioPais
from app.models.dimensiones import Gerente, Linea, Pais, RepresentanteMedico
from app.models.usuario import Rol, Usuario

BD_PRUEBA = "vista_test_alcance_scope"


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
        # `Base.metadata` es compartido por todo el proceso de pytest: al correr la
        # suite completa, otros archivos de test ya importaron modelos de otros
        # esquemas (Audit, DW, Visita, etc.) y quedan registrados aquí también,
        # aunque este archivo solo use Config/Security. Crear todos los esquemas
        # conocidos evita que `create_all` truene por un esquema faltante — mismo
        # patrón que `tests/test_medicos_top.py`.
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
    for tabla in ('"Security"."DIM_Usuario"', '"Config"."DIM_GerenteLinea"',
                  '"Config"."DIM_RM"', '"Config"."DIM_Gerente"',
                  '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """País DO y GT; líneas A y B en DO, línea A en GT; dos gerentes de distrito en
    DO sobre la línea A; un gerente de marca de DO con la línea A asignada en
    `DIM_GerenteLinea`; RM en cada combinación; y dos usuarios — uno sin filas en
    `FACT_UsuarioPais` y otro con `{GT, HN}` (HN no existe como país: no hace
    falta para probar el filtro, que solo compara códigos)."""
    do = Pais(codigo="DO", nombre="República Dominicana")
    gt = Pais(codigo="GT", nombre="Guatemala")
    db.add_all([do, gt])
    db.flush()

    linea_a_do = Linea(pais_codigo="DO", codigo="A", nombre="Línea A")
    linea_b_do = Linea(pais_codigo="DO", codigo="B", nombre="Línea B")
    linea_a_gt = Linea(pais_codigo="GT", codigo="A", nombre="Línea A")
    db.add_all([linea_a_do, linea_b_do, linea_a_gt])
    db.flush()

    gd1 = Gerente(pais_codigo="DO", codigo="GD01", nombre="GD Uno",
                  linea_id=linea_a_do.id, tipo="DISTRITO")
    gd2 = Gerente(pais_codigo="DO", codigo="GD02", nombre="GD Dos",
                  linea_id=linea_a_do.id, tipo="DISTRITO")
    gm_do = Gerente(pais_codigo="DO", codigo="GM01", nombre="Gerente de Marca DO",
                    linea_id=linea_a_do.id, tipo="MARCA")
    db.add_all([gd1, gd2, gm_do])
    db.flush()

    db.add(GerenteLinea(gerente_id=gm_do.id, linea_id=linea_a_do.id))
    db.flush()

    rm_linea_a_distrito_1 = RepresentanteMedico(
        pais_codigo="DO", linea_id=linea_a_do.id, gerente_id=gd1.id,
        codigo="RM01", nombre="RM Linea A Distrito 1")
    rm_linea_a_distrito_2 = RepresentanteMedico(
        pais_codigo="DO", linea_id=linea_a_do.id, gerente_id=gd2.id,
        codigo="RM02", nombre="RM Linea A Distrito 2")
    rm_linea_b = RepresentanteMedico(
        pais_codigo="DO", linea_id=linea_b_do.id, gerente_id=gd1.id,
        codigo="RM03", nombre="RM Linea B")
    rm_linea_a_guatemala = RepresentanteMedico(
        pais_codigo="GT", linea_id=linea_a_gt.id, gerente_id=None,
        codigo="RM04", nombre="RM Linea A Guatemala")
    db.add_all([rm_linea_a_distrito_1, rm_linea_a_distrito_2, rm_linea_b,
                rm_linea_a_guatemala])
    db.flush()

    usuario_sin_paises = Usuario(
        username="sin_paises", hashed_password="x", nombre_completo="Sin Países",
        rol=Rol.ADMIN)
    usuario_gt_hn = Usuario(
        username="gt_hn", hashed_password="x", nombre_completo="GT y HN",
        rol=Rol.ADMIN)
    gerente_marca_do = Usuario(
        username="gerente_marca_do", hashed_password="x", nombre_completo="Gerente de Marca DO",
        rol=Rol.GERENTE_MARCA, pais_codigo="DO", gerente_id=gm_do.id)
    db.add_all([usuario_sin_paises, usuario_gt_hn, gerente_marca_do])
    db.flush()

    db.add_all([
        UsuarioPais(usuario_id=usuario_gt_hn.id, pais_codigo="GT"),
        UsuarioPais(usuario_id=usuario_gt_hn.id, pais_codigo="HN"),
    ])
    db.commit()

    return {
        "usuario_sin_paises": usuario_sin_paises,
        "usuario_gt_hn": usuario_gt_hn,
        "gerente_marca_do": gerente_marca_do,
        "rm_linea_a_distrito_1": rm_linea_a_distrito_1,
        "rm_linea_a_distrito_2": rm_linea_a_distrito_2,
        "rm_linea_b": rm_linea_b,
        "rm_linea_a_guatemala": rm_linea_a_guatemala,
    }


def test_linea_es_mas_amplio_que_equipo_y_menos_que_todo():
    """`alcance_min` capa el export por la lectura; si LINEA quedara fuera del
    orden, la comparación daría KeyError en tiempo de ejecución."""
    assert alcance_min(Alcance.LINEA, Alcance.ALL) == Alcance.LINEA
    assert alcance_min(Alcance.LINEA, Alcance.TEAM) == Alcance.TEAM


def test_sin_filas_de_pais_el_usuario_ve_todos(db, escenario):
    u = escenario["usuario_sin_paises"]
    assert scope.paises_visibles(db, u) is None


def test_con_filas_el_usuario_ve_solo_esos(db, escenario):
    u = escenario["usuario_gt_hn"]
    assert scope.paises_visibles(db, u) == {"GT", "HN"}


def test_alcance_linea_ve_los_rm_de_su_linea_en_todos_los_distritos(db, escenario):
    """El Gerente de Marca ve su línea completa, no solo el equipo de un gerente."""
    u = escenario["gerente_marca_do"]
    ids = scope.rm_ids_visibles(db, u, Alcance.LINEA)
    assert escenario["rm_linea_a_distrito_1"].id in ids
    assert escenario["rm_linea_a_distrito_2"].id in ids
    assert escenario["rm_linea_b"].id not in ids


def test_el_pais_se_aplica_antes_que_la_linea(db, escenario):
    """EL TEST QUE DEFINE EL DISEÑO: el Gerente de Marca de RD NO ve al RM de su
    misma línea en Guatemala."""
    u = escenario["gerente_marca_do"]
    ids = scope.rm_ids_visibles(db, u, Alcance.LINEA)
    assert escenario["rm_linea_a_guatemala"].id not in ids


def test_el_pais_tambien_acota_el_alcance_total(db, escenario):
    """ALL ya no significa 'sin filtro' para quien tiene países asignados."""
    u = escenario["usuario_gt_hn"]
    ids = scope.rm_ids_visibles(db, u, Alcance.ALL)
    assert ids is not None, "con países asignados, ALL debe filtrar"
    assert escenario["rm_linea_a_guatemala"].id in ids
    assert escenario["rm_linea_a_distrito_1"].id not in ids   # es de RD


def test_sin_paises_asignados_todo_sigue_igual(db, escenario):
    """Compatibilidad: quien no tiene países conserva el comportamiento de hoy."""
    u = escenario["usuario_sin_paises"]
    assert scope.rm_ids_visibles(db, u, Alcance.ALL) is None
