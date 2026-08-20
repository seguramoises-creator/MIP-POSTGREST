"""Aviso por correo de los lotes que Mallén deja en RECIBIDO.

Cubre el punto ciego del circuito: Mallén escribe en `ext` y el lote espera; el
sistema no integra solo NI avisaba, así que un lote subido un viernes por la
noche esperaba hasta que alguien abría la pantalla.

EL TEST QUE DEFINE EL DISEÑO es `test_no_reavisa_el_mismo_lote`. Sin memoria del
aviso, el correo se repetiría en CADA pase del trabajo programado —cada 30 min—
porque el lote sigue en RECIBIDO hasta que alguien lo valida: «hay algo
pendiente» seguiría siendo cierto indefinidamente. Un aviso que llega cada media
hora se filtra a la papelera, y entonces el aviso que sí importa tampoco se lee.

El envío se sustituye por un doble que solo cuenta: aquí se prueba la LÓGICA de a
quién y cuándo se avisa, no SMTP.

Necesita PostgreSQL real: el servicio consulta `ext` y `Audit` en la misma
transacción.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import dimensiones, usuario  # noqa: F401 — registran las tablas
from app.models import integracion_ext  # noqa: F401
from app.models.integracion_ext import ExtControlCarga
from app.models.integracion_hallazgo import IntegracionAvisoLote
from app.models.usuario import Rol, Usuario
from app.services import notification_service

BD_PRUEBA = "vista_test_aviso_lotes"


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
        pytest.skip(f"sin PostgreSQL alcanzable: {exc}")
    eng = create_engine(_url(BD_PRUEBA))
    with eng.begin() as cx:
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
    for t in ('"Audit"."IntegracionAvisoLote"', 'ext.controlcarga', 'ext.dimpais',
              '"Security"."DIM_Usuario"'):
        s.execute(text(f"DELETE FROM {t}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def enviados(monkeypatch):
    """Doble del envío: cuenta destinatarios sin tocar SMTP."""
    caja: list[str] = []
    monkeypatch.setattr(notification_service, "_habilitado", lambda: True)
    monkeypatch.setattr(notification_service, "_enviar",
                        lambda destinatario, asunto, cuerpo: (caja.append(destinatario), True)[1])
    return caja


def _pais(db):
    # Por el ORM y no con SQL a mano: `ext` es contrato de un tercero y sus columnas
    # obligatorias no son adivinables desde el test.
    from app.models.integracion_ext import ExtDimPais
    if not db.get(ExtDimPais, "DO"):
        db.add(ExtDimPais(pais_codigo="DO", nombre="RD", activo=True))
    db.commit()


def _lote(db, lote_id: int, estado: str = "RECIBIDO"):
    db.add(ExtControlCarga(lote_id=lote_id, sistema_origen="SFA", modulo="VISITAS",
                           pais_codigo="DO", ciclo_codigo="C09", periodo="2026-09",
                           fecha_extraccion=datetime(2026, 9, 1),
                           fecha_recepcion=datetime(2026, 9, 1, 8, 0),
                           filas_enviadas=100, estado=estado))
    db.commit()


def _ti(db, username: str, rol=Rol.GERENTE_PRODUCTIVIDAD):
    db.add(Usuario(username=username, email=f"{username}@x.com", hashed_password="x",
                   nombre_completo=username, rol=rol, activo=True))
    db.commit()


def test_avisa_un_lote_recibido(db, enviados):
    _pais(db); _lote(db, 1); _ti(db, "ti1")
    assert notification_service.notificar_lotes_recibidos(db) == 1
    assert enviados == ["ti1@x.com"]


def test_no_reavisa_el_mismo_lote(db, enviados):
    """EL TEST QUE DEFINE EL DISEÑO. El lote sigue en RECIBIDO tras el primer aviso
    —solo sale de ahí al validarlo—, así que sin memoria el correo se repetiría en
    cada pase del trabajo programado."""
    _pais(db); _lote(db, 1); _ti(db, "ti1")
    assert notification_service.notificar_lotes_recibidos(db) == 1
    enviados.clear()
    assert notification_service.notificar_lotes_recibidos(db) == 0
    assert enviados == []


def test_avisa_solo_del_lote_nuevo(db, enviados):
    _pais(db); _lote(db, 1); _ti(db, "ti1")
    notification_service.notificar_lotes_recibidos(db)
    enviados.clear()
    _lote(db, 2)
    assert notification_service.notificar_lotes_recibidos(db) == 1
    assert {r[0] for r in db.query(IntegracionAvisoLote.lote_id).all()} == {1, 2}


def test_ignora_los_ya_validados(db, enviados):
    _pais(db); _lote(db, 1, estado="VALIDADO"); _lote(db, 2, estado="INTEGRADO")
    _ti(db, "ti1")
    assert notification_service.notificar_lotes_recibidos(db) == 0


def test_sin_destinatarios_no_marca_como_avisado(db, enviados):
    """Sin nadie a quien avisar NO se marca el lote: en cuanto exista un
    destinatario, el siguiente pase debe mandar el correo. Marcarlo aquí dejaría
    ese lote silenciado para siempre."""
    _pais(db); _lote(db, 1)
    assert notification_service.notificar_lotes_recibidos(db) == 0
    assert db.query(IntegracionAvisoLote).count() == 0
    _ti(db, "ti1")
    assert notification_service.notificar_lotes_recibidos(db) == 1


def test_avisa_a_admin_y_gerente_productividad(db, enviados):
    _pais(db); _lote(db, 1)
    _ti(db, "adm", Rol.ADMIN); _ti(db, "prod", Rol.GERENTE_PRODUCTIVIDAD)
    _ti(db, "rm", Rol.REPRESENTANTE_MEDICO)   # no es de TI: no debe recibirlo
    assert notification_service.notificar_lotes_recibidos(db) == 2
    assert set(enviados) == {"adm@x.com", "prod@x.com"}


def test_no_hace_nada_sin_smtp(db, monkeypatch):
    monkeypatch.setattr(notification_service, "_habilitado", lambda: False)
    _pais(db); _lote(db, 1); _ti(db, "ti1")
    assert notification_service.notificar_lotes_recibidos(db) == 0
    assert db.query(IntegracionAvisoLote).count() == 0
