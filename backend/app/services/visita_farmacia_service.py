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

from app.core.tiempo import ventana_dia_local
from app.models.dimensiones import Farmacia
from app.models.visita import FarmaciaVisita, FactVisitaFarmacia
from app.schemas.schemas_farmacia import VisitaFarmaciaRegistrar
from app.services.visita_cobertura_service import ciclo_por_defecto
from app.services import recalculo_service


def _pais_del_vm(db: Session, vm_id: int) -> str | None:
    from app.models.dimensiones import RepresentanteMedico
    return db.query(RepresentanteMedico.pais_codigo).filter(
        RepresentanteMedico.id == vm_id).scalar()


def _ahora_utc() -> datetime:
    """El instante actual tal y como se guarda: UTC y sin huso (ver `database.py`)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    # El reintento del móvil se resuelve ANTES de cualquier guard: si esa visita ya
    # entró, devolverla es la respuesta correcta aunque entretanto la farmacia haya
    # dejado de ser elegible o el ciclo se haya cerrado. Rechazar aquí borraría un
    # registro que YA existe en la base, y el teléfono lo marcaría como perdido.
    uuid_cliente = getattr(datos, "uuid_cliente", None)
    if uuid_cliente:
        repetida = db.query(FactVisitaFarmacia).filter(
            FactVisitaFarmacia.vm_id == vm_id,
            FactVisitaFarmacia.uuid_cliente == uuid_cliente).first()
        if repetida is not None:
            logger.info(f"Reintento de visita a farmacia ya registrada id={repetida.id} "
                        f"VM={vm_id} uuid={uuid_cliente} — se devuelve la existente")
            return repetida

    _guard_f22(db, panel)

    ciclo_id = ciclo_por_defecto(db, vm_id)  # ciclo ABIERTO del país del VM
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)

    hace_minutos = datos.hace_minutos or 0
    fecha_hora = _ahora_utc() - timedelta(minutes=hace_minutos)

    v = FactVisitaFarmacia(
        vm_id=vm_id, ciclo_id=ciclo_id, farmacia_id=panel.id,
        fecha_hora=fecha_hora,
        comentario=datos.comentario,
        ejecutada=datos.ejecutada,
        causa_no_visita=datos.causa_no_visita,
        latitud=datos.latitud, longitud=datos.longitud,
        registrado_por=usuario_id,
        uuid_cliente=uuid_cliente,
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
    from app.services.visita_registro_service import mime_de_imagen
    contenido = bytes(v.foto)
    return contenido, mime_de_imagen(contenido)   # de los bytes, no del foto_mime del cliente


# ── Estado de visita del panel (pestaña Farmacia de Registrar Visita) ──────────
# Espejo adaptado de `visita_cobertura_service._mapa_visitas` (médicos): UNA sola
# query agregada por VM+ciclo (no N+1 por farmacia), igual que el patrón usado para
# `estado_visita`/`fecha_ultima_visita` en `visita_service.listar_medicos`.

def estado_visita_panel(db: Session, vm_id: int, ciclo_id: int, panel_ids: list[int]) -> dict[int, dict]:
    """Estado de visita por farmacia del panel, por `farmacia_id` (id del panel,
    `Visita.DIM_FarmaciaVisita.id` — NO el id del maestro):
      - `visitada_hoy`: alguna visita EJECUTADA en el día LOCAL del país del VM.
      - `visitada_ciclo`: alguna visita EJECUTADA dentro del `ciclo_id` dado.
      - `ultimo_comentario`: comentario de la visita EJECUTADA más reciente (de
        cualquier ciclo) — mismo criterio de "visita anterior" que el historial
        de médicos (`visita_registro_service.historial_visitas`).

    AD-HOC (sin planeación): a diferencia de médicos, no hay un universo/agenda
    previo — este helper solo agrega lo que ya se registró.
    """
    if not panel_ids:
        return {}
    # El día del visitador, traducido a UTC para comparar contra la columna. Con la
    # fecha UTC a secas, una farmacia visitada a las 23:49 de RD salía como NO visitada
    # hoy —para UTC ya era mañana— y la tarjeta del móvil enseñaba 0.
    _, dia_inicio, dia_fin = ventana_dia_local(db, _pais_del_vm(db, vm_id))
    filas = (
        db.query(FactVisitaFarmacia)
        .filter(FactVisitaFarmacia.vm_id == vm_id,
                FactVisitaFarmacia.farmacia_id.in_(panel_ids),
                FactVisitaFarmacia.ejecutada == True)  # noqa: E712
        .order_by(FactVisitaFarmacia.fecha_hora.desc())
        .all()
    )
    salida: dict[int, dict] = {}
    for v in filas:
        # `setdefault` solo fija en el PRIMER encuentro de esta farmacia_id — como las
        # filas vienen ordenadas por fecha_hora DESC, ese primer encuentro es la visita
        # más reciente (de ahí sale `ultimo_comentario`, sea o no None).
        d = salida.setdefault(v.farmacia_id, {
            "visitada_hoy": False, "visitada_ciclo": False,
            "ultimo_comentario": v.comentario,
        })
        # La columna guarda UTC sin huso; `dia_inicio`/`dia_fin` vienen ya en esa
        # misma escala, así que la comparación es homogénea y sin conversiones sueltas.
        if v.fecha_hora and dia_inicio <= v.fecha_hora < dia_fin:
            d["visitada_hoy"] = True
        if v.ciclo_id == ciclo_id:
            d["visitada_ciclo"] = True
    return salida
