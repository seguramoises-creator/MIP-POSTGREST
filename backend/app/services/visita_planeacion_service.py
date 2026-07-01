"""Planeación del Ciclo (Parte 3 del spec). Reglas:
  P01 máx 2 visitas por médico (1 Vista + 1 Revisita)
  P02 la Revisita en semana >= semana de la Vista
  P03 Vista y Revisita no el mismo día
Patrón delete-then-insert por (vm, ciclo). Cat A sin Revisita se reporta como aviso.
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.visita import MedicoVisita, PlaneacionCiclo
from app.schemas.visita import PlaneacionItem
from app.services.visita_cobertura_service import ciclo_por_defecto, CICLO_DIAS_DEFAULT


def _validar(items: list[PlaneacionItem]) -> None:
    por_medico: dict[int, list[PlaneacionItem]] = {}
    for it in items:
        por_medico.setdefault(it.medico_id, []).append(it)
    for mid, grupo in por_medico.items():
        if len(grupo) > 2:
            raise ValueError(f"Máximo 2 visitas por médico (médico {mid} tiene {len(grupo)})")
        tipos = [g.tipo_visita for g in grupo]
        if tipos.count("V") > 1 or tipos.count("R") > 1:
            raise ValueError(f"Un médico solo puede tener 1 Vista y 1 Revisita (médico {mid})")
        if "V" in tipos and "R" in tipos:
            v = next(g for g in grupo if g.tipo_visita == "V")
            r = next(g for g in grupo if g.tipo_visita == "R")
            if r.semana < v.semana:
                raise ValueError(f"La Revisita debe ir en semana >= la Vista (médico {mid})")
            if r.semana == v.semana and r.dia_semana and v.dia_semana and r.dia_semana == v.dia_semana:
                raise ValueError(f"Vista y Revisita no pueden ser el mismo día (médico {mid})")
        if "R" in tipos and "V" not in tipos:
            raise ValueError(f"No se puede planear Revisita sin Vista (médico {mid})")


def guardar_planeacion(db: Session, vm_id: int, ciclo_id: int | None,
                       items: list[PlaneacionItem], usuario_id: int | None) -> int:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _validar(items)
    db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).delete(synchronize_session=False)
    for it in items:
        db.add(PlaneacionCiclo(
            vm_id=vm_id, ciclo_id=ciclo_id, medico_id=it.medico_id, tipo_visita=it.tipo_visita,
            semana=it.semana, dia_semana=it.dia_semana, hora_estimada=it.hora_estimada,
            fecha_creacion=datetime.now(timezone.utc), modificado_por=usuario_id))
    db.commit()
    logger.info(f"Planeación guardada VM={vm_id} ciclo={ciclo_id}: {len(items)} ítems")
    return len(items)


def listar_planeacion(db: Session, vm_id: int, ciclo_id: int | None) -> list[dict]:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    filas = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all()
    return [{"medico_id": f.medico_id, "tipo_visita": f.tipo_visita, "semana": f.semana,
             "dia_semana": f.dia_semana, "hora_estimada": f.hora_estimada} for f in filas]


def resumen_planeacion(db: Session, vm_id: int, ciclo_id: int | None) -> dict:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    medicos = db.query(MedicoVisita).filter(
        MedicoVisita.vm_id == vm_id, MedicoVisita.activo == True).all()  # noqa: E712
    panel = len(medicos)
    cat_a = {m.id for m in medicos if m.categoria == "A"}
    plan = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all()
    con_vista = {p.medico_id for p in plan if p.tipo_visita == "V"}
    con_revisita = {p.medico_id for p in plan if p.tipo_visita == "R"}
    cat_a_sin_revisita = len(cat_a - con_revisita)
    total = len(plan)
    return {
        "ciclo_id": ciclo_id, "panel": panel, "total_planeadas": total,
        "medicos_planeados": len(con_vista),
        "cobertura_planeada_pct": round(len(con_vista) / panel * 100, 1) if panel else 0.0,
        "cat_a_sin_revisita": cat_a_sin_revisita,
        "carga_por_dia": round(total / CICLO_DIAS_DEFAULT, 1),
    }
