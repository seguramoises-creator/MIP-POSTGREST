"""
SCGCPR — Utilidad de Paginación
FIX W-03: Todos los endpoints LIST usan paginación para evitar retornar
          tablas completas (500 RMs × 13 ciclos × 8 KPIs = 52,000 filas).

Uso en routers:
    from app.core.pagination import PaginationParams, paginate_query

    @router.get("", response_model=PagedResponse[MiSchema])
    def list_items(
        params: PaginationParams = Depends(),
        db: Session = Depends(get_db),
    ):
        q = db.query(MiModelo)
        return paginate_query(q, params)
"""
from typing import TypeVar, Generic, List, Type, Any
from fastapi import Query
from sqlalchemy.orm import Query as SAQuery
from pydantic import BaseModel

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE     = 500


class PaginationParams:
    """Dependency reutilizable para parámetros de paginación."""

    def __init__(
        self,
        page: int  = Query(1,    ge=1,              description="Número de página (1-based)"),
        size: int  = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE,
                           description=f"Registros por página (máx {MAX_PAGE_SIZE})"),
    ) -> None:
        self.page   = page
        self.size   = size
        self.offset = (page - 1) * size


class PagedResult(BaseModel, Generic[T]):
    """Respuesta paginada estándar."""
    items: List[T]
    total: int
    page:  int
    size:  int
    pages: int

    model_config = {"arbitrary_types_allowed": True}


def paginate_query(query: SAQuery, params: PaginationParams) -> dict:
    """
    Aplica paginación a una consulta SQLAlchemy.
    Retorna dict compatible con PagedResult.
    """
    total  = query.count()
    items  = query.offset(params.offset).limit(params.size).all()
    pages  = max(1, -(-total // params.size))  # ceil division

    return {
        "items": items,
        "total": total,
        "page":  params.page,
        "size":  params.size,
        "pages": pages,
    }


def paginate_list(items_all: list, params: PaginationParams) -> dict:
    """
    Versión para listas Python ya cargadas en memoria
    (cuando el query tiene GROUP BY o lógica compleja).
    """
    total = len(items_all)
    start = params.offset
    end   = start + params.size
    pages = max(1, -(-total // params.size))

    return {
        "items": items_all[start:end],
        "total": total,
        "page":  params.page,
        "size":  params.size,
        "pages": pages,
    }
