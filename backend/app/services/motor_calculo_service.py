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


def _rankear(rows: list[dict]) -> list[dict]:
    """Asigna posicion_global, posicion_linea (desempate score DESC, rm_id ASC) y elegible."""
    orden = sorted(rows, key=lambda r: (-r["score_total"], r["rm_id"]))
    por_linea: dict = {}
    for i, r in enumerate(orden, start=1):
        r["posicion_global"] = i
        k = r["linea_id"]
        por_linea[k] = por_linea.get(k, 0) + 1
        r["posicion_linea"] = por_linea[k]
        r["elegible"] = r["score_total"] >= Decimal("90")
    return orden


def _categoria_de(cats, score: Decimal):
    """Primer DIM_CategoriaDesempeno (id ASC) cuyo rango [score_min, score_max] contiene el score."""
    for c in cats:
        lo = _dec(c.score_min) if c.score_min is not None else Decimal("-1")
        hi = _dec(c.score_max) if c.score_max is not None else Decimal("999999")
        if lo <= score <= hi:
            return c.id
    return None


def generar_ranking(db: Session, ciclo_id: int, pais_codigo=None) -> int:
    """Equivale a DW.sp_GenerarRankingCiclo: score integral por RM, categoría, posiciones
    (global/línea, desempate por rm_id), elegible ≥ 90; delete-then-insert de
    FACT_ScoreIntegralRM y FACT_RankingRM (MENSUAL). Devuelve nº de filas de ranking."""
    ahora = datetime.now(timezone.utc)
    q = (db.query(ResultadoIndicador, Indicador)
         .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
         .filter(ResultadoIndicador.ciclo_id == ciclo_id,
                 ResultadoIndicador.activo == True,  # noqa: E712
                 ResultadoIndicador.puntos_obtenidos.isnot(None)))
    if pais_codigo:
        q = q.filter(ResultadoIndicador.pais_codigo == pais_codigo)
    filas = q.all()
    if not filas:
        return 0

    # score por RM = SUM(puntos)*100 / SUM(ponderacion)
    acc: dict = {}
    for ri, ind in filas:
        a = acc.setdefault(ri.rm_id, {"pais_codigo": ri.pais_codigo, "puntos": Decimal(0), "pond": Decimal(0)})
        a["puntos"] += _dec(ri.puntos_obtenidos)
        a["pond"] += _dec(ind.ponderacion_pct)

    rms = {r.id: r for r in db.query(RepresentanteMedico).filter(
        RepresentanteMedico.id.in_(list(acc))).all()}
    cats = (db.query(CategoriaDesempeno).filter(CategoriaDesempeno.activo == True)  # noqa: E712
            .order_by(CategoriaDesempeno.id.asc()).all())
    rows = []
    for rm_id, a in acc.items():
        rm = rms.get(rm_id)
        score = Decimal(0) if a["pond"] == 0 else (a["puntos"] * D100 / a["pond"])
        score = _clamp(score, Decimal(0), D100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        rows.append({"rm_id": rm_id, "pais_codigo": a["pais_codigo"],
                     "linea_id": rm.linea_id if rm else None,
                     "gerente_id": rm.gerente_id if rm else None,
                     "score_total": score, "categoria_id": _categoria_de(cats, score)})
    rankeados = _rankear(rows)

    # posicion_anterior del ranking previo (MENSUAL)
    prevq = db.query(RankingRM.rm_id, RankingRM.posicion_global).filter(
        RankingRM.ciclo_id == ciclo_id, RankingRM.tipo_ranking == "MENSUAL")
    if pais_codigo:
        prevq = prevq.filter(RankingRM.pais_codigo == pais_codigo)
    anterior = dict(prevq.all())

    # delete-then-insert
    dels = db.query(ScoreIntegralRM).filter(ScoreIntegralRM.ciclo_id == ciclo_id)
    delr = db.query(RankingRM).filter(RankingRM.ciclo_id == ciclo_id,
                                      RankingRM.tipo_ranking == "MENSUAL")
    if pais_codigo:
        dels = dels.filter(ScoreIntegralRM.pais_codigo == pais_codigo)
        delr = delr.filter(RankingRM.pais_codigo == pais_codigo)
    dels.delete(synchronize_session=False)
    delr.delete(synchronize_session=False)

    n = 0
    for r in rankeados:
        db.add(ScoreIntegralRM(
            pais_codigo=r["pais_codigo"], linea_id=r["linea_id"], gerente_id=r["gerente_id"],
            rm_id=r["rm_id"], ciclo_id=ciclo_id, score_total=r["score_total"],
            categoria_id=r["categoria_id"], elegible_reconocimiento=r["elegible"], fecha_calculo=ahora))
        db.add(RankingRM(
            pais_codigo=r["pais_codigo"], linea_id=r["linea_id"], gerente_id=r["gerente_id"],
            rm_id=r["rm_id"], ciclo_id=ciclo_id, tipo_ranking="MENSUAL", score_total=r["score_total"],
            categoria_id=r["categoria_id"], posicion_global=r["posicion_global"],
            posicion_linea=r["posicion_linea"], posicion_anterior=anterior.get(r["rm_id"]),
            elegible=r["elegible"], fecha_generacion=ahora))
        n += 1
    db.commit()
    logger.info(f"Motor: ranking generado ciclo={ciclo_id} pais={pais_codigo} filas={n}")
    return n
