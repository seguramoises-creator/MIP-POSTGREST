"""Asignación de países y líneas. Solo ADMIN.

`PUT` reemplaza el conjunto completo en vez de añadir: es lo que permite quitar un
país. Con un endpoint que solo agrega, revocar acceso exigiría un DELETE aparte
que se olvida — y el permiso de más no da ningún error.
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import dimensiones, usuario  # noqa: F401 — registran las tablas en Base.metadata
from app.models.alcance import GerenteLinea, UsuarioPais
from app.models.dimensiones import Gerente, Linea, Pais
from app.models.usuario import Rol, Usuario
from app.services import alcance_service

BD_PRUEBA = "vista_test_alcance_asignacion"


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
        # patrón que `tests/test_alcance_scope.py`.
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
                  '"Config"."DIM_Gerente"', '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    do = Pais(codigo="DO", nombre="República Dominicana")
    gt = Pais(codigo="GT", nombre="Guatemala")
    db.add_all([do, gt])
    db.flush()

    linea_a = Linea(pais_codigo="DO", codigo="A", nombre="Línea A")
    linea_b = Linea(pais_codigo="DO", codigo="B", nombre="Línea B")
    db.add_all([linea_a, linea_b])
    db.flush()

    gerente_marca = Gerente(pais_codigo="DO", codigo="GM01", nombre="Gerente de Marca DO",
                            linea_id=linea_a.id, tipo="MARCA")
    db.add(gerente_marca)
    db.flush()

    usuario_gt_hn = Usuario(
        username="gt_hn", hashed_password="x", nombre_completo="GT y HN",
        rol=Rol.ADMIN)
    db.add(usuario_gt_hn)
    db.commit()

    return {
        "usuario_gt_hn": usuario_gt_hn,
        "gerente_marca": gerente_marca,
        "linea_a": linea_a,
        "linea_b": linea_b,
    }


def test_asignar_paises_reemplaza_el_conjunto(db, escenario):
    u = escenario["usuario_gt_hn"]
    alcance_service.fijar_paises(db, u.id, ["DO"])
    db.commit()
    assert alcance_service.paises_de(db, u.id) == {"DO"}


def test_dejar_la_lista_vacia_devuelve_el_acceso_total(db, escenario):
    """Vaciar = "todos los países", según el spec §3. Es la forma de revertir."""
    u = escenario["usuario_gt_hn"]
    alcance_service.fijar_paises(db, u.id, [])
    db.commit()
    assert alcance_service.paises_de(db, u.id) == set()


def test_asignar_dos_veces_el_mismo_pais_no_duplica(db, escenario):
    u = escenario["usuario_gt_hn"]
    alcance_service.fijar_paises(db, u.id, ["GT", "GT", "HN"])
    db.commit()
    assert alcance_service.paises_de(db, u.id) == {"GT", "HN"}


def test_asignar_lineas_reemplaza_el_conjunto(db, escenario):
    g = escenario["gerente_marca"]
    alcance_service.fijar_lineas(db, g.id, [escenario["linea_b"].id])
    db.commit()
    assert alcance_service.lineas_de(db, g.id) == {escenario["linea_b"].id}
