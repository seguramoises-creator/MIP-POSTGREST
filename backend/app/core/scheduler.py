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
