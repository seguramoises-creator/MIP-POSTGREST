"""
SCGCPR — Router: Dashboards
GET /api/v1/dashboard/ejecutivo      — Presidencia
GET /api/v1/dashboard/productividad  — Operativo
GET /api/v1/dashboard/comercial      — Comercial
GET /api/v1/dashboard/reconocimiento — Premios
GET /api/v1/dashboard/capacitacion   — Formación
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Rol
from app.models.hechos import (
    Ranking, Reconocimiento, CapacitacionFact,
    Ventas, Coaching, RendimientoComercial
)
from app.models.dimensiones import Pais, Indicador

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/ejecutivo", response_model=dict, summary="Dashboard Ejecutivo — Presidencia")
def dashboard_ejecutivo(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(
        Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL, Rol.GERENTE_PRODUCTIVIDAD
    )),
):
    """
    KPIs estratégicos para presidencia:
    IUP Regional, Top Países, Top RMs, tendencias.
    """
    # IUP promedio regional
    q_iup = db.query(
        func.avg(Ranking.iup_total).label("iup_promedio"),
        func.count(func.distinct(Ranking.rm_id)).label("total_rms"),
        func.count(func.nullif(Ranking.elegible, False)).label("rms_elegibles"),
        func.max(Ranking.iup_total).label("iup_max"),
    ).filter(Ranking.tipo_ranking == "MENSUAL")

    if pais_id: q_iup = q_iup.filter(Ranking.pais_id == pais_id)
    if ciclo_id: q_iup = q_iup.filter(Ranking.ciclo_id == ciclo_id)
    iup_data = q_iup.first()

    # Top 5 RMs por IUP
    q_top = db.query(
        Ranking.rm_id,
        Ranking.iup_total,
        Ranking.posicion,
        Ranking.pais_id,
    ).filter(
        Ranking.tipo_ranking == "MENSUAL",
        Ranking.elegible == True,
    )
    if pais_id: q_top = q_top.filter(Ranking.pais_id == pais_id)
    if ciclo_id: q_top = q_top.filter(Ranking.ciclo_id == ciclo_id)
    top_rms = q_top.order_by(Ranking.posicion.asc()).limit(5).all()

    # Promedio por componente IUP
    q_comp = db.query(
        func.avg(Ranking.iup_productividad).label("productividad"),
        func.avg(Ranking.iup_comercial).label("comercial"),
        func.avg(Ranking.iup_coaching).label("coaching"),
        func.avg(Ranking.iup_capacitacion).label("capacitacion"),
        func.avg(Ranking.iup_consistencia).label("consistencia"),
    ).filter(Ranking.tipo_ranking == "MENSUAL")
    if pais_id: q_comp = q_comp.filter(Ranking.pais_id == pais_id)
    if ciclo_id: q_comp = q_comp.filter(Ranking.ciclo_id == ciclo_id)
    comp = q_comp.first()

    total_rms = iup_data.total_rms or 1
    rms_elegibles = iup_data.rms_elegibles or 0

    return {
        "iup_regional_promedio": float(iup_data.iup_promedio or 0),
        "iup_maximo": float(iup_data.iup_max or 0),
        "total_rms": iup_data.total_rms or 0,
        "rms_elegibles": rms_elegibles,
        "pct_elegibles": round(rms_elegibles / total_rms * 100, 2),
        "top_rms": [
            {"posicion": r.posicion, "rm_id": r.rm_id,
             "iup_total": float(r.iup_total), "pais_id": r.pais_id}
            for r in top_rms
        ],
        "componentes_iup": {
            "productividad": float(comp.productividad or 0),
            "comercial": float(comp.comercial or 0),
            "coaching": float(comp.coaching or 0),
            "capacitacion": float(comp.capacitacion or 0),
            "consistencia": float(comp.consistencia or 0),
        },
        "filtros": {"pais_id": pais_id, "ciclo_id": ciclo_id},
    }


@router.get("/productividad", response_model=dict, summary="Dashboard de Productividad")
def dashboard_productividad(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """KPIs de productividad: Cobertura F1, F2, Farmacias, Promedio Diario."""
    q = db.query(
        Indicador.codigo,
        Indicador.nombre,
        func.avg(RendimientoComercial.porcentaje_cumplimiento).label("cumplimiento_promedio"),
        func.avg(RendimientoComercial.puntaje).label("puntaje_promedio"),
        func.count(func.distinct(RendimientoComercial.rm_id)).label("total_rms"),
    ).join(
        Indicador, Indicador.id == RendimientoComercial.indicador_id
    ).filter(
        Indicador.modulo == "PRODUCTIVIDAD",
        RendimientoComercial.activo == True,
    )

    if pais_id: q = q.filter(RendimientoComercial.pais_id == pais_id)
    if ciclo_id: q = q.filter(RendimientoComercial.ciclo_id == ciclo_id)

    rows = q.group_by(Indicador.codigo, Indicador.nombre).all()

    return {
        "kpis": [
            {
                "codigo": r.codigo, "nombre": r.nombre,
                "cumplimiento_promedio_pct": float(r.cumplimiento_promedio or 0),
                "puntaje_promedio": float(r.puntaje_promedio or 0),
                "total_rms": r.total_rms,
            }
            for r in rows
        ],
        "filtros": {"pais_id": pais_id, "ciclo_id": ciclo_id},
    }


@router.get("/comercial", response_model=dict, summary="Dashboard Comercial")
def dashboard_comercial(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Ventas consolidadas, EVO IR y cumplimiento de cuota."""
    q = db.query(
        func.sum(Ventas.ventas_reales).label("ventas_totales"),
        func.sum(Ventas.cuota).label("cuota_total"),
        func.avg(Ventas.cumplimiento_pct).label("cumplimiento_promedio"),
        func.avg(Ventas.crecimiento_pct).label("crecimiento_promedio"),
        func.count(func.distinct(Ventas.rm_id)).label("total_rms"),
    )
    if pais_id: q = q.filter(Ventas.pais_id == pais_id)
    if ciclo_id: q = q.filter(Ventas.ciclo_id == ciclo_id)
    v = q.first()

    return {
        "ventas_totales": float(v.ventas_totales or 0),
        "cuota_total": float(v.cuota_total or 0),
        "cumplimiento_promedio_pct": float(v.cumplimiento_promedio or 0),
        "crecimiento_promedio_pct": float(v.crecimiento_promedio or 0),
        "total_rms_con_ventas": v.total_rms or 0,
        "filtros": {"pais_id": pais_id, "ciclo_id": ciclo_id},
    }


@router.get("/reconocimiento", response_model=dict, summary="Dashboard de Reconocimiento")
def dashboard_reconocimiento(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Elegibles, premiados, certificados generados."""
    q_rank = db.query(
        func.count(func.distinct(Ranking.rm_id)).label("total_rms"),
        func.count(func.nullif(Ranking.elegible, False)).label("elegibles"),
    ).filter(Ranking.tipo_ranking == "MENSUAL")
    if pais_id: q_rank = q_rank.filter(Ranking.pais_id == pais_id)
    if ciclo_id: q_rank = q_rank.filter(Ranking.ciclo_id == ciclo_id)
    rank_data = q_rank.first()

    q_rec = db.query(
        func.count(Reconocimiento.id).label("total_reconocimientos"),
        func.count(func.nullif(Reconocimiento.certificado_generado, False)).label("certificados"),
    )
    if pais_id: q_rec = q_rec.filter(Reconocimiento.pais_id == pais_id)
    if ciclo_id: q_rec = q_rec.filter(Reconocimiento.ciclo_id == ciclo_id)
    rec_data = q_rec.first()

    total = rank_data.total_rms or 1
    elegibles = rank_data.elegibles or 0

    return {
        "total_rms": rank_data.total_rms or 0,
        "rms_elegibles": elegibles,
        "pct_elegibles": round(elegibles / total * 100, 2),
        "total_reconocimientos": rec_data.total_reconocimientos or 0,
        "certificados_generados": rec_data.certificados or 0,
        "filtros": {"pais_id": pais_id, "ciclo_id": ciclo_id},
    }


@router.get("/capacitacion", response_model=dict, summary="Dashboard de Capacitación")
def dashboard_capacitacion(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    q = db.query(
        func.count(CapacitacionFact.id).label("total"),
        func.sum(CapacitacionFact.horas_completadas).label("horas_total"),
        func.avg(CapacitacionFact.calificacion).label("calificacion_promedio"),
        func.count(func.nullif(CapacitacionFact.aprobado, False)).label("aprobados"),
        func.count(func.nullif(CapacitacionFact.asistio, False)).label("con_asistencia"),
    )
    if pais_id: q = q.filter(CapacitacionFact.pais_id == pais_id)
    if ciclo_id: q = q.filter(CapacitacionFact.ciclo_id == ciclo_id)
    r = q.first()

    total = r.total or 1
    return {
        "total_registros": r.total or 0,
        "horas_formacion_total": float(r.horas_total or 0),
        "calificacion_promedio": float(r.calificacion_promedio or 0),
        "total_aprobados": r.aprobados or 0,
        "tasa_aprobacion_pct": round((r.aprobados or 0) / total * 100, 2),
        "tasa_asistencia_pct": round((r.con_asistencia or 0) / total * 100, 2),
        "filtros": {"pais_id": pais_id, "ciclo_id": ciclo_id},
    }
