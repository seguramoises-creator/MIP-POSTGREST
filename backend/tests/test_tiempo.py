"""Tests de `app.core.tiempo`: el día operativo es el día LOCAL del país, no el día UTC.

El caso que motivó el módulo: RD es UTC−4, así que el día UTC cambia a las 8 p.m. locales.
Un GD que registraba visitas por la tarde y cerraba su hoja de coaching de noche quedaba
bloqueado, porque sus visitas contaban como "ayer" para un corte hecho en UTC.
"""
from datetime import date, datetime
from unittest.mock import MagicMock

from app.core.tiempo import UTC, hoy_local, ventana_dia_local, zona_horaria


def _db(tz: str | None):
    """Sesión falsa: `db.query(Pais.zona_horaria).filter(...).scalar()` → tz."""
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = tz
    return db


# ── zona_horaria ──────────────────────────────────────────────────────────────

def test_lee_la_zona_horaria_configurada_del_pais():
    assert str(zona_horaria(_db("America/Santo_Domingo"), "DO")) == "America/Santo_Domingo"


def test_sin_zona_horaria_configurada_cae_a_utc():
    assert zona_horaria(_db(None), "DO") is UTC
    assert zona_horaria(_db("   "), "DO") is UTC


def test_zona_horaria_invalida_cae_a_utc_sin_reventar():
    # Un dato malo en DIM_Pais no puede tumbar el registro de coaching.
    assert zona_horaria(_db("Marte/Olympus"), "DO") is UTC


def test_sin_pais_cae_a_utc():
    assert zona_horaria(_db("America/Santo_Domingo"), None) is UTC


# ── ventana_dia_local ─────────────────────────────────────────────────────────

def test_dia_local_de_rd_va_de_4am_a_4am_utc():
    """RD (UTC−4): el 15-jul local es [15-jul 04:00 UTC, 16-jul 04:00 UTC)."""
    dia, desde, hasta = ventana_dia_local(_db("America/Santo_Domingo"), "DO", date(2026, 7, 15))
    assert dia == date(2026, 7, 15)
    assert desde == datetime(2026, 7, 15, 4, 0)
    assert hasta == datetime(2026, 7, 16, 4, 0)


def test_visita_de_las_11pm_local_cuenta_en_su_propio_dia():
    """EL BUG: 23:00 local del 15-jul se guarda como 03:00 UTC del 16-jul. Con el corte
    viejo (`date(fecha_hora) == hoy_utc`) caía en el 16; con la ventana local cae en el 15,
    que es el día en que el GD realmente hizo campo."""
    _, desde, hasta = ventana_dia_local(_db("America/Santo_Domingo"), "DO", date(2026, 7, 15))
    visita_11pm_local = datetime(2026, 7, 16, 3, 0)  # = 15-jul 23:00 en RD, guardada en UTC
    assert desde <= visita_11pm_local < hasta


def test_visita_de_medianoche_utc_no_se_adelanta_de_dia():
    """00:30 UTC del 16-jul = 20:30 local del 15-jul → sigue siendo el día 15."""
    _, desde, hasta = ventana_dia_local(_db("America/Santo_Domingo"), "DO", date(2026, 7, 15))
    assert desde <= datetime(2026, 7, 16, 0, 30) < hasta


def test_la_ventana_es_semiabierta_no_solapa_dias():
    _, _, fin_15 = ventana_dia_local(_db("America/Santo_Domingo"), "DO", date(2026, 7, 15))
    _, ini_16, _ = ventana_dia_local(_db("America/Santo_Domingo"), "DO", date(2026, 7, 16))
    assert fin_15 == ini_16  # el fin de un día es el inicio del siguiente, sin huecos


def test_sin_zona_horaria_la_ventana_es_el_dia_utc():
    """Comportamiento histórico intacto para países sin zona horaria configurada."""
    _, desde, hasta = ventana_dia_local(_db(None), "XX", date(2026, 7, 15))
    assert desde == datetime(2026, 7, 15, 0, 0)
    assert hasta == datetime(2026, 7, 16, 0, 0)


def test_hoy_local_devuelve_una_fecha():
    assert isinstance(hoy_local(_db("America/Santo_Domingo"), "DO"), date)
