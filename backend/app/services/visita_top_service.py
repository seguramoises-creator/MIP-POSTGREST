"""Médicos TOP — detección de visitas vencidas y de TOP sin cubrir (§7.3 del
Requerimiento de Datos VISTA · Laboratorios Mallén v2).

POR QUÉ HAY QUE TRADUCIR FECHAS
--------------------------------
`Visita.PlaneacionCiclo` NO guarda fechas: guarda `semana` (1-4) y `dia_semana`
("Lunes".."Viernes", texto libre). Para saber si una visita programada venció hay
que derivar una fecha de calendario real, y ese traductor no existía.

La fecha planeada se deriva por CALENDARIO PURO: lunes de la semana que contiene
`fecha_inicio`, más (semana-1) semanas, más el desplazamiento del día. Los
feriados NO la mueven — si alguien planeó para un día que resultó feriado, la
fecha planeada sigue siendo esa. Los feriados entran al medir el VENCIMIENTO
posterior y el porcentaje del ciclo, que sí se cuentan en días hábiles.

DÍAS HÁBILES: SE USA EL CÁLCULO CORRECTO
-----------------------------------------
Se importa `_networkdays`/`_feriados_pais` de `cobertura_predictiva_service`,
que consultan `Config.DIM_Feriado`. NO se usa `visita_cobertura_service._dias_habiles`,
que solo excluye sábado y domingo e ignora los feriados.
"""
from datetime import date, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Ciclo
from app.models.visita import MedicoVisita, PlaneacionCiclo, VisitaRegistro

#: "Lunes" → 0 … "Viernes" → 4. Es el vocabulario que guarda `dia_semana`.
DIAS_SEMANA: dict[str, int] = {
    "Lunes": 0, "Martes": 1, "Miércoles": 2, "Miercoles": 2,
    "Jueves": 3, "Viernes": 4,
}


def fecha_planeada(ciclo: Ciclo, semana: int, dia_semana: str | None) -> date | None:
    """`(ciclo, semana, dia_semana)` → fecha de calendario, acotada al ciclo.

    Devuelve None si el día no es reconocible: un dato de planeación incompleto
    no debe generar un correo de reclamo al representante.
    """
    if not dia_semana:
        return None
    offset = DIAS_SEMANA.get(dia_semana.strip())
    if offset is None:
        logger.debug(f"dia_semana no reconocido en planeación: {dia_semana!r}")
        return None
    # Lunes de la semana que CONTIENE fecha_inicio.
    lunes_1 = ciclo.fecha_inicio - timedelta(days=ciclo.fecha_inicio.weekday())
    f = lunes_1 + timedelta(weeks=max(semana, 1) - 1, days=offset)
    # Acotada al ciclo: no se puede planear antes de que empiece ni después de
    # que termine.
    if f < ciclo.fecha_inicio:
        return ciclo.fecha_inicio
    if f > ciclo.fecha_fin:
        return ciclo.fecha_fin
    return f


def _feriados(db: Session, ciclo: Ciclo) -> set:
    from app.services.cobertura_predictiva_service import _feriados_pais
    return _feriados_pais(db, ciclo.pais_codigo, ciclo.fecha_inicio, ciclo.fecha_fin)


def _habiles(desde: date, hasta: date, feriados: set) -> int:
    from app.services.cobertura_predictiva_service import _networkdays
    return _networkdays(desde, hasta, feriados)


def pct_ciclo_transcurrido(db: Session, ciclo: Ciclo, hoy: date) -> int:
    """% de DÍAS HÁBILES del ciclo ya transcurridos (0-100), no días naturales."""
    feriados = _feriados(db, ciclo)
    total = _habiles(ciclo.fecha_inicio, ciclo.fecha_fin, feriados)
    if total <= 0:
        return 0
    corte = min(hoy, ciclo.fecha_fin)
    if corte < ciclo.fecha_inicio:
        return 0
    return round(_habiles(ciclo.fecha_inicio, corte, feriados) / total * 100)


def _ejecutadas(db: Session, ciclo_id: int) -> set[tuple[int, str]]:
    """`(medico_id, tipo_visita)` de las visitas EJECUTADAS del ciclo."""
    filas = (db.query(VisitaRegistro.medico_id, VisitaRegistro.tipo_visita)
             .filter(VisitaRegistro.ciclo_id == ciclo_id,
                     VisitaRegistro.ejecutada == True).all())  # noqa: E712
    return {(m, t) for m, t in filas}


def _plan_top(db: Session, ciclo_id: int) -> list[tuple[PlaneacionCiclo, MedicoVisita]]:
    """Filas de planeación del ciclo cuyo médico es TOP."""
    return (db.query(PlaneacionCiclo, MedicoVisita)
            .join(MedicoVisita, MedicoVisita.id == PlaneacionCiclo.medico_id)
            .filter(PlaneacionCiclo.ciclo_id == ciclo_id,
                    MedicoVisita.es_top == True).all())  # noqa: E712


def pendientes_recordatorio(db: Session, ciclo: Ciclo, hoy: date,
                            dias_gracia: int) -> list[dict]:
    """Visitas planeadas a un TOP cuya fecha venció hace >= `dias_gracia` días
    hábiles y que siguen sin ejecutarse."""
    ejecutadas = _ejecutadas(db, ciclo.id)
    feriados = _feriados(db, ciclo)
    salida = []
    for p, m in _plan_top(db, ciclo.id):
        if (m.id, p.tipo_visita) in ejecutadas:
            continue
        f = fecha_planeada(ciclo, p.semana, p.dia_semana)
        if f is None or f >= hoy:
            continue
        # Días hábiles transcurridos DESPUÉS de la fecha planeada.
        if _habiles(f + timedelta(days=1), hoy, feriados) < dias_gracia:
            continue
        salida.append({"vm_id": p.vm_id, "medico_id": m.id,
                       "medico": m.nombre_completo, "tipo_visita": p.tipo_visita,
                       "fecha_planeada": f})
    return salida


def pendientes_escalamiento(db: Session, ciclo: Ciclo) -> list[dict]:
    """Visitas planeadas a un TOP que siguen sin ejecutarse, sin mirar la fecha:
    quien decide el momento es el umbral de % del ciclo, que evalúa el job."""
    ejecutadas = _ejecutadas(db, ciclo.id)
    salida = []
    for p, m in _plan_top(db, ciclo.id):
        if (m.id, p.tipo_visita) in ejecutadas:
            continue
        salida.append({"vm_id": p.vm_id, "medico_id": m.id,
                       "medico": m.nombre_completo, "tipo_visita": p.tipo_visita,
                       "fecha_planeada": fecha_planeada(ciclo, p.semana, p.dia_semana)})
    return salida


#: Claves de configuración (editables desde Administración, tabla de config en BD).
#: Los defaults son una posición razonable, NO una decisión del cliente: el
#: pendiente nº 8 del §10 del requerimiento sigue abierto con Mallén.
CFG_DIAS_RECORDATORIO = "top_dias_recordatorio"
CFG_PCT_ESCALAMIENTO = "top_pct_ciclo_escalamiento"
DIAS_RECORDATORIO_DEFAULT = 2
PCT_ESCALAMIENTO_DEFAULT = 70


def _ya_avisado(db: Session, ciclo_id: int, tipo_aviso: str) -> set[tuple]:
    from app.models.visita import AvisoTopEnviado
    filas = (db.query(AvisoTopEnviado.vm_id, AvisoTopEnviado.medico_id,
                      AvisoTopEnviado.tipo_visita)
             .filter(AvisoTopEnviado.ciclo_id == ciclo_id,
                     AvisoTopEnviado.tipo_aviso == tipo_aviso).all())
    return {(v, m, t) for v, m, t in filas}


def _marcar(db: Session, ciclo_id: int, items: list[dict], tipo_aviso: str) -> None:
    from app.models.visita import AvisoTopEnviado
    for it in items:
        db.add(AvisoTopEnviado(vm_id=it["vm_id"], ciclo_id=ciclo_id,
                               medico_id=it["medico_id"],
                               tipo_visita=it["tipo_visita"], tipo_aviso=tipo_aviso))


def procesar_avisos(db: Session, hoy: date | None = None) -> dict:
    """Recorre los ciclos ABIERTOS y manda lo que toque, una sola vez por caso.

    Es un cron de RECONCILIACIÓN, no un temporizador: cada corrida vuelve a
    preguntarle a la base qué está vencido. Por eso sobrevive a los reinicios
    del contenedor, a diferencia de un job agendado en memoria.
    """
    from app.models.dimensiones import Gerente, RepresentanteMedico
    from app.models.visita import AVISO_ESCALAMIENTO, AVISO_RECORDATORIO
    from app.services import config_service, notification_service

    hoy = hoy or date.today()
    dias_gracia = config_service.obtener_int(db, CFG_DIAS_RECORDATORIO,
                                             DIAS_RECORDATORIO_DEFAULT)
    pct_umbral = config_service.obtener_int(db, CFG_PCT_ESCALAMIENTO,
                                            PCT_ESCALAMIENTO_DEFAULT)
    n_rec = n_esc = 0

    # Ciclos CERRADOS no se procesan: son snapshots inmutables y nadie puede ya
    # actuar sobre ellos.
    for ciclo in db.query(Ciclo).filter(Ciclo.cerrado == False).all():  # noqa: E712
        # ── Recordatorio al representante ────────────────────────────────
        avisados = _ya_avisado(db, ciclo.id, AVISO_RECORDATORIO)
        pend = [p for p in pendientes_recordatorio(db, ciclo, hoy, dias_gracia)
                if (p["vm_id"], p["medico_id"], p["tipo_visita"]) not in avisados]
        por_vm: dict[int, list] = {}
        for p in pend:
            por_vm.setdefault(p["vm_id"], []).append(p)
        for vm_id, items in por_vm.items():
            rm = db.query(RepresentanteMedico).filter(
                RepresentanteMedico.id == vm_id).first()
            if rm is None or not rm.email:
                logger.warning(f"TOP: representante {vm_id} sin correo; no se avisa")
                continue
            if notification_service.notificar_top_pendiente(rm.email, rm.nombre, items):
                _marcar(db, ciclo.id, items, AVISO_RECORDATORIO)
                n_rec += len(items)

        # ── Escalamiento al Gerente de Distrito ──────────────────────────
        if pct_ciclo_transcurrido(db, ciclo, hoy) < pct_umbral:
            continue
        avisados_esc = _ya_avisado(db, ciclo.id, AVISO_ESCALAMIENTO)
        pend_esc = [p for p in pendientes_escalamiento(db, ciclo)
                    if (p["vm_id"], p["medico_id"], p["tipo_visita"]) not in avisados_esc]
        por_gerente: dict[int, dict] = {}
        for p in pend_esc:
            rm = db.query(RepresentanteMedico).filter(
                RepresentanteMedico.id == p["vm_id"]).first()
            if rm is None or rm.gerente_id is None:
                logger.warning(f"TOP: representante {p['vm_id']} sin gerente; no se escala")
                continue
            por_gerente.setdefault(rm.gerente_id, {}).setdefault(rm.nombre, []).append(p)
        for gerente_id, por_rm in por_gerente.items():
            g = db.query(Gerente).filter(Gerente.id == gerente_id).first()
            if g is None or not g.email:
                logger.warning(f"TOP: gerente {gerente_id} sin correo; no se escala")
                continue
            if notification_service.notificar_top_escalado(g.email, g.nombre, por_rm):
                planos = [x for lista in por_rm.values() for x in lista]
                _marcar(db, ciclo.id, planos, AVISO_ESCALAMIENTO)
                n_esc += len(planos)

    db.commit()
    logger.info(f"Avisos de médicos TOP: {n_rec} recordatorios, {n_esc} escalamientos")
    return {"recordatorios": n_rec, "escalamientos": n_esc}
