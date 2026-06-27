"""
SCGCPR — Motor de Elegibilidad
Evalúa si un RM cumple todas las reglas configuradas en DIM_ReglaElegibilidad.
Retorna: ELEGIBLE | NO_ELEGIBLE | CONDICIONADO
"""
from typing import Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from loguru import logger

from app.models.dimensiones import ReglaElegibilidad, RepresentanteMedico
from app.models.hechos import RendimientoComercial, Coaching, CapacitacionFact, Ventas
from app.models.dimensiones import Indicador


def evaluar_elegibilidad_rm(
    db: Session, rm_id: int, pais_id: int, ciclo_id: Optional[int] = None
) -> dict:
    """
    Evalúa todas las reglas activas de elegibilidad para un RM.
    """
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == rm_id).first()
    if not rm:
        return {"rm_id": rm_id, "elegible": False, "estado": "NO_ELEGIBLE",
                "detalle": "RM no encontrado"}

    # Obtener reglas configuradas para el país/ciclo
    q = db.query(ReglaElegibilidad).filter(
        ReglaElegibilidad.pais_id == pais_id,
        ReglaElegibilidad.activo == True,
    )
    if ciclo_id:
        q = q.filter(
            (ReglaElegibilidad.ciclo_id == ciclo_id) | (ReglaElegibilidad.ciclo_id == None)
        )
    reglas = q.all()

    if not reglas:
        return {"rm_id": rm_id, "elegible": True, "estado": "ELEGIBLE",
                "detalle": "Sin reglas configuradas", "reglas_evaluadas": []}

    resultados = []
    cumple_todas = True
    incumplimientos = 0

    for regla in reglas:
        valor_actual = _obtener_valor_indicador(db, rm_id, pais_id, ciclo_id, regla.indicador_codigo)
        cumple = valor_actual >= regla.umbral_minimo

        resultados.append({
            "regla": regla.nombre,
            "indicador": regla.indicador_codigo,
            "umbral_minimo": float(regla.umbral_minimo),
            "valor_actual": float(valor_actual),
            "cumple": cumple,
        })

        if not cumple:
            incumplimientos += 1
            if not _es_condicionado(regla):
                cumple_todas = False

    if cumple_todas and incumplimientos == 0:
        estado = "ELEGIBLE"
        elegible = True
    elif incumplimientos == 1 and _tiene_condicionado(reglas):
        estado = "CONDICIONADO"
        elegible = False
    else:
        estado = "NO_ELEGIBLE"
        elegible = False

    logger.info(f"Elegibilidad RM {rm_id}: {estado} ({incumplimientos} incumplimientos)")

    return {
        "rm_id": rm_id,
        "rm_nombre": rm.nombre,
        "pais_id": pais_id,
        "ciclo_id": ciclo_id,
        "elegible": elegible,
        "estado": estado,
        "total_reglas": len(reglas),
        "reglas_cumplidas": len(reglas) - incumplimientos,
        "incumplimientos": incumplimientos,
        "reglas_evaluadas": resultados,
    }


def _obtener_valor_indicador(
    db: Session, rm_id: int, pais_id: int, ciclo_id: Optional[int], indicador_codigo: str
) -> Decimal:
    """Obtiene el valor real del indicador para el RM dado."""

    # Indicadores de productividad (RendimientoComercial)
    prod_codigos = {"COBERTURA_F1", "COBERTURA_F2", "COBERTURA_FARMACIAS", "PROMEDIO_DIARIO"}
    if indicador_codigo.upper() in prod_codigos:
        q = db.query(func.avg(RendimientoComercial.porcentaje_cumplimiento)).join(
            Indicador, Indicador.id == RendimientoComercial.indicador_id
        ).filter(
            RendimientoComercial.rm_id == rm_id,
            RendimientoComercial.pais_id == pais_id,
            Indicador.codigo == indicador_codigo,
            RendimientoComercial.activo == True,
        )
        if ciclo_id: q = q.filter(RendimientoComercial.ciclo_id == ciclo_id)
        return Decimal(str(q.scalar() or 0))

    # Coaching
    if indicador_codigo.upper() == "COACHING":
        q = db.query(func.avg(Coaching.cumplimiento_pct)).filter(
            Coaching.rm_id == rm_id, Coaching.pais_id == pais_id
        )
        if ciclo_id: q = q.filter(Coaching.ciclo_id == ciclo_id)
        return Decimal(str(q.scalar() or 0))

    # Capacitación
    if indicador_codigo.upper() == "CAPACITACION":
        total = db.query(func.count(CapacitacionFact.id)).filter(
            CapacitacionFact.rm_id == rm_id, CapacitacionFact.pais_id == pais_id
        )
        aprobados = db.query(func.count(CapacitacionFact.id)).filter(
            CapacitacionFact.rm_id == rm_id, CapacitacionFact.pais_id == pais_id,
            CapacitacionFact.aprobado == True,
        )
        if ciclo_id:
            total = total.filter(CapacitacionFact.ciclo_id == ciclo_id)
            aprobados = aprobados.filter(CapacitacionFact.ciclo_id == ciclo_id)
        t = total.scalar() or 1
        a = aprobados.scalar() or 0
        return Decimal(str(a / t * 100))

    # Comercial (cumplimiento de cuota)
    if indicador_codigo.upper() == "COMERCIAL":
        q = db.query(func.avg(Ventas.cumplimiento_pct)).filter(
            Ventas.rm_id == rm_id, Ventas.pais_id == pais_id
        )
        if ciclo_id: q = q.filter(Ventas.ciclo_id == ciclo_id)
        return Decimal(str(q.scalar() or 0))

    return Decimal("0")


def _es_condicionado(regla: ReglaElegibilidad) -> bool:
    """Una regla es condicionada si aplica solo a reconocimiento (no bloquea ranking)."""
    return regla.aplica_reconocimiento and not regla.aplica_ranking


def _tiene_condicionado(reglas: list) -> bool:
    return any(_es_condicionado(r) for r in reglas)
