"""
asignar_paises_usuario.py — Acota un usuario a un conjunto de países (idempotente).

    docker compose exec backend python scripts/setup/asignar_paises_usuario.py qa_coordinador GT HN
    docker compose exec backend python scripts/setup/asignar_paises_usuario.py qa_coordinador    # <- lo DESACOTA

Escribe `Security.FACT_UsuarioPais`, la frontera de país. Reemplaza el conjunto completo,
no añade: `fijar_paises` borra lo vigente y pone lo indicado.

DOS COSAS QUE NO SE DEBEN OLVIDAR
1. **Sin filas = ve TODOS los países.** Llamar sin códigos no "deja al usuario sin acceso":
    lo deja SIN RESTRICCIÓN. Por eso el script lo pregunta en voz alta antes de hacerlo.
2. **El código se valida contra `DIM_Pais`.** `FACT_UsuarioPais.pais_codigo` es un String(10)
    SIN clave foránea: un típo como "G T" o "GTM" se guardaría sin queja y dejaría al usuario
    con un conjunto no vacío que no coincide con ningún país real — es decir, sin ver NADA, y
    sin ninguna excepción que avise. La validación vive en `alcance_service.fijar_paises`;
    aquí solo se reporta con claridad.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.models.usuario  # noqa: F401 — registran los mappers
import app.models.dimensiones  # noqa: F401
import app.models.alcance  # noqa: F401

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.usuario import Usuario
from app.services import alcance_service


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    username, codigos = sys.argv[1], [c.strip().upper() for c in sys.argv[2:] if c.strip()]

    db = SessionLocal()
    try:
        u = db.execute(select(Usuario).where(Usuario.username == username)).scalar_one_or_none()
        if not u:
            print(f"[ERROR] No existe el usuario '{username}'.")
            sys.exit(1)

        antes = sorted(alcance_service.paises_de(db, u.id))
        print(f"Usuario : {u.username} — {u.nombre_completo} ({u.rol})")
        print(f"Antes   : {antes or '(sin filas = TODOS los países)'}")

        if not codigos:
            print("\n[!] Sin códigos: esto DESACOTA al usuario y pasará a ver TODOS los países.")
            if input("    Escribe 'DESACOTAR' para confirmar: ").strip() != "DESACOTAR":
                print("    Cancelado, nada cambió.")
                return

        try:
            alcance_service.fijar_paises(db, u.id, codigos)
        except alcance_service.AlcanceInvalidoError as exc:
            db.rollback()
            print(f"[ERROR] {exc}")
            print("        Nada cambió: la validación corre ANTES de borrar el conjunto vigente.")
            sys.exit(1)
        db.commit()

        print(f"Después : {sorted(alcance_service.paises_de(db, u.id)) or '(sin filas = TODOS)'}")
        print("\nListo. El cambio aplica en la próxima petición del usuario "
              "(la frontera se lee de la BD en cada llamada, no se cachea).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
