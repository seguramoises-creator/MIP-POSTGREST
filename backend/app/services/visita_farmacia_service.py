"""Registro de Visita a Farmacia — Task 6 (plan `2026-07-22-modulo-farmacias.md`).

Espejo de `visita_registro_service.py` (hora del SERVIDOR, guard de ciclo abierto,
foto BLOB con magic bytes) pero opera sobre la tabla PARALELA
`Visita.FactVisitaFarmacia` (Opción A) — NUNCA toca `FactVisita` de médicos.

**AD-HOC, SIN planeación** (Global Constraint del plan): no existe equivalente de
`PlaneacionCiclo` para farmacias. El VM registra cuando la hace; no hay universo
planeado ni ruptura de secuencia programada.

**Guard F22** (bloqueante): solo se puede registrar visita a una farmacia cuyo
panel esté `estado_aprobacion="APROBADO"` y cuyo maestro esté `estado="ACTIVA"`.
Una farmacia PENDIENTE_APROBACION/PENDIENTE_ALTA no cuenta cobertura ni admite
registro de visita.
"""
from datetime import datetime, timezone, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Farmacia
from app.models.visita import FarmaciaVisita, FactVisitaFarmacia
from app.schemas.schemas_farmacia import VisitaFarmaciaRegistrar
from app.services.visita_cobertura_service import ciclo_por_defecto
from app.services import recalculo_service


class PanelNoAprobadoError(ValueError):
    """F22: la farmacia del panel no está APROBADA, o el maestro no está ACTIVA."""


def _guard_ciclo_abierto(db: Session, ciclo_id: int) -> None:
    """Bloquea escrituras sobre ciclos cerrados (inmutables) — mismo guard que
    el registro de visita a médico."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        raise ValueError("El ciclo está cerrado — solo lectura")


def _guard_f22(db: Session, panel: FarmaciaVisita) -> Farmacia:
    """F22: el panel debe estar APROBADO y el maestro debe estar ACTIVA. Devuelve
    el maestro ya validado (evita una segunda consulta en el llamador)."""
    if panel.estado_aprobacion != "APROBADO":
        raise PanelNoAprobadoError(
            "Esta farmacia todavía no fue aprobada por tu Gerente de Distrito — "
            "no puedes registrarle visita."
        )
    maestro = db.query(Farmacia).filter(Farmacia.id == panel.maestro_farmacia_id).first()
    if maestro is None or maestro.estado != "ACTIVA":
        raise PanelNoAprobadoError(
            "Esta farmacia no está activa en el maestro — no puedes registrarle visita."
        )
    return maestro


def registrar_visita(db: Session, vm_id: int, panel: FarmaciaVisita,
                     datos: VisitaFarmaciaRegistrar, usuario_id: int | None) -> FactVisitaFarmacia:
    """Registra una visita AD-HOC a una farmacia del panel del VM.

    `panel` debe ser el registro `Visita.DIM_FarmaciaVisita` propiedad del `vm_id`
    (la verificación de que pertenece al VM que llama es responsabilidad del
    router — mismo patrón que `_verificar_alcance_gd` en la aprobación).
    """
    _guard_f22(db, panel)

    ciclo_id = ciclo_por_defecto(db, vm_id)  # ciclo ABIERTO del país del VM
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)

    hace_minutos = datos.hace_minutos or 0
    fecha_hora = datetime.now(timezone.utc) - timedelta(minutes=hace_minutos)

    v = FactVisitaFarmacia(
        vm_id=vm_id, ciclo_id=ciclo_id, farmacia_id=panel.id,
        fecha_hora=fecha_hora,
        comentario=datos.comentario,
        ejecutada=datos.ejecutada,
        causa_no_visita=datos.causa_no_visita,
        latitud=datos.latitud, longitud=datos.longitud,
        registrado_por=usuario_id,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    logger.info(f"Visita a farmacia registrada id={v.id} VM={vm_id} panel={panel.id} ciclo={ciclo_id}")
    return v


# ── Foto de visita (BLOB) — espejo de visita_registro_service, tope 3 MB (spec del plan) ──
MAX_FOTO_BYTES = 3 * 1024 * 1024   # 3 MB (Task 6 del plan de Farmacias)
_MAGIC_JPEG = b"\xff\xd8\xff"
_MAGIC_PNG = b"\x89PNG\r\n"


def _es_imagen(contenido: bytes) -> bool:
    return contenido[:3] == _MAGIC_JPEG or contenido[:6] == _MAGIC_PNG


def guardar_foto_visita(db: Session, visita_id: int, contenido: bytes, mime: str) -> None:
    """Valida (magic bytes JPEG/PNG + tamaño ≤ 3MB) y guarda la foto como BLOB."""
    if len(contenido) > MAX_FOTO_BYTES:
        raise ValueError("La foto excede el tamaño máximo (3 MB)")
    if not _es_imagen(contenido):
        raise ValueError("El archivo no es una imagen JPEG/PNG válida")
    v = db.query(FactVisitaFarmacia).filter(FactVisitaFarmacia.id == visita_id).first()
    if v is None:
        raise ValueError("Visita a farmacia no encontrada")
    v.foto = contenido
    v.foto_mime = mime or "image/jpeg"
    db.commit()


def obtener_foto_visita(db: Session, visita_id: int):
    """Devuelve (bytes, mime) de la foto, o None si la visita no existe o no tiene foto."""
    v = db.query(FactVisitaFarmacia).filter(FactVisitaFarmacia.id == visita_id).first()
    if v is None or not v.foto:
        return None
    return bytes(v.foto), (v.foto_mime or "image/jpeg")
