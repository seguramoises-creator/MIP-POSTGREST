"""Panel de conexiones a proveedores de IA (§20.4) — solo Superadmin.

Deja al CLIENTE elegir y cambiar a qué IA se conecta VISTA, sin cambio de código
ni despliegue. Es una operación privilegiada: toca credenciales y tiene impacto
directo en costos, así que va restringida a ADMIN y toda acción queda auditada
(§20.6).

POR QUÉ SE GUARDA POR ROL Y NO POR LA MATRIZ RBAC
--------------------------------------------------
El resto de la aplicación es matriz-driven, pero esto sigue el mismo criterio ya
establecido para `/admin`: es administración de sistema, no una funcionalidad de
negocio con alcances por equipo. Además, agregar un recurso a la matriz exige una
migración —si solo se sembrara, quedaría denegado para todos— y no aporta nada
aquí, donde el §20.4 pide un único rol.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.services.ia import cifrado, conexion_service
from app.services.ia.base import ProveedorNoSoportado

router = APIRouter(prefix="/ia/conexiones", tags=["Conexiones de IA"])

RequireAdmin = Depends(require_roles(Rol.ADMIN))


class ConexionEntrada(BaseModel):
    """Los 9 campos del §20.4.

    `credencial_1`/`credencial_2` son opcionales al ACTUALIZAR a propósito: el
    formulario recibe el valor enmascarado y no debe reenviarlo, o sobrescribiría
    la credencial real con los puntos suspensivos.
    """
    nombre: str = Field(min_length=1, max_length=100)
    capacidad: str            # texto | voz
    proveedor_tipo: str
    endpoint_url: str | None = None
    metodo_auth: str = "api_key"
    credencial_1: str | None = None
    credencial_2: str | None = None
    modelo: str | None = None


class ConexionCambio(BaseModel):
    nombre: str | None = None
    capacidad: str | None = None
    proveedor_tipo: str | None = None
    endpoint_url: str | None = None
    metodo_auth: str | None = None
    credencial_1: str | None = None
    credencial_2: str | None = None
    modelo: str | None = None


@router.get("", summary="Conexiones guardadas (credenciales enmascaradas)")
def listar(capacidad: str | None = None, db: Session = Depends(get_db),
           _: Usuario = RequireAdmin):
    return {
        "conexiones": [conexion_service.a_dict(c) for c in conexion_service.listar(db, capacidad)],
        # Se avisa aquí, y no al fallar el guardado, para que el administrador
        # sepa antes de llenar el formulario que falta configurar la llave.
        "cifrado_configurado": cifrado.hay_llave(),
    }


@router.get("/proveedores", summary="Proveedores con adaptador construido")
def proveedores(_: Usuario = RequireAdmin):
    return conexion_service.proveedores_disponibles()


@router.post("", status_code=status.HTTP_201_CREATED, summary="Crear conexión")
def crear(datos: ConexionEntrada, db: Session = Depends(get_db),
          usuario: Usuario = RequireAdmin):
    try:
        c = conexion_service.crear(db, datos.model_dump(), actor=usuario)
    except (ValueError, ProveedorNoSoportado) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except cifrado.LlaveCifradoNoConfigurada as exc:
        # 503 y no 500: no es un error del sistema sino una configuración del
        # ambiente que falta, y el mensaje explica cómo resolverla.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return conexion_service.a_dict(c)


@router.put("/{conexion_id}", summary="Actualizar conexión")
def actualizar(conexion_id: int, datos: ConexionCambio, db: Session = Depends(get_db),
               usuario: Usuario = RequireAdmin):
    cambios = {k: v for k, v in datos.model_dump().items() if v is not None}
    try:
        c = conexion_service.actualizar(db, conexion_id, cambios, actor=usuario)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except cifrado.LlaveCifradoNoConfigurada as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return conexion_service.a_dict(c)


@router.delete("/{conexion_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Eliminar conexión")
def eliminar(conexion_id: int, db: Session = Depends(get_db), usuario: Usuario = RequireAdmin):
    conexion_service.eliminar(db, conexion_id, actor=usuario)


@router.post("/{conexion_id}/probar", summary="Probar conexión (§20.4.8)")
def probar(conexion_id: int, db: Session = Depends(get_db), usuario: Usuario = RequireAdmin):
    """Hace una llamada mínima al proveedor y guarda el resultado.

    Devuelve 200 incluso cuando la prueba falla: el fallo es información útil
    para quien configura —lleva el mensaje real del proveedor— y no un error de
    la petición.
    """
    try:
        ok, detalle = conexion_service.probar(db, conexion_id, actor=usuario)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"ok": ok, "detalle": detalle}


@router.post("/{conexion_id}/activar", summary="Activar (una por capacidad)")
def activar(conexion_id: int, db: Session = Depends(get_db), usuario: Usuario = RequireAdmin):
    try:
        c = conexion_service.activar(db, conexion_id, actor=usuario)
    except conexion_service.ConexionNoVerificada as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return conexion_service.a_dict(c)
