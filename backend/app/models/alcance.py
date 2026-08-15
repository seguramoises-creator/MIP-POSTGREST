"""Asignaciones de alcance: países de un usuario y líneas de un gerente.

Viven aparte de `usuario.py` y `dimensiones.py` a propósito: son la unión entre el
motor de autorización y las dimensiones del negocio, y no pertenecen del todo a
ninguno de los dos.
"""
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class UsuarioPais(Base):
    """Países que un usuario puede ver.

    SIN FILAS = TODOS LOS PAÍSES. No es un descuido: es lo que permite activar la
    frontera sin tocar a los usuarios que ya existen. Con filas, el usuario queda
    limitado exactamente a esos países.
    """
    __tablename__ = "FACT_UsuarioPais"
    __table_args__ = (
        UniqueConstraint("usuario_id", "pais_codigo", name="UQ_UsuarioPais"),
        {"schema": "Security"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)


class GerenteLinea(Base):
    """Líneas a cargo de un gerente. Sustituye funcionalmente a `DIM_Gerente.linea_id`,
    que se conserva para no romper lo que ya lo lee."""
    __tablename__ = "DIM_GerenteLinea"
    __table_args__ = (
        UniqueConstraint("gerente_id", "linea_id", name="UQ_GerenteLinea"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gerente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Gerente.id", ondelete="CASCADE"), nullable=False, index=True)
    linea_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False, index=True)
