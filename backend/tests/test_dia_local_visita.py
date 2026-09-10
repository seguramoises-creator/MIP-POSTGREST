"""El día del visitador no es el día UTC.

RD es UTC−4: su día va de las 04:00 UTC a las 04:00 UTC del día siguiente, así que
sus dos extremos caen en fechas UTC DISTINTAS. Todo lo que pregunte «¿qué hizo hoy?»
tiene que trabajar con ese rango; preguntarlo con la fecha UTC no da error, da un
número creíble — y falla justo de noche, que es cuando el visitador cierra su jornada.

Medido en el teléfono el 2026-09-09 a las 23:49 de RD: la visita a farmacia recién
registrada no contaba como de hoy y la tarjeta del móvil enseñaba 0.
"""
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from app.core.tiempo import ventana_dia_local, zona_horaria, hoy_local
from app.services import visita_registro_service as vrs

RD = ZoneInfo("America/Santo_Domingo")


def _db_con_zona(nombre):
    """`db` de mentira cuyo `DIM_Pais.zona_horaria` responde `nombre`."""
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = nombre
    return db


# ── La ventana del día local ────────────────────────────────────────────────

def test_ventana_del_dia_de_rd_va_de_las_4_a_las_4_utc():
    db = _db_con_zona("America/Santo_Domingo")
    dia, inicio, fin = ventana_dia_local(db, "DO", date(2026, 9, 9))

    assert dia == date(2026, 9, 9)
    # Naive: es la escala en la que están guardadas las columnas.
    assert inicio == datetime(2026, 9, 9, 4, 0)
    assert fin == datetime(2026, 9, 10, 4, 0)
    assert inicio.tzinfo is None and fin.tzinfo is None
    assert fin - inicio == timedelta(days=1)


def test_la_ventana_cubre_las_dos_puntas_del_dia_local():
    """El caso que se rompía: madrugada y noche del MISMO día local caen en dos
    fechas UTC distintas, y con la fecha UTC solo podía acertarse una."""
    db = _db_con_zona("America/Santo_Domingo")
    dia = date(2026, 9, 9)
    _, inicio, fin = ventana_dia_local(db, "DO", dia)

    def utc_naive(h, m):
        return datetime.combine(dia, time(h, m), tzinfo=RD).astimezone(timezone.utc).replace(tzinfo=None)

    madrugada, noche = utc_naive(0, 30), utc_naive(23, 30)
    assert madrugada.date() != noche.date(), "sin esto el caso no prueba nada"
    assert inicio <= madrugada < fin
    assert inicio <= noche < fin

    # Y el control por el otro lado: las 23:30 del día ANTERIOR quedan fuera.
    anoche = (datetime.combine(dia - timedelta(days=1), time(23, 30), tzinfo=RD)
              .astimezone(timezone.utc).replace(tzinfo=None))
    assert not (inicio <= anoche < fin)


def test_sin_zona_configurada_se_comporta_como_utc():
    """Comportamiento histórico: un país sin `zona_horaria` no se inventa un huso."""
    db = _db_con_zona(None)
    _, inicio, fin = ventana_dia_local(db, "XX", date(2026, 9, 9))
    assert inicio == datetime(2026, 9, 9, 0, 0)
    assert fin == datetime(2026, 9, 10, 0, 0)


def test_zona_invalida_cae_a_utc_y_no_revienta():
    assert zona_horaria(_db_con_zona("Marte/Olympus"), "XX") == ZoneInfo("UTC")


def test_hoy_local_de_rd_puede_ir_un_dia_por_detras_de_utc():
    """No se compara contra un valor fijo (dependería de la hora de la corrida):
    se comprueba la relación, que es lo que el negocio necesita."""
    db = _db_con_zona("America/Santo_Domingo")
    hoy_rd = hoy_local(db, "DO")
    hoy_utc = datetime.now(timezone.utc).date()
    assert hoy_rd in (hoy_utc, hoy_utc - timedelta(days=1))


# ── Lo guardado es UTC; lo enseñado es local ────────────────────────────────

def test_lo_que_se_guarda_es_utc_sin_huso():
    """Con huso, PostgreSQL lo convertiría a la zona de la SESIÓN al meterlo en una
    columna sin zona: lo almacenado dependería de la máquina y no del código."""
    ahora = vrs._ahora_utc()
    assert ahora.tzinfo is None
    # Es UTC, no la hora local del equipo (que es lo que se guardaba por accidente).
    assert abs((ahora - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()) < 5


def test_el_feed_devuelve_la_hora_en_local():
    """El visitador solo reconoce como suya la hora de su reloj."""
    db = _db_con_zona("America/Santo_Domingo")
    guardado = datetime(2026, 9, 10, 3, 49, 9)          # 23:49 del 9 en RD
    local = vrs._a_local(db, "DO", guardado)
    assert local.replace(tzinfo=None) == datetime(2026, 9, 9, 23, 49, 9)


def test_a_local_de_none_es_none():
    assert vrs._a_local(_db_con_zona("America/Santo_Domingo"), "DO", None) is None
