"""Router del Módulo de Visita Médica — Fase 1 (Panel Médico).

Prefijo: /visita.  Reutiliza Config.DIM_RM (VM), Config.DIM_Especialidad.
RBAC: el VM (REPRESENTANTE_MEDICO) gestiona su propio panel (auto-filtro por rm_id);
ADMIN/GERENTE ven/gestionan el de cualquier VM.
"""
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles, get_current_active_user
from app.core.authz.paises import PaisPermitido, exigir_pais
from app.core.authz import scope as _scope
from app.models.usuario import Rol
from app.schemas.visita import (
    MedicoVisitaCrear, MedicoVisitaActualizar, MedicoVisitaResponse, VisitaRegistrar,
    VisitaNoVisita, PlaneacionGuardar, ParrillaGuardar, MuestrasRegistrar,
    ParametroCostoGuardar, CostoEstructuraGuardar, ClasificacionCrear, _CAUSAS_NO_VISITA,
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


def _exigir_pais_vm(db, current_user, vm_id: int | None) -> None:
    """Exige que el país del VM (`Config.DIM_RM`) esté entre los países permitidos del
    usuario. `vm_id=None` no valida nada (no hay entidad que resolver).

    Extraído de `_scope_vm` (Bloqueante 1 de revisión, ago-2026, ronda 3) para reusarlo en
    TODOS los sitios donde un `vm_id` explícito llega desde el cliente y no pasa por
    `_scope_vm`/`_vm_registro` — la ronda 2 solo cerró los que pasaban por ahí; quedaron
    `mi_gerente`, `obtener_medico`/`actualizar_medico`/baja/reactivar (roles distintos de
    REPRESENTANTE_MEDICO), `crear_medico` y `costo/roi` con el mismo `vm_id` SIN piso."""
    if vm_id is None:
        return
    from app.models.dimensiones import RepresentanteMedico
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
    if rm is not None:
        exigir_pais(db, current_user, rm.pais_codigo)


def _exigir_pais_medico(db, current_user, medico_id: int | None) -> None:
    """Exige el país del médico (vía el país de su `vm_id`) — mismo criterio que
    `_exigir_pais_vm`, para endpoints que reciben `medico_id` en vez de `vm_id`."""
    if medico_id is None:
        return
    from app.models.visita import MedicoVisita
    vm_id = db.query(MedicoVisita.vm_id).filter(MedicoVisita.id == medico_id).scalar()
    _exigir_pais_vm(db, current_user, vm_id)


def _exigir_pais_linea(db, current_user, linea_id: int | None) -> None:
    """Exige el país de la línea (`Config.DIM_Linea`, `pais_codigo` NOT NULL)."""
    if linea_id is None:
        return
    from app.models.dimensiones import Linea
    pc = db.query(Linea.pais_codigo).filter(Linea.id == linea_id).scalar()
    if pc is not None:
        exigir_pais(db, current_user, pc)


def _exigir_pais_ciclo(db, current_user, ciclo_id: int | None) -> None:
    """Exige el país del ciclo (`Config.DIM_Ciclo`, `pais_codigo` NOT NULL)."""
    if ciclo_id is None:
        return
    from app.models.dimensiones import Ciclo
    pc = db.query(Ciclo.pais_codigo).filter(Ciclo.id == ciclo_id).scalar()
    if pc is not None:
        exigir_pais(db, current_user, pc)


def _exigir_pais_gerente(db, current_user, gerente_id: int | None) -> None:
    """Exige el país del gerente (`Config.DIM_Gerente`, `pais_codigo` NOT NULL)."""
    if gerente_id is None:
        return
    from app.models.dimensiones import Gerente
    pc = db.query(Gerente.pais_codigo).filter(Gerente.id == gerente_id).scalar()
    if pc is not None:
        exigir_pais(db, current_user, pc)


def _scope_vm(db, current_user, vm_id: int | None) -> int | None:
    """Un REPRESENTANTE_MEDICO se fuerza a su propio rm_id; los demás pasan vm_id libre,
    PERO si vienen con un `vm_id` explícito se exige que el país de ese VM esté entre los
    países permitidos del usuario.

    (Bloqueante 1 de revisión, ago-2026): antes un `vm_id` explícito quedaba SIN piso de
    país, también en lectura — `GET /visita/medicos/existentes?vm_id=` devolvía la ficha
    médica completa (nombre, dirección, GPS, teléfono, exequátur) de todos los médicos del
    país de ESE vm_id, sin importar los países del usuario que hace la llamada. Mismo
    criterio que `_verificar_acceso_rm`/`get_productividad_rm`: cuando el identificador
    señala una sola entidad, el guard va en el resolvedor. NO cubre el equipo (un GD puede
    pasar el vm_id de otro distrito) — ese agujero es preexistente y va en otro trabajo."""
    if _rol(current_user) == "REPRESENTANTE_MEDICO":
        rm = getattr(current_user, "rm_id", None)
        if not rm:
            raise HTTPException(status_code=403, detail="Tu usuario no está vinculado a un representante (rm_id).")
        return rm
    _exigir_pais_vm(db, current_user, vm_id)
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
    se resuelve por su propio rm_id; ADMIN/gerentes pueden pasar ?vm_id=.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): antes leía `rid = vm_id` directo, sin
    pasar por `_scope_vm` ni `exigir_pais` — devolvía gerente, línea y nombre del VM de
    CUALQUIER país. Ahora usa `_scope_vm` (fuerza al REP a su propio rm_id, valida país
    para los demás roles)."""
    from app.models.dimensiones import RepresentanteMedico, Gerente, Linea
    rid = _scope_vm(db, current_user, vm_id)
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
def listar_vms(pais_codigo: str | None = Depends(PaisPermitido), db: Session = Depends(get_db),
               current_user=RequireAnyAuth):
    """Visitadores médicos (DIM_RM) — para que ADMIN/GERENTE elijan el panel a ver.
    `pais_codigo` (aislamiento multipaís): sin filtro, listaba VMs de TODOS los países.
    `permitidos` (Menor de revisión, ago-2026): sin `pais_codigo` seguía listando VMs de
    TODOS los países — el piso de país se aplica siempre, no solo cuando llega el filtro."""
    from app.models.dimensiones import RepresentanteMedico
    q = db.query(RepresentanteMedico).filter(RepresentanteMedico.activo == True)  # noqa: E712
    if pais_codigo:
        q = q.filter(RepresentanteMedico.pais_codigo == pais_codigo)
    else:
        permitidos = _scope.paises_visibles(db, current_user)
        if permitidos is not None:
            q = q.filter(RepresentanteMedico.pais_codigo.in_(permitidos))
    return [{"id": r.id, "nombre": r.nombre} for r in q.order_by(RepresentanteMedico.nombre).all()]


@router.get("/medicos", response_model=list[dict])
def listar_medicos(vm_id: int | None = None, incluir_inactivos: bool = False,
                   lite: bool = False, pais_codigo: str | None = Depends(PaisPermitido),
                   db: Session = Depends(get_db), current_user=ReadMedicoPanel):
    """Panel médico. El VM ve solo el suyo; ADMIN/GERENTE pueden filtrar por ?vm_id=.
    `incluir_inactivos=true` incluye los médicos desactivados (para reactivarlos).
    `lite=true` devuelve solo los campos de LISTA (rendimiento; la ficha completa se
    obtiene con GET /visita/medicos/{id} al editar).
    `pais_codigo` (aislamiento multipaís): sin `vm_id`, acota el panel agregado a un país.
    `permitidos` (piso de país, siempre — incluso con `vm_id` explícito, ver
    `visita_service.listar_medicos`)."""
    vm = _scope_vm(db, current_user, vm_id)
    permitidos = _scope.paises_visibles(db, current_user)
    return visita_service.listar_medicos(db, vm_id=vm, incluir_inactivos=incluir_inactivos,
                                         lite=lite, pais_codigo=pais_codigo, permitidos=permitidos)


@router.get("/medicos/existentes", response_model=list[dict])
def listar_medicos_existentes(vm_id: int | None = None, db: Session = Depends(get_db),
                              current_user=ReadMedicoPanel):
    """Médicos ya registrados en otros paneles del mismo país, para COPIAR al panel del
    VM (evita reescribir la ficha). El VM se fuerza a su propio rm_id; ADMIN/GERENTE
    deben indicar el visitador destino con ?vm_id=."""
    vm = _scope_vm(db, current_user, vm_id)
    if not vm:
        raise HTTPException(status_code=400, detail="Indica el visitador destino (vm_id).")
    return visita_service.listar_medicos_existentes(db, vm)


@router.get("/medicos/{medico_id}", response_model=dict)
def obtener_medico(medico_id: int, db: Session = Depends(get_db), current_user=ReadMedicoPanel):
    """Ficha COMPLETA de un médico (para editar). El VM solo ve los de su panel.
    Declarado DESPUÉS de /medicos/existentes para no interceptar esa ruta literal.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): el guard de panel solo se aplicaba a
    REPRESENTANTE_MEDICO — ADMIN/GERENTE podían pedir la ficha COMPLETA (nombre, dirección,
    GPS, teléfono, exequátur) de un `medico_id` de cualquier país sin ningún piso. Se exige
    el país del médico (vía el VM de su panel) para TODOS los roles."""
    m = visita_service.obtener_ficha_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    if _rol(current_user) == "REPRESENTANTE_MEDICO" and m.get("vm_id") != getattr(current_user, "rm_id", None):
        raise HTTPException(status_code=403, detail="Solo puedes ver los médicos de tu panel.")
    _exigir_pais_vm(db, current_user, m.get("vm_id"))
    return m


@router.put("/medicos/{medico_id}", response_model=MedicoVisitaResponse)
def actualizar_medico(medico_id: int, datos: MedicoVisitaActualizar,
                      db: Session = Depends(get_db), current_user=RequireVisita):
    """Edita un médico o lo activa/desactiva (campo `activo`). El VM solo puede
    modificar médicos de su propio panel.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): mismo hallazgo que `obtener_medico`
    pero en ESCRITURA — ADMIN/GERENTE podían editar cualquier médico por id sin piso de
    país."""
    m = visita_service.obtener_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    _exigir_pais_vm(db, current_user, m.vm_id)
    if _rol(current_user) == "REPRESENTANTE_MEDICO":
        rm = _scope_vm(db, current_user, None)
        if m.vm_id != rm:
            raise HTTPException(status_code=403, detail="Este médico no pertenece a tu panel.")
        # El REP no deja el cambio activo por su cuenta: queda pendiente de validación del
        # Gerente de Distrito y el médico SIGUE ACTIVO CON LOS DATOS ANTERIORES, para no
        # interrumpir la operación del ciclo. (El GD/ADMIN, que es quien valida, edita directo.)
        if m.estado_aprobacion == "APROBADO":
            if datos.clasificacion is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Al modificar un médico debes completar su clasificación "
                           "(los 5 criterios); el cambio quedará pendiente de aprobación.")
            try:
                visita_service.solicitar_cambio_medico(
                    db, m, datos, datos.clasificacion, getattr(current_user, "id", None))
            except visita_service.SolicitudCambioError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
            return m          # sin cambios: el médico sigue como estaba
    # El alta/baja (campo `activo`) NO se cambia por edición directa: pasa por aprobación.
    # (actualizar_medico ignora `activo` explícitamente; no lo asignamos aquí para no
    #  marcarlo como "set" en Pydantic, lo que haría un UPDATE activo=NULL — bug histórico.)
    try:
        return visita_service.actualizar_medico(db, m, datos, getattr(current_user, "id", None))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _medico_de_mi_panel(db, current_user, m):
    """(Bloqueante 1 de revisión, ago-2026, ronda 3): antes solo restringía por panel al
    REPRESENTANTE_MEDICO — ADMIN/GERENTE podían solicitar baja/reactivar un médico de
    cualquier país sin piso. `_exigir_pais_vm` corre para TODOS los roles."""
    if _rol(current_user) == "REPRESENTANTE_MEDICO":
        rm = _scope_vm(db, current_user, None)
        if m.vm_id != rm:
            raise HTTPException(status_code=403, detail="Este médico no pertenece a tu panel.")
    _exigir_pais_vm(db, current_user, m.vm_id)


@router.post("/medicos/{medico_id}/baja", response_model=dict)
def solicitar_baja(medico_id: int, db: Session = Depends(get_db), current_user=RequireVisita):
    """Solicita la BAJA de un médico. Requiere aprobación del Gerente de Distrito;
    efectiva el próximo ciclo. El VM solo puede solicitar sobre su panel."""
    from app.services import visita_aprobacion_service as aps
    m = visita_service.obtener_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    _medico_de_mi_panel(db, current_user, m)
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
    _medico_de_mi_panel(db, current_user, m)
    m.activo = True
    m.estado_aprobacion = "PENDIENTE_ALTA"
    m.ciclo_alta_id = ciclo_actual_id(db, m.vm_id)
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


@router.get("/medicos/{medico_id}/clasificacion", response_model=dict)
def obtener_clasificacion(medico_id: int, db: Session = Depends(get_db), current_user=RequireVisita):
    """Plantilla de clasificación capturada al dar de alta el médico.

    La usa el Gerente de Distrito para revisarla (y corregirla) antes de aprobar. NO
    devuelve categoría: se revela al aprobar.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): sin ningún piso de país (ni siquiera el
    de panel del REPRESENTANTE_MEDICO) — cualquier rol de `RequireVisita` podía leer la
    plantilla de clasificación de un médico de otro país."""
    from app.models.visita import MedicoClasificacion
    m = visita_service.obtener_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    _exigir_pais_vm(db, current_user, m.vm_id)
    c = db.query(MedicoClasificacion).filter(
        MedicoClasificacion.medico_visita_id == medico_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Este médico no tiene plantilla de clasificación.")
    return {
        "medico_visita_id": c.medico_visita_id,
        "pacientes_semana": float(c.pacientes_semana) if c.pacientes_semana is not None else None,
        "costo_consulta": float(c.costo_consulta) if c.costo_consulta is not None else None,
        "potencial_prescripcion": c.potencial_prescripcion,
        "ubicacion_territorial": c.ubicacion_territorial,
        "kol_nivel": c.kol_nivel,
    }


@router.put("/medicos/{medico_id}/clasificacion", response_model=dict)
def actualizar_clasificacion(medico_id: int, datos: ClasificacionCrear,
                             db: Session = Depends(get_db), current_user=RequireAprobador):
    """El Gerente de Distrito ajusta la plantilla antes de aprobar.

    Solo mientras el alta está PENDIENTE: una vez aprobada, la categoría ya fue sellada
    y cambiarla a mano rompería la trazabilidad del cálculo."""
    from datetime import datetime as _dt, timezone as _tz
    from app.models.visita import MedicoClasificacion
    from app.services import visita_aprobacion_service as aps
    m = visita_service.obtener_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    if not aps.puede_aprobar(db, current_user, m):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="No autorizado para este médico (no es de tu distrito).")
    if m.estado_aprobacion != "PENDIENTE_ALTA":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="La clasificación solo se edita mientras el alta está pendiente.")
    c = db.query(MedicoClasificacion).filter(
        MedicoClasificacion.medico_visita_id == medico_id).first()
    if not c:
        c = MedicoClasificacion(medico_visita_id=medico_id)
        db.add(c)
    c.pacientes_semana = datos.pacientes_semana
    c.costo_consulta = datos.costo_consulta
    c.potencial_prescripcion = datos.potencial_prescripcion
    c.ubicacion_territorial = datos.ubicacion_territorial
    c.kol_nivel = datos.kol_nivel
    c.actualizado_por = getattr(current_user, "id", None)
    c.fecha_actualizacion = _dt.now(_tz.utc)
    db.commit()
    return {"medico_visita_id": medico_id, "actualizado": True}


@router.post("/medicos/cambios/{solicitud_id}/resolver", response_model=dict)
def resolver_cambio_medico(solicitud_id: int, aprobar: bool = True, motivo: str | None = None,
                           db: Session = Depends(get_db), current_user=RequireAprobador):
    """El Gerente de Distrito valida (o rechaza) un cambio propuesto por el representante.

    Al aprobar se vuelcan los datos sobre el médico y se recalcula su categoría; hasta
    entonces el médico siguió activo con la información anterior."""
    from app.services import visita_aprobacion_service as aps
    try:
        m = aps.resolver_cambio(db, solicitud_id, current_user, aprobar, motivo)
    except aps.AprobacionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return {"id": m.id, "aprobado": aprobar, "categoria": m.categoria}


@router.post("/medicos/{medico_id}/aprobar", response_model=dict)
def aprobar_medico(medico_id: int, db: Session = Depends(get_db), current_user=RequireAprobador):
    """Aprueba la solicitud pendiente (alta o baja).

    Al aprobar un ALTA se revela la categoría: el motor puntúa la plantilla y la sella en
    el Panel. El Maestro de Médicos queda SIN clasificación (un médico puede tener
    categorías distintas según la línea que lo visita)."""
    from app.services import visita_aprobacion_service as aps
    m = visita_service.obtener_medico(db, medico_id)
    if not m:
        raise HTTPException(status_code=404, detail="Médico no encontrado.")
    try:
        aps.aprobar(db, m, current_user)
    except aps.AprobacionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return {"id": m.id, "estado_aprobacion": m.estado_aprobacion, "categoria": m.categoria}


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
        datos.vm_id = _scope_vm(db, current_user, None)
    else:
        # (Bloqueante 1 de revisión, ago-2026, ronda 3): ADMIN/GERENTE mandaban `vm_id`
        # libre en el body — podían registrar un médico en el panel de un VM de otro país.
        _exigir_pais_vm(db, current_user, datos.vm_id)
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
def listar_gerentes(pais_codigo: str | None = Depends(PaisPermitido),
                    db: Session = Depends(get_db), current_user=RequireAnyAuth):
    """Gerentes de Distrito (para el filtro de cobertura). `pais_codigo` (aislamiento
    multipaís, opcional/retrocompatible): acota a los gerentes de ese país.
    `permitidos` (Menor de revisión, ago-2026): sin `pais_codigo` seguía listando
    gerentes de TODOS los países — el piso de país se aplica siempre."""
    from app.models.dimensiones import Gerente
    q = db.query(Gerente).filter(Gerente.tipo == "DISTRITO", Gerente.activo == True)  # noqa: E712
    if pais_codigo:
        q = q.filter(Gerente.pais_codigo == pais_codigo)
    else:
        permitidos = _scope.paises_visibles(db, current_user)
        if permitidos is not None:
            q = q.filter(Gerente.pais_codigo.in_(permitidos))
    return [{"id": g.id, "nombre": g.nombre} for g in q.order_by(Gerente.nombre).all()]


@router.get("/cobertura/resumen", response_model=dict)
def cobertura_resumen(ciclo_id: int | None = None, vm_id: int | None = None,
                      gerente_id: int | None = None, linea_id: int | None = None,
                      solo_ruptura: bool = False, pais_codigo: str | None = Depends(PaisPermitido),
                      db: Session = Depends(get_db), current_user=ReadCobertura):
    """Dashboard de Cobertura: gauges (cobertura/V+R/gap), desglose A/B/C, listas y ruptura.
    El VM ve su propia cobertura; ADMIN/GERENTE ven el equipo o filtran por visitador
    (?vm_id=), Gerente de Distrito (?gerente_id=), Línea (?linea_id=), país (?pais_codigo=,
    aislamiento multipaís) y ruptura (?solo_ruptura=).

    `permitidos` (hallazgo Critical de revisión, ago-2026): se pasa SIEMPRE al servicio como
    piso de país, exista o no `pais_codigo` en la query — omitirlo ya no basta para ver otro
    país (antes bastaba con no mandarlo)."""
    from app.services import visita_cobertura_service
    vm = _scope_vm(db, current_user, vm_id)
    permitidos = _scope.paises_visibles(db, current_user)
    return visita_cobertura_service.resumen_cobertura(
        db, ciclo_id, vm, gerente_id, linea_id, solo_ruptura, pais_codigo, permitidos)


@router.get("/cobertura/ranking", response_model=dict)
def cobertura_ranking(metrica: str = "cobertura", ciclo_id: int | None = None,
                      pais_codigo: str | None = Depends(PaisPermitido),
                      db: Session = Depends(get_db), current_user=ReadCobertura):
    """Detalle desplegable por visitador: ranking de quién cumple/no el indicador.
    metrica: 'cobertura' | 'completa' | 'sin_visitar'.
    `pais_codigo` (aislamiento multipaís): acota el ranking a los VMs de ese país.
    `permitidos` (piso de país, siempre — ver `cobertura_resumen`)."""
    from app.services import visita_cobertura_service
    permitidos = _scope.paises_visibles(db, current_user)
    return visita_cobertura_service.ranking_visitadores(db, ciclo_id, metrica, pais_codigo, permitidos)


# ── Registro de visita (Parte 4) ──────────────────────────────────────────────
def _vm_registro(db, current_user, vm_id: int | None) -> int:
    vm = _scope_vm(db, current_user, vm_id)
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
    return visita_registro_service.visitas_del_dia(db, _vm_registro(db, current_user, vm_id))


@router.get("/historial", response_model=list[dict])
def historial_visitas(vm_id: int | None = None, dias: int = 30,
                      db: Session = Depends(get_db), current_user=RequireVisita):
    """Visitas anteriores del VM (SOLO LECTURA): el RM consulta sus registros y
    ve su comentario, pero nunca puede modificarlos — no existen endpoints de
    edición/borrado de visitas."""
    from app.services import visita_registro_service
    return visita_registro_service.historial_visitas(db, _vm_registro(db, current_user, vm_id), dias)


@router.get("/agenda-hoy", response_model=list[dict])
def agenda_hoy(vm_id: int | None = None, db: Session = Depends(get_db), current_user=RequireVisita):
    """Médicos programados del VM para hoy (agenda), con su estado pendiente/registrada."""
    from app.services import visita_registro_service
    return visita_registro_service.agenda_hoy(db, _vm_registro(db, current_user, vm_id))


@router.post("/registrar", response_model=dict, status_code=status.HTTP_201_CREATED)
def registrar_visita(datos: VisitaRegistrar, vm_id: int | None = None,
                     db: Session = Depends(get_db), current_user=RegistrarVisitaGuard):
    """La captura de visitas está cerrada: las visitas provienen del SFA de
    Mallén (esquema `ext`) y se integran desde ahí.

    Se conserva el endpoint devolviendo 409 en vez de borrarlo para que un
    cliente antiguo reciba un motivo legible en lugar de un 404 sin explicación.
    """
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        "El registro de visitas está cerrado: las visitas provienen del SFA de "
        "Mallén y se integran automáticamente. Lo ya registrado sigue disponible "
        "para consulta.")


@router.post("/no-visita", response_model=dict, status_code=status.HTTP_201_CREATED)
def registrar_no_visita(datos: VisitaNoVisita, vm_id: int | None = None,
                        db: Session = Depends(get_db), current_user=RegistrarVisitaGuard):
    """La captura de visitas está cerrada: las visitas provienen del SFA de
    Mallén (esquema `ext`) y se integran desde ahí.

    Se conserva el endpoint devolviendo 409 en vez de borrarlo para que un
    cliente antiguo reciba un motivo legible en lugar de un 404 sin explicación.
    """
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        "El registro de visitas está cerrado: las visitas provienen del SFA de "
        "Mallén y se integran automáticamente. Lo ya registrado sigue disponible "
        "para consulta.")


@router.post("/{visita_id}/foto", response_model=dict, status_code=status.HTTP_201_CREATED)
async def subir_foto_visita(
    visita_id: int, archivo: UploadFile = File(...),
    db: Session = Depends(get_db), current_user=RegistrarVisitaGuard,
):
    """La captura de visitas está cerrada: las visitas provienen del SFA de
    Mallén (esquema `ext`) y se integran desde ahí.

    Se conserva el endpoint devolviendo 409 en vez de borrarlo para que un
    cliente antiguo reciba un motivo legible en lugar de un 404 sin explicación.
    """
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        "El registro de visitas está cerrado: las visitas provienen del SFA de "
        "Mallén y se integran automáticamente. Lo ya registrado sigue disponible "
        "para consulta.")


@router.get("/{visita_id}/foto")
def obtener_foto_visita_endpoint(
    visita_id: int, db: Session = Depends(get_db), current_user=RequireVisita,
):
    """Devuelve la imagen de la visita (BLOB). 404 si no tiene foto.

    (Bloqueante 1 de revisión, ago-2026, ronda 3, hallazgo adicional): `visita_id` no es
    uno de los 5 identificadores nombrados en el hallazgo, pero es la misma clase de bug —
    determina un país (vía el `vm_id` de la visita) sin ningún piso. Resuelto el país
    ANTES de leer el contenido: no tiene sentido comprobar después de haber devuelto ya
    los bytes de la foto."""
    from app.models.visita import VisitaRegistro
    vm_id = db.query(VisitaRegistro.vm_id).filter(VisitaRegistro.id == visita_id).scalar()
    _exigir_pais_vm(db, current_user, vm_id)
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
    return visita_planeacion_service.listar_planeacion(db, _vm_registro(db, current_user, vm_id), ciclo_id)


@router.post("/planeacion", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_planeacion(datos: PlaneacionGuardar, vm_id: int | None = None, ciclo_id: int | None = None,
                       db: Session = Depends(get_db), current_user=RegistrarPlaneacion):
    """Guarda (reemplaza) la planeación del ciclo. Valida reglas P01/P02/P03.
    Rechaza con 409 si la planeación ya fue publicada (congelada)."""
    from app.services import visita_planeacion_service
    try:
        n = visita_planeacion_service.guardar_planeacion(
            db, _vm_registro(db, current_user, vm_id), ciclo_id, datos.items, getattr(current_user, "id", None))
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
    return visita_planeacion_service.estado_planeacion(db, _vm_registro(db, current_user, vm_id), ciclo_id)


@router.post("/planeacion/publicar", response_model=dict)
def publicar_planeacion(vm_id: int | None = None, ciclo_id: int | None = None,
                        db: Session = Depends(get_db), current_user=RegistrarPlaneacion):
    """Publica (CONGELA) la planeación del ciclo. Irreversible salvo desbloqueo del ADMIN:
    es el denominador con el que se calcula la cobertura."""
    from app.services import visita_planeacion_service
    try:
        return visita_planeacion_service.publicar_planeacion(
            db, _vm_registro(db, current_user, vm_id), ciclo_id, getattr(current_user, "id", None))
    except visita_planeacion_service.PlaneacionPublicadaError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except visita_planeacion_service.TopSinPlanearError as e:
        # 409, no 400: la planeación no está en condiciones de publicarse (conflicto de
        # estado), no un error de validación del payload.
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        _raise_captura_error(e)


@router.post("/planeacion/desbloquear", response_model=dict)
def desbloquear_planeacion(vm_id: int, motivo: str = Body(..., embed=True),
                           ciclo_id: int | None = None,
                           db: Session = Depends(get_db), current_user=RequireDesbloqueo):
    """Devuelve la planeación a borrador. **Solo ADMIN** y con motivo: queda registrado quién
    desbloqueó, cuándo y por qué (`PlaneacionEvento`, append-only). `vm_id` es obligatorio —
    un admin desbloquea la de un representante concreto, nunca la suya "por defecto".

    (Bloqueante 1 de revisión, ago-2026, ronda 3 — señalado explícitamente): `RequireDesbloqueo`
    exige `Rol.ADMIN` pero eso NO exime del país — la frontera es ortogonal al rol. Un ADMIN
    acotado a un país no debe poder desbloquear la planeación de un VM de otro."""
    _exigir_pais_vm(db, current_user, vm_id)
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
    return visita_planeacion_service.resumen_planeacion(db, _vm_registro(db, current_user, vm_id), ciclo_id)


# ── Ruptura de secuencia / Cierre de ciclo (Parte 5) ──────────────────────────
@router.get("/ruptura", response_model=dict)
def estado_ruptura(vm_id: int | None = None, gerente_id: int | None = None,
                   linea_id: int | None = None, pais_codigo: str | None = Depends(PaisPermitido),
                   db: Session = Depends(get_db), current_user=ReadCobertura):
    """Médicos en ruptura por severidad (1 / 2 / ≥3 ciclos sin visita). El VM ve el suyo;
    gestión puede filtrar por Gerente de Distrito (?gerente_id=), Línea (?linea_id=) y
    País (?pais_codigo=, aislamiento multipaís del agregado "todos los visitadores").
    `permitidos` (piso de país, siempre — ver `cobertura_resumen`)."""
    from app.services import visita_cierre_service
    permitidos = _scope.paises_visibles(db, current_user)
    return visita_cierre_service.estado_ruptura(
        db, _scope_vm(db, current_user, vm_id), gerente_id, linea_id, pais_codigo, permitidos)


@router.get("/cierre/previsualizar", response_model=dict)
def previsualizar_cierre(ciclo_id: int | None = None, db: Session = Depends(get_db), current_user=RequireCierre):
    """Simula el cierre del ciclo (sin escribir): cuántos se resetean/incrementan y si ya está cerrado.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `RequireCierre` (ADMIN+GERENTE_PRODUCTIVIDAD)
    no exime del país — un `ciclo_id` de otro país no debe poder simularse/cerrarse."""
    _exigir_pais_ciclo(db, current_user, ciclo_id)
    from app.services import visita_cierre_service
    try:
        return visita_cierre_service.previsualizar_cierre(db, ciclo_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/cierre", response_model=dict, status_code=status.HTTP_201_CREATED)
def cerrar_ciclo(ciclo_id: int | None = None, db: Session = Depends(get_db), current_user=RequireCierre):
    """Cierra el ciclo de visita: hace rodar `ciclos_sin_visita`. Idempotente (409 si ya se cerró).

    (Bloqueante 1 de revisión, ago-2026, ronda 3): mismo piso que `previsualizar_cierre` —
    ser ADMIN/GERENTE_PRODUCTIVIDAD no exime del país."""
    _exigir_pais_ciclo(db, current_user, ciclo_id)
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
    """Historial de cierres de ciclo de visita, del más reciente al más antiguo.

    No recibe ningún identificador del cliente (fuera del alcance estricto de este
    hallazgo), pero por construcción mezclaba cierres de TODOS los países — hallazgo
    adicional (ronda 3): se le agrega el mismo piso de país (`permitidos`), consistente
    con el resto del módulo, aunque el dato (conteos agregados, sin PII) es de menor
    severidad que el resto de los hallazgos de esta ronda."""
    from app.services import visita_cierre_service
    permitidos = _scope.paises_visibles(db, current_user)
    return visita_cierre_service.historial_cierres(db, permitidos=permitidos)


# ── Parrilla promocional / Muestras (Parte 6) ─────────────────────────────────
@router.get("/lineas", response_model=list[dict])
def listar_lineas(pais_codigo: str | None = Depends(PaisPermitido), db: Session = Depends(get_db),
                  current_user=RequireAnyAuth):
    """Líneas de producto (para el selector de la parrilla).
    `pais_codigo` (aislamiento multipaís): sin filtro, listaba líneas de TODOS los países.
    `permitidos` (Menor de revisión, ago-2026): sin `pais_codigo` seguía listando líneas
    de TODOS los países — el piso de país se aplica siempre."""
    from app.services import visita_parrilla_service
    permitidos = _scope.paises_visibles(db, current_user) if not pais_codigo else None
    return visita_parrilla_service.listar_lineas(db, pais_codigo, permitidos)


@router.get("/parrilla/ultima-linea", response_model=dict)
def parrilla_ultima_linea(ciclo_id: int | None = None,
                          db: Session = Depends(get_db), current_user=ReadParrilla):
    """Línea de la parrilla más reciente — para que las pantallas de consulta arranquen
    en el último registro, no en la primera línea del catálogo.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `ciclo_id` explícito sin piso de país."""
    _exigir_pais_ciclo(db, current_user, ciclo_id)
    from app.services import visita_parrilla_service
    return {"linea_id": visita_parrilla_service.ultima_linea_con_parrilla(db, ciclo_id)}


@router.get("/parrilla", response_model=list[dict])
def obtener_parrilla(linea_id: int | None = None, ciclo_id: int | None = None,
                     vm_id: int | None = None,
                     db: Session = Depends(get_db), current_user=ReadParrilla):
    """Parrilla del ciclo para una línea. Sin `linea_id` se usa la línea del VM
    (el RM usa la suya propia; gestión puede indicar `vm_id`). El VM SOLO ve
    parrillas publicadas; el Gerente de Producto ve también los borradores.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): con `linea_id` explícito el piso de país
    del `vm_id` (vía `_scope_vm`) se saltaba entero — la rama `if linea_id is None` es la
    ÚNICA que pasa por `_scope_vm`. `_exigir_pais_linea`/`_exigir_pais_ciclo` cierran el
    resto de las combinaciones."""
    from app.services import visita_parrilla_service
    if linea_id is None:
        vm = _scope_vm(db, current_user, vm_id)
        linea_id = visita_parrilla_service.linea_de_vm(db, vm) if vm else None
    else:
        _exigir_pais_linea(db, current_user, linea_id)
    _exigir_pais_ciclo(db, current_user, ciclo_id)
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
                         db: Session = Depends(get_db), current_user=ReadParrilla):
    """Penetración del ciclo por producto (médicos alcanzados, muestras, promedio/visita).

    (Bloqueante 1 de revisión, ago-2026, ronda 3): mismo hallazgo que `obtener_parrilla` —
    con `linea_id` explícito no había piso de país."""
    from app.services import visita_parrilla_service
    if linea_id is None:
        vm = _scope_vm(db, current_user, None)
        linea_id = visita_parrilla_service.linea_de_vm(db, vm) if vm else None
    else:
        _exigir_pais_linea(db, current_user, linea_id)
    _exigir_pais_ciclo(db, current_user, ciclo_id)
    if linea_id is None:
        raise HTTPException(status_code=400, detail="Indica la línea (linea_id).")
    return visita_parrilla_service.penetracion_ciclo(db, ciclo_id, linea_id)


@router.post("/parrilla/publicar", response_model=dict)
def publicar_parrilla(linea_id: int, ciclo_id: int | None = None,
                      db: Session = Depends(get_db), current_user=ConfigurarParrilla):
    """Publica la parrilla al equipo (Gerente de Producto). El VM la recibe en solo lectura.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `linea_id`/`ciclo_id` sin piso de país —
    ni siquiera exige `Rol.ADMIN`, la puede llamar `GERENTE_MARCA`."""
    _exigir_pais_linea(db, current_user, linea_id)
    _exigir_pais_ciclo(db, current_user, ciclo_id)
    from app.services import visita_parrilla_service
    try:
        n = visita_parrilla_service.publicar_parrilla(db, ciclo_id, linea_id, getattr(current_user, "id", None))
        return {"publicados": n}
    except ValueError as e:
        _raise_captura_error(e)


@router.post("/parrilla", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_parrilla(datos: ParrillaGuardar, db: Session = Depends(get_db), current_user=ConfigurarParrilla):
    """Guarda (reemplaza) la parrilla de una línea en el ciclo. Solo Gerente de Producto.
    Queda en borrador hasta publicar.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `datos.linea_id`/`datos.ciclo_id`
    (payload) sin piso de país."""
    _exigir_pais_linea(db, current_user, datos.linea_id)
    _exigir_pais_ciclo(db, current_user, datos.ciclo_id)
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
    """Registra muestras entregadas a un médico del panel. El VM va contra su panel.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `datos.medico_id` sin piso de país —
    el `vm_id` ya se valida vía `_vm_registro`, pero el médico del payload podía ser de
    otro país/panel sin que nada lo detectara."""
    _exigir_pais_medico(db, current_user, datos.medico_id)
    from app.services import visita_parrilla_service
    try:
        n = visita_parrilla_service.registrar_muestras(
            db, _vm_registro(db, current_user, vm_id), datos.ciclo_id, datos.medico_id,
            datos.entregas, getattr(current_user, "id", None))
        return {"registradas": n}
    except ValueError as e:
        _raise_captura_error(e)


@router.get("/muestras/resumen", response_model=dict)
def resumen_muestras(vm_id: int | None = None, ciclo_id: int | None = None,
                     db: Session = Depends(get_db), current_user=ReadParrilla):
    """Resumen de muestras por producto: entregadas, médicos alcanzados, meta y cobertura."""
    from app.services import visita_parrilla_service
    return visita_parrilla_service.resumen_muestras(db, ciclo_id, _scope_vm(db, current_user, vm_id))


# ── Costo & ROI (Parte 8) ─────────────────────────────────────────────────────
# Los parámetros de costo (salario, viáticos, materiales) y el ROI por VM son datos
# financieros: solo gestión. `RequireFinanciero` está definido más arriba, junto a
# /costo/estructura.
@router.get("/costo/parametros", response_model=dict)
def obtener_parametros_costo(linea_id: int | None = None, ciclo_id: int | None = None,
                             db: Session = Depends(get_db), current_user=RequireFinanciero):
    """Parámetros de costo resueltos (cascada línea → default del ciclo). Solo gestión.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): toda la sección Costo & ROI recibía
    `linea_id`/`ciclo_id`/`vm_id` sin ningún piso de país — dato financiero (costos,
    ingresos, utilidad, ROI, salarios)."""
    _exigir_pais_linea(db, current_user, linea_id)
    _exigir_pais_ciclo(db, current_user, ciclo_id)
    from app.services import visita_costo_service
    return visita_costo_service.obtener_parametros(db, ciclo_id, linea_id)


@router.post("/costo/parametros", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_parametros_costo(datos: ParametroCostoGuardar, db: Session = Depends(get_db), current_user=ConfigurarCosto):
    """Configura los parámetros de costo del ciclo (por línea o default). Solo gestión.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): igual que `obtener_parametros_costo`,
    en escritura."""
    _exigir_pais_linea(db, current_user, datos.linea_id)
    _exigir_pais_ciclo(db, current_user, datos.ciclo_id)
    from app.services import visita_costo_service
    try:
        return visita_costo_service.guardar_parametros(db, datos, getattr(current_user, "id", None))
    except ValueError as e:
        _raise_captura_error(e)


@router.get("/costo/roi", response_model=dict)
def costo_roi(vm_id: int | None = None, ciclo_id: int | None = None,
              db: Session = Depends(get_db), current_user=LeerCostoFull):
    """Costo & ROI del ciclo: costo por contacto/médico, ingresos, utilidad y ROI. Solo gestión
    (dato financiero). El representante ve su recorte en /costo/mi-linea.

    (Bloqueante 1 de revisión, ago-2026, ronda 3 — señalado explícitamente en el hallazgo):
    `vm_id` se pasaba DIRECTO a `visita_costo_service.roi` sin pasar por `_scope_vm` ni por
    ningún guard de país. `LeerCostoFull` exige alcance ALL de RBAC (visión total del
    módulo), pero alcance y país son ejes ortogonales — un ADMIN con alcance ALL puede
    seguir acotado a un subconjunto de países en `FACT_UsuarioPais`."""
    _exigir_pais_vm(db, current_user, vm_id)
    _exigir_pais_ciclo(db, current_user, ciclo_id)
    from app.services import visita_costo_service
    return visita_costo_service.roi(db, ciclo_id, vm_id)


@router.get("/costo/ranking", response_model=dict)
def costo_ranking(ciclo_id: int | None = None, db: Session = Depends(get_db), current_user=RequireCierre):
    """Detalle desplegable de ROI por VM (peor primero). Solo gestión (dato financiero).

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `ciclo_id` sin piso de país; también
    `RequireCierre` (ADMIN+GERENTE_PRODUCTIVIDAD) no exime del país."""
    _exigir_pais_ciclo(db, current_user, ciclo_id)
    from app.services import visita_costo_service
    return visita_costo_service.roi_ranking(db, ciclo_id)


def _linea_del_representante(db, current_user) -> int | None:
    """Línea del representante logueado (para auto-acotar su vista de Costo)."""
    vm = _scope_vm(db, current_user, None)
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
    #15: SOLO FINANZAS/Director/ADMIN (dato con salarios/costos). El GD/RM usan /costo/mi-linea.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `linea_id`/`ciclo_id` sin piso de país —
    el más sensible del módulo (salarios, costos fijos, pool de ventas, presupuesto anual)."""
    _exigir_pais_linea(db, current_user, linea_id)
    _exigir_pais_ciclo(db, current_user, ciclo_id)
    from app.services import visita_costo_service
    full = visita_costo_service.calcular_full(db, ciclo_id, linea_id)
    return {**full, **visita_costo_service.estado_estructura(db, ciclo_id, linea_id)}


@router.get("/costo/hojas", response_model=list[dict])
def costo_hojas(ciclo_id: int | None = None, db: Session = Depends(get_db), current_user=LeerCostoVer):
    """Hojas de Costo/ROI creadas en el ciclo (una por línea), la ÚLTIMA creada primero. Sirve
    para que un rol de solo lectura navegue/filtre entre las hojas de los distintos visitadores/
    distritos sin entrar a la vista de configuración.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `ciclo_id` sin piso de país."""
    _exigir_pais_ciclo(db, current_user, ciclo_id)
    from app.services import visita_costo_service
    return visita_costo_service.listar_hojas(db, ciclo_id)


@router.get("/costo/mi-linea", response_model=dict)
def costo_mi_linea(ciclo_id: int | None = None, linea_id: int | None = None,
                   db: Session = Depends(get_db),
                   _auth=Depends(_autorizar_authz(_Acc.READ, _Rec.COSTOROI_VER))):
    """Vista ACOTADA de Costo & ROI (sin salarios/costos): unidades a producir por contacto para
    el 100% del presupuesto + impacto de la cobertura en el presupuesto de la línea. La usan el
    REPRESENTANTE (su línea), el GERENTE DE DISTRITO (la de su equipo — #15) y los roles de
    CONSULTA/observación (visión total → eligen la hoja/línea que quieren ver, solo lectura).

    (Bloqueante 1 de revisión, ago-2026, ronda 3): la rama del observador con alcance ALL
    tomaba `linea_id` directo — alcance (RBAC) y país (frontera) son ejes ortogonales; un
    observador ALL puede seguir acotado a un subconjunto de países. `ciclo_id` también se
    valida para las tres ramas."""
    from app.services import visita_costo_service
    current_user = _auth.usuario
    rol = _rol(current_user)
    if rol == "REPRESENTANTE_MEDICO":
        linea = _linea_del_representante(db, current_user)
    elif rol == "GERENTE_DISTRITO":
        linea = _linea_del_gerente(db, current_user)
    elif _auth.alcance == _Alc.ALL:
        _exigir_pais_linea(db, current_user, linea_id)
        linea = linea_id  # observador con visión total: ve la hoja de la línea elegida
    else:
        raise HTTPException(403, "Esta vista es para el representante, el gerente de distrito o un rol de consulta.")
    _exigir_pais_ciclo(db, current_user, ciclo_id)
    if not linea:
        raise HTTPException(400, "Elige una hoja (línea) para ver.")
    return visita_costo_service.vista_representante(db, ciclo_id, linea)


@router.post("/costo/estructura", response_model=dict, status_code=status.HTTP_201_CREATED)
def guardar_costo_estructura(datos: CostoEstructuraGuardar, background_tasks: BackgroundTasks,
                             db: Session = Depends(get_db), current_user=ConfigurarCosto):
    """Guarda la estructura (Finanzas configura → estado BORRADOR). Una config ya APROBADA solo
    la edita ADMIN (debe reabrirse primero). Si guarda Finanzas (no ADMIN), avisa al Director.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `datos.linea_id`/`datos.ciclo_id` sin
    piso de país."""
    _exigir_pais_linea(db, current_user, datos.linea_id)
    _exigir_pais_ciclo(db, current_user, datos.ciclo_id)
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
    (Finanzas) NO puede aprobar: la matriz separa CONFIGURE (Finanzas) de APPROVE (Director).

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `linea_id`/`ciclo_id` sin piso de país."""
    _exigir_pais_linea(db, current_user, linea_id)
    _exigir_pais_ciclo(db, current_user, ciclo_id)
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
    auditada.

    (Bloqueante 1 de revisión, ago-2026, ronda 3 — mismo patrón que `/planeacion/desbloquear`):
    `RequireDesbloqueo` (solo ADMIN) no exime del país."""
    _exigir_pais_linea(db, current_user, linea_id)
    _exigir_pais_ciclo(db, current_user, ciclo_id)
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
    presupuesto_anual, precio_prom.

    (Bloqueante 1 de revisión, ago-2026, ronda 3): `linea_id`/`ciclo_id` sin piso de país."""
    _exigir_pais_linea(db, current_user, linea_id)
    _exigir_pais_ciclo(db, current_user, ciclo_id)
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
