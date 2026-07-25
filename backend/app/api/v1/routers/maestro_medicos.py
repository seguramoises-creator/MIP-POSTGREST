"""SCGCPR — Router: Maestro de Médicos · prefix="/medicos".

Fuente única del dato general del médico (país-level). La categorización
(cat.*) y la asignación (Visita.DIM_MedicoVisita) referencian a este maestro.
"""
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.authz.deps import require as _require_authz
from app.core.authz.constantes import Accion as _Acc, Recurso as _Rec
from app.models.usuario import Usuario
from app.models.dimensiones import Medico
from app.schemas.schemas import (MaestroMedicoCrear, MaestroMedicoActualizar,
                                 MaestroMedicoResponse)
from app.services import maestro_medico_service as svc

router = APIRouter(prefix="/medicos", tags=["Maestro de Médicos"])

# RBAC por matriz editable (jul-2026). Las filas `medico.maestro` / `medico.maestro.editar` se
# calcaron del `require_roles` que había aquí, así que el acceso efectivo NO cambia; lo que cambia
# es que ahora se ajusta desde Administración → Roles y Permisos. Van dos recursos porque el alta
# es MÁS restringida que la edición (una celda no puede dar dos acciones distintas al mismo rol).
RequireLectura = Depends(_require_authz(_Acc.READ, _Rec.MEDICO_MAESTRO))        # cualquier autenticado
RequireEscritura = Depends(_require_authz(_Acc.CONFIGURE, _Rec.MEDICO_MAESTRO))  # ADMIN + GERENTE_PRODUCTIVIDAD
RequireSupervisor = Depends(_require_authz(_Acc.CONFIGURE, _Rec.MEDICO_MAESTRO_EDITAR))  # + GD + GERENTE_MARCA


def _filtrar(query, q, especialidad_id, provincia_id, estado, activo, pais_codigo=None):
    if q:
        like = f"%{q.upper()}%"
        query = query.filter(func.upper(Medico.nombre).like(like) |
                             func.upper(func.coalesce(Medico.codigo, "")).like(like) |
                             func.upper(func.coalesce(Medico.cedula, "")).like(like))
    if especialidad_id: query = query.filter(Medico.especialidad_id == especialidad_id)
    if provincia_id:    query = query.filter(Medico.provincia_id == provincia_id)
    if estado:          query = query.filter(Medico.estado_validacion == estado)
    if activo is not None: query = query.filter(Medico.activo == activo)
    if pais_codigo:     query = query.filter(Medico.pais_codigo == pais_codigo)
    return query.order_by(Medico.nombre)


@router.get("/maestro", response_model=list[MaestroMedicoResponse])
def listar(q: str | None = None, especialidad_id: int | None = None,
           provincia_id: int | None = None, estado: str | None = None,
           activo: bool | None = None, pais_codigo: str | None = None,
           skip: int = 0, limit: int = Query(100, le=500),
           db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    return _filtrar(db.query(Medico), q, especialidad_id, provincia_id, estado, activo, pais_codigo) \
        .offset(skip).limit(limit).all()


@router.get("/maestro/kpis")
def kpis(pais_codigo: str | None = None,
         db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    from app.models.visita import MedicoVisita

    def _q():
        qy = db.query(func.count(Medico.id))
        if pais_codigo:
            qy = qy.filter(Medico.pais_codigo == pais_codigo)
        return qy

    total = _q().scalar() or 0
    activos = _q().filter(Medico.activo == True).scalar() or 0  # noqa: E712
    ini_mes = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nuevos = _q().filter(Medico.created_at >= ini_mes).scalar() or 0
    pendientes = _q().filter(Medico.estado_validacion == "PENDIENTE").scalar() or 0
    asignados = {mid for (mid,) in db.query(MedicoVisita.maestro_medico_id)
                 .filter(MedicoVisita.maestro_medico_id.isnot(None)).distinct().all()}
    sin_asig = _q().filter(
        Medico.activo == True, ~Medico.id.in_(asignados or {-1})).scalar() or 0  # noqa: E712
    return {"total": total, "activos": activos, "nuevos_mes": nuevos,
            "sin_asignacion": sin_asig, "pendientes_validacion": pendientes}


def _leer_excel(contenido: bytes) -> list[dict]:
    """Valida magic bytes .xlsx y devuelve las filas como dicts (columnas en minúsculas)."""
    if contenido[:4] != b"PK\x03\x04":
        raise HTTPException(400, "El archivo no es un .xlsx válido.")
    try:
        df = pd.read_excel(BytesIO(contenido))
    except Exception as e:
        raise HTTPException(400, f"No se pudo leer el Excel: {e}")
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "nombre" not in df.columns:
        raise HTTPException(400, "El Excel debe tener una columna 'nombre'.")
    return df.to_dict("records")


@router.post("/maestro/preview", summary="Previsualiza el efecto de importar (no persiste)")
async def preview_import(pais_codigo: str = Query(...), archivo: UploadFile = File(...),
                         db: Session = Depends(get_db), _u: Usuario = RequireEscritura):
    return svc.preview_excel(db, pais_codigo, _leer_excel(await archivo.read()))


@router.post("/maestro/importar", summary="Importa (upsert) el maestro desde Excel")
async def ejecutar_import(pais_codigo: str = Query(...), archivo: UploadFile = File(...),
                          db: Session = Depends(get_db), current_user: Usuario = RequireEscritura):
    return svc.importar_excel(db, pais_codigo, _leer_excel(await archivo.read()), current_user.id)


_EXPORT_COLS = ["id", "nombre", "codigo", "cedula", "exequatur", "telefono", "email",
                "direccion", "sector", "especialidad_id", "provincia_id", "municipio_id",
                "centro_medico_id", "estado_validacion", "origen", "activo"]


@router.get("/maestro/exportar", summary="Exporta el Maestro a Excel (respeta filtros)")
def exportar(q: str | None = None, especialidad_id: int | None = None,
             provincia_id: int | None = None, estado: str | None = None,
             activo: bool | None = None, db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    filas = _filtrar(db.query(Medico), q, especialidad_id, provincia_id, estado, activo).all()
    df = pd.DataFrame([{c: getattr(m, c) for c in _EXPORT_COLS} for m in filas], columns=_EXPORT_COLS)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Maestro")
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=maestro_medicos.xlsx"})


@router.get("/maestro/{medico_id}", response_model=MaestroMedicoResponse)
def obtener(medico_id: int, db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    m = db.query(Medico).filter(Medico.id == medico_id).first()
    if not m: raise HTTPException(404, "Médico no encontrado")
    return m


@router.get("/maestro/{medico_id}/historial", summary="Historial de cambios del médico")
def historial(medico_id: int, db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    from app.models.hechos import Auditoria
    from app.models.usuario import Usuario as U
    filas = (db.query(Auditoria)
             .filter(Auditoria.tabla == "DIM_Medico", Auditoria.registro_id == str(medico_id))
             .order_by(Auditoria.fecha_hora.desc()).limit(100).all())
    ids = {f.usuario_id for f in filas if f.usuario_id}
    nombres = dict(db.query(U.id, U.nombre_completo).filter(U.id.in_(ids)).all()) if ids else {}
    return [{"fecha": f.fecha_hora.isoformat() if f.fecha_hora else None,
             "usuario": nombres.get(f.usuario_id) or f.username or (f"#{f.usuario_id}" if f.usuario_id else "sistema"),
             "accion": f.accion, "detalle": f.detalle} for f in filas]


@router.post("/maestro", response_model=MaestroMedicoResponse, status_code=201)
def crear(datos: MaestroMedicoCrear, db: Session = Depends(get_db),
          current_user: Usuario = RequireEscritura):
    payload = datos.model_dump(exclude={"pais_codigo", "confirmar_duplicado"})
    try:
        return svc.crear_maestro(db, datos.pais_codigo, payload, origen="MANUAL",
                                 confirmar_duplicado=datos.confirmar_duplicado,
                                 usuario_id=current_user.id)
    except svc.DuplicadoDuroError as e:
        raise HTTPException(409, detail={"tipo": "duro",
            "mensaje": "Ya existe un médico con ese exequátur o cédula. No se puede crear.",
            "coincidencias": e.coincidencias})
    except svc.PosibleDuplicadoError as e:
        raise HTTPException(409, detail={"tipo": "blando",
            "mensaje": "Posible médico duplicado (mismo nombre y ubicación). "
                       "Reenvíe con confirmar_duplicado=true para crear de todas formas.",
            "coincidencias": e.coincidencias})


@router.put("/maestro/{medico_id}", response_model=MaestroMedicoResponse)
def actualizar(medico_id: int, datos: MaestroMedicoActualizar,
               db: Session = Depends(get_db), current_user: Usuario = RequireSupervisor):
    m = db.query(Medico).filter(Medico.id == medico_id).first()
    if not m: raise HTTPException(404, "Médico no encontrado")
    return svc.actualizar_maestro(db, m, datos.model_dump(exclude_unset=True), current_user.id)
