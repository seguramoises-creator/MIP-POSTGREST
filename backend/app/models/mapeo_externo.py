"""Equivalencias entre los códigos de Laboratorio Mallén y los ids de VISTA.

POR QUÉ UNA TABLA Y NO UNA COLUMNA `codigo_externo` EN CADA DIM_*
------------------------------------------------------------------
1. No toca ninguna tabla interna existente. Producción es un piloto con datos
   reales; añadir columnas a nueve catálogos vivos es riesgo que no hace falta
   correr.
2. Funciona igual para las dimensiones que tienen código propio (DIM_RM) y para
   las que no (DIM_Especialidad se identifica por nombre, DIM_Ciclo por
   país+año+número, DIM_Farmacia no tiene código).
3. Deja el mapeo visible y corregible en UN solo sitio cuando algo se empareje
   mal, en vez de repartido por nueve tablas.
4. El identificador de un tercero no queda al alcance del resto del sistema,
   que podría acoplarse a él por accidente.

`id_interno` NO lleva clave foránea: apunta a nueve tablas distintas según
`entidad`. La integridad la mantiene el servicio, y un mapeo cuyo registro
interno fue borrado a mano se reconstruye solo (ver `integracion_mapeo`).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

ENT_PAIS = "pais"
ENT_LINEA = "linea"
ENT_GERENTE = "gerente"
ENT_REPRESENTANTE = "representante"
ENT_CICLO = "ciclo"
ENT_ESPECIALIDAD = "especialidad"
ENT_MEDICO = "medico"
ENT_FARMACIA = "farmacia"
ENT_PRODUCTO = "producto"

#: Módulo IR (Close-Up). NO entran en `ENTIDADES`: esa tupla es el orden de
#: sincronización de las nueve dimensiones de `integracion_dimensiones_service`,
#: que CREAN el registro interno cuando falta. Los puentes del IR solo enlazan
#: contra lo que ya existe (ver `integracion_ir_service`), así que meterlos ahí
#: los haría correr con una semántica que no es la suya.
ENT_MEDICO_IR = "medico_ir"
ENT_PRODUCTO_IR = "producto_ir"
ENT_PERIODO_IR = "periodo_ir"

#: En orden de dependencia: cada una resuelve claves foráneas contra las
#: anteriores, así que sincronizarlas en otro orden dejaría referencias sueltas.
ENTIDADES: tuple[str, ...] = (
    ENT_PAIS, ENT_LINEA, ENT_GERENTE, ENT_REPRESENTANTE, ENT_CICLO,
    ENT_ESPECIALIDAD, ENT_MEDICO, ENT_FARMACIA, ENT_PRODUCTO,
)


class MapeoExterno(Base):
    """Un código de Mallén ↔ un id de VISTA, por entidad y país."""
    __tablename__ = "MapeoExterno"
    __table_args__ = (
        UniqueConstraint("entidad", "pais_codigo", "codigo_externo",
                         name="UQ_MapeoExterno_clave"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entidad: Mapped[str] = mapped_column(String(30), nullable=False)
    # Cadena vacía —no NULL— para las entidades sin país (especialidad): en un
    # UNIQUE de PostgreSQL dos NULL se consideran distintos, así que permitiría
    # duplicar el mismo código.
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    codigo_externo: Mapped[str] = mapped_column(String(60), nullable=False)
    id_interno: Mapped[int] = mapped_column(Integer, nullable=False)
    sincronizado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
