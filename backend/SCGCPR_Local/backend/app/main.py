"""
SCGCPR — Punto de entrada principal FastAPI
Sistema Corporativo de Gestión Comercial, Productividad, Capacitación y Reconocimiento
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.audit_middleware import AuditMiddleware   # FIX C-07
from app.db.database import check_db_connection
from app.api.v1.router import api_router


# ── Inicialización ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup y shutdown del servidor."""
    setup_logging()

    from loguru import logger
    logger.info(f"Iniciando {settings.APP_NAME} v{settings.APP_VERSION} [{settings.APP_ENV}]")

    # Crear directorios necesarios
    for d in [settings.ETL_UPLOAD_DIR, settings.ETL_PROCESSED_DIR,
              settings.ETL_ERROR_DIR, settings.REPORTS_DIR,
              os.path.dirname(settings.LOG_FILE)]:
        os.makedirs(d, exist_ok=True)

    # Verificar conexión a BD
    if check_db_connection():
        logger.info("Base de datos: CONECTADA")
    else:
        logger.warning("Base de datos: NO disponible — verificar configuración")

    yield  # Servidor corriendo

    logger.info(f"Apagando {settings.APP_NAME}...")


# ── Aplicación FastAPI ────────────────────────────────────────────────────────

app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description="""
## Sistema Corporativo de Gestión Comercial, Productividad, Capacitación y Reconocimiento

API REST empresarial multipaís para la gestión integral del desempeño comercial.

### Módulos
- **Auth** — Autenticación JWT y gestión de sesiones
- **Productividad** — KPIs de cobertura y promedio diario
- **Comercial** — Ventas y EVO IR
- **Coaching** — Acompañamiento gerencial
- **Capacitación** — Cursos, certificaciones y evaluaciones
- **Ranking** — Rankings mensual, trimestral, anual y regional
- **Reconocimiento** — Premios y certificados corporativos
- **Dashboard** — KPIs ejecutivos por rol
- **ETL** — Carga automatizada de archivos Excel
- **Admin** — Gestión de catálogos y configuración
    """,
    version=settings.APP_VERSION,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
    lifespan=lifespan,
    contact={"name": "SCGCPR Team", "email": "soporte@empresa.com"},
    license_info={"name": "Propietario"},
)


# ── Middlewares ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
)

if settings.is_production:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*.empresa.com", "localhost"])

# FIX C-07: Auditoría global — registra POST/PUT/PATCH/DELETE en FACT_Auditoria
app.add_middleware(AuditMiddleware)


# ── Middleware de Request ID ──────────────────────────────────────────────────

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    import uuid
    request_id = str(uuid.uuid4())[:8]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Middleware de Auditoría HTTP ──────────────────────────────────────────────

@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    from loguru import logger
    logger.debug(f"{request.method} {request.url.path} — {request.client.host if request.client else 'unknown'}")
    response = await call_next(request)
    return response


# ── Manejo de errores globales ────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Error de validación",
            "detalle": exc.errors(),
            "body": str(exc.body)[:500] if exc.body else None,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    from loguru import logger
    logger.error(f"Error no manejado en {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Error interno del servidor", "detalle": str(exc) if settings.DEBUG else "Contacte al administrador"},
    )


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(api_router, prefix=settings.API_PREFIX)


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["Sistema"], summary="Estado del servidor")
def health_check():
    """Endpoint de salud para balanceadores de carga y monitoreo."""
    db_ok = check_db_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "database": "connected" if db_ok else "disconnected",
    }


@app.get("/", tags=["Sistema"], include_in_schema=False)
def root():
    return {"message": f"Bienvenido a {settings.APP_NAME} v{settings.APP_VERSION}"}
