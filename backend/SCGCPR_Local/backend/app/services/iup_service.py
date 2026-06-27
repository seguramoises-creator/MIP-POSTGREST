"""
SCGCPR — Motor IUP (Índice Único de Productividad)
FIX C-02: Los pesos se leen desde DIM_Indicador.peso_iup en BD,
          NO desde constantes hardcodeadas.
FIX W-02: Puntaje comercial pondera solo los componentes disponibles
          (no penaliza si EVO IR no fue cargado en el ciclo).
FIX W-08: Consistencia de RMs nuevos usa 0 como base neutral en lugar
          de 50, para evitar ventaja artificial sobre RMs con historial.

Fórmula configurable:
  IUP = Σ (puntaje_modulo × peso_modulo)
  donde los pesos provienen de DIM_Indicador.peso_iup agrupados por módulo.
"""
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from loguru import logger

from app.models.hechos import RendimientoComercial, Ventas, EvoIR, Coaching, CapacitacionFact, Ranking
from app.models.dimensiones import Indicador

# Pesos por defecto — solo usados si DIM_Indicador no tiene datos configurados
_PESOS_DEFECTO = {
    "PRODUCTIVIDAD": Decimal("0.30"),
    "COMERCIAL":     Decimal("0.30"),
    "COACHING":      Decimal("0.15"),
    "CAPACITACION":  Decimal("0.10"),
    "CONSISTENCIA":  Decimal("0.15"),
}


def _obtener_pesos(db: Session) -> dict:
    """
    FIX C-02: Lee los pesos configurados desde DIM_Indicador.peso_iup
    agrupando por módulo (suma de pesos de indicadores del mismo módulo).
    Si no hay datos configurados, usa los pesos por defecto.
    """
    rows = (
        db.query(
            Indicador.modulo,
            func.sum(Indicador.peso_iup).label("peso_total"),
        )
        .filter(Indicador.activo == True, Indicador.peso_iup > 0)
        .group_by(Indicador.modulo)
        .all()
    )

    if not rows:
        logger.debug("IUP: sin pesos en DIM_Indicador — usando pesos por defecto")
        return _PESOS_DEFECTO.copy()

    pesos = {r.modulo: Decimal(str(r.peso_total)) for r in rows}

    # Normalizar para que sumen 1.0 (por si la configuración no está balanceada)
    total = sum(pesos.values()) or Decimal("1")
    pesos_norm = {k: v / total for k, v in pesos.items()}

    # Garantizar clave CONSISTENCIA (no es un módulo de indicadores)
    if "CONSISTENCIA" not in pesos_norm:
        pesos_norm["CONSISTENCIA"] = _PESOS_DEFECTO["CONSISTENCIA"]
        # Re-normalizar dejando espacio para consistencia
        resto = Decimal("1") - pesos_norm["CONSISTENCIA"]
        otros = {k: v for k, v in pesos_norm.items() if k != "CONSISTENCIA"}
        total_otros = sum(otros.values()) or Decimal("1")
        for k in otros:
            pesos_norm[k] = (otros[k] / total_otros) * resto

    logger.debug(f"IUP pesos leídos de BD: {pesos_norm}")
    return pesos_norm


def calcular_iup(
    db: Session,
    rm_id: int,
    pais_id: int,
    ciclo_id: int,
) -> dict:
    """
    Calcula el IUP completo para un RM en un ciclo dado.
    Los pesos se obtienen desde DIM_Indicador en BD (FIX C-02).
    """
    logger.debug(f"Calculando IUP — rm_id={rm_id}, ciclo_id={ciclo_id}")

    pesos = _obtener_pesos(db)

    prod  = _get_puntaje_productividad(db, rm_id, pais_id, ciclo_id)
    com   = _get_puntaje_comercial(db, rm_id, pais_id, ciclo_id)
    coach = _get_puntaje_coaching(db, rm_id, pais_id, ciclo_id)
    cap   = _get_puntaje_capacitacion(db, rm_id, pais_id, ciclo_id)
    cons  = _get_puntaje_consistencia(db, rm_id, pais_id)

    iup = (
        prod  * pesos.get("PRODUCTIVIDAD", _PESOS_DEFECTO["PRODUCTIVIDAD"]) +
        com   * pesos.get("COMERCIAL",     _PESOS_DEFECTO["COMERCIAL"])     +
        coach * pesos.get("COACHING",      _PESOS_DEFECTO["COACHING"])      +
        cap   * pesos.get("CAPACITACION",  _PESOS_DEFECTO["CAPACITACION"])  +
        cons  * pesos.get("CONSISTENCIA",  _PESOS_DEFECTO["CONSISTENCIA"])
    )

    # IUP acotado a [0, 100]
    iup = max(Decimal("0"), min(iup, Decimal("100")))

    return {
        "rm_id":            rm_id,
        "pais_id":          pais_id,
        "ciclo_id":         ciclo_id,
        "iup_productividad": round(prod, 4),
        "iup_comercial":    round(com, 4),
        "iup_coaching":     round(coach, 4),
        "iup_capacitacion": round(cap, 4),
        "iup_consistencia": round(cons, 4),
        "iup_total":        round(iup, 4),
        "pesos_aplicados":  {k: float(v) for k, v in pesos.items()},
    }


def _get_puntaje_productividad(db: Session, rm_id: int, pais_id: int, ciclo_id: int) -> Decimal:
    """
    Promedio de puntajes ya convertidos (vía DIM_IndicadorTabla en ETL)
    de todos los KPIs de Productividad del RM en el ciclo.
    """
    result = (
        db.query(func.avg(RendimientoComercial.puntaje))
        .join(Indicador, Indicador.id == RendimientoComercial.indicador_id)
        .filter(
            RendimientoComercial.rm_id     == rm_id,
            RendimientoComercial.pais_id   == pais_id,
            RendimientoComercial.ciclo_id  == ciclo_id,
            Indicador.modulo == "PRODUCTIVIDAD",
        )
        .scalar()
    )
    return Decimal(str(result or 0))
