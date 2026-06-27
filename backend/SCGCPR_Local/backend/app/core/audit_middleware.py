"""
SCGCPR — Middleware de Auditoría Corporativa Global
FIX C-07: Registra automáticamente en FACT_Auditoria todos los eventos
          de escritura (POST/PUT/PATCH/DELETE) en cualquier router,
          eliminando la dependencia del enfoque manual por router.

Eventos capturados:
  - Método HTTP de escritura con estado 2xx
  - Usuario autenticado (extraído del JWT)
  - IP de origen, User-Agent
  - Módulo y acción inferidos desde la ruta

La auditoría de lectura (GET) NO se registra para evitar ruido.
Los endpoints de health/docs tampoco se registran.
"""
from datetime import datetime, timezone
from typing import Callable

from fastapi import Request, Response
from jose import JWTError
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.security import decode_token

# Rutas que NO se auditan
_RUTAS_EXCLUIDAS = {
    "/health",
    f"{settings.API_PREFIX}/docs",
    f"{settings.API_PREFIX}/redoc",
    f"{settings.API_PREFIX}/openapi.json",
    "/",
}

# Métodos que generan entrada de auditoría
_METODOS_AUDITABLES = {"POST", "PUT", "PATCH", "DELETE"}


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware que registra eventos de escritura en FACT_Auditoria.
    Se monta en main.py DESPUÉS del CORSMiddleware.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Solo auditar métodos de escritura con respuestas exitosas
        if (
            request.method not in _METODOS_AUDITABLES
            or request.url.path in _RUTAS_EXCLUIDAS
            or response.status_code >= 400
        ):
            return response

        # Extraer usuario del JWT (sin romper el request si no hay token)
        usuario_id = None
        username   = None
        rol        = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload    = decode_token(token)
                usuario_id = int(payload.get("sub", 0)) or None
            except (JWTError, ValueError):
                pass

        # Inferir módulo y acción desde la ruta
        path_parts = [p for p in request.url.path.split("/") if p]
        modulo = _inferir_modulo(path_parts)
        accion = _inferir_accion(request.method, path_parts)

        # Guardar en BD en background para no bloquear la respuesta
        try:
            _guardar_auditoria_background(
                request      = request,
                usuario_id   = usuario_id,
                accion       = accion,
                modulo       = modulo,
                status_code  = response.status_code,
            )
        except Exception as e:
            logger.warning(f"AuditMiddleware: error registrando evento — {e}")

        return response


def _inferir_modulo(path_parts: list) -> str:
    """Mapea segmentos de URL a nombres de módulo corporativo."""
    mapa = {
        "auth":           "AUTH",
        "admin":          "ADMIN",
        "productividad":  "PRODUCTIVIDAD",
        "comercial":      "COMERCIAL",
        "coaching":       "COACHING",
        "capacitacion":   "CAPACITACION",
        "ranking":        "RANKING",
        "reconocimiento": "RECONOCIMIENTO",
        "dashboard":      "DASHBOARD",
        "etl":            "ETL",
    }
    for part in path_parts:
        if part in mapa:
            return mapa[part]
    return "SISTEMA"


def _inferir_accion(method: str, path_parts: list) -> str:
    """Convierte método HTTP en nombre de acción de auditoría."""
    mapa_method = {
        "POST":   "CREATE",
        "PUT":    "UPDATE",
        "PATCH":  "UPDATE",
        "DELETE": "DELETE",
    }
    base = mapa_method.get(method, method)

    # Refinar por sub-ruta
    if "generar" in path_parts:
        return "GENERAR"
    if "cargar" in path_parts:
        return "ETL_CARGA"
    if "reprocesar" in path_parts:
        return "ETL_REPROCESAR"
    if "cerrar" in path_parts:
        return "CERRAR_CICLO"
    if "certificado" in path_parts:
        return "GENERAR_CERTIFICADO"

    return base


def _guardar_auditoria_background(
    request: Request,
    usuario_id: int | None,
    accion: str,
    modulo: str,
    status_code: int,
) -> None:
    """
    Guarda el registro de auditoría usando una sesión propia de BD
    para no interferir con la sesión HTTP ya cerrada.
    """
    from app.db.database import SessionLocal
    from app.models.hechos import Auditoria

    db = SessionLocal()
    try:
        db.add(Auditoria(
            fecha_hora  = datetime.now(timezone.utc),
            usuario_id  = usuario_id,
            accion      = accion,
            modulo      = modulo,
            tabla       = None,
            ip_address  = request.client.host if request.client else None,
            user_agent  = request.headers.get("user-agent"),
            exitoso     = status_code < 400,
            detalle     = f"{request.method} {request.url.path} → {status_code}",
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"AuditMiddleware: error al guardar en BD — {e}")
    finally:
        db.close()
