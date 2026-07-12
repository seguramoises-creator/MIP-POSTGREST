"""
SCGCPR — Servicio de Recálculo de KPIs, Score Integral y Ranking
================================================================
Proceso que se ejecuta DESPUÉS de cargar FACT_ResultadoIndicador vía ETL
(o al disparar manualmente POST /ranking/generar).

REGLA DE NEGOCIO CRÍTICA — alcance por ciclo (confirmada por el usuario,
jun-2026): el recálculo SOLO opera sobre el CICLO ABIERTO de cada país
(DIM_Ciclo.cerrado = False). Los ciclos cerrados son snapshots históricos
inmutables — el motor nunca los toca, ni siquiera si llegan datos nuevos
o correcciones para ellos.

ARQUITECTURA — cálculo 100% en Python (jul-2026): para dejar el core
agnóstico de base de datos, todo el motor de cálculo —puntajes, score
integral y ranking— vive en `motor_calculo_service`, parametrizado por
país + ciclo (los mismos valores que el usuario selecciona en la pantalla
"Calcular IUP y Ranking"):

  - motor_calculo_service.completar_puntajes   → completa FACT_ResultadoIndicador
  - motor_calculo_service.generar_ranking      → borra+regenera Score Integral y Ranking
  - motor_calculo_service.recalcular_ciclo_py  → orquestador (aplica el guard de
                                                 ciclo abierto y ejecuta los dos anteriores)

Este módulo actúa como capa de orquestación/traducción: valida el contrato
de negocio hacia el resto de la app (RBAC, logging, auditoría, forma del dict
de respuesta esperado por el endpoint /etl/recalcular y por
ranking_service/reconocimiento_service) y delega el CÁLCULO —incluyendo el
patrón "borrar e integrar todo de nuevo" (delete-then-regenerate, nunca upsert
parcial) y el guard de "solo ciclo abierto"— en motor_calculo_service.

`validar_ciclo_abierto` se conserva: la usan ranking_service y
reconocimiento_service como guard previo independiente del SP (p.ej. para
no disparar el recálculo en absoluto si el ciclo ya está cerrado).
"""
from typing import Optional

from sqlalchemy.orm import Session
from loguru import logger

from app.models.dimensiones import Ciclo


class CicloCerradoError(Exception):
    """Se intentó recalcular un ciclo que ya está cerrado (cerrado=True)."""
    pass


def validar_ciclo_abierto(db: Session, ciclo_id: int) -> Ciclo:
    """
    Guard central de la regla "solo ciclo abierto": obtiene el ciclo y
    verifica que NO esté cerrado. Si está cerrado, levanta
    CicloCerradoError — el llamador debe capturarla y abortar el
    recálculo sin tocar ninguna FACT_* calculada.

    Reutilizada por recalculo_service y ranking_service para garantizar
    que ningún camino de cálculo pueda escribir sobre un ciclo cerrado.
    """
    ciclo = db.query(Ciclo).filter(Ciclo.id == ciclo_id).first()
    if not ciclo:
        raise ValueError(f"Ciclo ID={ciclo_id} no encontrado")
    if ciclo.cerrado:
        raise CicloCerradoError(
            f"Ciclo '{ciclo.nombre}' (id={ciclo_id}) está CERRADO — "
            f"el recálculo no puede modificar ciclos cerrados (snapshot histórico inmutable)"
        )
    return ciclo


def recalcular_ciclo(
    db: Session,
    ciclo_id: int,
    pais_codigo: Optional[str] = None,
) -> dict:
    """
    Orquesta el recálculo de puntajes, score integral y ranking delegando en
    `motor_calculo_service.recalcular_ciclo_py` (Python), parametrizado por
    (ciclo_id, pais_codigo): los mismos valores que el usuario elige en la
    pantalla "Calcular IUP y Ranking". Si pais_codigo es None, se procesan
    todos los países del ciclo.

    El motor aplica internamente el guard "solo ciclo abierto"
    (`validar_ciclo_abierto`/`CicloCerradoError`) y el patrón "borrar e integrar
    todo de nuevo" (delete-then-regenerate). Esta función conserva el contrato
    de dict que consume el endpoint `/etl/recalcular/{ciclo_id}` y el frontend
    (ETL.tsx): `{ciclo_id, abortado, motivo?, filas_kpi_actualizadas,
    rankings_generados}`.
    """
    from app.services import motor_calculo_service
    return motor_calculo_service.recalcular_ciclo_py(db, ciclo_id, pais_codigo)
