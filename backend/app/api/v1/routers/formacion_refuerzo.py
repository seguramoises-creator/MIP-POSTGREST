"""Refuerzo de Memoria y su KPI (§10 y §11).

Router aparte del de Onboarding/Biblioteca porque son ciclos de vida distintos:
aquí Capacitación arma campañas y programa envíos, y el representante responde
cápsulas. Comparten el prefijo `/formacion` pero no el flujo.

LO QUE NUNCA SALE POR AQUÍ
---------------------------
La opción correcta de un reto no viaja con el enunciado. Si lo hiciera, bastaría
mirar la respuesta de la API para acertar siempre y el % de aciertos dejaría de
medir nada. Llega únicamente al responder, junto con la explicación, para el
resaltado inmediato del §10.7 — mismo criterio que el `score_oculto` de LSII.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authz import scope
from app.core.authz.constantes import Alcance
from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.formacion import RefuerzoCampana, RefuerzoCapsula
from app.models.usuario import Rol, Usuario
from app.services import formacion_kpi_refuerzo_service as kpi
from app.services import formacion_refuerzo_service as refuerzo

router = APIRouter(prefix="/formacion/refuerzo", tags=["Formación — Refuerzo de Memoria"])

RequireCapacitacion = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION))
RequireContenido = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION, Rol.GERENTE_MEDICO))
RequireAnyAuth = Depends(get_current_active_user)

#: Quién ve el consolidado completo y quién solo su equipo (§11.5).
_VEN_TODO = {Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION,
             Rol.PRESIDENCIA, Rol.GERENTE_MEDICO}


def _rm_propio(usuario: Usuario) -> int:
    rm_id = getattr(usuario, "rm_id", None)
    if rm_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tu usuario no está enlazado a un representante.")
    return rm_id


# ===========================================================================
# Gestión de campañas (Capacitación)
# ===========================================================================

class CampanaEntrada(BaseModel):
    pais_codigo: str
    nombre: str = Field(min_length=1, max_length=200)
    duracion_dias: int = 30
    modo_espaciado: str = "creciente"     # creciente | fijo_48h
    producto_id: int | None = None
    ciclo_id: int | None = None
    material_fuente_id: int | None = None


class CapsulaEntrada(BaseModel):
    formato: str                          # microlectura|reto|caso_breve|reflexion_abierta
    enunciado: str
    orden: int = 1
    opciones: dict | None = None
    opcion_correcta: str | None = None
    explicacion: str | None = None


class RespuestaEntrada(BaseModel):
    opcion: str | None = None
    texto_libre: str | None = None


@router.post("/campanas", status_code=status.HTTP_201_CREATED, summary="Crear campaña")
def crear_campana(datos: CampanaEntrada, db: Session = Depends(get_db),
                  usuario: Usuario = RequireCapacitacion):
    if datos.modo_espaciado not in refuerzo.MODOS_ESPACIADO:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Modo inválido. Use: {', '.join(refuerzo.MODOS_ESPACIADO)}.")
    if datos.duracion_dias not in refuerzo.DURACIONES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Duración inválida. El §10.2 define: {', '.join(map(str, refuerzo.DURACIONES))} días.")
    c = RefuerzoCampana(**datos.model_dump(), creado_por=usuario.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "nombre": c.nombre, "estado": c.estado,
            "modo_espaciado": c.modo_espaciado}


@router.get("/campanas", summary="Campañas del país")
def listar_campanas(pais_codigo: str, db: Session = Depends(get_db),
                    _: Usuario = RequireCapacitacion):
    filas = (db.query(RefuerzoCampana)
             .filter(RefuerzoCampana.pais_codigo == pais_codigo)
             .order_by(RefuerzoCampana.creado_en.desc()).all())
    return [{"id": c.id, "nombre": c.nombre, "duracion_dias": c.duracion_dias,
             "modo_espaciado": c.modo_espaciado, "estado": c.estado,
             "aprobado_por_gm": c.aprobado_por_gm} for c in filas]


@router.post("/campanas/{campana_id}/calendario",
             summary="Generar el calendario SUGERIDO de rondas")
def generar_calendario(campana_id: int, inicio: datetime | None = None,
                       db: Session = Depends(get_db), _: Usuario = RequireCapacitacion):
    """VISTA sugiere; nada queda publicado hasta que Capacitación confirme (§10.3)."""
    try:
        rondas = refuerzo.generar_calendario(db, campana_id, inicio)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return [{"id": r.id, "numero_ronda": r.numero_ronda,
             "fecha_hora_sugerida": r.fecha_hora_sugerida,
             "fecha_hora_programada": r.fecha_hora_programada,
             "publicada": r.publicada} for r in rondas]


@router.put("/rondas/{ronda_id}/programar",
            summary="Confirmar día y hora exactos de una ronda")
def programar(ronda_id: int, fecha_hora: datetime | None = None,
              db: Session = Depends(get_db), _: Usuario = RequireCapacitacion):
    """Sin fecha, se acepta la sugerida. Aceptarla también es confirmar: lo que
    no puede pasar es que una ronda salga sin que nadie la haya mirado."""
    try:
        r = refuerzo.programar_ronda(db, ronda_id, fecha_hora)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"id": r.id, "fecha_hora_programada": r.fecha_hora_programada}


@router.post("/rondas/{ronda_id}/capsulas", status_code=status.HTTP_201_CREATED,
             summary="Agregar una cápsula a la ronda")
def agregar_capsula(ronda_id: int, datos: CapsulaEntrada,
                    db: Session = Depends(get_db), _: Usuario = RequireContenido):
    if datos.formato not in refuerzo.FORMATOS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Formato inválido. Use: {', '.join(refuerzo.FORMATOS)}.")
    if datos.formato == "reto" and not datos.opcion_correcta:
        # §10.7: el reto SIEMPRE es opción múltiple con una única correcta, o no
        # se puede corregir en el acto.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Un reto necesita su opción correcta para poder corregirse al instante.")
    c = RefuerzoCapsula(ronda_id=ronda_id, **datos.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "formato": c.formato}


@router.post("/rondas/{ronda_id}/publicar",
             summary="Publicar la ronda y notificar (correo + push)")
def publicar(ronda_id: int, db: Session = Depends(get_db),
             _: Usuario = RequireCapacitacion):
    try:
        r = refuerzo.publicar_ronda(db, ronda_id)
    except refuerzo.CampanaNoPublicable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"id": r.id, "publicada": r.publicada, "notificada_en": r.notificada_en}


# ===========================================================================
# El representante responde
# ===========================================================================

@router.get("/mis-capsulas", summary="Cápsulas que tengo pendientes")
def mis_capsulas(db: Session = Depends(get_db), usuario: Usuario = RequireAnyAuth):
    return refuerzo.capsulas_pendientes(db, _rm_propio(usuario))


@router.post("/capsulas/{capsula_id}/responder",
             summary="Responder — devuelve la corrección inmediata (§10.7)")
def responder(capsula_id: int, datos: RespuestaEntrada,
              db: Session = Depends(get_db), usuario: Usuario = RequireAnyAuth):
    """La respuesta trae la opción correcta y su explicación SIEMPRE, se haya
    acertado o no: es lo que permite resaltarla en la misma interacción, sin una
    segunda llamada ni recarga."""
    try:
        return refuerzo.registrar_respuesta(
            db, capsula_id, _rm_propio(usuario),
            opcion=datos.opcion, texto_libre=datos.texto_libre)
    except refuerzo.RondaNoDisponible as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/mis-puntos", summary="Puntos de Refuerzo que aporto al Ranking")
def mis_puntos(campana_id: int | None = None, db: Session = Depends(get_db),
               usuario: Usuario = RequireAnyAuth):
    return {"puntos": refuerzo.puntos_de_refuerzo(db, _rm_propio(usuario), campana_id)}


# ===========================================================================
# §11 — Reporte de KPI
# ===========================================================================

@router.get("/kpi", summary="KPI de Refuerzo: 3 métricas por 4 desgloses")
def reporte_kpi(campana_id: int | None = None, pais_codigo: str | None = None,
                db: Session = Depends(get_db), usuario: Usuario = RequireAnyAuth):
    """§11.5 — el alcance depende del rol.

    Un Gerente de Distrito ve los desgloses acotados a su equipo, y SIN el
    desglose "Por GD": compararse consigo mismo no aporta, y ese corte existe
    para que Capacitación compare equipos entre sí (§11.3.c).
    """
    if usuario.rol in _VEN_TODO:
        rm_ids, incluir_por_gd = None, True
    elif usuario.rol == Rol.GERENTE_DISTRITO:
        visibles = scope.rm_ids_visibles(db, usuario, Alcance.TEAM)
        rm_ids = sorted(visibles) if visibles is not None else None
        incluir_por_gd = False
    elif usuario.rol == Rol.REPRESENTANTE_MEDICO:
        rm_ids, incluir_por_gd = [_rm_propio(usuario)], False
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Tu rol no tiene acceso al KPI de Refuerzo.")
    return kpi.reporte(db, campana_id=campana_id, pais_codigo=pais_codigo,
                       rm_ids=rm_ids, incluir_por_gd=incluir_por_gd)
