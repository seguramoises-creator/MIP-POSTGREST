"""Ranking de Formación (§8).

Los puntos que un representante acumula por formarse: certificaciones, exámenes,
refuerzo de memoria y avance de su ruta de inducción. Se guardan los cuatro
componentes por separado (§8.2) para que el RM vea DE DÓNDE sale su posición.

QUÉ NO HACE ESTE MÓDULO
------------------------
No toca el Score Integral ni el ranking oficial (`motor_calculo_service`): este
ranking es motivacional y aditivo. Cambiar el Score redefiniría premios,
comisiones y la comparabilidad del histórico de todos los representantes, que es
justo lo que se decidió evitar.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.dimensiones import CapacitacionDim, Ciclo, RepresentanteMedico
from app.models.exam_models import IntentoExamen
from app.models.formacion import (
    OnboardingAsignacion, OnboardingPasoProgreso, ParametroFormacion,
    RankingFormacionPuntos, RefuerzoCampana, RefuerzoRespuesta,
    RefuerzoRondaProgramada,
)
from app.models.hechos import CapacitacionFact

#: Valores de arranque. Cualquiera se sobrescribe por país escribiendo una fila
#: en `formacion.ParametroFormacion`, sin tocar código.
PESOS_DEFECTO: dict[str, float] = {
    "ranking_puntos_certificacion": 50.0,
    "ranking_puntos_examen": 30.0,
    "ranking_puntos_paso_onboarding": 5.0,
    "ranking_bono_ruta_completa": 25.0,
}


def pesos(db: Session, pais_codigo: str) -> dict[str, float]:
    """Los de arranque, con las sobrescrituras que haya configurado el país."""
    valores = dict(PESOS_DEFECTO)
    for p in (db.query(ParametroFormacion)
              .filter(ParametroFormacion.pais_codigo == pais_codigo).all()):
        if p.clave in valores:
            valores[p.clave] = float(p.valor)
    return valores


def fijar_peso(db: Session, pais_codigo: str, clave: str, valor: float,
               descripcion: str | None = None) -> ParametroFormacion:
    if clave not in PESOS_DEFECTO:
        raise ValueError(
            f"Peso desconocido: {clave}. Válidos: {', '.join(sorted(PESOS_DEFECTO))}.")
    p = (db.query(ParametroFormacion)
         .filter(ParametroFormacion.pais_codigo == pais_codigo,
                 ParametroFormacion.clave == clave).first())
    if p is None:
        p = ParametroFormacion(pais_codigo=pais_codigo, clave=clave,
                               valor=Decimal(str(valor)), descripcion=descripcion)
        db.add(p)
    else:
        p.valor = Decimal(str(valor))
        if descripcion:
            p.descripcion = descripcion
    db.commit()
    db.refresh(p)
    return p


def _dia_siguiente(d: date) -> date:
    """`DIM_Ciclo.fecha_fin` es un DATE y los eventos son DATETIME: comparar con
    `<= fecha_fin` dejaría fuera todo lo ocurrido ese último día después de las
    00:00. Se compara contra el día siguiente en su lugar."""
    from datetime import timedelta
    return d + timedelta(days=1)


def _puntos_certificacion(db: Session, rm_id: int, ciclo: Ciclo, peso: float) -> int:
    n = (db.query(CapacitacionFact)
         .join(CapacitacionDim, CapacitacionFact.capacitacion_id == CapacitacionDim.id)
         .filter(CapacitacionFact.rm_id == rm_id,
                 CapacitacionFact.ciclo_id == ciclo.id,
                 CapacitacionFact.aprobado.is_(True),
                 CapacitacionDim.tipo == "CERTIFICACION")
         .count())
    return int(n * peso)


def _puntos_examenes(db: Session, rm_id: int, ciclo: Ciclo, peso: float) -> int:
    """Atribución por fecha: `IntentoExamen` no guarda ciclo.

    Se usa `fecha_fin` (cuándo terminó el intento) porque el mérito es haberlo
    aprobado; los intentos abandonados (sin `fecha_fin`) no cuentan.
    """
    n = (db.query(IntentoExamen)
         .filter(IntentoExamen.evaluado_rm_id == rm_id,
                 IntentoExamen.aprobado.is_(True),
                 IntentoExamen.fecha_fin.isnot(None),
                 IntentoExamen.fecha_fin >= ciclo.fecha_inicio,
                 IntentoExamen.fecha_fin < _dia_siguiente(ciclo.fecha_fin))
         .count())
    return int(n * peso)


def _puntos_refuerzo(db: Session, rm_id: int, ciclo: Ciclo) -> int:
    """Suma los puntos ya calculados por §10.6 — sin multiplicador propio.

    Solo cuentan las campañas atribuidas a este ciclo: `RefuerzoCampana.ciclo_id`
    es nullable y una campaña sin ciclo no pertenece a ninguno.
    """
    filas = (db.query(RefuerzoRespuesta)
             .join(RefuerzoRondaProgramada,
                   RefuerzoRespuesta.ronda_id == RefuerzoRondaProgramada.id)
             .join(RefuerzoCampana,
                   RefuerzoRondaProgramada.campana_id == RefuerzoCampana.id)
             .filter(RefuerzoRespuesta.rm_id == rm_id,
                     RefuerzoCampana.ciclo_id == ciclo.id)
             .all())
    return int(sum(f.puntos_obtenidos or 0 for f in filas))


def _puntos_onboarding(db: Session, rm_id: int, ciclo: Ciclo,
                       peso_paso: float, bono_ruta: float) -> int:
    """Pasos completados dentro del ciclo, más el bono si la ruta se cerró aquí."""
    limite = _dia_siguiente(ciclo.fecha_fin)
    pasos = (db.query(OnboardingPasoProgreso)
             .join(OnboardingAsignacion,
                   OnboardingPasoProgreso.asignacion_id == OnboardingAsignacion.id)
             .filter(OnboardingAsignacion.rm_id == rm_id,
                     OnboardingPasoProgreso.completado.is_(True),
                     OnboardingPasoProgreso.completado_en.isnot(None),
                     OnboardingPasoProgreso.completado_en >= ciclo.fecha_inicio,
                     OnboardingPasoProgreso.completado_en < limite)
             .count())
    rutas = (db.query(OnboardingAsignacion)
             .filter(OnboardingAsignacion.rm_id == rm_id,
                     OnboardingAsignacion.completada_en.isnot(None),
                     OnboardingAsignacion.completada_en >= ciclo.fecha_inicio,
                     OnboardingAsignacion.completada_en < limite)
             .count())
    return int(pasos * peso_paso + rutas * bono_ruta)


def calcular_componentes(db: Session, rm_id: int, ciclo: Ciclo,
                         pesos_pais: dict[str, float]) -> dict:
    """Los cuatro componentes del §8.2 y su total, para un RM en un ciclo."""
    cert = _puntos_certificacion(db, rm_id, ciclo,
                                 pesos_pais["ranking_puntos_certificacion"])
    exam = _puntos_examenes(db, rm_id, ciclo, pesos_pais["ranking_puntos_examen"])
    ref = _puntos_refuerzo(db, rm_id, ciclo)
    onb = _puntos_onboarding(db, rm_id, ciclo,
                             pesos_pais["ranking_puntos_paso_onboarding"],
                             pesos_pais["ranking_bono_ruta_completa"])
    return {"puntos_certificacion": cert, "puntos_examenes": exam,
            "puntos_refuerzo": ref, "puntos_onboarding": onb,
            "puntos_total": cert + exam + ref + onb}
