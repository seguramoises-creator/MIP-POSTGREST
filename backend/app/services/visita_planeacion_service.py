"""Planeación del Ciclo (Parte 3 del spec). Reglas:
  P01 máx 2 visitas por médico (1 Vista + 1 Revisita)
  P02 la Revisita en semana >= semana de la Vista
  P03 Vista y Revisita no el mismo día
Patrón delete-then-insert por (vm, ciclo). Cat A sin Revisita se reporta como aviso.

**Borrador → Publicada (jul-2026).** La planeación es el DENOMINADOR de la cobertura
(`visitados / planeados`): editable a mitad de ciclo, un VM subiría su cobertura quitando
del plan a los médicos que no visitó, sin visitar a nadie más. Por eso se guarda libremente
como borrador y, al publicarla, queda CONGELADA. Solo un ADMIN puede desbloquearla, con
motivo obligatorio y dejando rastro (`PlaneacionEvento`, append-only).
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.visita import MedicoVisita, PlaneacionCiclo, PlaneacionEvento
from app.schemas.visita import PlaneacionItem
from app.services.visita_cobertura_service import ciclo_por_defecto, CICLO_DIAS_DEFAULT
from app.services import recalculo_service


class PlaneacionPublicadaError(Exception):
    """La planeación ya está publicada: es dato base de cálculo y no se puede modificar."""


class TopSinPlanearError(Exception):
    """La planeación omite médicos TOP. §7.3 del requerimiento de Mallén: al
    publicar, VISTA verifica que todos los TOP del panel estén incluidos y, si
    falta alguno, no permite publicar y muestra cuáles faltan."""


def _guard_ciclo_abierto(db, ciclo_id):
    """Bloquea escrituras sobre ciclos cerrados (inmutables)."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        raise ValueError("El ciclo está cerrado — solo lectura")


def _ultimo_evento(db: Session, vm_id: int, ciclo_id: int) -> PlaneacionEvento | None:
    return (db.query(PlaneacionEvento)
            .filter(PlaneacionEvento.vm_id == vm_id, PlaneacionEvento.ciclo_id == ciclo_id)
            .order_by(PlaneacionEvento.fecha.desc(), PlaneacionEvento.id.desc()).first())


def esta_publicada(db: Session, vm_id: int, ciclo_id: int) -> bool:
    """Publicada = el último evento del (vm, ciclo) es PUBLICADA. Sin eventos → borrador."""
    ev = _ultimo_evento(db, vm_id, ciclo_id)
    return ev is not None and ev.evento == "PUBLICADA"


def _guard_no_publicada(db: Session, vm_id: int, ciclo_id: int) -> None:
    if esta_publicada(db, vm_id, ciclo_id):
        raise PlaneacionPublicadaError(
            "La planeación de este ciclo ya fue publicada y no puede modificarse: es el dato "
            "base con el que se calcula tu cobertura. Si hay un error, un administrador debe "
            "desbloquearla indicando el motivo.")


def _medicos_del_ciclo(db: Session, vm_id: int, ciclo_id: int) -> list[MedicoVisita]:
    """Los médicos del panel que CUENTAN en el ciclo.

    Filtra por `cuenta_en_ciclo` y no por `activo` a secas: con `activo` se
    incluirían altas pendientes de aprobación y bajas ya efectivas, y se
    exigiría planear médicos sobre los que el representante no puede actuar.
    """
    from app.services.visita_aprobacion_service import ordenes_ciclo, cuenta_en_ciclo
    ordenes = ordenes_ciclo(db)
    ciclo_orden = ordenes.get(ciclo_id)
    medicos = db.query(MedicoVisita).filter(MedicoVisita.vm_id == vm_id).all()
    return [m for m in medicos if cuenta_en_ciclo(m, ciclo_orden, ordenes)]


def top_sin_planear(db: Session, vm_id: int, ciclo_id: int) -> list[dict]:
    """Médicos TOP del ciclo que no tienen NINGUNA fila en la planeación."""
    planeados = {p.medico_id for p in db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all()}
    return [{"id": m.id, "nombre": m.nombre_completo}
            for m in _medicos_del_ciclo(db, vm_id, ciclo_id)
            if m.es_top and m.id not in planeados]


def top_sin_revisita(db: Session, vm_id: int, ciclo_id: int) -> list[dict]:
    """TOP planeados pero sin Revisita. Se AVISA, no se bloquea: el §7.3 solo
    exige que estén «incluidos», pero el §3.4 dice que un TOP no puede terminar
    sin visita y revisita — planearlo solo con V es planear el incumplimiento."""
    plan_ = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all()
    planeados = {p.medico_id for p in plan_}
    con_revisita = {p.medico_id for p in plan_ if p.tipo_visita == "R"}
    return [{"id": m.id, "nombre": m.nombre_completo}
            for m in _medicos_del_ciclo(db, vm_id, ciclo_id)
            if m.es_top and m.id in planeados and m.id not in con_revisita]


def publicar_planeacion(db: Session, vm_id: int, ciclo_id: int | None, usuario_id: int | None) -> dict:
    """Congela la planeación del (vm, ciclo). Irreversible salvo desbloqueo del ADMIN."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    _guard_no_publicada(db, vm_id, ciclo_id)
    n = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).count()
    if n == 0:
        raise ValueError("No hay planeación que publicar: guarda al menos un médico primero.")
    faltantes = top_sin_planear(db, vm_id, ciclo_id)
    if faltantes:
        nombres = ", ".join(f["nombre"] for f in faltantes)
        raise TopSinPlanearError(
            f"No se puede publicar: faltan {len(faltantes)} médico(s) TOP en la "
            f"planeación del ciclo. Agrégalos y vuelve a intentarlo: {nombres}.")
    db.add(PlaneacionEvento(vm_id=vm_id, ciclo_id=ciclo_id, evento="PUBLICADA",
                            usuario_id=usuario_id, items=n))
    db.commit()
    logger.info(f"Planeación PUBLICADA vm={vm_id} ciclo={ciclo_id} items={n} por usuario={usuario_id}")
    return {"publicada": True, "items": n, "ciclo_id": ciclo_id}


def desbloquear_planeacion(db: Session, vm_id: int, ciclo_id: int | None,
                           usuario_id: int | None, motivo: str) -> dict:
    """Devuelve la planeación a borrador. **Solo ADMIN** (lo exige el router) y con motivo:
    sin él, desbloquear sería una vía silenciosa para maquillar la cobertura."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    if not (motivo or "").strip():
        raise ValueError("Indica el motivo del desbloqueo (queda registrado).")
    if not esta_publicada(db, vm_id, ciclo_id):
        raise ValueError("La planeación de este ciclo no está publicada.")
    db.add(PlaneacionEvento(vm_id=vm_id, ciclo_id=ciclo_id, evento="DESBLOQUEADA",
                            usuario_id=usuario_id, motivo=motivo.strip()))
    db.commit()
    logger.warning(f"Planeación DESBLOQUEADA vm={vm_id} ciclo={ciclo_id} por usuario={usuario_id}: {motivo}")
    return {"publicada": False, "ciclo_id": ciclo_id}


def estado_planeacion(db: Session, vm_id: int, ciclo_id: int | None) -> dict:
    """Estado + historial de publicación (para que la UI sepa qué mostrar y el admin audite)."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        return {"ciclo_id": None, "publicada": False, "historial": []}
    eventos = (db.query(PlaneacionEvento)
               .filter(PlaneacionEvento.vm_id == vm_id, PlaneacionEvento.ciclo_id == ciclo_id)
               .order_by(PlaneacionEvento.fecha.desc(), PlaneacionEvento.id.desc()).all())
    return {
        "ciclo_id": ciclo_id,
        "publicada": bool(eventos) and eventos[0].evento == "PUBLICADA",
        "publicada_en": eventos[0].fecha.isoformat() if eventos and eventos[0].evento == "PUBLICADA" else None,
        "historial": [{"evento": e.evento, "fecha": e.fecha.isoformat(),
                       "usuario_id": e.usuario_id, "motivo": e.motivo, "items": e.items}
                      for e in eventos],
    }


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
    ciclo_id = ciclo_id or ciclo_por_defecto(db, vm_id)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    # Publicada = congelada. El guard va ANTES del delete-then-insert: sin él, un re-guardado
    # borraria el plan publicado y lo reescribiria, moviendo el denominador de la cobertura.
    _guard_no_publicada(db, vm_id, ciclo_id)
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
    sin_planear = top_sin_planear(db, vm_id, ciclo_id)
    sin_revisita = top_sin_revisita(db, vm_id, ciclo_id)
    return {
        "ciclo_id": ciclo_id, "panel": panel, "total_planeadas": total,
        "medicos_planeados": len(con_vista),
        "cobertura_planeada_pct": round(len(con_vista) / panel * 100, 1) if panel else 0.0,
        "cat_a_sin_revisita": cat_a_sin_revisita,
        "carga_por_dia": round(total / CICLO_DIAS_DEFAULT, 1),
        "top_sin_planear": sin_planear,
        "top_sin_revisita": sin_revisita,
    }
