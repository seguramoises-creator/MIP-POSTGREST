"""
SCGCPR — Router principal v1: registra todos los sub-routers.
"""
from fastapi import APIRouter

from app.api.v1.routers.auth          import router as auth_router
from app.api.v1.routers.admin         import router as admin_router
from app.api.v1.routers.productividad import router as productividad_router
from app.api.v1.routers.comercial     import router as comercial_router
from app.api.v1.routers.coaching      import router as coaching_router
from app.api.v1.routers.capacitacion  import router as capacitacion_router
from app.api.v1.routers.ranking       import router as ranking_router
from app.api.v1.routers.reconocimiento import router as reconocimiento_router
from app.api.v1.routers.dashboard     import router as dashboard_router
from app.api.v1.routers.etl           import router as etl_router
from app.api.v1.routers.dims          import router as dims_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(productividad_router)
api_router.include_router(comercial_router)
api_router.include_router(coaching_router)
api_router.include_router(capacitacion_router)
api_router.include_router(ranking_router)
api_router.include_router(reconocimiento_router)
api_router.include_router(dashboard_router)
api_router.include_router(etl_router)
api_router.include_router(dims_router)
