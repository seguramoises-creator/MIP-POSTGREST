"""Servicio del Módulo de Visita Médica — Fase 1 (Panel Médico).

Incluye la prevención de duplicados del lado servidor (spec 2.2): si 2 o más
palabras del nombre coinciden con un médico ya registrado, se avisa al usuario.
"""
from loguru import logger
from sqlalchemy.orm import Session

from app.models.visita import MedicoVisita
from app.models.dimensiones import Especialidad
from app.schemas.visita import MedicoVisitaCrear


class DuplicadoMedicoError(Exception):
    """Se detectaron posibles duplicados y el usuario no confirmó el registro."""
    def __init__(self, duplicados: list[dict]):
        self.duplicados = duplicados
        super().__init__("Posible duplicidad de médico")


def detectar_duplicados(db: Session, nombre: str, excluir_id: int | None = None) -> list[dict]:
    """Devuelve médicos activos cuyo nombre comparte >= 2 palabras con `nombre`."""
    palabras = {p for p in nombre.upper().split() if len(p) >= 2}
    if len(palabras) < 2:
        return []
    q = db.query(MedicoVisita).filter(MedicoVisita.activo == True)  # noqa: E712
    if excluir_id:
        q = q.filter(MedicoVisita.id != excluir_id)
    dups = []
    for m in q.all():
        comunes = palabras & set(m.nombre_completo.upper().split())
        if len(comunes) >= 2:
            dups.append({
                "id": m.id,
                "nombre_completo": m.nombre_completo,
                "direccion": m.direccion,
                "palabras_coinciden": len(comunes),
            })
    dups.sort(key=lambda d: d["palabras_coinciden"], reverse=True)
    return dups


def crear_medico(db: Session, datos: MedicoVisitaCrear, usuario_id: int | None) -> MedicoVisita:
    """Crea un médico del panel. Si hay posible duplicado y no se confirmó, levanta
    DuplicadoMedicoError (el endpoint responde 409 con la lista de coincidencias)."""
    if not datos.confirmar_duplicado:
        dups = detectar_duplicados(db, datos.nombre_completo)
        if dups:
            logger.info(f"Posible duplicado al registrar médico '{datos.nombre_completo}': {len(dups)} coincidencia(s)")
            raise DuplicadoMedicoError(dups)
    medico = MedicoVisita(
        vm_id=datos.vm_id,
        nombre_completo=datos.nombre_completo,
        especialidad_id=datos.especialidad_id,
        categoria=datos.categoria,
        tipo_consultorio=datos.tipo_consultorio,
        direccion=datos.direccion,
        telefono=datos.telefono,
        ciclos_sin_visita=0,
        activo=True,
        registrado_por=usuario_id,
    )
    db.add(medico)
    db.commit()
    db.refresh(medico)
    logger.info(f"Médico de visita creado id={medico.id} '{medico.nombre_completo}' (VM {medico.vm_id})")
    return medico


def listar_medicos(db: Session, vm_id: int | None = None) -> list[dict]:
    """Lista los médicos del panel (opcionalmente de un VM), con el nombre de especialidad."""
    q = db.query(MedicoVisita).filter(MedicoVisita.activo == True)  # noqa: E712
    if vm_id:
        q = q.filter(MedicoVisita.vm_id == vm_id)
    medicos = q.order_by(MedicoVisita.nombre_completo).all()
    esp_ids = {m.especialidad_id for m in medicos if m.especialidad_id}
    esp_nom = dict(db.query(Especialidad.id, Especialidad.nombre)
                   .filter(Especialidad.id.in_(esp_ids)).all()) if esp_ids else {}
    salida = []
    for m in medicos:
        salida.append({
            "id": m.id, "vm_id": m.vm_id, "nombre_completo": m.nombre_completo,
            "especialidad_id": m.especialidad_id,
            "especialidad_nombre": esp_nom.get(m.especialidad_id),
            "categoria": m.categoria, "tipo_consultorio": m.tipo_consultorio,
            "direccion": m.direccion, "telefono": m.telefono,
            "ciclos_sin_visita": m.ciclos_sin_visita, "activo": m.activo,
        })
    return salida
