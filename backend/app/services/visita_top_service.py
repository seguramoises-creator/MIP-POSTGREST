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
    """Filas de planeación del ciclo cuyo médico es TOP, sigue vigente en el panel
    para este ciclo Y admite Registro de Visita.

    Dos filtros, DISTINTOS a propósito (C2 + I3 de la revisión final):

    1. `cuenta_en_ciclo` (mismo patrón que usan `visita_planeacion_service.
       _medicos_del_ciclo` y `visita_cobertura_service._cobertura_base`): un TOP
       con `activo=False` o con el alta aún pendiente/rechazada no forma parte
       del panel efectivo de este ciclo — no se le puede reclamar nada.
    2. `estado_aprobacion == "APROBADO"`: MÁS estricto que `cuenta_en_ciclo` a
       secas. `cuenta_en_ciclo` SÍ admite `PENDIENTE_BAJA` (planear la baja de
       un TOP es legítimo, y por eso el bloqueo de publicación —que reutiliza
       `cuenta_en_ciclo` tal cual, sin este segundo filtro— lo sigue exigiendo
       planeado). Pero `visita_registro_service._medico_del_vm` exige
       `estado_aprobacion == "APROBADO"` para dejar registrar la visita: avisar
       sobre un médico en PENDIENTE_BAJA le reclamaría al representante —y lo
       expondría ante su gerente— por algo que el propio sistema le rechazaría.
       NO se "unifican" estos dos criterios: resuelven preguntas distintas
       (¿cuenta en el panel? vs. ¿se le puede registrar una visita hoy?).
    """
    from app.services.visita_aprobacion_service import ordenes_ciclo, cuenta_en_ciclo
    ordenes = ordenes_ciclo(db)
    ciclo_orden = ordenes.get(ciclo_id)
    filas = (db.query(PlaneacionCiclo, MedicoVisita)
             .join(MedicoVisita, MedicoVisita.id == PlaneacionCiclo.medico_id)
             .filter(PlaneacionCiclo.ciclo_id == ciclo_id,
                     MedicoVisita.es_top == True).all())  # noqa: E712
    return [(p, m) for p, m in filas
            if cuenta_en_ciclo(m, ciclo_orden, ordenes) and m.estado_aprobacion == "APROBADO"]


def _publicadas_por_vm(db: Session, ciclo_id: int) -> dict[int, bool]:
    """Caché `vm_id -> ¿su planeación de este ciclo está PUBLICADA?`, resuelto
    perezosamente (evita una consulta por fila cuando muchas filas comparten VM)."""
    from app.services.visita_planeacion_service import esta_publicada

    class _Cache(dict):
        def __missing__(self, vm_id):
            val = esta_publicada(db, vm_id, ciclo_id)
            self[vm_id] = val
            return val
    return _Cache()


def pendientes_recordatorio(db: Session, ciclo: Ciclo, hoy: date,
                            dias_gracia: int) -> list[dict]:
    """Visitas planeadas a un TOP cuya fecha venció hace >= `dias_gracia` días
    hábiles y que siguen sin ejecutarse.

    Solo mira planeaciones PUBLICADAS (I2): un borrador es editable en cualquier
    momento, no es el compromiso congelado sobre el que tiene sentido reclamar.
    """
    ejecutadas = _ejecutadas(db, ciclo.id)
    feriados = _feriados(db, ciclo)
    publicadas = _publicadas_por_vm(db, ciclo.id)
    salida = []
    for p, m in _plan_top(db, ciclo.id):
        if not publicadas[p.vm_id]:
            continue
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
    quien decide el momento es el umbral de % del ciclo, que evalúa el job.

    Solo mira planeaciones PUBLICADAS (I2), mismo motivo que `pendientes_recordatorio`.
    """
    ejecutadas = _ejecutadas(db, ciclo.id)
    publicadas = _publicadas_por_vm(db, ciclo.id)
    salida = []
    for p, m in _plan_top(db, ciclo.id):
        if not publicadas[p.vm_id]:
            continue
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
#: Interruptor de emergencia del cron completo (I5 de la revisión final): permite
#: apagar los avisos de médicos TOP sin redesplegar, mientras el pendiente nº 8
#: del §10 se resuelve con Mallén o si algo sale mal en producción.
CFG_AVISOS_ACTIVOS = "top_avisos_activos"
DIAS_RECORDATORIO_DEFAULT = 2
PCT_ESCALAMIENTO_DEFAULT = 70
AVISOS_ACTIVOS_DEFAULT = True


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

    # I5: interruptor de emergencia — sin redesplegar. Si está apagado, ni siquiera
    # se leen los otros parámetros: la corrida completa se omite y queda en el log.
    if not config_service.obtener_bool(db, CFG_AVISOS_ACTIVOS, AVISOS_ACTIVOS_DEFAULT):
        logger.info(f"Avisos de médicos TOP: OMITIDOS — {CFG_AVISOS_ACTIVOS}=false")
        return {"recordatorios": 0, "escalamientos": 0}

    dias_gracia = config_service.obtener_int(db, CFG_DIAS_RECORDATORIO,
                                             DIAS_RECORDATORIO_DEFAULT)
    pct_umbral = config_service.obtener_int(db, CFG_PCT_ESCALAMIENTO,
                                            PCT_ESCALAMIENTO_DEFAULT)
    n_rec = n_esc = 0

    # Ciclos CERRADOS no se procesan: son snapshots inmutables y nadie puede ya
    # actuar sobre ellos. Pero "no cerrado" no basta (C1): un ciclo puede quedar
    # semanas en POR_CERRAR (terminó, nadie lo cerró todavía) — ahí ya no tiene
    # sentido reclamar nada, `visita_registro_service._guard_ventana_ciclo`
    # rechazaría el registro igual. Solo se procesan los ciclos VIGENTES: cuya
    # ventana [fecha_inicio, fecha_fin] contiene HOY.
    for ciclo in db.query(Ciclo).filter(Ciclo.cerrado == False).all():  # noqa: E712
        if not (ciclo.fecha_inicio <= hoy <= ciclo.fecha_fin):
            continue

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
                # I1: commit INMEDIATO por destinatario, no al final de toda la
                # corrida — si un envío posterior revienta (o el contenedor se
                # reinicia a mitad de camino), lo ya enviado no se debe reenviar.
                _marcar(db, ciclo.id, items, AVISO_RECORDATORIO)
                db.commit()
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
                # I1: mismo motivo — commit inmediato por gerente.
                planos = [x for lista in por_rm.values() for x in lista]
                _marcar(db, ciclo.id, planos, AVISO_ESCALAMIENTO)
                db.commit()
                n_esc += len(planos)

    logger.info(f"Avisos de médicos TOP: {n_rec} recordatorios, {n_esc} escalamientos")
    return {"recordatorios": n_rec, "escalamientos": n_esc}
