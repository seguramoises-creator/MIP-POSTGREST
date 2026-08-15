"""Frontera por país.

Vive aparte de `scope.py` porque NO es un alcance. Los alcances responden a "¿de
cuáles representantes?"; el país a "¿de cuál operación?". Son ortogonales, y
meterlo dentro de `Alcance` obligaría a multiplicar cada celda de la matriz por
cada país (spec §2).
"""
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.authz.scope import paises_visibles
from app.core.deps import get_current_active_user
from app.db.database import get_db
from app.models.usuario import Usuario


def exigir_pais(db: Session, user, pais_codigo: str | None) -> None:
    """403 si el usuario no puede operar sobre ese país. `None` no se valida.

    El mensaje NO enumera los países permitidos ni distingue "no autorizado" de
    "no existe": ambas cosas dejarían mapear la operación desde fuera.
    """
    if not pais_codigo:
        return
    permitidos = paises_visibles(db, user)
    if permitidos is None or pais_codigo in permitidos:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="No autorizado sobre ese país")


def PaisPermitido(
    pais_codigo: str | None = Query(None),
    user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> str | None:
    """Dependency que sustituye a `pais_codigo: str | None = Query(None)` en un
    endpoint: lee el parámetro, lo valida contra los países del usuario y lo
    devuelve. Migrar un endpoint es cambiar la declaración de su parámetro."""
    exigir_pais(db, user, pais_codigo)
    return pais_codigo
