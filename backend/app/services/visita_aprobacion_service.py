"""Flujo de aprobación de alta/baja de médicos del panel (Gerente de Distrito).

Reglas de negocio:
  - Al crear un médico (ALTA) queda PENDIENTE_ALTA y NO cuenta en la cobertura.
  - Al desactivar (BAJA) queda PENDIENTE_BAJA; sigue contando el ciclo actual.
  - El Gerente de Distrito de la línea (o ADMIN/GER. PRODUCTIVIDAD) aprueba o rechaza.
  - El cambio es efectivo **al próximo ciclo**: `ciclo_alta_id`/`ciclo_baja_id`
    guardan el ciclo durante el que se solicitó; un médico cuenta en un ciclo de
    orden O solo si O > orden(ciclo_alta) y O <= orden(ciclo_baja).

`orden(ciclo)` = anio*1000 + numero (cronológico). Los médicos existentes tienen
`ciclo_alta_id = NULL` → cuentan siempre (grandfathered).
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.visita import MedicoVisita
from app.models.dimensiones import RepresentanteMedico, Linea, Especialidad, Ciclo


class AprobacionError(Exception):
    pass


def ordenes_ciclo(db: Session) -> dict[int, int]:
    return {c.id: c.anio * 1000 + c.numero for c in db.query(Ciclo).all()}


def ciclo_actual_id(db: Session, vm_id: int | None = None) -> int | None:
    """Ciclo de trabajo durante el que se registra el alta/baja de un médico.

    CON `vm_id`: el ciclo ABIERTO del país del VM que corresponde a HOY (vía
    `ciclo_por_defecto`). Es lo correcto: sella `ciclo_alta_id`/`ciclo_baja_id` con el
    ciclo de trabajo, no con "el de número más alto".

    Bug histórico (jul-2026): sin `vm_id` devolvía el ciclo de mayor (anio, numero). Si
    existía un ciclo futuro (p.ej. C12) los médicos nuevos quedaban con `alta=C12` y
    `cuenta_en_ciclo` los excluía del panel del ciclo de trabajo (C07) → **panel efectivo
    0** aunque hubiera visitas. Mismo antipatrón "el más reciente ≠ el que corresponde a HOY".
    """
    if vm_id is not None:
        from app.services.visita_cobertura_service import ciclo_por_defecto
        cid = ciclo_por_defecto(db, vm_id)
        if cid:
            return cid
    c = db.query(Ciclo).order_by(Ciclo.anio.desc(), Ciclo.numero.desc()).first()
    return c.id if c else None


def cuenta_en_ciclo(m: MedicoVisita, ciclo_orden: int | None, ordenes: dict[int, int]) -> bool:
    """¿El médico forma parte del panel efectivo para un ciclo de orden `ciclo_orden`?"""
    if not m.activo:
        return False
    if m.estado_aprobacion in ("PENDIENTE_ALTA", "RECHAZADO"):
        return False
    if ciclo_orden is None:
        return True
    if m.ciclo_alta_id is not None:
        oa = ordenes.get(m.ciclo_alta_id)
        if oa is not None and ciclo_orden < oa:   # alta efectiva el MISMO ciclo (v2 jul-2026)
            return False
    if m.ciclo_baja_id is not None:
        ob = ordenes.get(m.ciclo_baja_id)
        if ob is not None and ciclo_orden > ob:     # baja efectiva desde el ciclo siguiente
            return False
    return True


def _gerente_id_de_medico(db: Session, m: MedicoVisita) -> int | None:
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == m.vm_id).first()
    return rm.gerente_id if rm else None


def puede_aprobar(db: Session, usuario, m: MedicoVisita) -> bool:
    """ADMIN y GER. PRODUCTIVIDAD aprueban cualquiera; el GERENTE_DISTRITO solo los
    médicos de su distrito (VM.gerente_id == su propio gerente_id)."""
    rol = usuario.rol.value if hasattr(usuario.rol, "value") else str(usuario.rol)
    if rol in ("ADMIN", "GERENTE_PRODUCTIVIDAD"):
        return True
    if rol == "GERENTE_DISTRITO":
        mi_gerente = getattr(usuario, "gerente_id", None)
        return mi_gerente is not None and _gerente_id_de_medico(db, m) == mi_gerente
    return False


def solicitar_baja(db: Session, m: MedicoVisita, usuario) -> MedicoVisita:
    """Registra una solicitud de BAJA (requiere aprobación). Efecto al próximo ciclo."""
    if m.estado_aprobacion == "PENDIENTE_ALTA":
        # Un médico aún no aprobado no se 'da de baja': se rechaza directamente.
        m.estado_aprobacion = "RECHAZADO"
        m.activo = False
    else:
        m.estado_aprobacion = "PENDIENTE_BAJA"
        m.ciclo_baja_id = ciclo_actual_id(db, m.vm_id)
    m.solicitado_por = getattr(usuario, "id", None)
    m.fecha_solicitud = datetime.now(timezone.utc)
    db.commit(); db.refresh(m)
    logger.info(f"Solicitud de baja médico id={m.id} estado={m.estado_aprobacion} por={getattr(usuario,'id',None)}")
    return m


def aprobar(db: Session, m: MedicoVisita, usuario) -> MedicoVisita:
    if not puede_aprobar(db, usuario, m):
        raise AprobacionError("No autorizado para aprobar este médico (no es de tu distrito).")
    if m.estado_aprobacion not in ("PENDIENTE_ALTA", "PENDIENTE_BAJA"):
        raise AprobacionError("El médico no tiene una solicitud pendiente.")
    era_alta = m.estado_aprobacion == "PENDIENTE_ALTA"
    m.estado_aprobacion = "APROBADO"   # para BAJA queda APROBADO con ciclo_baja programado
    m.aprobado_por = getattr(usuario, "id", None)
    m.fecha_aprobacion = datetime.now(timezone.utc)
    # Al aprobar el ALTA se revela la categoría: recién aquí el motor puntúa la plantilla
    # que capturó el representante (y que el GD pudo ajustar antes de aprobar).
    if era_alta:
        _clasificar_al_aprobar(db, m)
    db.commit(); db.refresh(m)
    logger.info(f"Médico id={m.id} APROBADO por={getattr(usuario,'id',None)} categoria={m.categoria}")
    return m


def _clasificar_al_aprobar(db: Session, m: MedicoVisita) -> None:
    """Calcula y sella la categoría A/B/C/D del médico a partir de su plantilla.

    Solo toca el Panel (`MedicoVisita.categoria`): el Maestro de Médicos queda SIN
    clasificación a propósito — un mismo médico puede tener categorías distintas según
    la línea/RM que lo visita, así que la clasificación vive en el plano de asignación.

    Best-effort: si el país no tiene reglas configuradas (o falta alguna), el médico
    queda aprobado SIN categoría (NULL) en vez de bloquear la aprobación o inventar una
    letra. El GD lo verá como 'sin clasificar' y podrá resolverse al configurar el país.
    """
    from app.models.visita import MedicoClasificacion
    from app.models.dimensiones import RepresentanteMedico
    from app.services import categorizacion_service

    try:
        clas = db.query(MedicoClasificacion).filter(
            MedicoClasificacion.medico_visita_id == m.id).first()
        if clas is None:
            return          # alta antigua, sin plantilla: no hay nada que puntuar
        rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == m.vm_id).first()
        if not rm or not rm.pais_codigo:
            return
        r = categorizacion_service.calcular_categoria_de_valores(db, rm.pais_codigo, {
            "PacientesSemana": clas.pacientes_semana,
            "CostoConsulta": clas.costo_consulta,
            "RecetasSemana": clas.potencial_prescripcion,
            "UbicacionTerritorialCM": clas.ubicacion_territorial,
            "KOL": clas.kol_nivel,
        })
        if r.get("categoria"):
            m.categoria = str(r["categoria"]).strip().upper()[:1]
        else:
            logger.warning(f"Médico id={m.id} aprobado SIN categoría "
                           f"(estado={r.get('estado')}, país={rm.pais_codigo})")
    except Exception as e:  # noqa: BLE001
        logger.error(f"No se pudo clasificar el médico id={m.id} al aprobar: {e}")


def rechazar(db: Session, m: MedicoVisita, usuario, motivo: str | None) -> MedicoVisita:
    if not puede_aprobar(db, usuario, m):
        raise AprobacionError("No autorizado para rechazar este médico (no es de tu distrito).")
    if m.estado_aprobacion == "PENDIENTE_ALTA":
        m.estado_aprobacion = "RECHAZADO"
        m.activo = False
    elif m.estado_aprobacion == "PENDIENTE_BAJA":
        m.estado_aprobacion = "APROBADO"   # se cancela la baja
        m.ciclo_baja_id = None
    else:
        raise AprobacionError("El médico no tiene una solicitud pendiente.")
    m.aprobado_por = getattr(usuario, "id", None)
    m.fecha_aprobacion = datetime.now(timezone.utc)
    m.motivo = motivo
    db.commit(); db.refresh(m)
    logger.info(f"Médico id={m.id} solicitud RECHAZADA por={getattr(usuario,'id',None)}")
    return m


def listar_pendientes(db: Session, usuario) -> list[dict]:
    """Solicitudes pendientes (alta/baja) que el usuario puede aprobar."""
    q = db.query(MedicoVisita).filter(
        MedicoVisita.estado_aprobacion.in_(("PENDIENTE_ALTA", "PENDIENTE_BAJA")))
    pend = q.order_by(MedicoVisita.fecha_solicitud.desc()).all()
    pend = [m for m in pend if puede_aprobar(db, usuario, m)]

    vm_ids = {m.vm_id for m in pend}
    rms = {r.id: r for r in db.query(RepresentanteMedico).filter(RepresentanteMedico.id.in_(vm_ids)).all()} if vm_ids else {}
    linea_ids = {r.linea_id for r in rms.values()}
    lineas = dict(db.query(Linea.id, Linea.nombre).filter(Linea.id.in_(linea_ids)).all()) if linea_ids else {}
    esp_ids = {m.especialidad_id for m in pend if m.especialidad_id}
    esps = dict(db.query(Especialidad.id, Especialidad.nombre).filter(Especialidad.id.in_(esp_ids)).all()) if esp_ids else {}

    salida = []
    for m in pend:
        rm = rms.get(m.vm_id)
        salida.append({
            "id": m.id, "nombre_completo": m.nombre_completo, "categoria": m.categoria,
            "especialidad_nombre": esps.get(m.especialidad_id),
            "vm_id": m.vm_id, "vm_nombre": rm.nombre if rm else f"VM #{m.vm_id}",
            "linea_nombre": lineas.get(rm.linea_id) if rm else None,
            "tipo_solicitud": "ALTA" if m.estado_aprobacion == "PENDIENTE_ALTA" else "BAJA",
            "fecha_solicitud": m.fecha_solicitud.isoformat() if m.fecha_solicitud else None,
        })
    return salida
