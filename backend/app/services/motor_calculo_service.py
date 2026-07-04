"""SCGCPR — Motor de cálculo Score/Ranking en Python (reemplaza los SPs DW.*).

Aritmética con Decimal para igualar exactamente al T-SQL original.
Verificado por caracterización (tests/test_caracterizacion_motor.py).
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from loguru import logger
from sqlalchemy.orm import Session

from app.models.hechos import ResultadoIndicador, ScoreIntegralRM, RankingRM
from app.models.dimensiones import Indicador, MetaIndicador, RepresentanteMedico, CategoriaDesempeno
from app.services.recalculo_service import validar_ciclo_abierto, CicloCerradoError

D100 = Decimal("100")


def _clamp(v: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return lo if v < lo else hi if v > hi else v


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _calc_puntajes_filas(pairs) -> int:
    """Muta cada ResultadoIndicador con resultado_porcentaje/puntos_obtenidos/fecha_calculo.
    Puro (sin DB) para poder testearlo. Devuelve nº de filas."""
    ahora = datetime.now(timezone.utc)
    n = 0
    for ri, ind in pairs:
        real = _dec(ri.resultado_real)
        valor_pct = real * D100 if int(ind.escala) == 1 else real
        cumpl = _clamp(valor_pct, Decimal(0), D100)
        ri.resultado_porcentaje = cumpl
        ri.puntos_obtenidos = (cumpl / D100) * _dec(ind.ponderacion_pct)
        ri.fecha_calculo = ahora
        n += 1
    return n


def completar_puntajes(db: Session, ciclo_id: int, pais_codigo=None) -> int:
    """Equivale a DW.sp_CompletarPuntajesCiclo: completa resultado_porcentaje,
    puntos_obtenidos y (con DIM_MetaIndicador) factor_aplicado/puntos_maximos/porcentaje_logro."""
    q = (db.query(ResultadoIndicador, Indicador)
         .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
         .filter(ResultadoIndicador.ciclo_id == ciclo_id,
                 ResultadoIndicador.activo == True,  # noqa: E712
                 ResultadoIndicador.resultado_real.isnot(None)))
    if pais_codigo:
        q = q.filter(ResultadoIndicador.pais_codigo == pais_codigo)
    pairs = q.all()
    n = _calc_puntajes_filas(pairs)

    # 2ª pasada: metas (factor, puntos_maximos, porcentaje_logro)
    metas = {m.indicador_id: m for m in
             db.query(MetaIndicador).filter(MetaIndicador.activo == True).all()}  # noqa: E712
    for ri, _ind in pairs:
        m = metas.get(ri.indicador_id)
        if m is None:
            continue
        ri.factor_aplicado = m.peso
        ri.puntos_maximos = m.puntaje_maximo
        real = _dec(ri.resultado_real)
        base = None
        if m.meta_100 is not None:
            base = _dec(m.meta_100)
        elif m.objetivo is not None:
            base = _dec(m.objetivo)
        if base is not None:
            ri.porcentaje_logro = (Decimal(0) if base == 0
                                   else _clamp((real / base) * D100, Decimal("-1e9"), D100))
    db.commit()
    logger.info(f"Motor: puntajes completados ciclo={ciclo_id} pais={pais_codigo} filas={n}")
    return n
