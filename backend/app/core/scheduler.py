"""Scheduler de tareas del backend (APScheduler).

Singleton simple para jobs programados. Uso actual: correo de correcciones de un
examen a T+30min del fin del tiempo hábil (fecha_limite de la asignación).
"""
from datetime import datetime, timedelta, timezone

from loguru import logger

_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler(timezone="UTC")
    return _scheduler


def iniciar() -> None:
    sch = get_scheduler()
    if not sch.running:
        sch.start()
        logger.info("APScheduler iniciado")


def apagar() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler apagado")


def _job_correcciones(examen_id: int) -> None:
    """Ejecuta el envío de correcciones con su propia sesión de BD."""
    from app.db.database import SessionLocal
    from app.services import notification_service
    db = SessionLocal()
    try:
        notification_service.notificar_correcciones_examen(db, examen_id)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Job de correcciones examen {examen_id} falló: {e}")
    finally:
        db.close()


def programar_correcciones(examen_id: int, fecha_limite: datetime) -> None:
    """Programa el correo de correcciones a fecha_limite + 30 min. Si la fecha ya
    pasó, el job se dispara de inmediato (misfire) — el disparo manual cubre el resto."""
    fl = fecha_limite if fecha_limite.tzinfo else fecha_limite.replace(tzinfo=timezone.utc)
    run_date = fl + timedelta(minutes=30)
    try:
        get_scheduler().add_job(
            _job_correcciones, "date", run_date=run_date, args=[examen_id],
            id=f"correcciones-{examen_id}", replace_existing=True, misfire_grace_time=3600)
        logger.info(f"Correcciones examen {examen_id} programadas para {run_date.isoformat()}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"No se pudo programar correcciones examen {examen_id}: {e}")


def _job_avisar_lotes() -> None:
    """Avisa de los lotes de Mallén en RECIBIDO, con su propia sesión de BD.

    Como todos los trabajos programados: sesión propia y cerrada en `finally`, y
    la excepción se registra sin propagarse — un fallo aquí (SMTP caído, `ext`
    inaccesible) no debe tumbar el scheduler y llevarse con él el job de médicos
    TOP, que no tiene nada que ver.
    """
    from app.db.database import SessionLocal
    from app.services import notification_service
    db = SessionLocal()
    try:
        notification_service.notificar_lotes_recibidos(db)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Job de aviso de lotes de Mallén falló: {e}")
    finally:
        db.close()


def _job_medicos_top() -> None:
    """Ejecuta los avisos de médicos TOP con su propia sesión de BD."""
    from app.db.database import SessionLocal
    from app.services import visita_top_service
    db = SessionLocal()
    try:
        visita_top_service.procesar_avisos(db)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Job de médicos TOP falló: {e}")
    finally:
        db.close()


def programar_medicos_top() -> None:
    """Cron diario de RECONCILIACIÓN de médicos TOP (§7.3 regla 3).

    Es un cron y no un temporizador por visita a propósito: el scheduler usa
    `MemoryJobStore`, así que cualquier reinicio del contenedor perdería los
    jobs agendados en silencio. Un cron se re-registra en cada arranque y cada
    corrida vuelve a preguntarle a la base qué está vencido.
    """
    try:
        get_scheduler().add_job(
            _job_medicos_top, "cron", hour=7, minute=0,
            id="medicos-top-diario", replace_existing=True, misfire_grace_time=3600)
        logger.info("Job diario de médicos TOP programado (07:00 UTC)")
    except Exception as e:  # noqa: BLE001
        logger.error(f"No se pudo programar el job de médicos TOP: {e}")

    # Aviso de lotes de Mallén pendientes de validar. Cada 30 min y no cada 5: el
    # circuito es de días, no de minutos —Mallén sube un lote y alguien lo valida
    # esa jornada—, así que consultar más seguido no adelanta nada y solo añade
    # trabajo. Y no cada 6 horas, porque entonces un lote de la mañana podría
    # avisarse por la tarde, que es justo la demora que este aviso viene a quitar.
    try:
        get_scheduler().add_job(
            _job_avisar_lotes, "interval", minutes=30,
            id="aviso-lotes-mallen", replace_existing=True, misfire_grace_time=1800)
        logger.info("Job de aviso de lotes de Mallén programado (cada 30 min)")
    except Exception as e:  # noqa: BLE001
        logger.error(f"No se pudo programar el job de aviso de lotes: {e}")
