"""Deja a un representante listo para enseñar un ciclo completo en el servidor de demos.

Un ciclo completo necesita cuatro cosas, y en una demostración es fácil que falte una
sin que se note hasta que alguien la busca en pantalla:

  * planeación del ciclo    — a quién le toca y qué día
  * médicos en su panel     — a quién puede visitar
  * parrilla PUBLICADA      — qué productos puede promocionar y cuántas muestras lleva
  * farmacias en su panel   — dónde puede registrar una visita a farmacia

Este script comprueba las cuatro y crea las que falten. Es idempotente: correrlo dos
veces no duplica nada.

    python scripts/preparar_demo_vm.py --vm VM-4                # dice qué falta
    python scripts/preparar_demo_vm.py --vm VM-4 --aplicar

Solo siembra datos de DEMOSTRACIÓN. Los productos que crea llevan nombres inventados a
propósito: en un servidor donde se enseña la suite a un cliente, los productos
comerciales de otro cliente no pintan nada.
"""
import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402

# Productos de demostración, uno por prioridad. `meta_muestras` distinto en cada uno
# para que se vea que la parrilla PROPONE cantidades y no un número fijo.
PRODUCTOS_DEMO = [
    ("VITALEX 500", "Primera línea en su indicación; dosis única diaria.", 1, 3),
    ("CARDIOVIT 10", "Perfil de tolerancia favorable en tratamiento prolongado.", 2, 3),
    ("NUTRIVIT D3", "Complemento de mantenimiento; adherencia sencilla.", 3, 4),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vm", required=True, help="código del representante, ej. VM-4")
    ap.add_argument("--aplicar", action="store_true", help="escribe de verdad")
    args = ap.parse_args()

    db = SessionLocal()
    rm = db.execute(text(
        'SELECT id, codigo, nombre, linea_id, pais_codigo FROM "Config"."DIM_RM" '
        'WHERE codigo = :c'), {"c": args.vm}).first()
    if rm is None:
        print(f"No existe el representante {args.vm}.")
        return 2

    ciclo = db.execute(text(
        'SELECT id, nombre FROM "Config"."DIM_Ciclo" '
        'WHERE pais_codigo = :p AND cerrado = false ORDER BY anio DESC, numero DESC LIMIT 1'),
        {"p": rm.pais_codigo}).first()
    if ciclo is None:
        print(f"No hay ciclo abierto en {rm.pais_codigo}.")
        return 2

    linea = db.execute(text('SELECT nombre FROM "Config"."DIM_Linea" WHERE id = :i'),
                       {"i": rm.linea_id}).scalar()
    print(f"{rm.codigo} · {rm.nombre} · línea {rm.linea_id} ({linea}) · ciclo {ciclo.nombre}\n")

    def contar(sql, **kw):
        return db.execute(text(sql), {"vm": rm.id, "ciclo": ciclo.id,
                                      "linea": rm.linea_id, **kw}).scalar()

    plan = contar('SELECT count(*) FROM "Visita"."PlaneacionCiclo" WHERE vm_id=:vm AND ciclo_id=:ciclo')
    medicos = contar('SELECT count(*) FROM "Visita"."DIM_MedicoVisita" WHERE vm_id=:vm AND activo')
    parrilla = contar('SELECT count(*) FROM "Visita"."ParrillaPromocional" '
                      'WHERE ciclo_id=:ciclo AND linea_id=:linea AND publicada')
    farmacias = contar('SELECT count(*) FROM "Visita"."DIM_FarmaciaVisita" '
                       "WHERE vm_id=:vm AND estado_aprobacion='APROBADO'")

    for etiqueta, n in (("planeación del ciclo", plan), ("médicos en el panel", medicos),
                        ("parrilla publicada", parrilla), ("farmacias aprobadas", farmacias)):
        print(f"  {'OK   ' if n else 'FALTA'} {etiqueta}: {n}")

    if not args.aplicar:
        print("\n(simulación) No se escribió nada. Añade --aplicar.")
        return 0

    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    creado = []

    if parrilla == 0:
        for nombre, mensaje, prioridad, muestras in PRODUCTOS_DEMO:
            pid = db.execute(text(
                'SELECT id FROM "Config"."DIM_Producto" WHERE nombre = :n AND linea_id = :l'),
                {"n": nombre, "l": rm.linea_id}).scalar()
            if pid is None:
                pid = db.execute(text(
                    'INSERT INTO "Config"."DIM_Producto" (nombre, linea_id, area_terapeutica, activo) '
                    'VALUES (:n, :l, :a, true) RETURNING id'),
                    {"n": nombre, "l": rm.linea_id, "a": linea}).scalar()
            db.execute(text(
                'INSERT INTO "Visita"."ParrillaPromocional" '
                '(ciclo_id, linea_id, producto_id, producto, mensaje_clave, prioridad, '
                ' meta_muestras, activo, publicada, fecha_publicacion, fecha_creacion) '
                'VALUES (:c, :l, :pid, :p, :m, :pr, :mm, true, true, :ts, :ts)'),
                {"c": ciclo.id, "l": rm.linea_id, "pid": pid, "p": nombre, "m": mensaje,
                 "pr": prioridad, "mm": muestras, "ts": ahora})
        creado.append(f"parrilla de {len(PRODUCTOS_DEMO)} productos (publicada)")

    if farmacias == 0:
        maestros = db.execute(text(
            'SELECT id FROM "Config"."DIM_Farmacia" WHERE estado = \'ACTIVA\' ORDER BY id')).all()
        for m in maestros:
            ya = db.execute(text(
                'SELECT id FROM "Visita"."DIM_FarmaciaVisita" '
                'WHERE vm_id = :vm AND maestro_farmacia_id = :m'),
                {"vm": rm.id, "m": m.id}).scalar()
            if ya is None:
                db.execute(text(
                    'INSERT INTO "Visita"."DIM_FarmaciaVisita" '
                    '(vm_id, maestro_farmacia_id, estado_aprobacion, ciclo_alta_id, '
                    ' ciclos_sin_visita, fecha_solicitud, fecha_aprobacion) '
                    "VALUES (:vm, :m, 'APROBADO', :c, 0, :ts, :ts)"),
                    {"vm": rm.id, "m": m.id, "c": ciclo.id, "ts": ahora})
            else:
                db.execute(text(
                    'UPDATE "Visita"."DIM_FarmaciaVisita" '
                    "SET estado_aprobacion = 'APROBADO', fecha_aprobacion = :ts WHERE id = :i"),
                    {"ts": ahora, "i": ya})
        creado.append(f"{len(maestros)} farmacias aprobadas en su panel")

    db.commit()
    print("\nCreado: " + (", ".join(creado) if creado else "nada, ya estaba todo"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
