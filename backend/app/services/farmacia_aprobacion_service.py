"""Flujo de aprobación VM→GD de Farmacias (panel de un VM ↔ maestro país-level).

Espejo de `visita_aprobacion_service.py`, adaptado al módulo de Farmacias (spec
`2026-07-22-modulo-farmacias-maestro-aprobacion-design.md`, Task 4 del plan):

  - **Acción A** (`solicitar_agregar_al_panel`): el VM agrega al panel una farmacia que
    YA existe (y está ACTIVA) en el maestro. Solo crea el registro de panel
    `PENDIENTE_ALTA` — el maestro no se toca.
  - **Acción B** (`solicitar_crear`): el VM da de alta una farmacia que no existe en el
    maestro. Crea el maestro vía `maestro_farmacia_service.crear_maestro` (que valida
    bloqueantes F23/F24 y corre el anti-dup duro F25/F09) con
    `estado="PENDIENTE_APROBACION"`, y el panel `PENDIENTE_ALTA` enlazado.
  - **Aprobar**: panel → APROBADO (con `ciclo_alta_id` = ciclo de trabajo del VM), y si el
    maestro seguía `PENDIENTE_APROBACION` pasa a `ACTIVA`.
  - **Rechazar**: exige motivo; panel → RECHAZADO; si el maestro era origen VM y seguía
    pendiente, pasa a `RECHAZADA` con `motivo_rechazo`.
  - **F22** (farmacia pendiente no cuenta cobertura ni aparece en Registro de Visita) lo
    aplican las queries de cobertura/registro (Tasks 6/7), no este servicio.
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Farmacia, RepresentanteMedico
from app.models.visita import FarmaciaVisita
from app.services import maestro_farmacia_service as maestro_svc
from app.services.visita_aprobacion_service import ciclo_actual_id


def _pais_de_vm(db: Session, vm_id: int) -> str | None:
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
    return rm.pais_codigo if rm else None


def _panel_existente(db: Session, vm_id: int, maestro_farmacia_id: int):
    return db.query(FarmaciaVisita).filter(
        FarmaciaVisita.vm_id == vm_id,
        FarmaciaVisita.maestro_farmacia_id == maestro_farmacia_id,
        FarmaciaVisita.activo == True,  # noqa: E712
    ).first()


def solicitar_agregar_al_panel(db: Session, vm_id: int, maestro_farmacia_id: int,
                               usuario_id=None) -> FarmaciaVisita:
    """Acción A: agrega al panel del VM una farmacia YA ACTIVA del maestro.

    Hallazgo importante 3: antes NO se consultaba `Farmacia` — se podía "agregar al
    panel" un `maestro_farmacia_id` inexistente, o uno RECHAZADA/PENDIENTE_APROBACION
    (violando F22), o de OTRO país. Ahora se valida el maestro antes de crear el panel.

    Hallazgo menor 4: simetría con `solicitar_crear` — si `vm_id` no resuelve a un RM,
    antes se seguía de largo (`_pais_de_vm` devolvía `None`, el chequeo de país se
    saltaba) y el 500 llegaba más adelante al insertar el panel (FK). Ahora se valida
    el VM antes de tocar el maestro.
    """
    pais_vm = _pais_de_vm(db, vm_id)
    if not pais_vm:
        raise ValueError(f"El VM ID={vm_id} no existe o no tiene país asignado.")

    maestro = db.query(Farmacia).filter(Farmacia.id == maestro_farmacia_id).first()
    if maestro is None:
        raise ValueError(f"La farmacia ID={maestro_farmacia_id} no existe en el maestro.")
    if maestro.estado != "ACTIVA":
        raise ValueError("La farmacia no está activa en el maestro.")
    if maestro.pais_codigo != pais_vm:
        raise ValueError("La farmacia no pertenece al país de tu operación.")

    if _panel_existente(db, vm_id, maestro_farmacia_id) is not None:
        raise ValueError("Esta farmacia ya está en tu panel.")

    panel = FarmaciaVisita(
        vm_id=vm_id, maestro_farmacia_id=maestro_farmacia_id,
        estado_aprobacion="PENDIENTE_ALTA",
        solicitado_por=usuario_id, fecha_solicitud=datetime.now(timezone.utc),
    )
    db.add(panel); db.commit(); db.refresh(panel)
    logger.info(f"Panel farmacia: Acción A vm={vm_id} maestro={maestro_farmacia_id} panel_id={panel.id}")
    return panel


def solicitar_crear(db: Session, vm_id: int, datos: dict, usuario_id=None) -> FarmaciaVisita:
    """Acción B: crea la farmacia en el maestro (PENDIENTE_APROBACION) y el panel enlazado.

    Propaga `DuplicadoDuroError`/`ValueError` de `maestro_farmacia_service.crear_maestro`
    (bloqueantes F23/F24, anti-dup F25/F09) sin envolverlos: el llamador (router) decide
    cómo traducirlos a HTTP.

    Hallazgo menor 4: si `vm_id` no resuelve a un RM, `_pais_de_vm` devolvía `None` y
    `crear_maestro` reventaba en 500 al intentar grabar `Farmacia(pais_codigo=None, ...)`
    (columna NOT NULL). Ahora se valida el VM antes de tocar el maestro.
    """
    pais_codigo = _pais_de_vm(db, vm_id)
    if not pais_codigo:
        raise ValueError(f"El VM ID={vm_id} no existe o no tiene país asignado.")
    maestro = maestro_svc.crear_maestro(
        db, pais_codigo, datos, origen="VM", estado="PENDIENTE_APROBACION", usuario_id=usuario_id)

    panel = FarmaciaVisita(
        vm_id=vm_id, maestro_farmacia_id=maestro.id,
        estado_aprobacion="PENDIENTE_ALTA",
        solicitado_por=usuario_id, fecha_solicitud=datetime.now(timezone.utc),
    )
    db.add(panel); db.commit(); db.refresh(panel)
    logger.info(f"Panel farmacia: Acción B vm={vm_id} maestro={maestro.id} panel_id={panel.id}")
    return panel


def pendientes_del_gd(db: Session, gerente_id: int) -> list[dict]:
    """Bandeja del Gerente de Distrito: solicitudes PENDIENTE_ALTA de su equipo."""
    vm_ids = [rm.id for rm in db.query(RepresentanteMedico).filter(
        RepresentanteMedico.gerente_id == gerente_id).all()]
    if not vm_ids:
        return []

    paneles = db.query(FarmaciaVisita).filter(
        FarmaciaVisita.estado_aprobacion == "PENDIENTE_ALTA",
        FarmaciaVisita.vm_id.in_(vm_ids),
    ).order_by(FarmaciaVisita.fecha_solicitud.desc()).all()
    if not paneles:
        return []

    maestro_ids = {p.maestro_farmacia_id for p in paneles}
    maestros = {f.id: f for f in db.query(Farmacia).filter(Farmacia.id.in_(maestro_ids)).all()}
    rms = {rm.id: rm for rm in db.query(RepresentanteMedico).filter(
        RepresentanteMedico.id.in_(vm_ids)).all()}

    salida = []
    for p in paneles:
        f = maestros.get(p.maestro_farmacia_id)
        rm = rms.get(p.vm_id)
        es_alta_nueva = bool(f) and f.origen == "VM" and f.estado == "PENDIENTE_APROBACION"
        # §3.2: alerta de posible duplicado VISIBLE en la bandeja (no bloquea). Solo tiene
        # sentido para altas nuevas (Acción B) contra OTRA farmacia ya ACTIVA del maestro; en
        # la Acción A (agregar una que ya está ACTIVA) no aplica — el propio maestro es esa
        # farmacia, no hay "otra" con la que compararla.
        posible_duplicado = (
            maestro_svc.detectar_posibles_duplicados(
                db, f.pais_codigo, nombre_completo=f.nombre_completo, excluir_id=f.id)
            if f and rm and es_alta_nueva else []
        )
        salida.append({
            "id": p.id,
            "maestro_farmacia_id": p.maestro_farmacia_id,
            "nombre_completo": f.nombre_completo if f else None,
            "direccion": f.direccion if f else None,
            "encargado": f.encargado if f else None,
            "estado_maestro": f.estado if f else None,
            "tipo_solicitud": "NUEVA" if es_alta_nueva else "AGREGAR",
            "vm_id": p.vm_id,
            "vm_nombre": rm.nombre if rm else f"VM #{p.vm_id}",
            "fecha_solicitud": p.fecha_solicitud.isoformat() if p.fecha_solicitud else None,
            "posible_duplicado": posible_duplicado,
        })
    return salida


def _guard_panel_pendiente(panel: FarmaciaVisita | None) -> None:
    if panel is None:
        raise ValueError("La solicitud de panel no existe.")
    if panel.estado_aprobacion != "PENDIENTE_ALTA":
        raise ValueError("La solicitud no tiene una alta pendiente.")


def aprobar(db: Session, panel_id: int, usuario_id=None) -> FarmaciaVisita:
    panel = db.query(FarmaciaVisita).filter(FarmaciaVisita.id == panel_id).first()
    _guard_panel_pendiente(panel)

    maestro = db.query(Farmacia).filter(Farmacia.id == panel.maestro_farmacia_id).first()
    if maestro is not None:
        if maestro.estado == "PENDIENTE_APROBACION":
            # Flujo normal (Acción B): el maestro nació con la solicitud, se promueve.
            maestro.estado = "ACTIVA"
            maestro.aprobado_por = usuario_id
            maestro.fecha_aprobacion = datetime.now(timezone.utc)
            maestro.updated_at = datetime.now(timezone.utc)
        elif maestro.estado != "ACTIVA":
            # Hallazgo menor M3: el maestro quedó INACTIVA/RECHAZADA (p.ej. un ADMIN lo
            # desactivó entre la Acción A y la aprobación) — no resucitarlo en silencio.
            raise ValueError(
                "La farmacia del maestro no está activa; no se puede aprobar la solicitud.")

    panel.estado_aprobacion = "APROBADO"
    panel.ciclo_alta_id = ciclo_actual_id(db, panel.vm_id)
    panel.aprobado_por = usuario_id
    panel.fecha_aprobacion = datetime.now(timezone.utc)

    db.commit(); db.refresh(panel)
    logger.info(f"Panel farmacia id={panel.id} APROBADO por={usuario_id} maestro={panel.maestro_farmacia_id}")
    return panel


def rechazar(db: Session, panel_id: int, motivo: str | None, usuario_id=None) -> FarmaciaVisita:
    if not motivo or not motivo.strip():
        raise ValueError("Debe indicar el motivo del rechazo.")

    panel = db.query(FarmaciaVisita).filter(FarmaciaVisita.id == panel_id).first()
    _guard_panel_pendiente(panel)

    maestro = db.query(Farmacia).filter(Farmacia.id == panel.maestro_farmacia_id).first()
    if maestro is not None and maestro.origen == "VM" and maestro.estado == "PENDIENTE_APROBACION":
        maestro.estado = "RECHAZADA"
        maestro.motivo_rechazo = motivo
        maestro.updated_at = datetime.now(timezone.utc)

    panel.estado_aprobacion = "RECHAZADO"
    panel.motivo = motivo
    panel.activo = False
    panel.aprobado_por = usuario_id
    panel.fecha_aprobacion = datetime.now(timezone.utc)

    db.commit(); db.refresh(panel)
    logger.info(f"Panel farmacia id={panel.id} RECHAZADO por={usuario_id} motivo={motivo!r}")
    return panel


def editar_y_aprobar(db: Session, panel_id: int, cambios: dict, usuario_id=None) -> FarmaciaVisita:
    """El GD corrige el maestro (p.ej. dirección/encargado) y aprueba en el mismo paso."""
    panel = db.query(FarmaciaVisita).filter(FarmaciaVisita.id == panel_id).first()
    _guard_panel_pendiente(panel)

    if cambios:
        maestro = db.query(Farmacia).filter(Farmacia.id == panel.maestro_farmacia_id).first()
        if maestro is not None:
            maestro_svc.actualizar_maestro(db, maestro, cambios, usuario_id=usuario_id)

    return aprobar(db, panel_id, usuario_id=usuario_id)
