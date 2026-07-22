"""
SCGCPR — Router principal v1: registra todos los sub-routers.
"""
from fastapi import APIRouter

from app.api.v1.routers.setup         import router as setup_router
from app.api.v1.routers.auth          import router as auth_router
from app.api.v1.routers.admin         import router as admin_router
from app.api.v1.routers.productividad import router as productividad_router
from app.api.v1.routers.coaching      import router as coaching_router
from app.api.v1.routers.ranking       import router as ranking_router
from app.api.v1.routers.reconocimiento import router as reconocimiento_router
from app.api.v1.routers.dashboard     import router as dashboard_router
from app.api.v1.routers.etl           import router as etl_router
from app.api.v1.routers.dims          import router as dims_router
from app.api.v1.routers.exportacion   import router as exportacion_router
from app.api.v1.routers.lsii          import router as lsii_router
from app.api.v1.routers.cobertura_predictiva import router as cobertura_predictiva_router
from app.api.v1.routers.categorizacion import router as categorizacion_router
from app.api.v1.routers.examenes      import router as examenes_router
from app.api.v1.routers.examenes      import intentos_router
from app.api.v1.routers.visita        import router as visita_router
from app.api.v1.routers.coaching_more import router as coaching_more_router
from app.api.v1.routers.maestro_medicos import router as maestro_medicos_router
from app.api.v1.routers.authz         import router as authz_router
from app.api.v1.routers.farmacias     import router as farmacias_router

api_router = APIRouter()

api_router.include_router(setup_router)  # primer arranque — sin auth
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(productividad_router)
api_router.include_router(cobertura_predictiva_router)  # sustituye a /comercial (ver comercial.py, no registrado)
api_router.include_router(coaching_router)
api_router.include_router(categorizacion_router)  # sustituye a /capacitacion (ver capacitacion.py, no registrado)
api_router.include_router(ranking_router)
api_router.include_router(reconocimiento_router)
api_router.include_router(dashboard_router)
api_router.include_router(etl_router)
api_router.include_router(dims_router)
api_router.include_router(exportacion_router)
api_router.include_router(lsii_router)
api_router.include_router(examenes_router)
api_router.include_router(intentos_router)
api_router.include_router(visita_router)  # Módulo de Visita Médica (esquema Visita)
api_router.include_router(coaching_more_router)  # Coaching MORE (esquema coaching)
api_router.include_router(maestro_medicos_router)  # Maestro de Médicos (Config.DIM_Medico)
api_router.include_router(authz_router)  # RBAC Fase 1: contrato de autorizacion (/authz/me/permisos)
api_router.include_router(farmacias_router)  # Módulo de Farmacias (Config.DIM_Farmacia / Visita.*)
