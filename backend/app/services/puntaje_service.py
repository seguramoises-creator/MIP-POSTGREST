"""
SCGCPR — Motor de Conversión KPI → Puntaje
Los rangos en DIM_IndicadorTabla son por (indicador_id, pais_codigo), por lo que
la búsqueda debe filtrar ambos para obtener el puntaje correcto por país.

Flujo:
  valor_real → normalizar según ESCALA → buscar rango en DIM_IndicadorTabla → retornar puntos

ESCALA = 1   → el valor ya es un porcentaje (0-100), se usa directo
ESCALA = 100 → el valor es un score directo (0-100), se usa directo
Los rangos en la tabla ya están expresados en la misma escala que el valor almacenado.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session
from loguru import logger

from app.models.dimensiones import IndicadorTabla, Indicador


def convertir_a_puntaje(
    db: Session,
    indicador_id: int,
    valor: Decimal,
    pais_codigo: Optional[str] = None,
) -> Decimal:
    """
    Busca el puntaje correspondiente a `valor` en DIM_IndicadorTabla
    para el indicador y país dados.

    - Si se provee pais_codigo, filtra por país (comportamiento correcto multi-país).
    - Si no hay tabla configurada para ese indicador+país → retorna el valor directo.
    - Rangos: [rango_desde, rango_hasta] inclusive.
    - Valor sobre el rango máximo → puntaje máximo de la tabla.
    - Valor bajo el rango mínimo → 0 puntos.
    """
    q = db.query(IndicadorTabla).filter(
        IndicadorTabla.indicador_id == indicador_id,
        IndicadorTabla.activo == True,
    )
    if pais_codigo is not None:
        q = q.filter(IndicadorTabla.pais_codigo == pais_codigo)

    tablas = q.order_by(IndicadorTabla.rango_desde.asc()).all()

    if not tablas:
        logger.debug(
            f"Indicador {indicador_id} / país {pais_codigo}: sin tabla de conversión — "
            "usando valor directo como puntaje"
        )
        return _clamp(valor, Decimal("0"), Decimal("100"))

    for tabla in tablas:
        if tabla.rango_desde <= valor <= tabla.rango_hasta:
            logger.debug(
                f"Indicador {indicador_id} / país {pais_codigo}: valor={valor} → "
                f"rango [{tabla.rango_desde}, {tabla.rango_hasta}] → puntos={tabla.puntos}"
            )
            return tabla.puntos

    if valor > tablas[-1].rango_hasta:
        logger.debug(
            f"Indicador {indicador_id} / país {pais_codigo}: valor={valor} supera máximo "
            f"{tablas[-1].rango_hasta} → puntos máximos={tablas[-1].puntos}"
        )
        return tablas[-1].puntos

    logger.debug(
        f"Indicador {indicador_id} / país {pais_codigo}: valor={valor} por debajo del mínimo "
        f"{tablas[0].rango_desde} → 0 puntos"
    )
    return Decimal("0")


def convertir_puntaje_por_codigo(
    db: Session,
    indicador_codigo: str,
    valor: Decimal,
    pais_codigo: Optional[str] = None,
) -> Decimal:
    """
    Versión que busca el indicador por código y país (útil en ETL donde se tiene
    el código del Excel, no el ID).
    """
    q = db.query(Indicador).filter(
        Indicador.codigo == indicador_codigo.upper(),
        Indicador.activo == True,
    )
    if pais_codigo is not None:
        q = q.filter(Indicador.pais_codigo == pais_codigo)

    indicador = q.first()
    if not indicador:
        logger.warning(
            f"Indicador '{indicador_codigo}' (país {pais_codigo}) no encontrado para conversión de puntaje"
        )
        return _clamp(valor, Decimal("0"), Decimal("100"))

    return convertir_a_puntaje(db, indicador.id, valor, pais_codigo)


def calcular_puntaje_coaching(
    cumplimiento_pct: Decimal,
    calificacion_calidad: Decimal,
    peso_cantidad: Decimal = Decimal("0.7"),
    peso_calidad: Decimal = Decimal("0.3"),
) -> Decimal:
    """
    Fórmula del motor coaching:
    resultado = (peso_cantidad × cumplimiento%) + (peso_calidad × calidad)
    Acotado a [0, 100].
    """
    resultado = (peso_cantidad * cumplimiento_pct) + (peso_calidad * calificacion_calidad)
    return _clamp(resultado, Decimal("0"), Decimal("100"))


def calcular_cumplimiento(valor_real: Decimal, valor_meta: Decimal) -> Decimal:
    """
    Calcula cumplimiento acotado a 100%.
    Evita divisiones por cero y valores > 100%.
    """
    if valor_meta <= 0:
        return Decimal("0")
    raw = (valor_real / valor_meta) * Decimal("100")
    return _clamp(raw, Decimal("0"), Decimal("100"))


def _clamp(value: Decimal, min_val: Decimal, max_val: Decimal) -> Decimal:
    """Restringe value al intervalo [min_val, max_val]."""
    return max(min_val, min(value, max_val))
