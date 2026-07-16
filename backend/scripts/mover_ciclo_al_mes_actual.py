"""
Mueve el ciclo ABIERTO de un país (o de todos) a la ventana del MES EN CURSO:
  fecha_inicio = día 1 del mes actual
  fecha_fin    = último día del mes actual
  dias_laborables = NETWORKDAYS(inicio, fin) menos feriados del país (recalculado)

Así el ciclo abierto vuelve a estar VIGENTE (contiene la fecha de hoy) y los dashboards
(cobertura, ritmo diario requerido, proyección) vuelven a tener días hábiles restantes.
Todas las informaciones ya ligadas a ese ciclo (visitas, planeación, etc.) permanecen
en él — no se mueven registros, solo se corrige la ventana de fechas del ciclo.

Uso (dentro del contenedor backend o con el venv):
    python scripts/mover_ciclo_al_mes_actual.py            # todos los países con ciclo abierto
    python scripts/mover_ciclo_al_mes_actual.py --pais DO  # solo un país
    python scripts/mover_ciclo_al_mes_actual.py --dry-run  # muestra qué haría, sin escribir

Con Docker:
    docker compose exec -e PYTHONPATH=/app backend python scripts/mover_ciclo_al_mes_actual.py --dry-run
"""
import argparse
import calendar
import os
import sys
from datetime import date, timedelta

# Permite `python scripts/mover_ciclo_al_mes_actual.py` desde backend/ sin PYTHONPATH.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Registrar todas las tablas/FKs antes de abrir sesión.
import app.models.dimensiones  # noqa: F401
import app.models.hechos       # noqa: F401
import app.models.usuario      # noqa: F401
from app.db.database import SessionLocal
from app.models.dimensiones import Ciclo, Feriado


def _networkdays(db, pais_codigo: str, inicio: date, fin: date) -> int:
    if inicio is None or fin is None or fin < inicio:
        return 0
    feriados = {
        f.fecha for f in db.query(Feriado).filter(
            Feriado.pais_codigo == pais_codigo, Feriado.activo == True,  # noqa: E712
            Feriado.fecha >= inicio, Feriado.fecha <= fin).all()
        if f.fecha.weekday() < 5
    }
    total, d = 0, inicio
    while d <= fin:
        if d.weekday() < 5 and d not in feriados:
            total += 1
        d += timedelta(days=1)
    return total


def _ciclo_abierto(db, pais_codigo: str):
    """El ciclo abierto (cerrado=False, activo) más reciente por (anio, numero)."""
    abiertos = (db.query(Ciclo)
                .filter(Ciclo.activo == True, Ciclo.cerrado == False,  # noqa: E712
                        Ciclo.pais_codigo == pais_codigo)
                .all())
    if not abiertos:
        return None
    return max(abiertos, key=lambda c: (c.anio, c.numero))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pais", default=None, help="Código de país (ej. DO). Por defecto: todos.")
    ap.add_argument("--dry-run", action="store_true", help="No escribe; solo muestra.")
    args = ap.parse_args()

    hoy = date.today()
    primero = hoy.replace(day=1)
    ultimo = hoy.replace(day=calendar.monthrange(hoy.year, hoy.month)[1])

    db = SessionLocal()
    try:
        if args.pais:
            paises = [args.pais]
        else:
            paises = [row[0] for row in db.query(Ciclo.pais_codigo).distinct().all()]

        for pais in paises:
            c = _ciclo_abierto(db, pais)
            if not c:
                print(f"[{pais}] sin ciclo abierto — omitido")
                continue
            dh = _networkdays(db, pais, primero, ultimo)
            print(f"[{pais}] ciclo '{c.nombre}' (id={c.id}): "
                  f"{c.fecha_inicio}..{c.fecha_fin} (dias={c.dias_laborables})  ->  "
                  f"{primero}..{ultimo} (dias={dh})")
            if not args.dry_run:
                c.fecha_inicio = primero
                c.fecha_fin = ultimo
                c.dias_laborables = dh
        if args.dry_run:
            print("\n(dry-run: no se escribió nada)")
        else:
            db.commit()
            print("\nListo. Ciclos abiertos movidos al mes en curso.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
