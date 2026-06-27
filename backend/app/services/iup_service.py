"""
SCGCPR — Motor IUP / Score Integral del RM
FIX C-02: Los pesos se leen desde DIM_Indicador.peso_iup en BD,
          NO desde constantes hardcodeadas.
FIX W-02: Puntaje comercial pondera solo los componentes disponibles
          (no penaliza si EVO IR no fue cargado en el ciclo).
FIX W-08: Consistencia de RMs nuevos usa 0 como base neutral en lugar
          de 50, para evitar ventaja artificial sobre RMs con historial.

REDISEÑO (jun-2026): la fuente de productividad pasó de
FACT_RendimientoComercial (campo `puntaje`) a FACT_ResultadoIndicador
(campo `puntos_obtenidos`) — ver app.models.hechos.ResultadoIndicador.
El nombre "IUP" se conserva como métrica interna (módulos/pesos), aunque
la salida consolidada ahora se persiste como FACT_ScoreIntegralRM.score_total
en lugar de FACT_Ranking.iup_total.

Fórmula configurable:
  Score = Σ (puntaje_modulo × peso_modulo)
  donde los pesos provienen de DIM_Indicador.peso_iup agrupados por módulo.
"""
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from loguru import logger

from app.models.hechos import ResultadoIndicador, Ventas, EvoIR, Coaching, CapacitacionFact, ScoreIntegralRM
from app.models.dimensiones import Indicador, Ciclo

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
        logger.debug("SCORE: sin pesos en DIM_Indicador — usando pesos por defecto")
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

    logger.debug(f"SCORE pesos leídos de BD: {pesos_norm}")
    return pesos_norm


def calcular_iup(
    db: Session,
    rm_id: int,
    pais_codigo: str,
    ciclo_id: int,
) -> dict:
    """
    Calcula el score integral completo (antes "IUP") para un RM en un ciclo dado.
    Los pesos se obtienen desde DIM_Indicador en BD (FIX C-02).

    Mantiene las claves iup_* en la respuesta por compatibilidad con el resto
    del sistema (ranking_service, elegibilidad, dashboards): son los
    componentes por módulo del score consolidado, no una tabla "FACT_IUP".
    """
    logger.debug(f"Calculando score integral — rm_id={rm_id}, ciclo_id={ciclo_id}")

    pesos = _obtener_pesos(db)

    prod  = _get_puntaje_productividad(db, rm_id, pais_codigo, ciclo_id)
    com   = _get_puntaje_comercial(db, rm_id, pais_codigo, ciclo_id)
    coach = _get_puntaje_coaching(db, rm_id, pais_codigo, ciclo_id)
    cap   = _get_puntaje_capacitacion(db, rm_id, pais_codigo, ciclo_id)
    cons  = _get_puntaje_consistencia(db, rm_id, pais_codigo, ciclo_id)

    score = (
        prod  * pesos.get("PRODUCTIVIDAD", _PESOS_DEFECTO["PRODUCTIVIDAD"]) +
        com   * pesos.get("COMERCIAL",     _PESOS_DEFECTO["COMERCIAL"])     +
        coach * pesos.get("COACHING",      _PESOS_DEFECTO["COACHING"])      +
        cap   * pesos.get("CAPACITACION",  _PESOS_DEFECTO["CAPACITACION"])  +
        cons  * pesos.get("CONSISTENCIA",  _PESOS_DEFECTO["CONSISTENCIA"])
    )

    # Score acotado a [0, 100]
    score = max(Decimal("0"), min(score, Decimal("100")))

    return {
        "rm_id":            rm_id,
        "pais_codigo":          pais_codigo,
        "ciclo_id":         ciclo_id,
        "iup_productividad": round(prod, 4),
        "iup_comercial":    round(com, 4),
        "iup_coaching":     round(coach, 4),
        "iup_capacitacion": round(cap, 4),
        "iup_consistencia": round(cons, 4),
        "iup_total":        round(score, 4),
        "score_total":      round(score, 4),
        "pesos_aplicados":  {k: float(v) for k, v in pesos.items()},
    }


def _get_puntaje_productividad(db: Session, rm_id: int, pais_codigo: str, ciclo_id: int) -> Decimal:
    """
    Promedio de puntos ya convertidos (vía DIM_IndicadorTabla en el recálculo)
    de todos los KPIs de Productividad del RM en el ciclo.
    Fuente: FACT_ResultadoIndicador.puntos_obtenidos (antes RendimientoComercial.puntaje).
    """
    result = (
        db.query(func.avg(ResultadoIndicador.puntos_obtenidos))
        .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
        .filter(
            ResultadoIndicador.rm_id     == rm_id,
            ResultadoIndicador.pais_codigo   == pais_codigo,
            ResultadoIndicador.ciclo_id  == ciclo_id,
            ResultadoIndicador.activo    == True,
            Indicador.modulo == "PRODUCTIVIDAD",
        )
        .scalar()
    )
    return Decimal(str(result or 0))


def _get_puntaje_comercial(db: Session, rm_id: int, pais_codigo: str, ciclo_id: int) -> Decimal:
    """
    FIX W-02: promedia solo los componentes comerciales que sí tienen datos
    cargados en el ciclo (Ventas y/o EvoIR), sin penalizar al RM por
    componentes ausentes.
    """
    componentes = []

    venta = (
        db.query(func.avg(Ventas.puntaje))
        .filter(Ventas.rm_id == rm_id, Ventas.pais_codigo == pais_codigo, Ventas.ciclo_id == ciclo_id)
        .scalar()
    )
    if venta is not None:
        componentes.append(Decimal(str(venta)))

    evoir = (
        db.query(func.avg(EvoIR.puntaje))
        .filter(EvoIR.rm_id == rm_id, EvoIR.pais_codigo == pais_codigo, EvoIR.ciclo_id == ciclo_id)
        .scalar()
    )
    if evoir is not None:
        componentes.append(Decimal(str(evoir)))

    if not componentes:
        return Decimal("0")
    return sum(componentes) / Decimal(len(componentes))


def _get_puntaje_coaching(db: Session, rm_id: int, pais_codigo: str, ciclo_id: int) -> Decimal:
    result = (
        db.query(func.avg(Coaching.puntaje))
        .filter(Coaching.rm_id == rm_id, Coaching.pais_codigo == pais_codigo, Coaching.ciclo_id == ciclo_id)
        .scalar()
    )
    return Decimal(str(result or 0))


def _get_puntaje_capacitacion(db: Session, rm_id: int, pais_codigo: str, ciclo_id: int) -> Decimal:
    result = (
        db.query(func.avg(CapacitacionFact.puntaje))
        .filter(
            CapacitacionFact.rm_id == rm_id,
            CapacitacionFact.pais_codigo == pais_codigo,
            CapacitacionFact.ciclo_id == ciclo_id,
        )
        .scalar()
    )
    return Decimal(str(result or 0))


def _get_puntaje_consistencia(db: Session, rm_id: int, pais_codigo: str, ciclo_id: int) -> Decimal:
    """
    CLAUDE.md §18 "IUP consistencia completo": componente de consistencia
    calculado como el promedio del score consolidado
    (FACT_ScoreIntegralRM.score_total) de los últimos 3 ciclos PREVIOS del
    RM — ordenados cronológicamente (DIM_Ciclo.anio/numero descendente),
    excluyendo el ciclo que se está calculando.

    Reglas:
      - Si tiene 3 o más ciclos con historial -> promedio de los 3 más recientes.
      - Si tiene 1-2 ciclos -> promedio de los disponibles.
      - Si no tiene historial (RM nuevo) -> 0 (base neutral, FIX W-08:
        evita ventaja artificial de un RM nuevo frente a uno con trayectoria).

    Nota: se lee de FACT_ScoreIntegralRM (no de FACT_RankingRM) porque es la
    tabla que persiste el score consolidado por RM/ciclo de forma
    independiente del tipo de ranking — la fuente correcta de "historial".
    """
    rows = (
        db.query(ScoreIntegralRM.score_total)
        .join(Ciclo, Ciclo.id == ScoreIntegralRM.ciclo_id)
        .filter(
            ScoreIntegralRM.rm_id    == rm_id,
            ScoreIntegralRM.pais_codigo  == pais_codigo,
            ScoreIntegralRM.ciclo_id != ciclo_id,
        )
        .order_by(Ciclo.anio.desc(), Ciclo.numero.desc())
        .limit(3)
        .all()
    )

    if not rows:
        logger.debug(f"CONSISTENCIA: RM {rm_id} sin historial previo — usando base neutral 0")
        return Decimal("0")

    valores = [Decimal(str(r[0] or 0)) for r in rows]
    promedio = sum(valores) / Decimal(len(valores))
    logger.debug(
        f"CONSISTENCIA: RM {rm_id} — {len(valores)} ciclo(s) previos, "
        f"promedio={promedio}"
    )
    return promedio
