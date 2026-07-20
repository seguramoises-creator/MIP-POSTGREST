"""Servicio del Módulo de Visita Médica — Fase 1 (Panel Médico).

Incluye la prevención de duplicados del lado servidor (spec 2.2): si 2 o más
palabras del nombre coinciden con un médico ya registrado, se avisa al usuario.
"""
from loguru import logger
from sqlalchemy.orm import Session

from app.models.visita import MedicoVisita, MedicoClasificacion
from app.models.dimensiones import Especialidad, RepresentanteMedico, Linea, Medico
from app.schemas.visita import MedicoVisitaCrear, MedicoVisitaActualizar


class DuplicadoMedicoError(Exception):
    """Se detectaron posibles duplicados y el usuario no confirmó el registro."""
    def __init__(self, duplicados: list[dict]):
        self.duplicados = duplicados
        super().__init__("Posible duplicidad de médico")


# Campos GENERALES del panel que se sincronizan al Maestro (panel → maestro).
# Los de asignación (frecuencia_visita, zona, ruta, categoría, potencial…) NO se propagan.
_MAESTRO_SYNC = {
    "nombre_completo": "nombre", "codigo": "codigo", "especialidad_id": "especialidad_id",
    "exequatur": "exequatur", "telefono": "telefono", "email": "email",
    "direccion": "direccion", "sector": "sector",
}


def _pais_de_vm(db: Session, vm_id: int) -> str | None:
    return db.query(RepresentanteMedico.pais_codigo).filter(RepresentanteMedico.id == vm_id).scalar()


def _resolver_o_crear_maestro(db: Session, datos: MedicoVisitaCrear, usuario_id: int | None) -> int | None:
    """Resuelve el médico central del Maestro para un alta del Panel: match duro
    (exequátur→código) → linkea; sin match → crea (origen=PANEL, estado=PENDIENTE).
    Convierte el duplicado del Maestro en DuplicadoMedicoError (409 ya manejado)."""
    from app.services import maestro_medico_service as mm
    pais = _pais_de_vm(db, datos.vm_id)
    if not pais:
        return None
    existente = mm._resolver_por_llave_dura(db, pais, mm._s(datos.exequatur), None, mm._s(datos.codigo))
    if existente:
        return existente.id
    campos = {}
    for src, dst in _MAESTRO_SYNC.items():
        v = getattr(datos, src, None)
        if v not in (None, ""):
            campos[dst] = v
    try:
        m = mm.crear_maestro(db, pais, campos, origen="PANEL", estado="PENDIENTE",
                             confirmar_duplicado=getattr(datos, "confirmar_duplicado", False),
                             usuario_id=usuario_id)
    except mm.DuplicadoDuroError as e:
        # El médico YA EXISTE en el Maestro (exequátur/cédula, o mismo nombre en el mismo
        # centro). En el PANEL eso NO es un error: es la señal para REUTILIZAR la ficha
        # central y asignársela también a este representante. El Maestro sigue único (no se
        # crea una segunda ficha) y el Panel puede repetir el médico entre representantes,
        # que es justo lo que exige el requerimiento. Bloquear aquí impedía que un segundo
        # visitador agregara a su panel un médico ya registrado por otro.
        ya = (e.coincidencias or [{}])[0]
        if ya.get("id"):
            logger.info(f"Panel: médico ya existe en el Maestro (id={ya['id']}) — se reutiliza "
                        f"para el VM {datos.vm_id} en vez de crear un duplicado.")
            return ya["id"]
        raise DuplicadoMedicoError(e.coincidencias)
    except mm.PosibleDuplicadoError as e:
        # Coincidencia BLANDA (mismo nombre, otro centro): puede ser un homónimo distinto.
        # Se devuelve al usuario para que confirme, como hasta ahora.
        raise DuplicadoMedicoError(e.coincidencias)
    return m.id


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
    # Puente al Maestro central: linkea (match duro) o crea el médico del Maestro.
    maestro_id = _resolver_o_crear_maestro(db, datos, usuario_id)
    medico = MedicoVisita(
        vm_id=datos.vm_id,
        maestro_medico_id=maestro_id,
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
        ciclo_alta_id=ciclo_actual_id(db, datos.vm_id),
        solicitado_por=usuario_id,
        fecha_solicitud=_dt.now(_tz.utc),
        registrado_por=usuario_id,
    )
    db.add(medico)
    db.flush()   # necesitamos el id para colgar la plantilla de clasificación
    # Plantilla de clasificación (Bloque B): se guarda tal cual la capturó el rep. NO se
    # calcula la categoría aquí — la revela el motor cuando el GD aprueba el alta.
    clas = getattr(datos, "clasificacion", None)
    if clas is not None:
        db.add(MedicoClasificacion(
            medico_visita_id=medico.id,
            pacientes_semana=clas.pacientes_semana,
            costo_consulta=clas.costo_consulta,
            potencial_prescripcion=clas.potencial_prescripcion,
            ubicacion_territorial=clas.ubicacion_territorial,
            kol_nivel=clas.kol_nivel,
            capturado_por=usuario_id,
        ))
    db.commit()
    db.refresh(medico)
    logger.info(f"Médico de visita creado id={medico.id} '{medico.nombre_completo}' (VM {medico.vm_id})")
    _avisar_gerente_medico_pendiente(db, medico)
    return medico


def _avisar_gerente_medico_pendiente(db: Session, medico: MedicoVisita) -> None:
    """Correo al Gerente de Distrito del VM: tiene un médico nuevo por aprobar.
    Best-effort — un fallo de correo nunca revierte el alta (ya commiteada)."""
    try:
        from app.models.dimensiones import RepresentanteMedico, Gerente, Especialidad
        from app.models.usuario import Usuario
        from app.services import notification_service

        rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == medico.vm_id).first()
        if not rm or not rm.gerente_id:
            return
        ger = db.query(Gerente).filter(Gerente.id == rm.gerente_id).first()
        correo = ger.email if (ger and ger.email) else None
        if not correo:   # sin email en DIM_Gerente, prueba el usuario vinculado
            ug = db.query(Usuario).filter(Usuario.gerente_id == rm.gerente_id).first()
            correo = ug.email if ug else None
        if not correo:
            return
        esp = None
        if medico.especialidad_id:
            e = db.query(Especialidad).filter(Especialidad.id == medico.especialidad_id).first()
            esp = e.nombre if e else None
        notification_service.notificar_medico_pendiente_aprobacion(
            destinatario=correo, nombre_gerente=(ger.nombre if ger else "Gerente"),
            representante=rm.nombre, medico=medico.nombre_completo,
            especialidad=esp, centro=medico.centro_trabajo)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Aviso de médico pendiente al GD falló (no bloquea) medico={medico.id}: {e}")


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
    # Sincronizar al Maestro SOLO los campos generales que cambiaron (los de
    # asignación —frecuencia, zona, etc.— no se propagan).
    if getattr(medico, "maestro_medico_id", None):
        generales = {_MAESTRO_SYNC[k]: cambios[k] for k in cambios if k in _MAESTRO_SYNC}
        if generales:
            from app.services import maestro_medico_service as mm
            m = db.query(Medico).filter(Medico.id == medico.maestro_medico_id).first()
            if m:
                mm.actualizar_maestro(db, m, generales, usuario_id)
    logger.info(f"Médico de visita actualizado id={medico.id} "
                f"(campos: {', '.join(cambios) or 'ninguno'}) por usuario={usuario_id}")
    return medico


def listar_medicos(db: Session, vm_id: int | None = None, ciclo_id: int | None = None,
                   incluir_inactivos: bool = False, lite: bool = False) -> list[dict]:
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
        # Campos ligeros: los que usan las LISTAS y filtros del Panel/Planeación/Registro.
        base = {
            "id": m.id, "vm_id": m.vm_id, "codigo": m.codigo,
            "nombre_completo": m.nombre_completo,
            "especialidad_id": m.especialidad_id,
            "especialidad_nombre": esp_nom.get(m.especialidad_id),
            "linea_id": lid, "linea_nombre": linea_nom.get(lid),
            "categoria": m.categoria,
            "centro_trabajo": m.centro_trabajo,
            "provincia": m.provincia, "municipio": m.municipio,
            "fecha_ultima_visita": uv.isoformat() if uv else None,
            "ciclos_sin_visita": m.ciclos_sin_visita, "activo": m.activo,
            "estado_visita": estado,
            "estado_aprobacion": m.estado_aprobacion,
            "ciclo_baja_id": m.ciclo_baja_id,
        }
        # Campos pesados (ficha completa): solo para editar un médico (lite=False).
        if not lite:
            base.update({
                "nombre": m.nombre, "apellidos": m.apellidos,
                "subespecialidad": m.subespecialidad,
                "institucion_tipo": m.institucion_tipo, "tipo_consultorio": m.tipo_consultorio,
                "sector": m.sector, "direccion": m.direccion,
                "latitud": float(m.latitud) if m.latitud is not None else None,
                "longitud": float(m.longitud) if m.longitud is not None else None,
                "telefono": m.telefono, "email": m.email, "exequatur": m.exequatur,
                "dias_consulta": m.dias_consulta, "horario_consulta": m.horario_consulta,
                "frecuencia_visita": m.frecuencia_visita, "acepta_visita": m.acepta_visita,
                "potencial_prescripcion": m.potencial_prescripcion, "kol": m.kol,
                "segmento": m.segmento, "observaciones": m.observaciones,
                "fecha_alta": m.fecha_alta.isoformat() if m.fecha_alta else None,
            })
        salida.append(base)
    return salida


def obtener_ficha_medico(db: Session, medico_id: int) -> dict | None:
    """Ficha COMPLETA de UN médico (para editar en el Panel) — consulta directa por id.
    Devuelve un dict (NO el objeto ORM). Para el objeto ORM usar obtener_medico()."""
    m = db.query(MedicoVisita).filter(MedicoVisita.id == medico_id).first()
    if not m:
        return None
    esp = (db.query(Especialidad.nombre).filter(Especialidad.id == m.especialidad_id).scalar()
           if m.especialidad_id else None)
    lid = db.query(RepresentanteMedico.linea_id).filter(RepresentanteMedico.id == m.vm_id).scalar()
    lnom = db.query(Linea.nombre).filter(Linea.id == lid).scalar() if lid else None
    return {
        "id": m.id, "vm_id": m.vm_id, "codigo": m.codigo,
        "nombre_completo": m.nombre_completo, "nombre": m.nombre, "apellidos": m.apellidos,
        "especialidad_id": m.especialidad_id, "especialidad_nombre": esp,
        "subespecialidad": m.subespecialidad,
        "linea_id": lid, "linea_nombre": lnom, "categoria": m.categoria,
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
        "ciclos_sin_visita": m.ciclos_sin_visita, "activo": m.activo,
        "estado_aprobacion": m.estado_aprobacion, "ciclo_baja_id": m.ciclo_baja_id,
    }


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


# ── Puente: importar médicos del Panel desde los datos de Categorización ──────
# Fuente: cat.FactMedicoCategoriaSnapshot (médico → VM → categoría → geografía →
# centro), ya cargado del Excel. Crea en Visita.DIM_MedicoVisita los médicos que
# falten, asignados a su VM y en estado PENDIENTE_ALTA (aprobación del GD).
_SQL_MEDICOS_CAT = """
SELECT rm.id AS vm_id, m."NombreMedico" AS nombre, ce.id AS especialidad_id,
       COALESCE(sn."CategoriaCalculada", sn."CategoriaExcel") AS categoria,
       cm."CentroMedico" AS centro, sn."Provincia" AS provincia, sn."Municipio" AS municipio,
       sn."Periodo" AS periodo
FROM "cat"."FactMedicoCategoriaSnapshot" sn
JOIN "cat"."DimMedico" m ON m."MedicoKey"=sn."MedicoKey"
JOIN "cat"."DimRepresentanteMedico" dr ON dr."RepresentanteKey"=sn."RepresentanteKey"
JOIN "Config"."DIM_RM" rm ON rm.codigo=dr."CodigoRepresentante"
LEFT JOIN "cat"."DimEspecialidad" ecat ON ecat."EspecialidadKey"=m."EspecialidadKey"
LEFT JOIN "Config"."DIM_Especialidad" ce ON LOWER(ce.nombre)=LOWER(TRIM(ecat."Especialidad")) AND ce.activo=TRUE
LEFT JOIN "cat"."DimCentroMedico" cm ON cm."CentroMedicoKey"=sn."CentroMedicoKey"
ORDER BY rm.id, m."NombreMedico", sn."Periodo" DESC
"""


def importar_desde_categorizacion(db: Session, usuario_id: int | None = None) -> dict:
    """Crea en el Panel Médico los médicos cargados en Categorización que aún no
    existan (dedup por VM + nombre). Quedan en PENDIENTE_ALTA. Idempotente."""
    from datetime import date as _date, datetime as _dt, timezone as _tz
    from sqlalchemy import text
    from app.schemas.visita import validar_nombre_medico
    from app.services.visita_aprobacion_service import ciclo_actual_id

    ahora = _dt.now(_tz.utc)
    filas = db.execute(text(_SQL_MEDICOS_CAT)).mappings().all()
    # Alta por VM = ciclo de trabajo del PAÍS del VM (no el de número más alto). Cacheado por VM
    # para no re-consultar. Sellar con el ciclo futuro dejaba el panel efectivo en 0 (ver
    # ciclo_actual_id / cuenta_en_ciclo).
    _ciclo_cache: dict[int, int | None] = {}
    def _ciclo_de_vm(vm: int) -> int | None:
        if vm not in _ciclo_cache:
            _ciclo_cache[vm] = ciclo_actual_id(db, vm)
        return _ciclo_cache[vm]
    # Médicos ya existentes en el panel (vm_id + nombre en MAYÚSCULAS) para no duplicar.
    existentes = {(m.vm_id, (m.nombre_completo or "").upper())
                  for m in db.query(MedicoVisita.vm_id, MedicoVisita.nombre_completo).all()}
    vistos: set[tuple[int, str]] = set()
    creados = omitidos = invalidos = 0
    for f in filas:
        try:
            nombre = validar_nombre_medico(f["nombre"])   # MAYÚSCULAS, ≥2 palabras, sin puntos
        except (ValueError, AttributeError):
            invalidos += 1
            continue
        clave = (f["vm_id"], nombre)
        if clave in vistos or clave in existentes:
            omitidos += 1
            continue
        vistos.add(clave)
        cat = (f["categoria"] or "").strip().upper()
        if cat not in ("A", "B", "C", "D"):
            cat = "C"
        db.add(MedicoVisita(
            vm_id=f["vm_id"], nombre_completo=nombre, especialidad_id=f["especialidad_id"],
            categoria=cat, centro_trabajo=f["centro"], provincia=f["provincia"], municipio=f["municipio"],
            acepta_visita=True, kol=False, ciclos_sin_visita=0, activo=True,
            # Carga masiva autoritativa (admin/gerente): quedan APROBADOS directamente,
            # sin requerir aprobación uno-por-uno del GD. El alta individual por un RM
            # sí queda PENDIENTE_ALTA (ver crear_medico).
            estado_aprobacion="APROBADO", ciclo_alta_id=_ciclo_de_vm(f["vm_id"]),
            fecha_alta=_date.today(), solicitado_por=usuario_id,
            fecha_solicitud=ahora, aprobado_por=usuario_id, fecha_aprobacion=ahora,
            registrado_por=usuario_id))
        creados += 1
    db.commit()
    logger.info(f"Importación Panel←Categorización: creados={creados} omitidos={omitidos} invalidos={invalidos}")
    return {"creados": creados, "omitidos": omitidos, "invalidos": invalidos, "total_origen": len(filas)}


# ── Modificación por el REPRESENTANTE: pasa por validación del GD ──────────────
# Requerimiento jul-2026: al modificar un médico ya aprobado de su panel, el médico
# SIGUE ACTIVO CON LOS DATOS ANTERIORES (no se interrumpe la operación del ciclo) y el
# cambio queda pendiente. Solo aplica al REP: si edita el GD/ADMIN —que es quien valida—
# el cambio se aplica directo.

class SolicitudCambioError(Exception):
    pass


def solicitar_cambio_medico(db: Session, medico: MedicoVisita, datos, clasificacion,
                            usuario_id: int | None):
    """Registra un cambio propuesto SIN tocar el médico. Reemplaza cualquier solicitud
    pendiente previa del mismo médico (la última propuesta es la que vale)."""
    import json
    from app.models.visita import MedicoSolicitudCambio

    cambios = datos.model_dump(exclude_unset=True) if datos is not None else {}
    cambios.pop("activo", None)          # el alta/baja va por su propio flujo
    # Solo se guarda lo que REALMENTE cambia, para que el GD revise diferencias y no
    # un volcado completo de la ficha.
    cambios = {k: v for k, v in cambios.items() if getattr(medico, k, None) != v}
    if not cambios and clasificacion is None:
        raise SolicitudCambioError("No hay cambios que solicitar.")

    db.query(MedicoSolicitudCambio).filter(
        MedicoSolicitudCambio.medico_visita_id == medico.id,
        MedicoSolicitudCambio.estado == "PENDIENTE").delete(synchronize_session=False)

    sol = MedicoSolicitudCambio(
        medico_visita_id=medico.id,
        cambios_json=json.dumps(cambios, default=str) if cambios else None,
        estado="PENDIENTE", solicitado_por=usuario_id,
    )
    if clasificacion is not None:
        sol.pacientes_semana = clasificacion.pacientes_semana
        sol.costo_consulta = clasificacion.costo_consulta
        sol.potencial_prescripcion = clasificacion.potencial_prescripcion
        sol.ubicacion_territorial = clasificacion.ubicacion_territorial
        sol.kol_nivel = clasificacion.kol_nivel
    db.add(sol)
    db.commit()
    db.refresh(sol)
    logger.info(f"Solicitud de cambio {sol.id} sobre médico {medico.id} "
                f"(campos: {', '.join(cambios) or 'solo clasificación'}) por usuario={usuario_id}")
    _avisar_gerente_medico_pendiente(db, medico)
    return sol


def aplicar_solicitud_cambio(db: Session, sol, usuario_id: int | None) -> MedicoVisita:
    """El GD validó: vuelca los cambios sobre el médico y recalcula su categoría."""
    import json
    from datetime import datetime as _dt, timezone as _tz
    from app.models.visita import MedicoClasificacion

    medico = db.query(MedicoVisita).filter(MedicoVisita.id == sol.medico_visita_id).first()
    if not medico:
        raise SolicitudCambioError("El médico ya no existe.")

    if sol.cambios_json:
        for campo, valor in json.loads(sol.cambios_json).items():
            if hasattr(medico, campo):
                setattr(medico, campo, valor)

    # La clasificación propuesta pasa a ser la vigente del médico.
    if sol.potencial_prescripcion or sol.pacientes_semana is not None:
        c = db.query(MedicoClasificacion).filter(
            MedicoClasificacion.medico_visita_id == medico.id).first()
        if c is None:
            c = MedicoClasificacion(medico_visita_id=medico.id)
            db.add(c)
        c.pacientes_semana = sol.pacientes_semana
        c.costo_consulta = sol.costo_consulta
        c.potencial_prescripcion = sol.potencial_prescripcion
        c.ubicacion_territorial = sol.ubicacion_territorial
        c.kol_nivel = sol.kol_nivel
        c.actualizado_por = usuario_id
        c.fecha_actualizacion = _dt.now(_tz.utc)
        db.flush()
        # Recalcular la categoría con los valores nuevos (misma regla que en el alta).
        from app.services.visita_aprobacion_service import _clasificar_al_aprobar
        _clasificar_al_aprobar(db, medico)

    sol.estado = "APROBADO"
    sol.resuelto_por = usuario_id
    sol.fecha_resolucion = _dt.now(_tz.utc)
    db.commit()
    db.refresh(medico)
    logger.info(f"Solicitud de cambio {sol.id} APROBADA por={usuario_id} "
                f"medico={medico.id} categoria={medico.categoria}")
    return medico
