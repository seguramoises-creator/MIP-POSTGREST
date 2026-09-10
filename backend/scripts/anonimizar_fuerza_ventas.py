"""Cambia los nombres de gerentes y representantes por nombres genéricos.

Para qué: el servidor de calidad se usa para enseñar la suite a clientes nuevos, y los
nombres reales de la fuerza de ventas de un cliente no tienen por qué viajar a una
demostración de otro.

Solo toca NOMBRES. No mueve códigos (GD001, VM-1), ni líneas, ni jerarquía, ni un solo
dato de negocio: las cifras, los rankings y la cobertura siguen siendo exactamente los
mismos. Lo que cambia es cómo se llama quien aparece en pantalla.

    python scripts/anonimizar_fuerza_ventas.py                 # enseña lo que haría
    python scripts/anonimizar_fuerza_ventas.py --aplicar
    python scripts/anonimizar_fuerza_ventas.py --restaurar <respaldo.json>

SIEMPRE deja un respaldo antes de escribir, y el respaldo es lo que permite volver. Sin
él esto sería una pérdida irreversible de datos por una demostración.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402

# Nombres corrientes y sin parecido con nadie: el objetivo es que se lean como un
# ejemplo, no que parezcan otra persona real a la que se pudiera confundir.
NOMBRES = [
    "Ana", "Luis", "Carmen", "Jorge", "Elena", "Pablo", "Marta", "Diego",
    "Sofía", "Andrés", "Lucía", "Miguel", "Clara", "Tomás", "Irene", "Javier",
    "Paula", "Raúl", "Nuria", "Óscar", "Alba", "Iván", "Rosa", "Hugo",
    "Silvia", "Adrián", "Julia", "Marcos", "Teresa", "Alonso", "Nerea", "Gabriel",
    "Beatriz", "Emilio", "Patricia", "Sergio", "Cristina", "Daniel", "Laura", "Rubén",
    "Mónica", "Álvaro", "Isabel", "Fernando", "Natalia", "Ramiro", "Verónica", "Leandro",
    "Susana", "Ignacio", "Amelia", "Rodrigo", "Olivia", "Néstor", "Eva", "Bruno",
]
APELLIDOS = [
    "Álvarez", "Bravo", "Campos", "Delgado", "Escudero", "Fuentes", "Gil", "Herrera",
    "Ibáñez", "Jaramillo", "Lozano", "Molina", "Navarro", "Ortega", "Pardo", "Quintana",
    "Rivas", "Serrano", "Toledo", "Ureña", "Valdés", "Zamora", "Acosta", "Benítez",
    "Cabrera", "Duarte", "Espinosa", "Ferrer", "Guzmán", "Hidalgo", "Iglesias", "Juárez",
    "Lara", "Miranda", "Nieto", "Olmedo", "Peralta", "Quiroga", "Rueda", "Salazar",
    "Tejada", "Urbina", "Vega", "Yáñez", "Arroyo", "Bermúdez", "Castaño", "Domínguez",
    "Esteban", "Franco", "Galindo", "Higuera", "Izquierdo", "Ledesma", "Mena", "Noriega",
]


def generar(n: int) -> list[str]:
    """`n` nombres distintos, en un orden fijo — dos corridas dan lo mismo."""
    out, i = [], 0
    while len(out) < n:
        nombre = f"{NOMBRES[i % len(NOMBRES)]} {APELLIDOS[(i * 7 + i // len(NOMBRES)) % len(APELLIDOS)]}"
        if nombre not in out:
            out.append(nombre)
        i += 1
    return out


def leer(db):
    ger = db.execute(text(
        'SELECT id, codigo, nombre, tipo FROM "Config"."DIM_Gerente" ORDER BY tipo, id')).all()
    rms = db.execute(text(
        'SELECT id, codigo, nombre FROM "Config"."DIM_RM" ORDER BY id')).all()
    usu = db.execute(text(
        'SELECT id, username, nombre_completo, rol, rm_id, gerente_id '
        'FROM "Security"."DIM_Usuario" ORDER BY id')).all()
    return ger, rms, usu


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="escribe de verdad")
    ap.add_argument("--restaurar", metavar="RESPALDO.json", help="deshace usando un respaldo")
    args = ap.parse_args()

    db = SessionLocal()

    if args.restaurar:
        datos = json.loads(Path(args.restaurar).read_text(encoding="utf-8"))
        for tabla, esquema, campo, clave in (
                ("DIM_Gerente", "Config", "nombre", "gerentes"),
                ("DIM_RM", "Config", "nombre", "rms"),
                ("DIM_Usuario", "Security", "nombre_completo", "usuarios")):
            for fila in datos[clave]:
                db.execute(text(
                    f'UPDATE "{esquema}"."{tabla}" SET "{campo}" = :v WHERE id = :id'),
                    {"v": fila["antes"], "id": fila["id"]})
        db.commit()
        print(f"Restaurado desde {args.restaurar}.")
        return 0

    ger, rms, usu = leer(db)
    nuevos = generar(len(ger) + len(rms))
    mapa_ger = {g.id: nuevos[i] for i, g in enumerate(ger)}
    mapa_rm = {r.id: nuevos[len(ger) + i] for i, r in enumerate(rms)}

    # Los usuarios que se llaman igual que un gerente o un representante se renombran
    # con él: si no, la pantalla de Usuarios seguiría enseñando el nombre real y el
    # cambio solo habría tapado la mitad.
    por_nombre = {}
    for g in ger:
        por_nombre[(g.nombre or "").strip().upper()] = mapa_ger[g.id]
    for r in rms:
        por_nombre[(r.nombre or "").strip().upper()] = mapa_rm[r.id]
    # Se empareja PRIMERO por el vínculo (rm_id / gerente_id) y solo después por el
    # texto del nombre.
    # SOLO la fuerza de ventas. Atar por `rm_id`/`gerente_id` sin mirar el ROL renombró
    # la cuenta del ADMINISTRADOR y una de QA, que tenían ese vínculo puesto de arrastre:
    # se pidieron los nombres de gerentes y visitadores, no los de todo el que estuviera
    # enlazado a una ficha.
    ROLES = {"REPRESENTANTE_MEDICO", "GERENTE_DISTRITO", "GERENTE_MARCA"}
    cambios_usu = []
    for u in usu:
        if (u.rol or "") not in ROLES:
            continue
        destino = None
        if u.rm_id and u.rm_id in mapa_rm:
            destino = mapa_rm[u.rm_id]
        elif u.gerente_id and u.gerente_id in mapa_ger:
            destino = mapa_ger[u.gerente_id]
        else:
            destino = por_nombre.get((u.nombre_completo or "").strip().upper())
        if destino and destino != (u.nombre_completo or ""):
            cambios_usu.append((u.id, u.nombre_completo, destino))

    print(f"Gerentes: {len(ger)} · Representantes: {len(rms)} · "
          f"Usuarios que comparten nombre: {len(cambios_usu)}\n")
    for g in ger:
        print(f"  {g.codigo:<8} {g.tipo:<9} {g.nombre:<28} -> {mapa_ger[g.id]}")
    for r in rms[:6]:
        print(f"  {r.codigo:<8} {'RM':<9} {r.nombre:<28} -> {mapa_rm[r.id]}")
    if len(rms) > 6:
        print(f"  … y {len(rms) - 6} representantes más")

    if not args.aplicar:
        print("\n(simulación) No se escribió nada. Añade --aplicar.")
        return 0

    sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    respaldo = Path(f"respaldo_nombres_{sello}.json")
    respaldo.write_text(json.dumps({
        "generado": sello,
        "gerentes": [{"id": g.id, "antes": g.nombre, "despues": mapa_ger[g.id]} for g in ger],
        "rms": [{"id": r.id, "antes": r.nombre, "despues": mapa_rm[r.id]} for r in rms],
        "usuarios": [{"id": i, "antes": a, "despues": d} for i, a, d in cambios_usu],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRespaldo escrito en {respaldo.resolve()}")

    for gid, nombre in mapa_ger.items():
        db.execute(text('UPDATE "Config"."DIM_Gerente" SET nombre = :v WHERE id = :id'),
                   {"v": nombre, "id": gid})
    for rid, nombre in mapa_rm.items():
        db.execute(text('UPDATE "Config"."DIM_RM" SET nombre = :v WHERE id = :id'),
                   {"v": nombre, "id": rid})
    for uid, _antes, despues in cambios_usu:
        db.execute(text('UPDATE "Security"."DIM_Usuario" SET nombre_completo = :v WHERE id = :id'),
                   {"v": despues, "id": uid})
    db.commit()
    print(f"Aplicado: {len(mapa_ger)} gerentes, {len(mapa_rm)} representantes, "
          f"{len(cambios_usu)} usuarios.")
    print("Para deshacerlo:  python scripts/anonimizar_fuerza_ventas.py --restaurar "
          f"{respaldo.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
