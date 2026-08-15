"""La frontera de país, de filtro a límite real.

El test `test_hoy_un_gerente_de_rd_puede_ver_guatemala` documenta el agujero que
este trabajo cierra: ANTES del cambio pasa, porque el backend nunca imponía el
país. Que falle tras implementar es la señal de que la frontera existe.

Necesita PostgreSQL real: `exigir_pais` delega en `scope.paises_visibles`, que
consulta `FACT_UsuarioPais` con SQLAlchemy encadenado, no con dobles de prueba
— mismo motivo que `test_alcance_scope.py`.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.authz import paises
from app.db.database import Base
from app.models import dimensiones, usuario  # noqa: F401 — registran las tablas en Base.metadata
from app.models.alcance import UsuarioPais
from app.models.dimensiones import Pais
from app.models.usuario import Rol, Usuario

BD_PRUEBA = "vista_test_alcance_frontera_pais"


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
        # patrón que `test_alcance_scope.py`.
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
    for tabla in ('"Security"."FACT_UsuarioPais"', '"Security"."DIM_Usuario"',
                  '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """Un usuario sin filas en `FACT_UsuarioPais` (histórico, ve todos los países)
    y otro con `{GT, HN}` asignados (HN no existe como país: no hace falta para
    probar el filtro, que solo compara códigos)."""
    do = Pais(codigo="DO", nombre="República Dominicana")
    gt = Pais(codigo="GT", nombre="Guatemala")
    db.add_all([do, gt])
    db.flush()

    usuario_sin_paises = Usuario(
        username="sin_paises_frontera", hashed_password="x",
        nombre_completo="Sin Países", rol=Rol.ADMIN)
    usuario_gt_hn = Usuario(
        username="gt_hn_frontera", hashed_password="x",
        nombre_completo="GT y HN", rol=Rol.ADMIN)
    db.add_all([usuario_sin_paises, usuario_gt_hn])
    db.flush()

    db.add_all([
        UsuarioPais(usuario_id=usuario_gt_hn.id, pais_codigo="GT"),
        UsuarioPais(usuario_id=usuario_gt_hn.id, pais_codigo="HN"),
    ])
    db.commit()

    return {
        "usuario_sin_paises": usuario_sin_paises,
        "usuario_gt_hn": usuario_gt_hn,
    }


def test_sin_paises_asignados_se_permite_cualquiera(db, escenario):
    """Compatibilidad: los 37 usuarios existentes no tienen filas y deben seguir igual."""
    paises.exigir_pais(db, escenario["usuario_sin_paises"], "DO")   # no lanza


def test_con_paises_asignados_se_permite_uno_de_ellos(db, escenario):
    paises.exigir_pais(db, escenario["usuario_gt_hn"], "GT")        # no lanza


def test_con_paises_asignados_se_rechaza_otro(db, escenario):
    """EL TEST QUE CONVIERTE EL FILTRO EN FRONTERA."""
    with pytest.raises(HTTPException) as e:
        paises.exigir_pais(db, escenario["usuario_gt_hn"], "DO")
    assert e.value.status_code == 403


def test_pais_none_no_se_valida(db, escenario):
    """Un endpoint sin `pais_codigo` consulta todos los países que le permita su
    alcance; la restricción la aplica `rm_ids_visibles`, no este guard."""
    paises.exigir_pais(db, escenario["usuario_gt_hn"], None)        # no lanza


def test_el_rechazo_no_revela_que_paises_existen(db, escenario):
    """El mensaje no debe enumerar los países del usuario ni decir si 'XX' existe:
    sería un canal para mapear la operación desde fuera."""
    with pytest.raises(HTTPException) as e:
        paises.exigir_pais(db, escenario["usuario_gt_hn"], "XX")
    assert "GT" not in e.value.detail and "HN" not in e.value.detail
