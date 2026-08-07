"""Onboarding y Biblioteca de la Ampliación del Módulo de Formación (§4 y §5).

Van en el mismo router porque son inseparables en el uso: el gating de exámenes
del §5.3 es lo que hace funcionar el paso 6 de la ruta, y el representante los
vive como una sola pantalla ("me falta leer esto para poder presentar aquello").

REPARTO DE RESPONSABILIDADES (§4.6 y §5.6)
-------------------------------------------
No es un detalle administrativo, es lo que da valor a los pasos: si el propio
representante pudiera marcar su hito de campo, el hito no probaría que el GD lo
acompañó. Por eso el rol viaja al servicio y este lo hace cumplir, en vez de
confiar en que la interfaz esconda el botón.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.formacion import ProductoLinea
from app.models.usuario import Rol, Usuario
from app.services import formacion_biblioteca_service as biblioteca
from app.services import formacion_onboarding_service as onboarding

router = APIRouter(prefix="/formacion", tags=["Formación — Onboarding y Biblioteca"])

# Capacitación = "Gerente de Capacitación y Productividad" en la matriz de roles
# del cliente (§2). Gerente Médico co-edita el contenido científico: es el
# firewall PhRMA, no una cortesía.
RequireCapacitacion = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION))
RequireContenido = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION, Rol.GERENTE_MEDICO))
RequireGerenteMedico = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_MEDICO))
RequireAnyAuth = Depends(get_current_active_user)

#: Traducción del rol del sistema al vocabulario del requerimiento (§2). Vive
#: aquí, en la frontera, para que el servicio hable el idioma del documento y no
#: el del enum interno.
_ROL_EN_RUTA = {
    Rol.REPRESENTANTE_MEDICO: "representante",
    Rol.GERENTE_DISTRITO: "gd",
    Rol.GERENTE_PRODUCTIVIDAD: "capacitacion",
    Rol.CAPACITACION: "capacitacion",
    Rol.ADMIN: "admin",
}


def _rol_ruta(usuario: Usuario) -> str:
    return _ROL_EN_RUTA.get(usuario.rol, "otro")


def _rm_propio(usuario: Usuario) -> int:
    rm_id = getattr(usuario, "rm_id", None)
    if rm_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tu usuario no está enlazado a un representante, así que no tiene "
            "ruta de formación propia.")
    return rm_id


# ===========================================================================
# Productos de la línea (§4.3)
# ===========================================================================

class ProductoEntrada(BaseModel):
    pais_codigo: str
    linea_id: int
    nombre_producto: str = Field(min_length=1, max_length=200)
    rol_en_ruta: str = "principal"   # principal | relacionado


@router.get("/productos", summary="Productos de una línea")
def listar_productos(pais_codigo: str, linea_id: int, db: Session = Depends(get_db),
                     _: Usuario = RequireAnyAuth):
    return [{"id": p.id, "nombre_producto": p.nombre_producto,
             "rol_en_ruta": p.rol_en_ruta, "activo": p.activo}
            for p in biblioteca.productos_de_linea(db, pais_codigo, linea_id)]


@router.post("/productos", status_code=status.HTTP_201_CREATED,
             summary="Registrar producto de la línea")
def crear_producto(datos: ProductoEntrada, db: Session = Depends(get_db),
                   _: Usuario = RequireCapacitacion):
    if datos.rol_en_ruta not in ("principal", "relacionado"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "rol_en_ruta debe ser 'principal' o 'relacionado'.")
    p = ProductoLinea(**datos.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "nombre_producto": p.nombre_producto, "rol_en_ruta": p.rol_en_ruta}


# ===========================================================================
# §5 — Biblioteca
# ===========================================================================

class MaterialEntrada(BaseModel):
    pais_codigo: str
    titulo: str = Field(min_length=1, max_length=250)
    tipo: str                       # manual|ayuda_visual|estudio_clinico|ficha_tecnica|video
    archivo_url: str
    producto_id: int | None = None
    obligatorio: bool = True        # §5.3: activado por defecto
    usado_en_examen_id: int | None = None
    usado_en_coaching_av: bool = False


@router.get("/biblioteca", summary="Material disponible")
def listar_material(pais_codigo: str, producto_id: int | None = None,
                    db: Session = Depends(get_db), usuario: Usuario = RequireAnyAuth):
    # El representante solo ve lo aprobado: el material sin pasar el firewall
    # PhRMA no debe llegarle (§2).
    solo_aprobados = usuario.rol == Rol.REPRESENTANTE_MEDICO
    return [{"id": m.id, "titulo": m.titulo, "tipo": m.tipo,
             "archivo_url": m.archivo_url, "obligatorio": m.obligatorio,
             "producto_id": m.producto_id, "aprobado_por_gm": m.aprobado_por_gm}
            for m in biblioteca.listar_materiales(db, pais_codigo, producto_id,
                                                  solo_aprobados)]


@router.post("/biblioteca", status_code=status.HTTP_201_CREATED,
             summary="Subir material")
def subir_material(datos: MaterialEntrada, db: Session = Depends(get_db),
                   usuario: Usuario = RequireContenido):
    try:
        m = biblioteca.subir_material(db, datos.model_dump(), actor=usuario)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"id": m.id, "titulo": m.titulo, "aprobado_por_gm": m.aprobado_por_gm}


@router.post("/biblioteca/{material_id}/aprobar",
             summary="Aprobación de Gerencia Médica (firewall PhRMA)")
def aprobar_material(material_id: int, db: Session = Depends(get_db),
                     usuario: Usuario = RequireGerenteMedico):
    try:
        m = biblioteca.aprobar_material(db, material_id, actor=usuario)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"id": m.id, "aprobado_por_gm": m.aprobado_por_gm}


@router.post("/biblioteca/{material_id}/confirmar",
             summary="El representante confirma que lo leyó")
def confirmar_lectura(material_id: int, db: Session = Depends(get_db),
                      usuario: Usuario = RequireAnyAuth):
    try:
        c = biblioteca.confirmar_lectura(db, material_id, _rm_propio(usuario))
    except biblioteca.MaterialNoAprobado as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"material_id": c.material_id, "confirmado_en": c.timestamp_confirmacion}


@router.get("/biblioteca/{material_id}/confirmaciones",
            summary="Quién ya confirmó (§5.4)")
def confirmaciones(material_id: int, db: Session = Depends(get_db),
                   _: Usuario = RequireContenido):
    return biblioteca.confirmaciones_de_material(db, material_id)


@router.get("/biblioteca/progreso", summary="Mi progreso de lectura obligatoria")
def progreso(producto_ids: str, db: Session = Depends(get_db),
             usuario: Usuario = RequireAnyAuth):
    ids = [int(x) for x in producto_ids.split(",") if x.strip().isdigit()]
    return biblioteca.progreso_lectura(db, _rm_propio(usuario), ids)


# ===========================================================================
# §4 — Onboarding
# ===========================================================================

class PlantillaEntrada(BaseModel):
    pais_codigo: str
    linea_id: int
    nombre_plantilla: str = Field(min_length=1, max_length=200)
    duracion_dias: int = 30


class AsignacionEntrada(BaseModel):
    plantilla_id: int
    rm_id: int
    fecha_inicio: date | None = None


@router.post("/onboarding/plantillas", status_code=status.HTTP_201_CREATED,
             summary="Crear la ruta estándar de 10 pasos para una línea")
def crear_plantilla(datos: PlantillaEntrada, db: Session = Depends(get_db),
                    usuario: Usuario = RequireContenido):
    p = onboarding.crear_plantilla_estandar(
        db, datos.pais_codigo, datos.linea_id, datos.nombre_plantilla,
        datos.duracion_dias, actor=usuario)
    pasos = onboarding.pasos_de(db, p.id)
    return {"id": p.id, "nombre_plantilla": p.nombre_plantilla,
            "pasos": [{"id": x.id, "orden": x.orden, "titulo": x.titulo,
                       "tipo": x.tipo, "plazo_sugerido": x.plazo_sugerido,
                       "bloqueante": x.bloqueante, "quien_lo_marca": x.quien_lo_marca}
                      for x in pasos]}


@router.get("/onboarding/plantillas/{plantilla_id}/pasos", summary="Pasos de una ruta")
def ver_pasos(plantilla_id: int, db: Session = Depends(get_db),
              _: Usuario = RequireAnyAuth):
    return [{"id": p.id, "orden": p.orden, "titulo": p.titulo, "tipo": p.tipo,
             "plazo_sugerido": p.plazo_sugerido, "bloqueante": p.bloqueante,
             "quien_lo_marca": p.quien_lo_marca}
            for p in onboarding.pasos_de(db, plantilla_id)]


@router.post("/onboarding/asignaciones", status_code=status.HTTP_201_CREATED,
             summary="Asignar una ruta a un representante")
def asignar(datos: AsignacionEntrada, db: Session = Depends(get_db),
            usuario: Usuario = RequireCapacitacion):
    a = onboarding.asignar(db, datos.plantilla_id, datos.rm_id,
                           datos.fecha_inicio, actor=usuario)
    return {"id": a.id, "rm_id": a.rm_id, "progreso_pct": float(a.progreso_pct)}


@router.get("/onboarding/mis-asignaciones",
            summary="Mis rutas de formación (el representante descubre la suya)")
def mis_asignaciones(db: Session = Depends(get_db), usuario: Usuario = RequireAnyAuth):
    """Auto-scope: no recibe rm_id, siempre devuelve las del usuario en sesión.

    No es un filtro opcional sino el único comportamiento: no debe existir un
    camino por el que alguien pida la ruta de otro por esta vía.
    """
    return onboarding.asignaciones_de_rm(db, _rm_propio(usuario))


@router.get("/onboarding/asignaciones/{asignacion_id}",
            summary="Estado de la ruta: qué está disponible y qué bloquea")
def estado(asignacion_id: int, db: Session = Depends(get_db),
           usuario: Usuario = RequireAnyAuth):
    try:
        datos = onboarding.estado_ruta(db, asignacion_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    # Un representante solo ve la suya (auto-filtro de scope, §17 de CLAUDE.md).
    if usuario.rol == Rol.REPRESENTANTE_MEDICO and datos["rm_id"] != _rm_propio(usuario):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esa ruta no es tuya.")
    return datos


@router.post("/onboarding/asignaciones/{asignacion_id}/pasos/{paso_id}/completar",
             summary="Marcar un paso como completado")
def completar(asignacion_id: int, paso_id: int, observaciones: str | None = None,
              db: Session = Depends(get_db), usuario: Usuario = RequireAnyAuth):
    try:
        p = onboarding.completar_paso(db, asignacion_id, paso_id,
                                      rol_actor=_rol_ruta(usuario), actor=usuario,
                                      observaciones=observaciones)
    except onboarding.RolNoAutorizado as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except onboarding.PasoBloqueado as exc:
        # 409 y no 422: la petición es válida, lo que falta es que se cumplan
        # las condiciones. El mensaje dice exactamente cuáles.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"paso_id": p.paso_id, "completado_en": p.completado_en}
