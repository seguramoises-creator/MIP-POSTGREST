"""Módulo de autorización RBAC/ABAC (Fase 1). Fuente de verdad: matrix.MATRIZ."""
from app.core.authz.constantes import (
    Accion, Alcance, Recurso, RECURSOS, RECURSOS_META, alcance_min,
)
from app.core.authz.matrix import MATRIZ

__all__ = ["Accion", "Alcance", "Recurso", "RECURSOS", "RECURSOS_META", "alcance_min", "MATRIZ"]
