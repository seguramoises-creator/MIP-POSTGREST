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
    """Convierte el score (0-100) a la nota escala 0-10."""
    return round(float(score) / 10.0, 2)


def _examen_de_intento(db: Session, intento) -> Examen | None:
    asig = db.query(AsignacionExamen).filter(
        AsignacionExamen.id == intento.asignacion_id).first()
    if asig is None:
        return None
    return db.query(Examen).filter(Examen.id == asig.examen_id).first()


def _nota_promedio_rm(db: Session, rm_id: int, ciclo_id: int) -> float | None:
    """Promedio de score/10 del último intento de cada examen marcado del RM en el ciclo."""
    examenes = db.query(Examen).filter(
        Examen.indicador_codigo == INDICADOR_EXAMEN,
        Examen.ciclo_id == ciclo_id,
    ).all()
    notas = []
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
            notas.append(nota_desde_score(ultimo.score))
    if not notas:
        return None
    return round(sum(notas) / len(notas), 2)


def _indicador_de_pais(db: Session, pais_codigo: str):
    return db.query(Indicador).filter(
        Indicador.codigo == INDICADOR_EXAMEN,
        Indicador.pais_codigo == pais_codigo,
    ).first()


def upsert_nota_rm(db: Session, rm, ciclo_id: int) -> float | None:
    """Calcula el promedio EVAL_CONOCIMIENTOS del RM en el ciclo y hace upsert
    (delete-then-insert) en FACT_ResultadoIndicador. NO recalcula ni hace commit
    (la consolidación dispara un único recálculo al final). Devuelve la nota o
    None si no aplica (sin indicador de país o sin nota)."""
    indicador = _indicador_de_pais(db, rm.pais_codigo)
    if indicador is None:
        logger.warning(f"Examen: no existe indicador {INDICADOR_EXAMEN} para país {rm.pais_codigo}")
        return None
    nota = _nota_promedio_rm(db, rm.id, ciclo_id)
    if nota is None:
        return None
    db.query(ResultadoIndicador).filter(
        ResultadoIndicador.rm_id == rm.id,
        ResultadoIndicador.indicador_id == indicador.id,
        ResultadoIndicador.ciclo_id == ciclo_id,
    ).delete(synchronize_session=False)
    db.add(ResultadoIndicador(
        rm_id=rm.id, indicador_id=indicador.id, ciclo_id=ciclo_id,
        pais_codigo=rm.pais_codigo, linea_id=rm.linea_id, gerente_id=rm.gerente_id,
        resultado_real=nota, activo=True,
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
