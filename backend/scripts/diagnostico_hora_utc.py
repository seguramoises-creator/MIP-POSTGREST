"""¿Esta instalación guardó las fechas en UTC o en hora local?

Hasta el 2026-09-10 el código escribía `datetime.now(timezone.utc)` —un valor
CONSCIENTE— en columnas `TIMESTAMP WITHOUT TIME ZONE`. PostgreSQL convierte ese valor
a la zona de la SESIÓN y descarta el huso, así que lo que quedaba almacenado no lo
decidía el código sino la configuración de la máquina:

  * servidor en `Etc/UTC`   → se guardó UTC          → nada que hacer
  * servidor en otra zona   → se guardó hora LOCAL   → las filas viejas están corridas

Desde entonces `app/db/database.py` fuerza `timezone=UTC` en cada conexión, de modo que
lo nuevo siempre es UTC. Este script sirve para saber qué pasó con lo VIEJO, y para
corregirlo si hiciera falta.

    python scripts/diagnostico_hora_utc.py                  # solo diagnostica
    python scripts/diagnostico_hora_utc.py --corregir       # simula el arreglo
    python scripts/diagnostico_hora_utc.py --corregir --aplicar

El arreglo NO adivina: usa la zona por defecto del servidor —la misma que causó el
desvío— y solo toca las filas anteriores al corte. `--aplicar` es obligatorio para
escribir; sin él únicamente enseña lo que haría.

ATENCIÓN AL ALCANCE. El desvío afecta solo a las filas que escribió la APLICACIÓN con
la hora del servidor. Una fila cargada desde Excel o sembrada por un script trae su
propia fecha, ya correcta, y moverla la estropearía — y nada en la fila distingue un
caso del otro. Por eso hay `--desde`: acota la ventana a lo que se sabe capturado por
la app. Sin `--desde` se mueve TODO lo anterior al corte; úsalo solo si consta que esa
tabla no tiene filas importadas.
"""
import argparse
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402

# (esquema, tabla, columnas de fecha) del módulo Visita, que es donde el desvío tiene
# consecuencias de negocio: el "día" del visitador se compara contra estas columnas.
TABLAS = [
    ("Visita", "FactVisita", ["fecha_hora"]),
    ("Visita", "FactVisitaFarmacia", ["fecha_hora"]),
]

# El commit que fuerza `timezone=UTC` en la conexión. Lo escrito a partir de aquí ya
# es UTC de verdad; lo anterior es lo que puede estar corrido.
CORTE = datetime(2026, 9, 10, 4, 0, 0)


def zona_del_servidor() -> tuple[str, str]:
    """La zona por DEFECTO del servidor: `(zona, de dónde sale)`.

    Se abre una conexión CRUDA a propósito, sin la opción que estamos comprobando. Por
    la sesión de la aplicación no vale preguntarlo: ni `SHOW timezone` ni el `reset_val`
    de `pg_settings` dicen la verdad, porque los dos devuelven el `-c timezone=UTC` que
    esa misma conexión acaba de imponer (`source='client'`). Medido: por la sesión de la
    app salía «UTC, nada que corregir»; por una conexión limpia, `America/La_Paz` desde
    el fichero de configuración — con 900 filas efectivamente corridas. Un diagnóstico
    que se pregunta a sí mismo siempre se aprueba."""
    import psycopg2
    from app.core.config import settings
    con = psycopg2.connect(host=settings.DB_SERVER, port=settings.DB_PORT,
                           dbname=settings.DB_NAME, user=settings.DB_USER,
                           password=settings.DB_PASSWORD)
    try:
        cur = con.cursor()
        cur.execute("SELECT reset_val, source FROM pg_settings WHERE name = 'TimeZone'")
        zona, origen = cur.fetchone()
        return zona or "?", origen or "?"
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corregir", action="store_true",
                    help="propone mover las filas anteriores al corte")
    ap.add_argument("--aplicar", action="store_true",
                    help="escribe de verdad (sin esto, solo simula)")
    ap.add_argument("--desde-zona", default=None,
                    help="zona en la que se guardó (por defecto, la del servidor)")
    ap.add_argument("--desde", default=None, metavar="AAAA-MM-DD",
                    help="mueve solo desde esta fecha (deja fuera lo importado/sembrado)")
    args = ap.parse_args()
    desde = datetime.fromisoformat(args.desde) if args.desde else None

    db = SessionLocal()
    servidor, origen_zona = zona_del_servidor()
    sesion = db.execute(text("SHOW timezone")).scalar()
    print(f"Zona por defecto del servidor : {servidor}   (según {origen_zona}, "
          f"leída por conexión limpia)")
    print(f"Zona de esta sesión           : {sesion}   (la fuerza la aplicación)")

    origen = args.desde_zona or servidor
    try:
        tz = ZoneInfo(origen)
    except Exception:
        print(f"\nNo se reconoce la zona '{origen}'. Indícala con --desde-zona.")
        return 2

    desfase = tz.utcoffset(datetime.now())
    if desfase.total_seconds() == 0:
        print("\nLas fechas viejas ya están en UTC: no hay nada que corregir.")
        return 0

    horas = desfase.total_seconds() / 3600
    # En minutos, no en horas: `make_interval(hours => ...)` solo acepta enteros y hay
    # husos a media hora (Venezuela estuvo en UTC-4:30). Con horas float el UPDATE
    # reventaba con un error de tipos — mejor eso que redondear en silencio.
    minutos = int(desfase.total_seconds() // 60)
    print(f"\nLas filas anteriores a {CORTE} se guardaron en {origen} (UTC{horas:+g}).")
    print(f"Para dejarlas en UTC hay que SUMARLES {-horas:+g} horas.\n")

    if desde is None:
        print("Sin --desde: entran TODAS las filas anteriores al corte, incluidas las "
              "que se hayan importado con su propia fecha.\n")
    else:
        print(f"Acotado a las filas desde {desde}.\n")

    filtro = f'"{{col}}" < :corte' + (' AND "{col}" >= :desde' if desde else '')
    params = {"corte": CORTE} | ({"desde": desde} if desde else {})

    total = 0
    for esquema, tabla, columnas in TABLAS:
        for col in columnas:
            donde = filtro.format(col=col)
            n = db.execute(text(
                f'SELECT count(*) FROM "{esquema}"."{tabla}" WHERE {donde}'
            ), params).scalar()
            total += n
            print(f"  {esquema}.{tabla}.{col}: {n} filas por mover")
            if args.corregir and args.aplicar and n:
                db.execute(text(
                    f'UPDATE "{esquema}"."{tabla}" '
                    f'SET "{col}" = "{col}" - make_interval(mins => :m) '
                    f'WHERE {donde}'
                ), params | {"m": minutos})

    if args.corregir and args.aplicar:
        db.commit()
        print(f"\nAplicado: {total} filas movidas a UTC.")
    elif args.corregir:
        print(f"\nSimulación: se moverían {total} filas. Añade --aplicar para escribir.")
    else:
        print("\nAñade --corregir para ver el arreglo (y --aplicar para ejecutarlo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
