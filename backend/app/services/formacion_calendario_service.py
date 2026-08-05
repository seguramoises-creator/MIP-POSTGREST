"""Calendario de Coaching (§7).

Consume el cuadrante LSII vigente (FACT_EvaluacionReceptividad) — NO lo recalcula —
y sugiere una frecuencia de acompañamiento por RM, repartida en el ciclo. El GD
edita y publica. Es planeación; la ejecución del coaching vive en Coaching MORE.
"""
from math import ceil

from sqlalchemy.orm import Session

from app.models.formacion import ParametroFrecuenciaLSII

CUADRANTES: tuple[str, ...] = ("D1", "D2", "D3", "D4")

#: Arranque del §7.2 (ilustrativo, punto abierto 4): a menor desarrollo, más
#: acompañamiento. Editable por país en ParametroFrecuenciaLSII.
FRECUENCIA_DEFECTO: dict[str, int] = {"D1": 4, "D2": 3, "D3": 2, "D4": 1}


def frecuencias(db: Session, pais_codigo: str) -> dict[str, int]:
    """Los valores de arranque, con las sobrescrituras del país."""
    valores = dict(FRECUENCIA_DEFECTO)
    for p in (db.query(ParametroFrecuenciaLSII)
              .filter(ParametroFrecuenciaLSII.pais_codigo == pais_codigo).all()):
        if p.cuadrante in valores:
            valores[p.cuadrante] = int(p.visitas_por_ciclo)
    return valores


def fijar_frecuencia(db: Session, pais_codigo: str, cuadrante: str, visitas: int,
                     descripcion: str | None = None) -> ParametroFrecuenciaLSII:
    if cuadrante not in CUADRANTES:
        raise ValueError(f"Cuadrante inválido: {cuadrante}. Válidos: {', '.join(CUADRANTES)}.")
    if visitas < 0:
        raise ValueError("visitas_por_ciclo no puede ser negativo.")
    p = (db.query(ParametroFrecuenciaLSII)
         .filter(ParametroFrecuenciaLSII.pais_codigo == pais_codigo,
                 ParametroFrecuenciaLSII.cuadrante == cuadrante).first())
    if p is None:
        p = ParametroFrecuenciaLSII(pais_codigo=pais_codigo, cuadrante=cuadrante,
                                    visitas_por_ciclo=visitas, descripcion=descripcion)
        db.add(p)
    else:
        p.visitas_por_ciclo = visitas
        if descripcion:
            p.descripcion = descripcion
    db.commit()
    db.refresh(p)
    return p
