"""
SCGCPR — Motor de Ranking
FIX C-04: Implementa UPSERT (delete por ciclo+tipo antes de insertar)
          para evitar duplicados en cada ejecución del ranking.

Flujo:
  1. Calcular IUP para cada RM activo del país
  2. Evaluar elegibilidad con reglas configuradas
  3. Ordenar por IUP descendente
  4. DELETE registros anteriores del mismo ciclo/tipo/pais
  5. INSERT nuevos registros con posición actualizada
  6. Registrar en auditoría
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from loguru import logger

from app.models.dimensiones import RepresentanteMedico
from app.models.hechos import Ranking, Auditoria
from app.services.iup_service import calcular_iup
from app.services.elegibilidad_service import evaluar_elegibilidad_rm


def generar_ranking_task(
    db: Session,
    pais_id: int,
    ciclo_id: Optional[int],
    tipo_ranking: str,
    usuario_id: int,
):
    """
    Genera el ranking completo para un país/ciclo/tipo.
    FIX C-04: Elimina registros anteriores antes de insertar (UPSERT semántico).
    """
    tipo_ranking = tipo_ranking.upper()
    logger.info(
        f"Iniciando ranking {tipo_ranking} — "
        f"pais_id={pais_id}, ciclo_id={ciclo_id}"
    )

    try:
        rms = (
            db.query(RepresentanteMedico)
            .filter(
                RepresentanteMedico.pais_id == pais_id,
                RepresentanteMedico.activo == True,
            )
            .all()
        )

        if not rms:
            logger.warning(f"No hay RMs activos para pais_id={pais_id}")
            return

        resultados = []
        errores_rm = []

        for rm in rms:
            try:
                iup_data = calcular_iup(
                    db, rm_id=rm.id, pais_id=pais_id, ciclo_id=ciclo_id or 0
                )
                elig_data = evaluar_elegibilidad_rm(
                    db, rm_id=rm.id, pais_id=pais_id, ciclo_id=ciclo_id
                )
                resultados.append({
                    "rm_id":           rm.id,
                    "iup_total":       iup_data["iup_total"],
                    "iup_productividad": iup_data["iup_productividad"],
                    "iup_comercial":   iup_data["iup_comercial"],
                    "iup_coaching":    iup_data["iup_coaching"],
                    "iup_capacitacion": iup_data["iup_capacitacion"],
                    "iup_consistencia": iup_data["iup_consistencia"],
                    "elegible":        elig_data["elegible"],
                })
            except Exception as e:
                logger.error(f"Error procesando RM {rm.id} en ranking: {e}")
                errores_rm.append(rm.id)

        # Ordenar por IUP descendente
        resultados.sort(key=lambda x: x["iup_total"], reverse=True)

        # Capturar posiciones anteriores ANTES de borrar
        posiciones_anteriores = {
            r.rm_id: r.posicion
            for r in db.query(Ranking.rm_id, Ranking.posicion)
            .filter(
                Ranking.pais_id      == pais_id,
                Ranking.tipo_ranking == tipo_ranking,
                Ranking.ciclo_id     == ciclo_id,
            )
            .all()
        }

        # FIX C-04: Borrar registros anteriores del mismo ciclo/tipo/pais
        deleted = (
            db.query(Ranking)
            .filter(
                Ranking.pais_id      == pais_id,
                Ranking.tipo_ranking == tipo_ranking,
                Ranking.ciclo_id     == ciclo_id,
            )
            .delete(synchronize_session=False)
        )
        logger.debug(
            f"Ranking {tipo_ranking} — {deleted} registros anteriores eliminados "
            f"(pais={pais_id}, ciclo={ciclo_id})"
        )

        # Insertar nueva generacion
        db.bulk_insert_mappings(Ranking, [r.__dict__ for r in nueva_generacion])
        db.commit()
        logger.info(f"Ranking {tipo_ranking} generado: {len(nueva_generacion)} registros (pais={pais_id}, ciclo={ciclo_id})")

    except Exception as e:
        db.rollback()
        logger.error(f"Error generando ranking: {e}")
        raise
