"""
SCGCPR — Servicio de Recálculo de KPIs e IUP
==============================================
Proceso que se ejecuta DESPUÉS de cargar FACT_KPI_RM via ETL.

Fases:
  1. Completar FACT_RendimientoComercial:
       - porcentaje_cumplimiento = valor_real * 100 (si escala=1)
       - puntaje = lookup en DIM_IndicadorTabla
  2. Calcular IUP por RM/ciclo agrupando por módulo con ponderaciones
  3. Generar/actualizar FACT_Ranking
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func
from loguru import logger

from app.models.hechos import RendimientoComercial, Ranking
from app.models.dimensiones import (
    RepresentanteMedico, Indicador, IndicadorTabla, Ciclo, Linea
)
from app.services.puntaje_service import convertir_a_puntaje


def recalcular_ciclo(
    db: Session,
    ciclo_id: int,
    pais_id: Optional[int] = None,
) -> dict:
    """
    Recalcula puntajes IUP y ranking para todos los RMs de un ciclo.
    Si pais_id es None, procesa todos los países del ciclo.
    """
    logger.info(f"RECALCULO: ciclo_id={ciclo_id}, pais_id={pais_id}")

    # ── Fase 1: Completar puntajes en FACT_RendimientoComercial ──────────
    filas_actualizadas = _completar_puntajes(db, ciclo_id, pais_id)
    logger.info(f"RECALCULO: {filas_actualizadas} filas de KPI actualizadas")

    # ── Fase 2: Calcular IUP y generar ranking ───────────────────────────
    rankings_generados = _generar_ranking(db, ciclo_id, pais_id)
    logger.info(f"RECALCULO: {rankings_generados} registros de ranking generados")

    return {
        "ciclo_id": ciclo_id,
        "filas_kpi_actualizadas": filas_actualizadas,
        "rankings_generados": rankings_generados,
    }


def _completar_puntajes(db: Session, ciclo_id: int, pais_id: Optional[int]) -> int:
    """
    Para cada fila de FACT_RendimientoComercial del ciclo:
    - Calcula porcentaje_cumplimiento (escala 0-100)
    - Calcula puntaje desde DIM_IndicadorTabla
    """
    q = db.query(RendimientoComercial, Indicador).join(
        Indicador, Indicador.id == RendimientoComercial.indicador_id
    ).filter(
        RendimientoComercial.ciclo_id == ciclo_id,
        RendimientoComercial.activo == True,
    )
    if pais_id:
        q = q.filter(RendimientoComercial.pais_id == pais_id)

    rows = q.all()
    actualizados = 0

    for rc, ind in rows:
        if rc.valor_real is None:
            continue

        valor_real = Decimal(str(rc.valor_real))

        # Convertir a escala 0-100 según escala del indicador
        # escala=1 → valor viene en 0-1, multiplicar por 100
        # escala=100 → valor ya en 0-100
        if ind.escala and int(ind.escala) == 1:
            valor_lookup = valor_real * Decimal("100")
        else:
            valor_lookup = valor_real

        # Calcular puntaje desde tabla de rangos
        puntaje = convertir_a_puntaje(db, ind.id, valor_lookup, rc.pais_id)

        rc.porcentaje_cumplimiento = valor_lookup
        rc.puntaje = puntaje
        # valor_meta: para KPIs de porcentaje la meta es 100%
        if rc.valor_meta is None:
            rc.valor_meta = Decimal("1.0") if ind.escala and int(ind.escala) == 1 else Decimal("100")

        actualizados += 1

    db.commit()
    return actualizados


def _generar_ranking(db: Session, ciclo_id: int, pais_id: Optional[int]) -> int:
    """
    Calcula IUP por RM y genera FACT_Ranking.
    """
    # Obtener combinaciones únicas rm+pais del ciclo
    q = db.query(
        RendimientoComercial.rm_id,
        RendimientoComercial.pais_id,
        RendimientoComercial.linea_id,
    ).filter(
        RendimientoComercial.ciclo_id == ciclo_id,
        RendimientoComercial.activo == True,
        RendimientoComercial.puntaje.isnot(None),
    ).distinct()

    if pais_id:
        q = q.filter(RendimientoComercial.pais_id == pais_id)

    combinaciones = q.all()

    if not combinaciones:
        logger.warning(f"RECALCULO: sin datos para ranking ciclo={ciclo_id}")
        return 0

    # Obtener ponderaciones de indicadores agrupadas por módulo
    pesos_modulo = _get_pesos_modulo(db, pais_id)
    logger.info(f"RECALCULO: pesos por módulo = {pesos_modulo}")

    resultados_iup = []

    for rm_id, p_id, linea_id in combinaciones:
        iup = _calcular_iup_rm(db, rm_id, p_id, ciclo_id, pesos_modulo)
        resultados_iup.append({
            "rm_id": rm_id,
            "pais_id": p_id,
            "linea_id": linea_id,
            "iup_total": iup["total"],
            "iup_productividad": iup["GESTION"],
            "iup_comercial": iup["RESULTADOS"],
            "iup_coaching": iup["COACHING"],
            "iup_capacitacion": iup["CAPACITACION"],
            "iup_consistencia": Decimal("0"),
        })

    if not resultados_iup:
        return 0

    # Ordenar por IUP total descendente y asignar posiciones
    resultados_iup.sort(key=lambda x: x["iup_total"], reverse=True)

    # Obtener posiciones anteriores para comparación
    anteriores = {
        r.rm_id: r.posicion
        for r in db.query(Ranking).filter(
            Ranking.ciclo_id == ciclo_id, Ranking.tipo_ranking == "MENSUAL"
        ).all()
    }

    ahora = datetime.now(timezone.utc)
    generados = 0

    for pos, r in enumerate(resultados_iup, start=1):
        # Elegible si IUP total > 0
        elegible = 1 if r["iup_total"] > Decimal("0") else 0
        pos_anterior = anteriores.get(r["rm_id"], pos)

        # Buscar o crear registro de ranking
        ranking = db.query(Ranking).filter(
            Ranking.rm_id == r["rm_id"],
            Ranking.ciclo_id == ciclo_id,
            Ranking.tipo_ranking == "MENSUAL",
        ).first()

        if not ranking:
            ranking = Ranking(
                pais_id=r["pais_id"],
                linea_id=r["linea_id"],
                rm_id=r["rm_id"],
                ciclo_id=ciclo_id,
                tipo_ranking="MENSUAL",
            )
            db.add(ranking)

        ranking.iup_total          = r["iup_total"]
        ranking.iup_productividad  = r["iup_productividad"]
        ranking.iup_comercial      = r["iup_comercial"]
        ranking.iup_coaching       = r["iup_coaching"]
        ranking.iup_capacitacion   = r["iup_capacitacion"]
        ranking.iup_consistencia   = r["iup_consistencia"]
        ranking.posicion           = pos
        ranking.posicion_anterior  = pos_anterior
        ranking.elegible           = elegible
        ranking.fecha_generacion   = ahora
        generados += 1

    db.commit()
    return generados


def _get_pesos_modulo(db: Session, pais_id: Optional[int]) -> dict:
    """
    Lee ponderaciones desde DIM_Indicador agrupadas por módulo.
    Retorna dict {modulo: peso_decimal}
    """
    q = db.query(
        Indicador.modulo,
        func.sum(Indicador.ponderacion_pct).label("total_pct"),
    ).filter(Indicador.activo == True, Indicador.ponderacion_pct > 0)

    if pais_id:
        q = q.filter(Indicador.pais_id == pais_id)

    rows = q.group_by(Indicador.modulo).all()

    if not rows:
        # Pesos por defecto
        return {
            "GESTION":     Decimal("0.40"),
            "RESULTADOS":  Decimal("0.30"),
            "COACHING":    Decimal("0.15"),
            "CAPACITACION": Decimal("0.15"),
        }

    total = sum(r.total_pct for r in rows) or Decimal("100")
    pesos = {r.modulo: Decimal(str(r.total_pct)) / Decimal(str(total)) for r in rows}

    # Garantizar módulos con valor 0 si no existen
    for m in ["GESTION", "RESULTADOS", "COACHING", "CAPACITACION"]:
        pesos.setdefault(m, Decimal("0"))

    return pesos


def _calcular_iup_rm(
    db: Session, rm_id: int, pais_id: int, ciclo_id: int, pesos: dict
) -> dict:
    """
    Calcula IUP para un RM agrupando puntajes por módulo.
    """
    # Promedio de puntajes por módulo
    rows = (
        db.query(
            Indicador.modulo,
            func.avg(RendimientoComercial.puntaje).label("puntaje_prom"),
        )
        .join(Indicador, Indicador.id == RendimientoComercial.indicador_id)
        .filter(
            RendimientoComercial.rm_id    == rm_id,
            RendimientoComercial.pais_id  == pais_id,
            RendimientoComercial.ciclo_id == ciclo_id,
            RendimientoComercial.puntaje.isnot(None),
        )
        .group_by(Indicador.modulo)
        .all()
    )

    puntajes = {r.modulo: Decimal(str(r.puntaje_prom or 0)) for r in rows}

    iup_total = Decimal("0")
    for modulo, peso in pesos.items():
        iup_total += puntajes.get(modulo, Decimal("0")) * peso

    # Normalizar a 0-1 si viene en 0-100
    if iup_total > Decimal("1"):
        iup_total = iup_total / Decimal("100")

    result = {m: Decimal("0") for m in ["GESTION", "RESULTADOS", "COACHING", "CAPACITACION"]}
    for modulo, puntaje in puntajes.items():
        val = puntaje / Decimal("100") if puntaje > Decimal("1") else puntaje
        result[modulo] = val

    result["total"] = min(iup_total, Decimal("1"))
    return result
