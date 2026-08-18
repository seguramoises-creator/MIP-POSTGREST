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


def exigir_gestion_alcance(db: Session, actor, paises_objetivo: set[str] | None,
                           paises_otorgados: list[str] | None = None) -> None:
    """Guard de las rutas que ADMINISTRAN la frontera misma (asignar países a un
    usuario, líneas a un gerente).

    Es distinto de `exigir_pais` y por eso no se reusa aquel: las demás rutas LEEN
    `FACT_UsuarioPais` como dato de entrada; estas lo ESCRIBEN. Mientras estuvieran
    sin guard, blindar las otras veinte no servía de nada — quien quisiera saltarse
    el límite no necesitaba encontrar un hueco, solo ampliarse el suyo y usar las
    rutas ya cerradas con total legitimidad.

    `paises_objetivo` = los países que hoy alcanza la entidad que se va a modificar
    (`None` o vacío = la entidad no tiene restricción, es decir, alcanza TODOS).
    `paises_otorgados` = el conjunto que se pretende fijar (`None` en las lecturas).

    Reglas, en orden:
      1. Un actor SIN restricción (`paises_visibles` → `None`) pasa: es el superadmin
         global y no hay nada que acotar.
      2. Nadie otorga lo que no tiene. **La lista vacía es el caso peligroso**: por
         convención del spec §3 significa "todos los países", así que un ADMIN acotado
         a DO que se fije `[]` a sí mismo quedaba sin restricción. Es la escalada más
         corta que existía y se rechaza explícitamente, no por caer en la resta de
         conjuntos (donde `set() - permitidos` es vacío y habría pasado).
      3. La entidad destino debe estar DENTRO del alcance del actor. Sin esto, un ADMIN
         de DO podía re-acotar a un usuario de GT — no se sube sus propios permisos,
         pero manipula a alguien que no le corresponde. Una entidad sin restricción
         (que ve todo) queda fuera del alcance de cualquier actor restringido.

    Consecuencia asumida: un ADMIN acotado NO puede asignar países a un usuario nuevo
    (nace sin filas = ve todo, y la regla 3 lo deja fuera). Es deliberado — la gestión
    de privilegios se equivoca del lado de negar; para eso está el ADMIN global.
    """
    permitidos = paises_visibles(db, actor)
    if permitidos is None:
        return

    if paises_otorgados is not None:
        if not paises_otorgados:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado: no puedes otorgar acceso a todos los países")
        if set(paises_otorgados) - permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado: no puedes otorgar países fuera de tu alcance")

    if not paises_objetivo or (set(paises_objetivo) - permitidos):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado sobre ese usuario")


def PaisPermitido(
    pais_codigo: str | None = Query(None, description="Código de país, ej. DO"),
    user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> str | None:
    """Dependency que sustituye a `pais_codigo: str | None = Query(None)` en un
    endpoint: lee el parámetro, lo valida contra los países del usuario y lo
    devuelve. Migrar un endpoint es cambiar la declaración de su parámetro.

    (Minor de revisión, ago-2026): la descripción de Swagger es genérica a propósito —
    varios endpoints cableados a esta dependency traían su propio texto (p.ej. "Código de
    país, ej. DO"); al sustituir `Query(None, description=...)` por esta dependency se
    perdía. Mantener aquí un texto razonable por defecto evita que Swagger quede sin
    descripción en ninguno de los sitios donde se usa."""
    exigir_pais(db, user, pais_codigo)
    return pais_codigo
