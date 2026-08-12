"""SCGCPR — Puente Exámenes → indicador EVAL_CONOCIMIENTOS del motor de Score.

Al entregar un examen marcado (`DimExamen.indicador_codigo == 'EVAL_CONOCIMIENTOS'`
con `ciclo_id`), si el evaluado es RM y el ciclo está abierto, calcula la nota
(promedio de score/10 del último intento de los exámenes marcados del RM en el
ciclo), hace upsert en `DW.FACT_ResultadoIndicador.resultado_real` y dispara el
recálculo — que aplica la parametrización de `DIM_IndicadorTabla` y regenera el
ranking. El factor NO se recalcula en Python (única fuente de verdad: el motor).
"""
from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import Examen, AsignacionExamen, IntentoExamen
from app.models.dimensiones import Indicador, RepresentanteMedico
from app.models.hechos import ResultadoIndicador
from app.services import recalculo_service

INDICADOR_EXAMEN = "EVAL_CONOCIMIENTOS"


def nota_desde_score(score) -> float:
    """Convierte el score (0-100) a la nota escala 0-10 — SOLO para
    presentación (consolidación, logs). NUNCA se escribe en
    `FACT_ResultadoIndicador`: ese indicador tiene `escala=100` (ver el
    CRITICAL del sub-proyecto 7 y `upsert_nota_rm` más abajo) — motor_calculo
    espera el mismo 0-100 que ya llegan CAPTURA_MANUAL/NOTA_EXTERNA, y
    escribir la nota 0-10 puntuaba una décima parte de lo que puntúan esos
    otros dos caminos."""
    return round(float(score) / 10.0, 2)


def _examen_de_intento(db: Session, intento) -> Examen | None:
    asig = db.query(AsignacionExamen).filter(
        AsignacionExamen.id == intento.asignacion_id).first()
    if asig is None:
        return None
    return db.query(Examen).filter(Examen.id == asig.examen_id).first()


def _ultimos_scores_rm(db: Session, rm_id: int, ciclo_id: int) -> list[float]:
    """Score 0-100 (escala nativa del examen) del último intento de cada
    examen marcado del RM en el ciclo. Fuente única de la que derivan tanto
    la nota de presentación (`_nota_promedio_rm`, 0-10) como el score que
    entra al KPI (`_score_promedio_rm`, 0-100) — una sola consulta, dos
    escalas de salida."""
    examenes = db.query(Examen).filter(
        Examen.indicador_codigo == INDICADOR_EXAMEN,
        Examen.ciclo_id == ciclo_id,
    ).all()
    scores = []
    for ex in examenes:
        ultimo = (
            db.query(IntentoExamen)
            .join(AsignacionExamen, AsignacionExamen.id == IntentoExamen.asignacion_id)
            .filter(
                AsignacionExamen.examen_id == ex.id,
                IntentoExamen.evaluado_rm_id == rm_id,
                IntentoExamen.fecha_fin.isnot(None),
            )
            .order_by(IntentoExamen.fecha_fin.desc())
            .first()
        )
        if ultimo is not None and ultimo.score is not None:
            scores.append(float(ultimo.score))
    return scores


def _nota_promedio_rm(db: Session, rm_id: int, ciclo_id: int) -> float | None:
    """Promedio, en escala 0-10, del último intento de cada examen marcado
    del RM en el ciclo. SOLO para presentación (`nota_promedio_equipo` de la
    consolidación, logs) — el KPI usa `_score_promedio_rm` (0-100)."""
    scores = _ultimos_scores_rm(db, rm_id, ciclo_id)
    if not scores:
        return None
    return round(sum(nota_desde_score(s) for s in scores) / len(scores), 2)


def _score_promedio_rm(db: Session, rm_id: int, ciclo_id: int) -> float | None:
    """Promedio, en escala 0-100, del último intento de cada examen marcado
    del RM en el ciclo. Esta es la escala que espera `FACT_ResultadoIndicador`
    (EVAL_CONOCIMIENTOS tiene `escala=100`, igual que CAPTURA_MANUAL/
    NOTA_EXTERNA) — ver `upsert_nota_rm`."""
    scores = _ultimos_scores_rm(db, rm_id, ciclo_id)
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def _indicador_de_pais(db: Session, pais_codigo: str):
    return db.query(Indicador).filter(
        Indicador.codigo == INDICADOR_EXAMEN,
        Indicador.pais_codigo == pais_codigo,
    ).first()


def upsert_nota_rm(db: Session, rm, ciclo_id: int) -> float | None:
    """Calcula el promedio EVAL_CONOCIMIENTOS del RM en el ciclo y hace upsert
    (delete-then-insert) en FACT_ResultadoIndicador. NO recalcula ni hace commit
    (la consolidación dispara un único recálculo al final).

    CRITICAL (revisión final del sub-proyecto 7): `FACT_ResultadoIndicador.
    resultado_real` recibe el SCORE 0-100 —la escala nativa del examen, la
    misma que ya escriben CAPTURA_MANUAL y NOTA_EXTERNA—, NO la nota 0-10.
    EVAL_CONOCIMIENTOS tiene `escala=100`, así que `motor_calculo_service`
    usa `resultado_real` DIRECTO, sin normalizar: escribir la nota 0-10 aquí
    puntuaba una décima parte de lo que puntúan los otros dos caminos para el
    mismo desempeño real (8.0 vs 80 puntos, sobre un indicador que pesa 10%
    del Score). Sigue devolviendo la NOTA 0-10 (no el score): es lo que
    consume `examen_consolidacion_service` para `nota_promedio_equipo`, la
    cifra que se le muestra al usuario — ese consumidor no cambia.
    Devuelve None si no aplica (sin indicador de país o sin nota)."""
    indicador = _indicador_de_pais(db, rm.pais_codigo)
    if indicador is None:
        logger.warning(f"Examen: no existe indicador {INDICADOR_EXAMEN} para país {rm.pais_codigo}")
        return None
    nota = _nota_promedio_rm(db, rm.id, ciclo_id)
    score = _score_promedio_rm(db, rm.id, ciclo_id)
    if nota is None or score is None:
        return None
    db.query(ResultadoIndicador).filter(
        ResultadoIndicador.rm_id == rm.id,
        ResultadoIndicador.indicador_id == indicador.id,
        ResultadoIndicador.ciclo_id == ciclo_id,
    ).delete(synchronize_session=False)
    db.add(ResultadoIndicador(
        rm_id=rm.id, indicador_id=indicador.id, ciclo_id=ciclo_id,
        pais_codigo=rm.pais_codigo, linea_id=rm.linea_id, gerente_id=rm.gerente_id,
        resultado_real=score, activo=True,
    ))
    return nota


def alimentar_eval_conocimientos(db: Session, intento) -> bool:
    """
    DEPRECADO como auto-feed: ya NO se llama en la entrega de exámenes. La nota
    EVAL_CONOCIMIENTOS solo entra al KPI vía examen_consolidacion_service cuando
    Capacitación consolida el (ciclo, país). Se conserva por compatibilidad de tests.

    Retorna True si alimentó, False si no aplicaba (no marcado / evaluado no RM /
    ciclo cerrado / sin nota). Nunca lanza por ciclo cerrado.
    """
    if intento.evaluado_tipo != "RM" or not intento.evaluado_rm_id:
        return False
    examen = _examen_de_intento(db, intento)
    if examen is None or examen.indicador_codigo != INDICADOR_EXAMEN or not examen.ciclo_id:
        return False
    ciclo_id = examen.ciclo_id
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        logger.info(f"Examen: ciclo {ciclo_id} cerrado — no se alimenta EVAL_CONOCIMIENTOS")
        return False
    rm = db.query(RepresentanteMedico).filter(
        RepresentanteMedico.id == intento.evaluado_rm_id).first()
    if rm is None:
        return False
    nota = upsert_nota_rm(db, rm, ciclo_id)
    if nota is None:
        return False
    db.commit()
    logger.info(f"Examen→EVAL_CONOCIMIENTOS: RM {rm.id} ciclo {ciclo_id} nota={nota}")
    recalculo_service.recalcular_ciclo(db, ciclo_id, rm.pais_codigo)
    return True
