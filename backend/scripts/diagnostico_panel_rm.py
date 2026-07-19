"""
Diagnóstico (SOLO LECTURA): panel efectivo por RM en el ciclo de trabajo.

Para cada RM activo calcula su panel EFECTIVO (aplicando `cuenta_en_ciclo` en el ciclo
abierto de su país) y lo compara con sus médicos crudos y sus visitas registradas.
Señala los RMs con panel 0 y explica la causa probable:

  - ALTA_FUTURA     : médicos con `ciclo_alta_id` en un ciclo posterior al de trabajo
                      (el bug corregido en a5b9dcf; se sanea con fix_medico_alta.py).
  - SIN_APROBAR     : médicos en PENDIENTE_ALTA/RECHAZADO (faltan aprobar por el GD).
  - SIN_MEDICOS     : el RM no tiene médicos en su panel.
  - USUARIO_SIN_RMID: hay médicos/visitas pero ningún usuario está vinculado a ese rm_id
                      (el RM no podría entrar a ver su cobertura — caso "amiceli").

No escribe nada. Uso (dentro del contenedor):
  docker compose exec -e PYTHONPATH=/app backend python scripts/diagnostico_panel_rm.py
  docker compose exec -e PYTHONPATH=/app backend python scripts/diagnostico_panel_rm.py --solo-problemas
"""
from __future__ import annotations
import sys

from app.db.database import SessionLocal
from app.models.dimensiones import RepresentanteMedico
from app.models.visita import MedicoVisita, VisitaRegistro
from app.models.usuario import Usuario
from app.services.visita_aprobacion_service import cuenta_en_ciclo, ordenes_ciclo
from app.services.visita_cobertura_service import ciclo_por_defecto


def main() -> None:
    solo_problemas = "--solo-problemas" in sys.argv
    db = SessionLocal()
    try:
        ordenes = ordenes_ciclo(db)
        # rm_id vinculados a algún usuario (para detectar RMs "huérfanos" tipo amiceli).
        rmids_con_usuario = {u.rm_id for u in db.query(Usuario.rm_id).filter(Usuario.rm_id.isnot(None)).all()}

        rms = (db.query(RepresentanteMedico)
               .filter(RepresentanteMedico.activo == True)  # noqa: E712
               .order_by(RepresentanteMedico.pais_codigo, RepresentanteMedico.codigo).all())

        print(f"{'RM':<12} {'PAIS':<5} {'CICLO':<6} {'MED':>4} {'PANEL':>5} {'VIS':>4}  CAUSA")
        print("-" * 78)
        total = con_problema = 0
        for rm in rms:
            ciclo_id = ciclo_por_defecto(db, rm.id)
            orden = ordenes.get(ciclo_id) if ciclo_id else None
            meds = db.query(MedicoVisita).filter(
                MedicoVisita.vm_id == rm.id, MedicoVisita.activo == True).all()  # noqa: E712
            panel = sum(1 for m in meds if cuenta_en_ciclo(m, orden, ordenes))
            alta_fut = sum(1 for m in meds
                           if m.ciclo_alta_id and orden is not None
                           and (ordenes.get(m.ciclo_alta_id) or 0) > orden)
            sin_aprob = sum(1 for m in meds
                            if m.estado_aprobacion in ("PENDIENTE_ALTA", "RECHAZADO"))
            vis = db.query(VisitaRegistro).filter(
                VisitaRegistro.vm_id == rm.id,
                VisitaRegistro.ciclo_id == ciclo_id).count() if ciclo_id else 0

            causa = ""
            if panel == 0:
                if not meds:
                    causa = "SIN_MEDICOS"
                elif alta_fut:
                    causa = f"ALTA_FUTURA (x{alta_fut}) -> fix_medico_alta.py"
                elif sin_aprob:
                    causa = f"SIN_APROBAR (x{sin_aprob}) -> aprobar en Panel Médico"
                else:
                    causa = "PANEL_0 (revisar)"
            if rm.id not in rmids_con_usuario and (meds or vis):
                causa = (causa + " | " if causa else "") + "USUARIO_SIN_RMID"

            total += 1
            problema = bool(causa)
            if problema:
                con_problema += 1
            if solo_problemas and not problema:
                continue
            print(f"{rm.codigo:<12} {rm.pais_codigo:<5} {str(ciclo_id or '-'):<6} "
                  f"{len(meds):>4} {panel:>5} {vis:>4}  {causa}")

        print("-" * 78)
        print(f"RMs revisados: {total} · con panel 0 o sin vínculo: {con_problema}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
