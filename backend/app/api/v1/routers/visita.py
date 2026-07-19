"""Router del Módulo de Visita Médica — Fase 1 (Panel Médico).

Prefijo: /visita.  Reutiliza Config.DIM_RM (VM), Config.DIM_Especialidad.
RBAC: el VM (REPRESENTANTE_MEDICO) gestiona su propio panel (auto-filtro por rm_id);
ADMIN/GERENTE ven/gestionan el de cualquier VM.
"""
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles, get_current_active_user
from app.models.usuario import Rol
from app.schemas.visita import (
    MedicoVisitaCrear, MedicoVisitaActualizar, MedicoVisitaResponse, VisitaRegistrar,
    VisitaNoVisita, PlaneacionGuardar, ParrillaGuardar, MuestrasRegistrar,
    ParametroCostoGuardar, CostoEstructuraGuardar, _CAUSAS_NO_VISITA,
)
from app.services import visita_service

router = APIRouter(prefix="/visita", tags=["Visita Médica"])

RequireVisita = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_DISTRITO, Rol.GERENTE_PRODUCTIVIDAD, Rol.REPRESENTANTE_MEDICO))
# El cierre de ciclo hace rodar el contador de todos los paneles: operación gerencial.
RequireCierre = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))
# Aprobación de alta/baja de médicos: Gerente de Distrito (acotado a su distrito) + superusuarios.
RequireAprobador = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO))
# Parrilla promocional: solo el Gerente de Producto (marca/productividad) + ADMIN.
RequireGerenteProducto = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_MARCA))
# Desbloquear una planeación publicada: SOLO ADMIN (decisión del cliente, jul-2026). Ni el
# Gerente de Distrito — es justo quien tiene interés en que su distrito luzca bien.
RequireDesbloqueo = Depends(require_roles(Rol.ADMIN))
# Costo & ROI (salarios, costos, ROI de la fuerza de venta, presupuestos): dato gerencial.
# El representante NO entra aquí — usa /costo/mi-linea (recorte autorizado: unidades por
# contacto + impacto de la cobertura en el presupuesto de su línea).
RequireFinanciero = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA))
RequireAnyAuth = Depends(get_current_active_user)
# RBAC Fase 2: captura por matriz. Registrar visita = RM (register) + ADMIN; planeación = RM
# register / GD read (equipo). Parrilla consulta = lectura amplia. Parrilla CONFIG = Gerente de
# Producto (GERENTE_MARCA) + ADMIN — DECISIÓN jul-2026: se resolvió el conflicto matriz-vs-app a
# favor del Gerente de Producto (inversión de marca); la matriz se ajustó (parrilla.configurar →
# GERENTE_MARCA configure, GD solo consulta).
from app.core.authz.deps import require as _require_authz, autorizar as _autorizar_authz
from app.core.authz.constantes import Accion as _Acc, Recurso as _Rec, Alcance as _Alc
RegistrarVisitaGuard = Depends(_require_authz(_Acc.REGISTER, _Rec.VISITA_REGISTRAR))
ReadPlaneacion = Depends(_require_authz(_Acc.READ, _Rec.PLANEACION_CICLO))
RegistrarPlaneacion = Depends(_require_authz(_Acc.REGISTER, _Rec.PLANEACION_CICLO))
ReadParrilla = Depends(_require_authz(_Acc.READ, _Rec.PARRILLA_CONSULTA))
ConfigurarParrilla = Depends(_require_authz(_Acc.CONFIGURE, _Rec.PARRILLA_CONFIGURAR))
# Cobertura de Visita (gauges/ranking) y Ruptura: lectura por matriz (cobertura.diaria). La ven
# todos los roles con lectura de cobertura (incl. CONSULTA/Analista/Dirección = todo; RM acotado).
ReadCobertura = Depends(_require_authz(_Acc.READ, _Rec.COBERTURA_DIARIA))
# Panel Médico (lista/ficha de médicos): lectura por matriz (medico.panel). CONSULTA/Analista/
# Dirección/Gerentes leen; el RM ve su panel (scope propio). Las ESCRITURAS siguen restringidas aparte.
ReadMedicoPanel = Depends(_require_authz(_Acc.READ, _Rec.MEDICO_PANEL))
# Costo/ROI: Finanzas CONFIGURA (BORRADOR), Director APRUEBA. Segregación estructural (quien
# configura no aprueba: FINANZAS≠PRESIDENCIA). ADMIN puede ambas + reabrir (dato cerrado).
ConfigurarCosto = Depends(_require_authz(_Acc.CONFIGURE, _Rec.COSTOROI_CONFIGURAR))
AprobarCosto = Depends(_require_authz(_Acc.APPROVE, _Rec.COSTOROI_CONFIGURAR))
# #15 (jul-2026): el MODELO FINANCIERO completo (salarios, costos, pool) lo LEEN quienes tienen
# visión TOTAL de Costo/ROI (costoroi.ver = todo): FINANZAS, Director, Analista, Gerentes de
# Producto/Marketing, CONSULTA, ADMIN. El GD y el RM tienen alcance propio/equipo → NO ven
# salarios/costos: usan el RECORTE (/costo/mi-linea). CONFIGURAR/APROBAR siguen restringidos aparte.
def _leer_costo_full(_a=Depends(_autorizar_authz(_Acc.READ, _Rec.COSTOROI_VER))):
    if _a.alcance != _Alc.ALL:
        raise HTTPException(
            status_code=403,
            detail="El modelo financiero completo requiere visión total de Costo/ROI. "
                   "Tu vista acotada está en Costo & ROI de tu línea.")
    return _a.usuario


LeerCostoFull = Depends(_leer_costo_full)
LeerCostoVer = Depends(_require_authz(_Acc.READ, _Rec.COSTOROI_VER))


def _rol(u) -> str:
    return u.rol.value if hasattr(u.rol, "value") else str(u.rol)


def _scope_vm(current_user, vm_id: int | None) -> int | None:
    """Un REPRESENTANTE_MEDICO se fuerza a su propio rm_id; los demás pasan vm_id libre."""
    if _rol(current_user) == "REPRESENTANTE_MEDICO":
        rm = getattr(current_user, "rm_id", None)
        if not rm:
            raise HTTPException(status_code=403, detail="Tu usuario no está vinculado a un representante (rm_id).")
        return rm
    return vm_id


def _raise_captura_error(e: ValueError) -> None:
    """Traduce un ValueError de una función de captura ligada a un ciclo: 409 si el
    motivo es el guard de ciclo cerrado (solo lectura), 400 para cualquier otra
    validación de negocio."""
    mensaje = str(e)
    if "cerrado" in mensaje.lower() or "solo lectura" in mensaje.lower():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=mensaje)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=mensaje)


@router.get("/especialidades", response_model=list[dict])
def listar_especialidades(db: Session = Depends(get_db), current_user=RequireAnyAuth):
    """Catálogo de especialidades (para el selector al registrar médicos)."""
    from app.services import geo_catalogo_service
    return geo_catalogo_service.listar_especialidades(db)


@router.get("/provincias", response_model=list[dict])
def listar_provincias(pais_codigo: str | None = None, db: Session = Depends(get_db),
                      current_user=RequireAnyAuth):
    """Provincias (dropdown del maestro de médicos). Filtra por país si se indica."""
    from app.services import geo_catalogo_service
    return geo_catalogo_service.listar_provincias(db, pais_codigo)


@router.get("/municipios", response_model=list[dict])
def listar_municipios(provincia_id: int | None = None, db: Session = Depends(get_db),
                      current_user=RequireAnyAuth):
    """Municipios de una provincia (dropdown en cascada)."""
    from app.services import geo_catalogo_service
    return geo_catalogo_service.listar_municipios(db, provincia_id)


@router.get("/centros", response_model=list[dict])
def listar_centros(pais_codigo: str | None = None, db: Session = Depends(get_db),
                   current_user=RequireAnyAuth):
    """Centros médicos (dropdown del maestro de médicos). Filtra por país si se indica."""
    from app.services import geo_catalogo_service
    return geo_catalogo_service.listar_centros(db, pais_codigo)


@router.get("/mi-gerente", response_model=dict)
def mi_gerente(vm_id: int | None = None, db: Session = Depends(get_db), current_user=RequireAnyAuth):
    """Gerente de Distrito de la línea del visitador. Para un REPRESENTANTE_MEDICO
    se resuelve por su propio rm_id; ADMIN/gerentes pueden pasar ?vm_id=."""
    from app.models.dimensiones import RepresentanteMedico, Gerente, Linea
    rid = vm_id
    if rid is None and _rol(current_user) == "REPRESENTANTE_MEDICO":
        rid = getattr(current_user, "rm_id", None)
    if not rid:
        return {"gerente": None, "linea": None, "vm": None}
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == rid).first()
    if not rm:
        return {"gerente": None, "linea": None, "vm": None}
    g = db.query(Gerente).filter(Gerente.id == rm.gerente_id).first() if rm.gerente_id else None
    linea = db.query(Linea).filter(Linea.id == rm.linea_id).first() if rm.linea_id else None
    return {
        "gerente": g.nombre if g else None,
        "gerente_tipo": getattr(g, "tipo", None) if g else None,
        "linea": linea.nombre if linea else None,
        "vm": rm.nombre,
    }


@router.get("/vms", response_model=list[dict])
def listar_vms(db: Session = Depends(get_db), current_user=RequireAnyAuth):
    """Visitadores médicos (DIM_RM) — para que ADMIN/GERENTE elijan el panel a ver."""
    from app.models.dimensiones import RepresentanteMedico
    return [{"id": r.id, "nombre": r.nombre}
            for r in db.query(RepresentanteMedico).filter(RepresentanteMedico.activo == True)  # noqa: E712
            .order_by(RepresentanteMedico.nombre).all()]


@router.get("/medicos", response_model=list[dict])
def listar_medicos(vm_id: int | None = None, incluir_inactivos: bool = False,
                   lite: bool = False,
                   db: Session = Depends(get_db), current_user=ReadMedicoPanel):
    """Panel médico. El VM ve solo el suyo; ADMIN/GERENTE pueden filtrar por ?vm_id=.
    `incluir_inactivos=true` incluye los médicos desactivados (para reactivarlos).
    `lite=true` devuelve solo los campos de LISTA (rendimiento; la ficha completa se
    obtiene con GET /visita/medicos/{id} al editar)."""
    vm = _scope_vm(current_user, vm_id)
    return visita_service.listar_medicos(db, vm_id=vm, incluir_inactivos=incluir_inactivos, lite=lite)


@router.get("/medicos/existentes", response_model=list[dict])
def listar_medicos_existentes(vm_id: int | None = None, db: Session = Depends(get_db),
                              current_user=ReadMedicoPanel):
    """Médicos ya registrados en otros paneles del mismo país, para COPIAR al panel del
    VM (evita reescribir la ficha). El VM se fuerza a su propio rm_id; ADMIN/GERENTE
    deben indicar el visitador destino con ?vm_id=."""
    vm = _scope_vm(current_user, vm_id)
    if not vm:
        raise HTTPException(status_code=400, detail="Indica el visitador destino (vm_id).")
    return visita_service.listar_medicos_existentes(db, vm)


@router.get("/medicos/{medico_id}", response_model=dict)
def obtener_medico(medico_id: int, db: Session = Depends(get_db), current_user=ReadMedicoPanel):
    """Ficha COMPLETA de un médico (para editar). El VM solo ve los de su panel.
    Declarado DESPUÉS de /medicos/existentes para no interceptar esa ruta literal."""
    m = visita_service.obtener_ficha_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    if _rol(current_user) == "REPRESENTANTE_MEDICO" and m.get("vm_id") != getattr(current_user, "rm_id", None):
        raise HTTPException(status_code=403, detail="Solo puedes ver los médicos de tu panel.")
    return m


@router.put("/medicos/{medico_id}", response_model=MedicoVisitaResponse)
def actualizar_medico(medico_id: int, datos: MedicoVisitaActualizar,
                      db: Session = Depends(get_db), current_user=RequireVisita):
    """Edita un médico o lo activa/desactiva (campo `activo`). El VM solo puede
    modificar médicos de su propio panel."""
    m = visita_service.obtener_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    if _rol(current_user) == "REPRESENTANTE_MEDICO":
        rm = _scope_vm(current_user, None)
        if m.vm_id != rm:
            raise HTTPException(status_code=403, detail="Este médico no pertenece a tu panel.")
    # El alta/baja (campo `activo`) NO se cambia por edición directa: pasa por aprobación.
    # (actualizar_medico ignora `activo` explícitamente; no lo asignamos aquí para no
    #  marcarlo como "set" en Pydantic, lo que haría un UPDATE activo=NULL — bug histórico.)
    try:
        return visita_service.actualizar_medico(db, m, datos, getattr(current_user, "id", None))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _medico_de_mi_panel(current_user, m):
    if _rol(current_user) == "REPRESENTANTE_MEDICO":
        rm = _scope_vm(current_user, None)
        if m.vm_id != rm:
            raise HTTPException(status_code=403, detail="Este médico no pertenece a tu panel.")


@router.post("/medicos/{medico_id}/baja", response_model=dict)
def solicitar_baja(medico_id: int, db: Session = Depends(get_db), current_user=RequireVisita):
    """Solicita la BAJA de un médico. Requiere aprobación del Gerente de Distrito;
    efectiva el próximo ciclo. El VM solo puede solicitar sobre su panel."""
    from app.services import visita_aprobacion_service as aps
    m = visita_service.obtener_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    _medico_de_mi_panel(current_user, m)
    aps.solicitar_baja(db, m, current_user)
    return {"id": m.id, "estado_aprobacion": m.estado_aprobacion}


@router.post("/medicos/{medico_id}/reactivar", response_model=dict)
def reactivar_medico(medico_id: int, db: Session = Depends(get_db), current_user=RequireVisita):
    """Reactiva un médico inactivo/rechazado: vuelve a quedar PENDIENTE_ALTA (requiere
    aprobación, efectivo el próximo ciclo)."""
    from app.services.visita_aprobacion_service import ciclo_actual_id
    from datetime import datetime as _dt, timezone as _tz
    m = visita_service.obtener_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    _medico_de_mi_panel(current_user, m)
    m.activo = True
    m.estado_aprobacion = "PENDIENTE_ALTA"
    m.ciclo_alta_id = ciclo_actual_id(db)
    m.ciclo_baja_id = None
    m.solicitado_por = getattr(current_user, "id", None)
    m.fecha_solicitud = _dt.now(_tz.utc)
    db.commit()
    return {"id": m.id, "estado_aprobacion": m.estado_aprobacion}


@router.get("/aprobaciones", response_model=list[dict])
def listar_aprobaciones(db: Session = Depends(get_db), current_user=RequireAprobador):
    """Solicitudes de alta/baja pendientes que este gerente puede aprobar."""
    from app.services import visita_aprobacion_service as aps
    return aps.listar_pendientes(db, current_user)


@router.post("/medicos/{medico_id}/aprobar", response_model=dict)
def aprobar_medico(medico_id: int, db: Session = Depends(get_db), current_user=RequireAprobador):
    """Aprueba la solicitud pendiente (alta o baja). Efecto al próximo ciclo."""
    from app.services import visita_aprobacion_service as aps
    m = visita_service.obtener_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    try:
        aps.aprobar(db, m, current_user)
    except aps.AprobacionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return {"id": m.id, "estado_aprobacion": m.estado_aprobacion}


@router.post("/medicos/{medico_id}/rechazar", response_model=dict)
def rechazar_medico(medico_id: int, motivo: str | None = None,
                    db: Session = Depends(get_db), current_user=RequireAprobador):
    """Rechaza la solicitud pendiente (alta → queda inactivo; baja → se cancela)."""
    from app.services import visita_aprobacion_service as aps
    m = visita_service.obtener_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    try:
        aps.rechazar(db, m, current_user, motivo)
    except aps.AprobacionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return {"id": m.id, "estado_aprobacion": m.estado_aprobacion}


@router.post("/medicos", response_model=MedicoVisitaResponse, status_code=status.HTTP_201_CREATED)
def crear_medico(datos: MedicoVisitaCrear, db: Session = Depends(get_db), current_user=RequireVisita):
    """Registra un médico nuevo. Si hay posible duplicado y no se confirmó, responde
    409 con la lista de coincidencias (el cliente muestra el aviso y reintenta con
    confirmar_duplicado=true)."""
    # El VM solo registra en su propio panel.
    if _rol(current_user) == "REPRESENTANTE_MEDICO":
        datos.vm_id = _scope_vm(current_user, None)
    try:
        return visita_service.crear_medico(db, datos, getattr(current_user, "id", None))
    except visita_service.DuplicadoMedicoError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"mensaje": "Posible duplicidad — verificar", "duplicados": e.duplicados},
        )


@router.post("/medicos/importar-categorizacion", response_model=dict)
def importar_medicos_categorizacion(db: Session = Depends(get_db), current_user=RequireCierre):
    """Carga masiva del Panel Médico desde los datos ya cargados en Categorización:
    crea los médicos faltantes (dedup por VM + nombre), asignados a su VM y en estado
    PENDIENTE_ALTA. Solo ADMIN / GERENTE_PRODUCTIVIDAD."""
    return visita_service.importar_desde_categorizacion(db, getattr(current_user, "id", None))


@router.get("/gerentes", response_model=list[dict])
def listar_gerentes(db: Session = Depends(get_db), current_user=RequireAnyAuth):
    """Gerentes de Distrito (para el filtro de cobertura)."""
    from app.models.dimensiones import Gerente
    return [{"id": g.id, "nombre": g.nombre}
            for g in db.query(Gerente).filter(Gerente.tipo == "DISTRITO", Gerente.activo == True)  # noqa: E712
            .order_by(Gerente.nombre).all()]


@router.get("/cobertura/resumen", response_model=dict)
def cobertura_resumen(ciclo_id: int | None = None, vm_id: int | None = None,
                      gerente_id: int | None = None, linea_id: int | None = None,
                      solo_ruptura: bool = False,
                      db: Session = Depends(get_db), current_user=ReadCobertura):
    """Dashboard de Cobertura: gauges (cobertura/V+R/gap), desglose A/B/C, listas y ruptura.
    El VM ve su propia cobertura; ADMIN/GERENTE ven el equipo o filtran por visitador
    (?vm_id=), Gerente de Distrito (?gerente_id=), Línea (?linea_id=) y ruptura (?solo_ruptura=)."""
    from app.services import visita_cobertura_service
    vm = _scope_vm(current_user, vm_id)
    return visita_cobertura_service.resumen_cobertura(
        db, ciclo_id, vm, gerente_id, linea_id, solo_ruptura)


@router.get("/cobertura/ranking", response_model=dict)
def cobertura_ranking(metrica: str = "cobertura", ciclo_id: int | None = None,
                      db: Session = Depends(get_db), current_user=ReadCobertura):
    """Detalle desplegable por visitador: ranking de quién cumple/no el indicador.
    metrica: 'cobertura' | 'completa' | 'sin_visitar'."""
    from app.services import visita_cobertura_service
    return visita_cobertura_service.ranking_visitadores(db, ciclo_id, metrica)


# ── Registro de visita (Parte 4) ──────────────────────────────────────────────
def _vm_registro(current_user, vm_id: int | None) -> int:
    vm = _scope_vm(current_user, vm_id)
    if not vm:
        raise HTTPException(status_code=400, detail="Indica el visitador (vm_id).")
    return vm


@router.get("/causas", response_model=list[str])
def causas_no_visita(current_user=RequireAnyAuth):
    """Catálogo de causas de no-visita (para el selector)."""
    return sorted(_CAUSAS_NO_VISITA)


@router.get("/mis-visitas-hoy", response_model=list[dict])
def mis_visitas_hoy(vm_id: int | None = None, db: Session = Depends(get_db), current_user=RequireVisita):
    """Visitas registradas hoy por el VM (feed del móvil)."""
    from app.services import visita_registro_service
    return visita_registro_service.visitas_del_dia(db, _vm_registro(current_user, vm_id))


@router.get("/historial", response_model=list[dict])
def historial_visitas(vm_id: int | None = None, dias: int = 30,
                      db: Session = Depends(get_db), current_user=RequireVisita):
    """Visitas anteriores del VM (SOLO LECTURA): el RM consulta sus registros y
    ve su comentario, pero nunca puede modificarlos — no existen endpoints de
    edición/borrado de visitas."""
    from app.services import visita_registro_service
    return visita_registro_service.historial_visitas(db, _vm_registro(current_user, vm_id), dias)


@router.get("/agenda-hoy", response_model=list[dict])
def agenda_hoy(vm_id: int | None = None, db: Session = Depends(get_db), current_user=RequireVisita):
    """Médicos programados del VM para hoy (agenda), con su estado pendiente/registrada."""
    from app.services import visita_registro_service
    return visita_registro_service.agenda_hoy(db, _vm_registro(current_user, vm_id))


@router.post("/registrar", response_model=dict, status_code=status.HTTP_201_CREATED)
def registrar_visita(datos: VisitaRegistrar, vm_id: int | None = None,
                     db: Session = Depends(get_db), current_user=RegistrarVisitaGuard):
    """Registra una visita ejecutada. Usa la hora del servidor (ventana 60 min)."""
    from app.services import visita_registro_service
    try:
        v = visita_registro_service.registrar_visita(db, _vm_registro(current_user, vm_id), datos, getattr(current_user, "id", None))
        return {"id": v.id, "tipo": v.tipo_visita, "hora": v.fecha_hora.isoformat() if v.fecha_hora else None}
    except ValueError as e:
        _raise_captura_error(e)


@router.post("/no-visita", response_model=dict, status_code=status.HTTP_201_CREATED)
def registrar_no_visita(datos: VisitaNoVisita, vm_id: int | None = None,
                        db: Session = Depends(get_db), current_user=RegistrarVisitaGuard):
    """Registra una no-visita con su causa (no cuenta como visita, no penaliza cobertura)."""
    from app.services import visita_registro_service
    try:
        v = visita_registro_service.registrar_no_visita(db, _vm_registro(current_user, vm_id), datos, getattr(current_user, "id", None))
        return {"id": v.id, "causa": v.causa_no_visita}
    except ValueError as e:
        _raise_captura_error(e)


@router.post("/{visita_id}/foto", response_model=dict, status_code=status.HTTP_201_CREATED)
async def subir_foto_visita(
    visita_id: int, archivo: UploadFile = File(...),
    db: Session = Depends(get_db), current_user=RegistrarVisitaGuard,
):
    """Sube la foto del centro para una visita (JPEG/PNG, ≤ 15 MB). Se guarda como BLOB.
    El frontend convierte/comprime a JPEG antes de subir (incl. HEIC de iPhone)."""
    from app.services import visita_registro_service
    contenido = await archivo.read()
    try:
        visita_registro_service.guardar_foto_visita(
            db, visita_id, contenido, archivo.content_type or "image/jpeg")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"id": visita_id, "bytes": len(contenido)}


@router.get("/{visita_id}/foto")
def obtener_foto_visita_endpoint(
    visita_id: int, db: Session = Depends(get_db), current_user=RequireVisita,
):
    """Devuelve la imagen de la visita (BLOB). 404 si no tiene foto."""
    from fastapi import Response
    from app.services import visita_registro_service
    data = visita_registro_service.obtener_foto_visita(db, visita_id)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin foto")
    contenido, mime = data
    return Response(content=contenido, media_type=mime)


# ── Planeación del ciclo (Parte 3) ────────────────────────────────────────────
@router.get("/planeacion", response_model=list[dict])
def obtener_planeacion(vm_id: int | None = None, ciclo_id: int | None = None,
                       db: Session = Depends(get_db), current_user=ReadPlaneacion):
    """Planeación del ciclo del VM (ítems Vista/Revisita por médico). El VM ve la suya."""
    from app.services import visita_planeacion_service
    return visita_planeacion_service.listar_planeacion(db, _vm_registro(current_user, vm_id), ciclo_id)


@router.post("/planeacion", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_planeacion(datos: PlaneacionGuardar, vm_id: int | None = None, ciclo_id: int | None = None,
                       db: Session = Depends(get_db), current_user=RegistrarPlaneacion):
    """Guarda (reemplaza) la planeación del ciclo. Valida reglas P01/P02/P03.
    Rechaza con 409 si la planeación ya fue publicada (congelada)."""
    from app.services import visita_planeacion_service
    try:
        n = visita_planeacion_service.guardar_planeacion(
            db, _vm_registro(current_user, vm_id), ciclo_id, datos.items, getattr(current_user, "id", None))
        return {"guardadas": n}
    except visita_planeacion_service.PlaneacionPublicadaError as e:
        # No es ValueError: sin este except escapaba como 500 "Error interno del servidor" y
        # el representante nunca leia el motivo real.
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        _raise_captura_error(e)


@router.get("/planeacion/estado", response_model=dict)
def estado_planeacion(vm_id: int | None = None, ciclo_id: int | None = None,
                      db: Session = Depends(get_db), current_user=ReadPlaneacion):
    """Si la planeación del ciclo está publicada (congelada) + su historial de eventos."""
    from app.services import visita_planeacion_service
    return visita_planeacion_service.estado_planeacion(db, _vm_registro(current_user, vm_id), ciclo_id)


@router.post("/planeacion/publicar", response_model=dict)
def publicar_planeacion(vm_id: int | None = None, ciclo_id: int | None = None,
                        db: Session = Depends(get_db), current_user=RegistrarPlaneacion):
    """Publica (CONGELA) la planeación del ciclo. Irreversible salvo desbloqueo del ADMIN:
    es el denominador con el que se calcula la cobertura."""
    from app.services import visita_planeacion_service
    try:
        return visita_planeacion_service.publicar_planeacion(
            db, _vm_registro(current_user, vm_id), ciclo_id, getattr(current_user, "id", None))
    except visita_planeacion_service.PlaneacionPublicadaError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        _raise_captura_error(e)


@router.post("/planeacion/desbloquear", response_model=dict)
def desbloquear_planeacion(vm_id: int, motivo: str = Body(..., embed=True),
                           ciclo_id: int | None = None,
                           db: Session = Depends(get_db), current_user=RequireDesbloqueo):
    """Devuelve la planeación a borrador. **Solo ADMIN** y con motivo: queda registrado quién
    desbloqueó, cuándo y por qué (`PlaneacionEvento`, append-only). `vm_id` es obligatorio —
    un admin desbloquea la de un representante concreto, nunca la suya "por defecto"."""
    from app.services import visita_planeacion_service
    try:
        return visita_planeacion_service.desbloquear_planeacion(
            db, vm_id, ciclo_id, getattr(current_user, "id", None), motivo)
    except ValueError as e:
        _raise_captura_error(e)


@router.get("/planeacion/resumen", response_model=dict)
def resumen_planeacion(vm_id: int | None = None, ciclo_id: int | None = None,
                       db: Session = Depends(get_db), current_user=ReadPlaneacion):
    """Resumen de la planeación: cobertura planeada, carga por día y aviso de Cat A sin Revisita."""
    from app.services import visita_planeacion_service
    return visita_planeacion_service.resumen_planeacion(db, _vm_registro(current_user, vm_id), ciclo_id)


# ── Ruptura de secuencia / Cierre de ciclo (Parte 5) ──────────────────────────
@router.get("/ruptura", response_model=dict)
def estado_ruptura(vm_id: int | None = None, gerente_id: int | None = None,
                   linea_id: int | None = None, db: Session = Depends(get_db),
                   current_user=ReadCobertura):
    """Médicos en ruptura por severidad (1 / 2 / ≥3 ciclos sin visita). El VM ve el suyo;
    gestión puede filtrar por Gerente de Distrito (?gerente_id=) y Línea (?linea_id=)."""
    from app.services import visita_cierre_service
    return visita_cierre_service.estado_ruptura(
        db, _scope_vm(current_user, vm_id), gerente_id, linea_id)


@router.get("/cierre/previsualizar", response_model=dict)
def previsualizar_cierre(ciclo_id: int | None = None, db: Session = Depends(get_db), current_user=RequireCierre):
    """Simula el cierre del ciclo (sin escribir): cuántos se resetean/incrementan y si ya está cerrado."""
    from app.services import visita_cierre_service
    try:
        return visita_cierre_service.previsualizar_cierre(db, ciclo_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/cierre", response_model=dict, status_code=status.HTTP_201_CREATED)
def cerrar_ciclo(ciclo_id: int | None = None, db: Session = Depends(get_db), current_user=RequireCierre):
    """Cierra el ciclo de visita: hace rodar `ciclos_sin_visita`. Idempotente (409 si ya se cerró)."""
    from app.services import visita_cierre_service
    try:
        return visita_cierre_service.cerrar_ciclo(db, ciclo_id, getattr(current_user, "id", None))
    except visita_cierre_service.CicloVisitaYaCerradoError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"mensaje": "Este ciclo ya fue cerrado.",
                    "fecha_cierre": e.cierre.fecha_cierre.isoformat() if e.cierre.fecha_cierre else None})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/cierre/historial", response_model=list[dict])
def historial_cierres(db: Session = Depends(get_db), current_user=RequireCierre):
    """Historial de cierres de ciclo de visita, del más reciente al más antiguo."""
    from app.services import visita_cierre_service
    return visita_cierre_service.historial_cierres(db)


# ── Parrilla promocional / Muestras (Parte 6) ─────────────────────────────────
@router.get("/lineas", response_model=list[dict])
def listar_lineas(db: Session = Depends(get_db), current_user=RequireAnyAuth):
    """Líneas de producto (para el selector de la parrilla)."""
    from app.services import visita_parrilla_service
    return visita_parrilla_service.listar_lineas(db)


@router.get("/parrilla", response_model=list[dict])
def obtener_parrilla(linea_id: int | None = None, ciclo_id: int | None = None,
                     vm_id: int | None = None,
                     db: Session = Depends(get_db), current_user=ReadParrilla):
    """Parrilla del ciclo para una línea. Sin `linea_id` se usa la línea del VM
    (el RM usa la suya propia; gestión puede indicar `vm_id`). El VM SOLO ve
    parrillas publicadas; el Gerente de Producto ve también los borradores."""
    from app.services import visita_parrilla_service
    if linea_id is None:
        vm = _scope_vm(current_user, vm_id)
        linea_id = visita_parrilla_service.linea_de_vm(db, vm) if vm else None
    if linea_id is None:
        raise HTTPException(status_code=400, detail="Indica la línea (linea_id).")
    solo_pub = _rol(current_user) in ("REPRESENTANTE_MEDICO", "GERENTE_DISTRITO", "CONSULTA")
    return visita_parrilla_service.listar_parrilla(db, ciclo_id, linea_id, solo_publicada=solo_pub)


@router.get("/productos", response_model=list[dict])
def listar_productos(linea_id: int | None = None, db: Session = Depends(get_db), current_user=RequireAnyAuth):
    """Catálogo DIM_Producto (para llenar la parrilla)."""
    from app.services import visita_parrilla_service
    return visita_parrilla_service.listar_productos(db, linea_id)


@router.get("/parrilla/penetracion", response_model=dict)
def parrilla_penetracion(linea_id: int | None = None, ciclo_id: int | None = None,
                         db: Session = Depends(get_db), current_user=RequireVisita):
    """Penetración del ciclo por producto (médicos alcanzados, muestras, promedio/visita)."""
    from app.services import visita_parrilla_service
    if linea_id is None:
        vm = _scope_vm(current_user, None)
        linea_id = visita_parrilla_service.linea_de_vm(db, vm) if vm else None
    if linea_id is None:
        raise HTTPException(status_code=400, detail="Indica la línea (linea_id).")
    return visita_parrilla_service.penetracion_ciclo(db, ciclo_id, linea_id)


@router.post("/parrilla/publicar", response_model=dict)
def publicar_parrilla(linea_id: int, ciclo_id: int | None = None,
                      db: Session = Depends(get_db), current_user=ConfigurarParrilla):
    """Publica la parrilla al equipo (Gerente de Producto). El VM la recibe en solo lectura."""
    from app.services import visita_parrilla_service
    try:
        n = visita_parrilla_service.publicar_parrilla(db, ciclo_id, linea_id, getattr(current_user, "id", None))
        return {"publicados": n}
    except ValueError as e:
        _raise_captura_error(e)


@router.post("/parrilla", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_parrilla(datos: ParrillaGuardar, db: Session = Depends(get_db), current_user=ConfigurarParrilla):
    """Guarda (reemplaza) la parrilla de una línea en el ciclo. Solo Gerente de Producto.
    Queda en borrador hasta publicar."""
    from app.services import visita_parrilla_service
    try:
        n = visita_parrilla_service.guardar_parrilla(
            db, datos.ciclo_id, datos.linea_id, datos.items, getattr(current_user, "id", None))
        return {"guardados": n}
    except ValueError as e:
        _raise_captura_error(e)


@router.post("/muestras", response_model=dict, status_code=status.HTTP_201_CREATED)
def registrar_muestras(datos: MuestrasRegistrar, vm_id: int | None = None,
                       db: Session = Depends(get_db), current_user=RequireVisita):
    """Registra muestras entregadas a un médico del panel. El VM va contra su panel."""
    from app.services import visita_parrilla_service
    try:
        n = visita_parrilla_service.registrar_muestras(
            db, _vm_registro(current_user, vm_id), datos.ciclo_id, datos.medico_id,
            datos.entregas, getattr(current_user, "id", None))
        return {"registradas": n}
    except ValueError as e:
        _raise_captura_error(e)


@router.get("/muestras/resumen", response_model=dict)
def resumen_muestras(vm_id: int | None = None, ciclo_id: int | None = None,
                     db: Session = Depends(get_db), current_user=RequireVisita):
    """Resumen de muestras por producto: entregadas, médicos alcanzados, meta y cobertura."""
    from app.services import visita_parrilla_service
    return visita_parrilla_service.resumen_muestras(db, ciclo_id, _scope_vm(current_user, vm_id))


# ── Costo & ROI (Parte 8) ─────────────────────────────────────────────────────
# Los parámetros de costo (salario, viáticos, materiales) y el ROI por VM son datos
# financieros: solo gestión. `RequireFinanciero` está definido más arriba, junto a
# /costo/estructura.
@router.get("/costo/parametros", response_model=dict)
def obtener_parametros_costo(linea_id: int | None = None, ciclo_id: int | None = None,
                             db: Session = Depends(get_db), current_user=RequireFinanciero):
    """Parámetros de costo resueltos (cascada línea → default del ciclo). Solo gestión."""
    from app.services import visita_costo_service
    return visita_costo_service.obtener_parametros(db, ciclo_id, linea_id)


@router.post("/costo/parametros", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_parametros_costo(datos: ParametroCostoGuardar, db: Session = Depends(get_db), current_user=ConfigurarCosto):
    """Configura los parámetros de costo del ciclo (por línea o default). Solo gestión."""
    from app.services import visita_costo_service
    try:
        return visita_costo_service.guardar_parametros(db, datos, getattr(current_user, "id", None))
    except ValueError as e:
        _raise_captura_error(e)


@router.get("/costo/roi", response_model=dict)
def costo_roi(vm_id: int | None = None, ciclo_id: int | None = None,
              db: Session = Depends(get_db), current_user=LeerCostoFull):
    """Costo & ROI del ciclo: costo por contacto/médico, ingresos, utilidad y ROI. Solo gestión
    (dato financiero). El representante ve su recorte en /costo/mi-linea."""
    from app.services import visita_costo_service
    return visita_costo_service.roi(db, ciclo_id, vm_id)


@router.get("/costo/ranking", response_model=dict)
def costo_ranking(ciclo_id: int | None = None, db: Session = Depends(get_db), current_user=RequireCierre):
    """Detalle desplegable de ROI por VM (peor primero). Solo gestión (dato financiero)."""
    from app.services import visita_costo_service
    return visita_costo_service.roi_ranking(db, ciclo_id)


def _linea_del_representante(db, current_user) -> int | None:
    """Línea del representante logueado (para auto-acotar su vista de Costo)."""
    vm = _scope_vm(current_user, None)
    if not vm:
        return None
    from app.services.visita_parrilla_service import linea_de_vm
    return linea_de_vm(db, vm)


def _linea_del_gerente(db, current_user) -> int | None:
    """Línea del equipo del Gerente de Distrito (resuelta por la línea de sus RMs). #15."""
    gid = getattr(current_user, "gerente_id", None)
    if not gid:
        return None
    from app.models.dimensiones import RepresentanteMedico
    row = (db.query(RepresentanteMedico.linea_id)
           .filter(RepresentanteMedico.gerente_id == gid,
                   RepresentanteMedico.linea_id.isnot(None))
           .first())
    return row[0] if row else None


# ── Costo & ROI de Visita — modelo financiero completo ────────────────────────
@router.get("/costo/estructura", response_model=dict)
def costo_estructura(linea_id: int | None = None, ciclo_id: int | None = None,
                     db: Session = Depends(get_db), current_user=LeerCostoFull):
    """Modelo financiero completo (costo fijo, muestras, pool de ventas, plan anual,
    resumen ROI e impacto de cobertura) por (ciclo, línea). Incluye el estado de aprobación.
    #15: SOLO FINANZAS/Director/ADMIN (dato con salarios/costos). El GD/RM usan /costo/mi-linea."""
    from app.services import visita_costo_service
    full = visita_costo_service.calcular_full(db, ciclo_id, linea_id)
    return {**full, **visita_costo_service.estado_estructura(db, ciclo_id, linea_id)}


@router.get("/costo/mi-linea", response_model=dict)
def costo_mi_linea(ciclo_id: int | None = None, db: Session = Depends(get_db),
                   current_user=LeerCostoVer):
    """Vista ACOTADA de Costo & ROI (sin salarios/costos): unidades a producir por contacto para
    el 100% del presupuesto + impacto de la cobertura en el presupuesto de la línea. La usan el
    REPRESENTANTE (su línea) y el GERENTE DE DISTRITO (la línea de su equipo — #15)."""
    from app.services import visita_costo_service
    rol = _rol(current_user)
    if rol == "REPRESENTANTE_MEDICO":
        linea_id = _linea_del_representante(db, current_user)
    elif rol == "GERENTE_DISTRITO":
        linea_id = _linea_del_gerente(db, current_user)
    else:
        raise HTTPException(403, "Esta vista acotada es para el representante o el gerente de distrito.")
    if not linea_id:
        raise HTTPException(403, "No hay una línea asignada para esta vista (representante o equipo).")
    return visita_costo_service.vista_representante(db, ciclo_id, linea_id)


@router.post("/costo/estructura", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_costo_estructura(datos: CostoEstructuraGuardar, background_tasks: BackgroundTasks,
                             db: Session = Depends(get_db), current_user=ConfigurarCosto):
    """Guarda la estructura (Finanzas configura → estado BORRADOR). Una config ya APROBADA solo
    la edita ADMIN (debe reabrirse primero). Si guarda Finanzas (no ADMIN), avisa al Director."""
    from app.services import visita_costo_service
    from app.core.authz.audit import registrar_evento_seguridad
    es_admin = _rol(current_user) == "ADMIN"
    try:
        r = visita_costo_service.guardar_estructura(db, datos, getattr(current_user, "id", None), es_admin=es_admin)
    except visita_costo_service.CostoAprobadoError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        _raise_captura_error(e)
    registrar_evento_seguridad(db, current_user, "CONFIG_COSTO_ROI",
                               recurso=_Rec.COSTOROI_CONFIGURAR, accion="configure",
                               objetivo=f"ciclo={datos.ciclo_id} linea={datos.linea_id}", resultado="OK")
    # Deuda #5: si guarda Finanzas (no un ADMIN que puede autoaprobar), avisar al Director que hay
    # un BORRADOR pendiente. Best-effort en background (crea su propia sesión).
    if not es_admin:
        cid, lid = datos.ciclo_id, datos.linea_id
        def _avisar():
            from app.db.database import SessionLocal
            from app.services import notification_service
            _db = SessionLocal()
            try:
                notification_service.notificar_costo_pendiente_aprobacion(
                    _db, cid, lid, getattr(current_user, "nombre_completo", "") or "")
            finally:
                _db.close()
        background_tasks.add_task(_avisar)
    return r


@router.post("/costo/estructura/aprobar", response_model=dict)
def aprobar_costo_estructura(linea_id: int | None = None, ciclo_id: int | None = None,
                             db: Session = Depends(get_db), current_user=AprobarCosto):
    """Director aprueba la estructura de Costo/ROI (BORRADOR → APROBADO). El que configura
    (Finanzas) NO puede aprobar: la matriz separa CONFIGURE (Finanzas) de APPROVE (Director)."""
    from app.services import visita_costo_service
    from app.core.authz.audit import registrar_evento_seguridad
    try:
        r = visita_costo_service.aprobar_estructura(db, ciclo_id, linea_id, getattr(current_user, "id", None))
    except ValueError as e:
        _raise_captura_error(e)
    registrar_evento_seguridad(db, current_user, "APROBACION_COSTO_ROI",
                               recurso=_Rec.COSTOROI_CONFIGURAR, accion="approve",
                               objetivo=f"ciclo={ciclo_id} linea={linea_id}", resultado="OK")
    return r


@router.post("/costo/estructura/reabrir", response_model=dict)
def reabrir_costo_estructura(linea_id: int | None = None, ciclo_id: int | None = None,
                             db: Session = Depends(get_db), current_user=RequireDesbloqueo):
    """Reabre una estructura APROBADA (→ BORRADOR). **Solo ADMIN** (excepción de dato cerrado),
    auditada."""
    from app.services import visita_costo_service
    from app.core.authz.audit import registrar_evento_seguridad
    try:
        r = visita_costo_service.reabrir_estructura(db, ciclo_id, linea_id, getattr(current_user, "id", None))
    except ValueError as e:
        _raise_captura_error(e)
    registrar_evento_seguridad(db, current_user, "EXCEPCION_SUPERADMIN",
                               recurso=_Rec.COSTOROI_CONFIGURAR, accion="admin",
                               objetivo=f"ciclo={ciclo_id} linea={linea_id}",
                               detalle="reapertura de Costo/ROI aprobado", resultado="OK")
    return r


@router.post("/costo/importar", response_model=dict, status_code=status.HTTP_201_CREATED)
async def importar_costo_excel(linea_id: int | None = None, ciclo_id: int | None = None,
                               archivo: UploadFile = File(...),
                               db: Session = Depends(get_db), current_user=ConfigurarCosto):
    """Importa los datos financieros por producto desde un Excel (.xlsx). Columnas:
    producto, costo_unitario_muestra, cantidad_muestras, pool_ventas, visitas_detalladas,
    presupuesto_anual, precio_prom."""
    from app.services import visita_costo_service
    nombre = (archivo.filename or "").lower()
    if not (nombre.endswith(".xlsx") or nombre.endswith(".xls")):
        raise HTTPException(status_code=400, detail="El archivo debe ser Excel (.xlsx/.xls).")
    contenido = await archivo.read()
    try:
        return visita_costo_service.importar_excel(db, contenido, ciclo_id, linea_id, getattr(current_user, "id", None))
    except ValueError as e:
        _raise_captura_error(e)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No se pudo leer el Excel: {e}")
