"""Servicio del Módulo de Visita Médica — Fase 1 (Panel Médico).

Incluye la prevención de duplicados del lado servidor (spec 2.2): si 2 o más
palabras del nombre coinciden con un médico ya registrado, se avisa al usuario.
"""
from loguru import logger
from sqlalchemy.orm import Session

from app.models.visita import MedicoVisita
from app.models.dimensiones import Especialidad, RepresentanteMedico, Linea
from app.schemas.visita import MedicoVisitaCrear, MedicoVisitaActualizar


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
    from datetime import date as _date, datetime as _dt, timezone as _tz
    from app.services.visita_aprobacion_service import ciclo_actual_id
    medico = MedicoVisita(
        vm_id=datos.vm_id,
        codigo=datos.codigo,
        nombre_completo=datos.nombre_completo,
        nombre=datos.nombre,
        apellidos=datos.apellidos,
        especialidad_id=datos.especialidad_id,
        subespecialidad=datos.subespecialidad,
        categoria=datos.categoria,
        centro_trabajo=datos.centro_trabajo,
        institucion_tipo=datos.institucion_tipo,
        tipo_consultorio=datos.tipo_consultorio,
        provincia=datos.provincia,
        municipio=datos.municipio,
        sector=datos.sector,
        direccion=datos.direccion,
        latitud=datos.latitud,
        longitud=datos.longitud,
        telefono=datos.telefono,
        email=datos.email,
        exequatur=datos.exequatur,
        dias_consulta=datos.dias_consulta,
        horario_consulta=datos.horario_consulta,
        frecuencia_visita=datos.frecuencia_visita,
        acepta_visita=datos.acepta_visita,
        potencial_prescripcion=datos.potencial_prescripcion,
        kol=datos.kol,
        segmento=datos.segmento,
        observaciones=datos.observaciones,
        fecha_alta=datos.fecha_alta or _date.today(),
        ciclos_sin_visita=0,
        activo=True,
        # Alta sujeta a aprobación del Gerente de Distrito; efectiva el próximo ciclo.
        estado_aprobacion="PENDIENTE_ALTA",
        ciclo_alta_id=ciclo_actual_id(db),
        solicitado_por=usuario_id,
        fecha_solicitud=_dt.now(_tz.utc),
        registrado_por=usuario_id,
    )
    db.add(medico)
    db.commit()
    db.refresh(medico)
    logger.info(f"Médico de visita creado id={medico.id} '{medico.nombre_completo}' (VM {medico.vm_id})")
    return medico


def obtener_medico(db: Session, medico_id: int) -> MedicoVisita | None:
    return db.query(MedicoVisita).filter(MedicoVisita.id == medico_id).first()


def actualizar_medico(db: Session, medico: MedicoVisita,
                      datos: MedicoVisitaActualizar, usuario_id: int | None) -> MedicoVisita:
    """Aplica solo los campos enviados (patrón PATCH). Sirve tanto para editar el
    médico como para activar/desactivar (campo `activo`)."""
    cambios = datos.model_dump(exclude_unset=True)
    # El alta/baja (campo `activo`) se gestiona solo por el flujo de aprobación
    # (solicitar_baja / reactivar), nunca por edición directa del médico.
    cambios.pop("activo", None)
    # El nombre solo se valida (sin puntos, ≥2 palabras) si REALMENTE cambia, para no
    # bloquear la edición de otros campos en médicos con nombre heredado no conforme.
    if "nombre_completo" in cambios:
        nuevo = cambios["nombre_completo"]
        if nuevo == medico.nombre_completo:
            cambios.pop("nombre_completo")  # sin cambio → no re-validar ni re-escribir
        else:
            from app.schemas.visita import validar_nombre_medico
            cambios["nombre_completo"] = validar_nombre_medico(nuevo)  # ValueError → 400
    for campo, valor in cambios.items():
        setattr(medico, campo, valor)
    db.commit()
    db.refresh(medico)
    logger.info(f"Médico de visita actualizado id={medico.id} "
                f"(campos: {', '.join(cambios) or 'ninguno'}) por usuario={usuario_id}")
    return medico


def listar_medicos(db: Session, vm_id: int | None = None, ciclo_id: int | None = None,
                   incluir_inactivos: bool = False) -> list[dict]:
    """Lista los médicos del panel (opcionalmente de un VM), con el nombre de la
    especialidad y el estado de visita del ciclo (para el Panel Médico enriquecido):
    `estado_visita` = 'vr' (Vista+Revisita), 'v' (una visita), 'sin' (sin visitar)."""
    from app.services.visita_cobertura_service import ciclo_por_defecto, _mapa_visitas

    q = db.query(MedicoVisita)
    if not incluir_inactivos:
        q = q.filter(MedicoVisita.activo == True)  # noqa: E712
    if vm_id:
        q = q.filter(MedicoVisita.vm_id == vm_id)
    medicos = q.order_by(MedicoVisita.nombre_completo).all()
    esp_ids = {m.especialidad_id for m in medicos if m.especialidad_id}
    esp_nom = dict(db.query(Especialidad.id, Especialidad.nombre)
                   .filter(Especialidad.id.in_(esp_ids)).all()) if esp_ids else {}

    # Línea de cada médico (vía su visitador: DIM_RM.linea_id → DIM_Linea.nombre).
    vm_ids = {m.vm_id for m in medicos}
    rm_linea = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.linea_id)
                    .filter(RepresentanteMedico.id.in_(vm_ids)).all()) if vm_ids else {}
    linea_nom = dict(db.query(Linea.id, Linea.nombre)
                     .filter(Linea.id.in_(set(rm_linea.values()))).all()) if rm_linea else {}

    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    mapa = _mapa_visitas(db, ciclo_id, vm_id) if ciclo_id else {}

    # Fecha de última visita ejecutada por médico (derivada de FactVisita).
    from sqlalchemy import func
    from app.models.visita import VisitaRegistro
    med_ids = [m.id for m in medicos]
    ult_visita = {}
    if med_ids:
        ult_visita = dict(
            db.query(VisitaRegistro.medico_id, func.max(VisitaRegistro.fecha_hora))
            .filter(VisitaRegistro.medico_id.in_(med_ids), VisitaRegistro.ejecutada == True)  # noqa: E712
            .group_by(VisitaRegistro.medico_id).all())

    salida = []
    for m in medicos:
        d = mapa.get(m.id)
        if d and d["v"] and d["r"]:
            estado = "vr"
        elif d and (d["v"] or d["r"]):
            estado = "v"
        else:
            estado = "sin"
        lid = rm_linea.get(m.vm_id)
        uv = ult_visita.get(m.id)
        salida.append({
            "id": m.id, "vm_id": m.vm_id, "codigo": m.codigo,
            "nombre_completo": m.nombre_completo, "nombre": m.nombre, "apellidos": m.apellidos,
            "especialidad_id": m.especialidad_id,
            "especialidad_nombre": esp_nom.get(m.especialidad_id),
            "subespecialidad": m.subespecialidad,
            "linea_id": lid, "linea_nombre": linea_nom.get(lid),
            "categoria": m.categoria,
            "centro_trabajo": m.centro_trabajo, "institucion_tipo": m.institucion_tipo,
            "tipo_consultorio": m.tipo_consultorio,
            "provincia": m.provincia, "municipio": m.municipio, "sector": m.sector,
            "direccion": m.direccion,
            "latitud": float(m.latitud) if m.latitud is not None else None,
            "longitud": float(m.longitud) if m.longitud is not None else None,
            "telefono": m.telefono, "email": m.email, "exequatur": m.exequatur,
            "dias_consulta": m.dias_consulta, "horario_consulta": m.horario_consulta,
            "frecuencia_visita": m.frecuencia_visita, "acepta_visita": m.acepta_visita,
            "potencial_prescripcion": m.potencial_prescripcion, "kol": m.kol,
            "segmento": m.segmento, "observaciones": m.observaciones,
            "fecha_alta": m.fecha_alta.isoformat() if m.fecha_alta else None,
            "fecha_ultima_visita": uv.isoformat() if uv else None,
            "ciclos_sin_visita": m.ciclos_sin_visita, "activo": m.activo,
            "estado_visita": estado,
            "estado_aprobacion": m.estado_aprobacion,
            "ciclo_baja_id": m.ciclo_baja_id,
        })
    return salida


def listar_medicos_existentes(db: Session, vm_id: int) -> list[dict]:
    """Médicos ya registrados por CUALQUIER visitador del mismo país que `vm_id`, para
    COPIARLOS al panel del VM sin reescribir la ficha. Deduplicados por nombre y
    excluyendo los que ya están en el panel del VM. Devuelve los campos que precargan
    el formulario de alta."""
    vm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
    if not vm:
        return []
    vm_ids_pais = [r[0] for r in db.query(RepresentanteMedico.id)
                   .filter(RepresentanteMedico.pais_codigo == vm.pais_codigo).all()]
    if not vm_ids_pais:
        return []
    # Nombres ya presentes en el panel del VM (para no ofrecer un médico que ya tiene).
    ya = {n[0].upper() for n in db.query(MedicoVisita.nombre_completo)
          .filter(MedicoVisita.vm_id == vm_id).all()}
    esp_nom = dict(db.query(Especialidad.id, Especialidad.nombre).all())
    vm_nom = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.nombre)
                  .filter(RepresentanteMedico.id.in_(vm_ids_pais)).all())
    medicos = (db.query(MedicoVisita)
               .filter(MedicoVisita.vm_id.in_(vm_ids_pais), MedicoVisita.activo == True)  # noqa: E712
               .order_by(MedicoVisita.nombre_completo).all())
    vistos: set[str] = set()
    salida = []
    for m in medicos:
        clave = m.nombre_completo.upper()
        if clave in ya or clave in vistos:
            continue
        vistos.add(clave)
        salida.append({
            "id": m.id, "vm_id": m.vm_id, "vm_nombre": vm_nom.get(m.vm_id),
            "codigo": m.codigo, "nombre_completo": m.nombre_completo,
            "nombre": m.nombre, "apellidos": m.apellidos,
            "especialidad_id": m.especialidad_id, "especialidad_nombre": esp_nom.get(m.especialidad_id),
            "subespecialidad": m.subespecialidad, "categoria": m.categoria,
            "centro_trabajo": m.centro_trabajo, "institucion_tipo": m.institucion_tipo,
            "tipo_consultorio": m.tipo_consultorio, "provincia": m.provincia,
            "municipio": m.municipio, "sector": m.sector, "direccion": m.direccion,
            "latitud": float(m.latitud) if m.latitud is not None else None,
            "longitud": float(m.longitud) if m.longitud is not None else None,
            "telefono": m.telefono, "email": m.email, "exequatur": m.exequatur,
            "dias_consulta": m.dias_consulta, "horario_consulta": m.horario_consulta,
            "frecuencia_visita": m.frecuencia_visita, "acepta_visita": m.acepta_visita,
            "potencial_prescripcion": m.potencial_prescripcion, "kol": m.kol,
            "segmento": m.segmento, "observaciones": m.observaciones,
        })
    return salida
