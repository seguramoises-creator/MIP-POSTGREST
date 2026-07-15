"""
Backfill Panel → Maestro de Médicos (idempotente).

Por cada Visita.DIM_MedicoVisita con maestro_medico_id NULL:
  - deriva el país vía su VM (DIM_RM.pais_codigo),
  - busca coincidencia DURA (exequátur → código) en el Maestro; si existe, LINKEA,
  - si no, CREA el maestro (origen=PANEL, estado=APROBADO por ser dato histórico ya
    en uso) con los campos generales del panel, y linkea.

Idempotente: reejecutable sin duplicar (solo procesa los que aún no tienen link).
Nota: las dimensiones geográficas del panel son texto (provincia/municipio/centro)
y no se mapean a los *_id del maestro; se dejan nulas para completarse luego.

Uso (en el servidor, dentro del contenedor):
  docker compose exec -e PYTHONPATH=/app backend python scripts/backfill_maestro_medicos.py
  ... --dry-run   (solo reporta, no escribe)
"""
from __future__ import annotations
import sys

from app.db.database import SessionLocal
# Carga TODOS los modelos para poblar el registry de mappers (FKs a Security/DW/etc.).
from app.models import dimensiones, visita, usuario, hechos  # noqa: F401
from app.models.visita import MedicoVisita
from app.models.dimensiones import RepresentanteMedico
from app.services import maestro_medico_service as svc

# Campos generales del panel → campo del maestro.
_MAP = {
    "nombre_completo": "nombre", "codigo": "codigo", "especialidad_id": "especialidad_id",
    "exequatur": "exequatur", "telefono": "telefono", "email": "email",
    "direccion": "direccion", "sector": "sector",
}


def _campos(mv: MedicoVisita) -> dict:
    out = {}
    for src, dst in _MAP.items():
        v = getattr(mv, src, None)
        if v not in (None, ""):
            out[dst] = v
    return out


def main() -> None:
    dry = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        rm_pais = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.pais_codigo).all())
        pendientes = db.query(MedicoVisita).filter(MedicoVisita.maestro_medico_id.is_(None)).all()
        print(f"MedicoVisita sin maestro: {len(pendientes)}")
        linkeados = creados = sin_pais = 0
        for mv in pendientes:
            pais = rm_pais.get(mv.vm_id)
            if not pais:
                sin_pais += 1
                continue
            campos = _campos(mv)
            existente = svc._resolver_por_llave_dura(db, pais, campos.get("exequatur"),
                                                     None, campos.get("codigo"))
            if existente:
                if not dry:
                    mv.maestro_medico_id = existente.id
                linkeados += 1
            else:
                if dry:
                    creados += 1
                    continue
                m = svc.crear_maestro(db, pais, campos, origen="PANEL", estado="APROBADO",
                                      confirmar_duplicado=True)
                mv.maestro_medico_id = m.id
                creados += 1
            if not dry:
                db.commit()
        if dry:
            print(f"[dry-run] linkearía {linkeados}, crearía {creados}, sin país {sin_pais}")
        else:
            print(f"OK — linkeados {linkeados}, creados {creados}, sin país (omitidos) {sin_pais}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
