"""Router del Módulo de Visita Médica — Fase 1 (Panel Médico).

Prefijo: /visita.  Reutiliza Config.DIM_RM (VM), Config.DIM_Especialidad.
RBAC: el VM (REPRESENTANTE_MEDICO) gestiona su propio panel (auto-filtro por rm_id);
ADMIN/GERENTE ven/gestionan el de cualquier VM.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles, get_current_active_user
from app.models.usuario import Rol
from app.schemas.visita import (
    MedicoVisitaCrear, MedicoVisitaActualizar, MedicoVisitaResponse, VisitaRegistrar,
    VisitaNoVisita, PlaneacionGuardar, ParrillaGuardar, MuestrasRegistrar,
    ParametroCostoGuardar, _CAUSAS_NO_VISITA,
)
from app.services import visita_service

router = APIRouter(prefix="/visita", tags=["Visita Médica"])

RequireVisita = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_DISTRITO, Rol.GERENTE_PRODUCTIVIDAD, Rol.REPRESENTANTE_MEDICO))
# El cierre de ciclo hace rodar el contador de todos los paneles: operación gerencial.
RequireCierre = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))
# Aprobación de alta/baja de médicos: Gerente de Distrito (acotado a su distrito) + superusuarios.
RequireAprobador = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO))
RequireAnyAuth = Depends(get_current_active_user)


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


@router.get("/especialidades", response_model=list[dict])
def listar_especialidades(db: Session = Depends(get_db), current_user=RequireVisita):
    """Catálogo de especialidades (para el selector al registrar médicos)."""
    from app.models.dimensiones import Especialidad
    return [{"id": e.id, "nombre": e.nombre}
            for e in db.query(Especialidad).filter(Especialidad.activo == True)  # noqa: E712
            .order_by(Especialidad.nombre).all()]


@router.get("/vms", response_model=list[dict])
def listar_vms(db: Session = Depends(get_db), current_user=RequireVisita):
    """Visitadores médicos (DIM_RM) — para que ADMIN/GERENTE elijan el panel a ver."""
    from app.models.dimensiones import RepresentanteMedico
    return [{"id": r.id, "nombre": r.nombre}
            for r in db.query(RepresentanteMedico).filter(RepresentanteMedico.activo == True)  # noqa: E712
            .order_by(RepresentanteMedico.nombre).all()]


@router.get("/medicos", response_model=list[dict])
def listar_medicos(vm_id: int | None = None, incluir_inactivos: bool = False,
                   db: Session = Depends(get_db), current_user=RequireVisita):
    """Panel médico. El VM ve solo el suyo; ADMIN/GERENTE pueden filtrar por ?vm_id=.
    `incluir_inactivos=true` incluye los médicos desactivados (para reactivarlos)."""
    vm = _scope_vm(current_user, vm_id)
    return visita_service.listar_medicos(db, vm_id=vm, incluir_inactivos=incluir_inactivos)


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
    datos.activo = None
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


@router.get("/cobertura/resumen", response_model=dict)
def cobertura_resumen(ciclo_id: int | None = None, vm_id: int | None = None,
                      db: Session = Depends(get_db), current_user=RequireVisita):
    """Dashboard de Cobertura: gauges (cobertura/V+R/gap), desglose A/B/C, listas y ruptura.
    El VM ve su propia cobertura; ADMIN/GERENTE ven el equipo o filtran por ?vm_id=."""
    from app.services import visita_cobertura_service
    vm = _scope_vm(current_user, vm_id)
    return visita_cobertura_service.resumen_cobertura(db, ciclo_id, vm)


@router.get("/cobertura/ranking", response_model=dict)
def cobertura_ranking(metrica: str = "cobertura", ciclo_id: int | None = None,
                      db: Session = Depends(get_db), current_user=RequireVisita):
    """Detalle desplegable por visitador: ranking de quién cumple/no el indicador.
    metrica: 'cobertura' | 'completa' | 'sin_visitar'."""
    from app.services import visita_cobertura_service
    return visita_cobertura_service.ranking_visitadores(db, ciclo_id, metrica)


@router.get("/proyeccion", response_model=dict)
def proyeccion_visita(vm_id: int | None = None, dia_actual: int | None = None,
                      db: Session = Depends(get_db), current_user=RequireVisita):
    """Proyección de cobertura al cierre del ciclo (ritmo actual vs requerido).
    `dia_actual` permite simular. El VM ve la suya; ADMIN/GERENTE el equipo o ?vm_id=."""
    from app.services import visita_cobertura_service
    vm = _scope_vm(current_user, vm_id)
    return visita_cobertura_service.proyeccion(db, None, vm, dia_actual)


@router.get("/proyeccion/ranking", response_model=dict)
def proyeccion_ranking(dia_actual: int | None = None,
                       db: Session = Depends(get_db), current_user=RequireVisita):
    """Detalle desplegable de Proyección: por VM, la proyección final y si alcanza el objetivo."""
    from app.services import visita_cobertura_service
    return visita_cobertura_service.ranking_proyeccion(db, None, dia_actual)


# ── Registro de visita (Parte 4) ──────────────────────────────────────────────
def _vm_registro(current_user, vm_id: int | None) -> int:
    vm = _scope_vm(current_user, vm_id)
    if not vm:
        raise HTTPException(status_code=400, detail="Indica el visitador (vm_id).")
    return vm


@router.get("/causas", response_model=list[str])
def causas_no_visita(current_user=RequireVisita):
    """Catálogo de causas de no-visita (para el selector)."""
    return sorted(_CAUSAS_NO_VISITA)


@router.get("/mis-visitas-hoy", response_model=list[dict])
def mis_visitas_hoy(vm_id: int | None = None, db: Session = Depends(get_db), current_user=RequireVisita):
    """Visitas registradas hoy por el VM (feed del móvil)."""
    from app.services import visita_registro_service
    return visita_registro_service.visitas_del_dia(db, _vm_registro(current_user, vm_id))


@router.get("/agenda-hoy", response_model=list[dict])
def agenda_hoy(vm_id: int | None = None, db: Session = Depends(get_db), current_user=RequireVisita):
    """Médicos programados del VM para hoy (agenda), con su estado pendiente/registrada."""
    from app.services import visita_registro_service
    return visita_registro_service.agenda_hoy(db, _vm_registro(current_user, vm_id))


@router.post("/registrar", response_model=dict, status_code=status.HTTP_201_CREATED)
def registrar_visita(datos: VisitaRegistrar, vm_id: int | None = None,
                     db: Session = Depends(get_db), current_user=RequireVisita):
    """Registra una visita ejecutada. Usa la hora del servidor (ventana 60 min)."""
    from app.services import visita_registro_service
    try:
        v = visita_registro_service.registrar_visita(db, _vm_registro(current_user, vm_id), datos, getattr(current_user, "id", None))
        return {"id": v.id, "tipo": v.tipo_visita, "hora": v.fecha_hora.isoformat() if v.fecha_hora else None}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/no-visita", response_model=dict, status_code=status.HTTP_201_CREATED)
def registrar_no_visita(datos: VisitaNoVisita, vm_id: int | None = None,
                        db: Session = Depends(get_db), current_user=RequireVisita):
    """Registra una no-visita con su causa (no cuenta como visita, no penaliza cobertura)."""
    from app.services import visita_registro_service
    try:
        v = visita_registro_service.registrar_no_visita(db, _vm_registro(current_user, vm_id), datos, getattr(current_user, "id", None))
        return {"id": v.id, "causa": v.causa_no_visita}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── Planeación del ciclo (Parte 3) ────────────────────────────────────────────
@router.get("/planeacion", response_model=list[dict])
def obtener_planeacion(vm_id: int | None = None, ciclo_id: int | None = None,
                       db: Session = Depends(get_db), current_user=RequireVisita):
    """Planeación del ciclo del VM (ítems Vista/Revisita por médico). El VM ve la suya."""
    from app.services import visita_planeacion_service
    return visita_planeacion_service.listar_planeacion(db, _vm_registro(current_user, vm_id), ciclo_id)


@router.post("/planeacion", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_planeacion(datos: PlaneacionGuardar, vm_id: int | None = None, ciclo_id: int | None = None,
                       db: Session = Depends(get_db), current_user=RequireVisita):
    """Guarda (reemplaza) la planeación del ciclo. Valida reglas P01/P02/P03."""
    from app.services import visita_planeacion_service
    try:
        n = visita_planeacion_service.guardar_planeacion(
            db, _vm_registro(current_user, vm_id), ciclo_id, datos.items, getattr(current_user, "id", None))
        return {"guardadas": n}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/planeacion/resumen", response_model=dict)
def resumen_planeacion(vm_id: int | None = None, ciclo_id: int | None = None,
                       db: Session = Depends(get_db), current_user=RequireVisita):
    """Resumen de la planeación: cobertura planeada, carga por día y aviso de Cat A sin Revisita."""
    from app.services import visita_planeacion_service
    return visita_planeacion_service.resumen_planeacion(db, _vm_registro(current_user, vm_id), ciclo_id)


# ── Ruptura de secuencia / Cierre de ciclo (Parte 5) ──────────────────────────
@router.get("/ruptura", response_model=dict)
def estado_ruptura(vm_id: int | None = None, db: Session = Depends(get_db), current_user=RequireVisita):
    """Médicos en ruptura por severidad (1 / 2 / ≥3 ciclos sin visita). El VM ve el suyo."""
    from app.services import visita_cierre_service
    return visita_cierre_service.estado_ruptura(db, _scope_vm(current_user, vm_id))


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
def listar_lineas(db: Session = Depends(get_db), current_user=RequireVisita):
    """Líneas de producto (para el selector de la parrilla)."""
    from app.services import visita_parrilla_service
    return visita_parrilla_service.listar_lineas(db)


@router.get("/parrilla", response_model=list[dict])
def obtener_parrilla(linea_id: int | None = None, ciclo_id: int | None = None,
                     db: Session = Depends(get_db), current_user=RequireVisita):
    """Parrilla del ciclo para una línea. El VM usa su propia línea si no se indica."""
    from app.services import visita_parrilla_service
    if linea_id is None:
        vm = _scope_vm(current_user, None)
        linea_id = visita_parrilla_service.linea_de_vm(db, vm) if vm else None
    if linea_id is None:
        raise HTTPException(status_code=400, detail="Indica la línea (linea_id).")
    return visita_parrilla_service.listar_parrilla(db, ciclo_id, linea_id)


@router.post("/parrilla", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_parrilla(datos: ParrillaGuardar, db: Session = Depends(get_db), current_user=RequireCierre):
    """Guarda (reemplaza) la parrilla de una línea en el ciclo. Solo gestión."""
    from app.services import visita_parrilla_service
    try:
        n = visita_parrilla_service.guardar_parrilla(
            db, datos.ciclo_id, datos.linea_id, datos.items, getattr(current_user, "id", None))
        return {"guardados": n}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/muestras/resumen", response_model=dict)
def resumen_muestras(vm_id: int | None = None, ciclo_id: int | None = None,
                     db: Session = Depends(get_db), current_user=RequireVisita):
    """Resumen de muestras por producto: entregadas, médicos alcanzados, meta y cobertura."""
    from app.services import visita_parrilla_service
    return visita_parrilla_service.resumen_muestras(db, ciclo_id, _scope_vm(current_user, vm_id))


# ── Costo & ROI (Parte 8) ─────────────────────────────────────────────────────
@router.get("/costo/parametros", response_model=dict)
def obtener_parametros_costo(linea_id: int | None = None, ciclo_id: int | None = None,
                             db: Session = Depends(get_db), current_user=RequireVisita):
    """Parámetros de costo resueltos (cascada línea → default del ciclo)."""
    from app.services import visita_costo_service
    if linea_id is None:
        vm = _scope_vm(current_user, None)
        if vm:
            from app.services.visita_parrilla_service import linea_de_vm
            linea_id = linea_de_vm(db, vm)
    return visita_costo_service.obtener_parametros(db, ciclo_id, linea_id)


@router.post("/costo/parametros", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_parametros_costo(datos: ParametroCostoGuardar, db: Session = Depends(get_db), current_user=RequireCierre):
    """Configura los parámetros de costo del ciclo (por línea o default). Solo gestión."""
    from app.services import visita_costo_service
    try:
        return visita_costo_service.guardar_parametros(db, datos, getattr(current_user, "id", None))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/costo/roi", response_model=dict)
def costo_roi(vm_id: int | None = None, ciclo_id: int | None = None,
              db: Session = Depends(get_db), current_user=RequireVisita):
    """Costo & ROI del ciclo: costo por contacto/médico, ingresos, utilidad y ROI. VM ve el suyo."""
    from app.services import visita_costo_service
    return visita_costo_service.roi(db, ciclo_id, _scope_vm(current_user, vm_id))


@router.get("/costo/ranking", response_model=dict)
def costo_ranking(ciclo_id: int | None = None, db: Session = Depends(get_db), current_user=RequireCierre):
    """Detalle desplegable de ROI por VM (peor primero). Solo gestión (dato financiero)."""
    from app.services import visita_costo_service
    return visita_costo_service.roi_ranking(db, ciclo_id)
