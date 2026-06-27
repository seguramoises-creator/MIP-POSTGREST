"""
SCGCPR — Motor de Ranking
FIX C-04: Implementa delete-then-regenerate (borra por ciclo+tipo+país
          antes de insertar) para evitar duplicados en cada ejecución.
FIX (jun-2026): la función generaba `nueva_generacion`, una variable que
          nunca se construía (bug latente — `bulk_insert_mappings` fallaba
          con NameError). Se reescribió el flujo para construir
          explícitamente los objetos RankingRM antes de insertarlos.

REGLA DE NEGOCIO — ciclo abierto (jun-2026): este motor también puede
disparar la regeneración de FACT_* calculadas (vía /ranking/generar), así
que aplica el mismo guard que recalculo_service: si el ciclo indicado está
cerrado, se aborta sin escribir nada — los ciclos cerrados son snapshots
históricos inmutables. Ver recalculo_service.validar_ciclo_abierto().

Flujo:
  1. Calcular score integral para cada RM activo del país (iup_service)
  2. Evaluar elegibilidad con reglas configuradas
  3. Ordenar por score descendente y asignar posiciones (global y por línea)
  4. DELETE registros anteriores del mismo ciclo/tipo/país (solo si abierto)
  5. INSERT nuevos registros con posición actualizada
  6. (Opcional) consolidar ranking de Gerentes de Distrito (FACT_RankingGerente)
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func
from loguru import logger

from app.db.database import SessionLocal
from app.models.dimensiones import RepresentanteMedico, Gerente
from app.models.hechos import RankingRM, RankingGerente
from app.services.iup_service import calcular_iup
from app.services.elegibilidad_service import evaluar_elegibilidad_rm
from app.services.recalculo_service import validar_ciclo_abierto, CicloCerradoError
from app.services import notification_service


def generar_ranking_task(
    pais_codigo: str,
    ciclo_id: Optional[int],
    tipo_ranking: str,
    usuario_id: Optional[int] = None,
):
    """
    Genera el ranking RM completo para un país/ciclo/tipo, y de paso
    consolida el ranking de Gerentes de Distrito del mismo ciclo.

    GUARD: si ciclo_id corresponde a un ciclo CERRADO, aborta sin tocar
    FACT_RankingRM/FACT_RankingGerente — regla de negocio "solo ciclo
    abierto" (ver recalculo_service.validar_ciclo_abierto).

    NOTA (CLAUDE.md §19): se ejecuta como BackgroundTask (desde
    POST /ranking/generar), así que crea su PROPIA sesión de BD con
    SessionLocal() y la cierra en `finally` — nunca reutiliza la sesión
    de la request, que puede estar cerrada cuando esta tarea corre.
    """
    tipo_ranking = tipo_ranking.upper()
    logger.info(
        f"Iniciando ranking {tipo_ranking} — "
        f"pais_codigo={pais_codigo}, ciclo_id={ciclo_id}"
    )

    db: Session = SessionLocal()
    try:
        if ciclo_id:
            try:
                validar_ciclo_abierto(db, ciclo_id)
            except CicloCerradoError as e:
                logger.warning(f"RANKING abortado — {e}")
                return
            except ValueError as e:
                logger.error(f"RANKING abortado — {e}")
                return

        rms = (
            db.query(RepresentanteMedico)
            .filter(
                RepresentanteMedico.pais_codigo == pais_codigo,
                RepresentanteMedico.activo == True,
            )
            .all()
        )

        if not rms:
            logger.warning(f"No hay RMs activos para pais_codigo={pais_codigo}")
            return

        resultados = []
        errores_rm = []

        for rm in rms:
            try:
                iup_data = calcular_iup(
                    db, rm_id=rm.id, pais_codigo=pais_codigo, ciclo_id=ciclo_id or 0
                )
                elig_data = evaluar_elegibilidad_rm(
                    db, rm_id=rm.id, pais_codigo=pais_codigo, ciclo_id=ciclo_id
                )
                resultados.append({
                    "rm_id":       rm.id,
                    "linea_id":    rm.linea_id,
                    "gerente_id":  rm.gerente_id,
                    "score_total": (Decimal(str(iup_data["score_total"])) * Decimal("100")
                                    if Decimal(str(iup_data["score_total"])) <= Decimal("1")
                                    else Decimal(str(iup_data["score_total"]))),
                    "elegible":    elig_data["elegible"],
                })
            except Exception as e:
                logger.error(f"Error procesando RM {rm.id} en ranking: {e}")
                errores_rm.append(rm.id)

        if not resultados:
            logger.warning(f"Ranking {tipo_ranking}: sin resultados calculables (pais={pais_codigo})")
            return

        # Ordenar por score descendente y asignar posiciones globales y por línea
        resultados.sort(key=lambda x: x["score_total"], reverse=True)
        for pos, r in enumerate(resultados, start=1):
            r["posicion_global"] = pos

        por_linea: dict = {}
        for r in resultados:
            por_linea.setdefault(r["linea_id"], []).append(r)
        for grupo in por_linea.values():
            grupo.sort(key=lambda x: x["score_total"], reverse=True)
            for pos, r in enumerate(grupo, start=1):
                r["posicion_linea"] = pos

        # Capturar posiciones anteriores ANTES de borrar (para variación)
        posiciones_anteriores = {
            rm_id: pos
            for rm_id, pos in db.query(RankingRM.rm_id, RankingRM.posicion_global)
            .filter(
                RankingRM.pais_codigo      == pais_codigo,
                RankingRM.tipo_ranking == tipo_ranking,
                RankingRM.ciclo_id     == ciclo_id,
            )
            .all()
        }

        # FIX C-04: borrar registros anteriores del mismo ciclo/tipo/país (delete-then-regenerate)
        deleted = (
            db.query(RankingRM)
            .filter(
                RankingRM.pais_codigo      == pais_codigo,
                RankingRM.tipo_ranking == tipo_ranking,
                RankingRM.ciclo_id     == ciclo_id,
            )
            .delete(synchronize_session=False)
        )
        logger.debug(
            f"Ranking {tipo_ranking} — {deleted} registros anteriores eliminados "
            f"(pais={pais_codigo}, ciclo={ciclo_id})"
        )

        ahora = datetime.now(timezone.utc)
        nueva_generacion = [
            RankingRM(
                pais_codigo=pais_codigo,
                linea_id=r["linea_id"],
                gerente_id=r["gerente_id"],
                rm_id=r["rm_id"],
                ciclo_id=ciclo_id,
                tipo_ranking=tipo_ranking,
                score_total=r["score_total"],
                posicion_global=r["posicion_global"],
                posicion_linea=r["posicion_linea"],
                posicion_anterior=posiciones_anteriores.get(r["rm_id"]),
                elegible=r["elegible"],
                fecha_generacion=ahora,
            )
            for r in resultados
        ]

        db.add_all(nueva_generacion)
        db.commit()
        logger.info(
            f"Ranking {tipo_ranking} generado: {len(nueva_generacion)} registros "
            f"(pais={pais_codigo}, ciclo={ciclo_id}, errores_rm={len(errores_rm)})"
        )

        if ciclo_id:
            _consolidar_ranking_gerentes(db, pais_codigo, ciclo_id)

        # Notificaciones por correo (CLAUDE.md §18 — "Notificaciones email").
        # No bloquea ni revierte el ranking si el envío falla — ver
        # notification_service (no-op silencioso si MAIL_SERVER="").
        try:
            notification_service.notificar_ranking_generado(
                db,
                pais_codigo=pais_codigo,
                ciclo_id=ciclo_id,
                tipo_ranking=tipo_ranking,
                resultados=resultados,
            )
        except Exception as e:
            logger.warning(f"No se pudieron enviar notificaciones de ranking: {e}")

    except Exception as e:
        db.rollback()
        logger.error(f"Error generando ranking: {e}")
    finally:
        db.close()


def _consolidar_ranking_gerentes(db: Session, pais_codigo: str, ciclo_id: int):
    """
    Genera FACT_RankingGerente promediando el score_total de los RMs de
    cada Gerente de Distrito en el ciclo (delete-then-regenerate, scoped
    a ciclo_id+pais_codigo — cubre el pendiente de CLAUDE.md §18).
    """
    filas = (
        db.query(
            RankingRM.gerente_id,
            func.avg(RankingRM.score_total).label("score_prom"),
        )
        .join(Gerente, Gerente.id == RankingRM.gerente_id)
        .filter(
            RankingRM.pais_codigo == pais_codigo,
            RankingRM.ciclo_id == ciclo_id,
            RankingRM.tipo_ranking == "MENSUAL",
            RankingRM.gerente_id.isnot(None),
            Gerente.tipo == "DISTRITO",
        )
        .group_by(RankingRM.gerente_id)
        .all()
    )

    if not filas:
        logger.debug(f"Ranking gerentes: sin GD con equipo en ciclo={ciclo_id}, pais={pais_codigo}")
        return

    resultados = sorted(
        [{"gerente_id": g, "score_total": Decimal(str(s or 0))} for g, s in filas],
        key=lambda x: x["score_total"], reverse=True,
    )
    for pos, r in enumerate(resultados, start=1):
        r["posicion"] = pos

    db.query(RankingGerente).filter(
        RankingGerente.pais_codigo == pais_codigo,
        RankingGerente.ciclo_id == ciclo_id,
    ).delete(synchronize_session=False)

    ahora = datetime.now(timezone.utc)
    for r in resultados:
        db.add(RankingGerente(
            pais_codigo=pais_codigo,
            gerente_id=r["gerente_id"],
            ciclo_id=ciclo_id,
            score_total=r["score_total"],
            posicion=r["posicion"],
            metodo_calculo="PROMEDIO_EQUIPO",
            fecha_generacion=ahora,
        ))

    db.commit()
    logger.info(f"Ranking Gerentes de Distrito generado: {len(resultados)} registros (pais={pais_codigo}, ciclo={ciclo_id})")
