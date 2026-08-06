"""Simulacro de Venta con IA (§9). Genera el escenario con la capa IA de la Fase 0."""
import io

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.services import formacion_simulacro_service as sim
from app.services.ia.conexion_service import SinConexionIA

router = APIRouter(prefix="/formacion/simulacro", tags=["Formación — Simulacro IA"])

RequirePractica = Depends(require_roles(Rol.ADMIN, Rol.REPRESENTANTE_MEDICO))
RequireLectura = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION,
    Rol.GERENTE_DISTRITO, Rol.PRESIDENCIA, Rol.GERENTE_MEDICO,
    Rol.REPRESENTANTE_MEDICO))


def _rm_propio(usuario: Usuario) -> int:
    rm_id = getattr(usuario, "rm_id", None)
    if rm_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Tu usuario no está enlazado a un representante.")
    return rm_id


def _scope(usuario: Usuario) -> int | None:
    """rm_id a exigir como dueño; None para ADMIN (sin restricción)."""
    return None if usuario.rol == Rol.ADMIN else _rm_propio(usuario)


class IniciarEntrada(BaseModel):
    rm_id: int | None = None       # solo ADMIN puede indicar otro RM
    estilo: str | None = None
    medico: str | None = None
    genero: str | None = None


class ResponderEntrada(BaseModel):
    opcion: str


@router.post("/iniciar", summary="Generar un escenario y arrancar la sesión")
def iniciar(datos: IniciarEntrada, db: Session = Depends(get_db),
            usuario: Usuario = RequirePractica):
    rm_id = datos.rm_id if (usuario.rol == Rol.ADMIN and datos.rm_id) else _rm_propio(usuario)
    try:
        return sim.iniciar(db, rm_id, estilo=datos.estilo, medico=datos.medico,
                           genero=datos.genero)
    except SinConexionIA as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except sim.SimulacroIAError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.get("/mis-sesiones", summary="Historial de prácticas del RM")
def mis_sesiones(db: Session = Depends(get_db), usuario: Usuario = RequirePractica):
    return sim.mis_sesiones(db, _rm_propio(usuario))


@router.get("/sesion/{sesion_id}", summary="Detalle de una sesión")
def sesion(sesion_id: int, db: Session = Depends(get_db), usuario: Usuario = RequireLectura):
    try:
        d = sim.detalle(db, sesion_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    scope = _scope(usuario)
    if scope is not None and d["sesion"]["rm_id"] != scope:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No es tu sesión.")
    return d


@router.get("/ronda/{ronda_id}/voz", summary="Audio de la objeción (o señal Web Speech)")
def voz(ronda_id: int, db: Session = Depends(get_db), _: Usuario = RequireLectura):
    try:
        audio = sim.voz_ronda(db, ronda_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if audio.en_navegador:
        r = db.get(sim.SimulacroRonda, ronda_id)
        return {"en_navegador": True, "texto": r.objecion_texto, "aviso": audio.aviso}
    return StreamingResponse(io.BytesIO(audio.contenido or b""),
                             media_type=audio.mime or "audio/mpeg")


@router.post("/ronda/{ronda_id}/responder", summary="Responder — revela la correcta")
def responder(ronda_id: int, datos: ResponderEntrada, db: Session = Depends(get_db),
              usuario: Usuario = RequirePractica):
    try:
        return sim.responder(db, ronda_id, datos.opcion, rm_id_scope=_scope(usuario))
    except sim.PermisoError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/sesion/{sesion_id}/finalizar", summary="Calcular el resultado D/P/A/E")
def finalizar(sesion_id: int, db: Session = Depends(get_db), usuario: Usuario = RequirePractica):
    try:
        return sim.finalizar(db, sesion_id, rm_id_scope=_scope(usuario))
    except sim.PermisoError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/resumen", summary="Agregado de prácticas (GD/Capacitación)")
def resumen(db: Session = Depends(get_db), usuario: Usuario = RequireLectura):
    if usuario.rol == Rol.REPRESENTANTE_MEDICO:
        return sim.resumen(db, [_rm_propio(usuario)])
    return sim.resumen(db)
