"""
SCGCPR — Schemas Pydantic comunes (respuestas genéricas, paginación)
"""
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class Msg(BaseModel):
    message: str


class PagedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


class TokenData(BaseModel):
    sub: Optional[str] = None
