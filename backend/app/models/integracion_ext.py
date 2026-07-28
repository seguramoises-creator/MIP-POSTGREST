"""VISTA — Capa de recepción de datos de la integración (esquema `ext`).

Es el área donde Laboratorio Mallén ESCRIBE y VISTA LEE. Implementa el
"Requerimiento de Datos · VISTA · Laboratorios Mallén" (v1.0, 25-jul-2026):
22 tablas —nueve dimensiones, cinco del módulo IR y ocho de hechos—, sus claves
foráneas y sus índices de unicidad.

Dirección de la conexión (§8): Mallén empuja hacia estas tablas por ODBC.
VISTA nunca se conecta a su SQL Server. El usuario `mallen_etl` solo alcanza
este esquema, y sin permiso de DELETE: las correcciones se hacen reenviando el
registro con el mismo `origen_id`, nunca borrando, para no perder trazabilidad.

DOS DECISIONES QUE NO SON OBVIAS LEYENDO EL DOCUMENTO
-----------------------------------------------------
1. **Los nombres van en minúsculas.** El documento crea las tablas sin comillas
   (`CREATE TABLE ext.DimPais`), y PostgreSQL pliega ese identificador a
   `ext.dimpais`; pero luego las claves foráneas y los índices sí las llevan
   (`ext."DimPais"`), que exige el nombre en mayúsculas y minúsculas exactas.
   Corridas en ese orden, las sentencias de §6.4 fallan con «no existe la
   relación». Se unificó SIN comillas —minúsculas— y no al revés porque es lo
   que menos ata al integrador: escriba `ext.DimPais`, `ext.dimpais` o
   `EXT.DIMPAIS`, las tres funcionan. Con el nombre entrecomillado, en cambio,
   toda referencia tendría que reproducir las mayúsculas al pie de la letra.
   Es lo contrario a la convención interna de VISTA (`"Config"."DIM_Pais"`),
   a propósito: esto es un contrato con un tercero, no una tabla nuestra.

2. **No hay CHECK sobre los campos acotados** (`tipo_visita`, `frecuencia_objetivo`,
   `prioridad`, `estado`). Tentador, porque §11.6 advierte que son los campos que
   rompen indicadores en silencio, pero un CHECK rechaza el INSERT y §7.1 pide
   justo lo contrario: «las inconsistencias se registran sin detener el lote
   completo». El dominio se valida en el paso de Validación, que anota la fila
   inconsistente y deja pasar el resto del lote.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR, BigInteger, Boolean, Date, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, Numeric, PrimaryKeyConstraint, String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

ESQUEMA = "ext"


# ===========================================================================
# §3.1 — Nueve dimensiones que gobiernan los movimientos
# ===========================================================================

class ExtDimPais(Base):
    """Raíz del modelo: VISTA es multipaís y aísla la información entre países."""
    __tablename__ = "dimpais"
    __table_args__ = {"schema": ESQUEMA}

    pais_codigo: Mapped[str] = mapped_column(String(10), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    moneda: Mapped[str | None] = mapped_column(String(10))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimLinea(Base):
    """Líneas de producto o fuerzas de venta. Segmentan los ocho indicadores."""
    __tablename__ = "dimlinea"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "linea_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        {"schema": ESQUEMA},
    )

    linea_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimGerente(Base):
    """Gerentes. `tipo` distingue DISTRITO, MARCA o REGIONAL; el acompañamiento
    de visitas —y por tanto EVAL_COACHING— corresponde a los de DISTRITO."""
    __tablename__ = "dimgerente"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "gerente_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "linea_codigo"],
                             [f"{ESQUEMA}.dimlinea.pais_codigo", f"{ESQUEMA}.dimlinea.linea_codigo"]),
        {"schema": ESQUEMA},
    )

    gerente_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    linea_codigo: Mapped[str | None] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimRepresentante(Base):
    """Entidad sobre la que se calculan LOS OCHO INDICADORES: cada resultado,
    ranking y reconocimiento se atribuye a un representante.

    `gerente_codigo` es opcional en el esquema pero indispensable en la práctica:
    sin él no hay agregación por equipo ni coaching (§11.3)."""
    __tablename__ = "dimrepresentante"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "rm_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "linea_codigo"],
                             [f"{ESQUEMA}.dimlinea.pais_codigo", f"{ESQUEMA}.dimlinea.linea_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "gerente_codigo"],
                             [f"{ESQUEMA}.dimgerente.pais_codigo", f"{ESQUEMA}.dimgerente.gerente_codigo"]),
        {"schema": ESQUEMA},
    )

    rm_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    linea_codigo: Mapped[str | None] = mapped_column(String(30))
    gerente_codigo: Mapped[str | None] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    cedula: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(200))
    zona: Mapped[str | None] = mapped_column(String(100))
    fecha_ingreso: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimCiclo(Base):
    """Período de medición de los ocho indicadores.

    `dias_laborables` es el denominador de PROM_DIARIO: sin ese dato el
    indicador no se calcula (§11.3)."""
    __tablename__ = "dimciclo"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "ciclo_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        {"schema": ESQUEMA},
    )

    ciclo_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre: Mapped[str | None] = mapped_column(String(100))
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    dias_laborables: Mapped[int] = mapped_column(Integer, nullable=False)
    cerrado: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimEspecialidad(Base):
    """Catálogo general, sin país: es el único maestro compartido entre países."""
    __tablename__ = "dimespecialidad"
    __table_args__ = {"schema": ESQUEMA}

    especialidad_codigo: Mapped[str] = mapped_column(String(30), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimMedico(Base):
    """Maestro de médicos del país, independiente de a quién esté asignado en un
    ciclo (esa asignación vive en `panelmedico`).

    `exequatur` es la llave que une este maestro con el prescriptor de Close-Up
    (§3.2). Su índice único es PARCIAL —solo cuando está informado— para no
    bloquear la carga del maestro mientras el dato falte en algunos médicos."""
    __tablename__ = "dimmedico"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "medico_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        ForeignKeyConstraint(["especialidad_codigo"],
                             [f"{ESQUEMA}.dimespecialidad.especialidad_codigo"]),
        Index("ux_dm_exequatur", "pais_codigo", "exequatur",
              unique=True, postgresql_where="exequatur IS NOT NULL"),
        {"schema": ESQUEMA},
    )

    medico_codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    especialidad_codigo: Mapped[str | None] = mapped_column(String(30))
    exequatur: Mapped[str | None] = mapped_column(String(50))
    centro_trabajo: Mapped[str | None] = mapped_column(String(200))
    provincia: Mapped[str | None] = mapped_column(String(120))
    municipio: Mapped[str | None] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimFarmacia(Base):
    """Maestro de farmacias del país. Denominador de COB_FARMACIAS junto con
    `targetfarmacia`."""
    __tablename__ = "dimfarmacia"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "farmacia_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        {"schema": ESQUEMA},
    )

    farmacia_codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(40))
    provincia: Mapped[str | None] = mapped_column(String(120))
    municipio: Mapped[str | None] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimProducto(Base):
    """Catálogo de productos de Laboratorio Mallén.

    `codigo_closeup` es la homologación con la codificación de Close-Up; es el
    pendiente 5 de §10 y hoy puede venir vacío."""
    __tablename__ = "dimproducto"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "producto_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "linea_codigo"],
                             [f"{ESQUEMA}.dimlinea.pais_codigo", f"{ESQUEMA}.dimlinea.linea_codigo"]),
        {"schema": ESQUEMA},
    )

    producto_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    linea_codigo: Mapped[str | None] = mapped_column(String(30))
    presentacion: Mapped[str | None] = mapped_column(String(120))
    codigo_closeup: Mapped[str | None] = mapped_column(String(50))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


# ===========================================================================
# §3.2 — Cinco dimensiones del módulo IR (codificación de Close-Up)
# ===========================================================================

class ExtDimPeriodoIR(Base):
    """Equivalencia entre el calendario MENSUAL de Close-Up y los ciclos de
    Mallén. Sin ella no se puede asignar la prescripción al ciclo correcto."""
    __tablename__ = "dimperiodoir"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "periodo_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "ciclo_codigo"],
                             [f"{ESQUEMA}.dimciclo.pais_codigo", f"{ESQUEMA}.dimciclo.ciclo_codigo"]),
        {"schema": ESQUEMA},
    )

    periodo_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    ciclo_codigo: Mapped[str | None] = mapped_column(String(20))
    cerrado: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimMercadoIR(Base):
    """Mercados o clases terapéuticas de Close-Up. Sin país: la clasificación
    terapéutica es de la fuente, no de la operación."""
    __tablename__ = "dimmercadoir"
    __table_args__ = {"schema": ESQUEMA}

    mercado_codigo: Mapped[str] = mapped_column(String(40), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    nivel: Mapped[str | None] = mapped_column(String(30))
    mercado_padre: Mapped[str | None] = mapped_column(String(40))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimProductoIR(Base):
    """Productos en la codificación de Close-Up, INCLUIDOS los de la competencia.

    `producto_codigo` guarda la equivalencia con el catálogo de Mallén y vive
    aquí, no repetido en cada fila del hecho. Los productos de la competencia se
    cargan con esa equivalencia vacía: hacen falta para medir participación de
    mercado (§11.8)."""
    __tablename__ = "dimproductoir"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "producto_ir_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        ForeignKeyConstraint(["mercado_codigo"], [f"{ESQUEMA}.dimmercadoir.mercado_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "producto_codigo"],
                             [f"{ESQUEMA}.dimproducto.pais_codigo", f"{ESQUEMA}.dimproducto.producto_codigo"]),
        {"schema": ESQUEMA},
    )

    producto_ir_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    laboratorio: Mapped[str | None] = mapped_column(String(150))
    mercado_codigo: Mapped[str | None] = mapped_column(String(40))
    molecula: Mapped[str | None] = mapped_column(String(200))
    presentacion: Mapped[str | None] = mapped_column(String(120))
    producto_codigo: Mapped[str | None] = mapped_column(String(50))
    es_propio: Mapped[bool] = mapped_column(Boolean, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimMedicoIR(Base):
    """Prescriptores en la codificación de Close-Up. Es lo que conecta la receta
    con el panel médico del representante.

    `exequatur` es OBLIGATORIO y único por país: es el único identificador que
    existe en los dos sistemas. Una receta cuyo prescriptor no se pueda enlazar
    se cuenta para el mercado pero no se atribuye a ningún representante (§3.2)."""
    __tablename__ = "dimmedicoir"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "medico_ir_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        ForeignKeyConstraint(["especialidad_codigo"],
                             [f"{ESQUEMA}.dimespecialidad.especialidad_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "territorio_codigo"],
                             [f"{ESQUEMA}.dimterritorio.pais_codigo", f"{ESQUEMA}.dimterritorio.territorio_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "medico_codigo"],
                             [f"{ESQUEMA}.dimmedico.pais_codigo", f"{ESQUEMA}.dimmedico.medico_codigo"]),
        Index("ux_dmir_exequatur", "pais_codigo", "exequatur", unique=True),
        {"schema": ESQUEMA},
    )

    medico_ir_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    exequatur: Mapped[str] = mapped_column(String(50), nullable=False)
    medico_codigo: Mapped[str | None] = mapped_column(String(40))
    especialidad_codigo: Mapped[str | None] = mapped_column(String(30))
    territorio_codigo: Mapped[str | None] = mapped_column(String(40))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtDimTerritorio(Base):
    """Territorios geográficos, para el análisis territorial del IR."""
    __tablename__ = "dimterritorio"
    __table_args__ = (
        PrimaryKeyConstraint("pais_codigo", "territorio_codigo"),
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        {"schema": ESQUEMA},
    )

    territorio_codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    provincia: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


# ===========================================================================
# §3.3 — Ocho tablas de movimientos
# ===========================================================================

class ExtControlCarga(Base):
    """Un registro por lote enviado. Es lo que permite reconciliar y repetir una
    carga con seguridad.

    `estado` lo abre Mallén en RECIBIDO; VISTA lo mueve a VALIDADO, INTEGRADO o
    RECHAZADO, y deja el detalle en `mensaje` (§7.1)."""
    __tablename__ = "controlcarga"
    __table_args__ = (
        ForeignKeyConstraint(["pais_codigo"], [f"{ESQUEMA}.dimpais.pais_codigo"]),
        {"schema": ESQUEMA},
    )

    lote_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    sistema_origen: Mapped[str] = mapped_column(String(30), nullable=False)
    modulo: Mapped[str] = mapped_column(String(40), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    ciclo_codigo: Mapped[str | None] = mapped_column(String(20))
    periodo: Mapped[str | None] = mapped_column(String(20))
    fecha_extraccion: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_recepcion: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    filas_enviadas: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    mensaje: Mapped[str | None] = mapped_column(String(500))


class ExtPanelMedico(Base):
    """Panel del representante: qué médicos tiene asignados en cada ciclo.

    Es el DENOMINADOR de la cobertura médica. El detalle de visitas solo aporta
    el numerador; sin esta tabla los cuatro indicadores de cobertura se quedan
    sin base de cálculo (§11.4).

    `prioridad` (TOP/REGULAR) es obligatoria en todas las filas: es la regla de
    negocio nueva de §3.4."""
    __tablename__ = "panelmedico"
    __table_args__ = (
        ForeignKeyConstraint(["lote_id"], [f"{ESQUEMA}.controlcarga.lote_id"]),
        ForeignKeyConstraint(["pais_codigo", "ciclo_codigo"],
                             [f"{ESQUEMA}.dimciclo.pais_codigo", f"{ESQUEMA}.dimciclo.ciclo_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "rm_codigo"],
                             [f"{ESQUEMA}.dimrepresentante.pais_codigo", f"{ESQUEMA}.dimrepresentante.rm_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "medico_codigo"],
                             [f"{ESQUEMA}.dimmedico.pais_codigo", f"{ESQUEMA}.dimmedico.medico_codigo"]),
        Index("ux_tm_clave", "pais_codigo", "ciclo_codigo", "rm_codigo", "medico_codigo", unique=True),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    ciclo_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    rm_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    medico_codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    frecuencia_objetivo: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    prioridad: Mapped[str] = mapped_column(String(10), nullable=False)
    categoria: Mapped[str | None] = mapped_column(CHAR(1))
    visitas_programadas: Mapped[int | None] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtFactVisitaMedico(Base):
    """La tabla más importante del contrato: de ella salen cuatro de los ocho
    indicadores.

    `tipo_visita` (V=visita, R=revisita) y `acompanado` son dos de los cinco
    campos que rompen indicadores en silencio (§11.6)."""
    __tablename__ = "factvisitamedico"
    __table_args__ = (
        ForeignKeyConstraint(["lote_id"], [f"{ESQUEMA}.controlcarga.lote_id"]),
        ForeignKeyConstraint(["pais_codigo", "ciclo_codigo"],
                             [f"{ESQUEMA}.dimciclo.pais_codigo", f"{ESQUEMA}.dimciclo.ciclo_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "rm_codigo"],
                             [f"{ESQUEMA}.dimrepresentante.pais_codigo", f"{ESQUEMA}.dimrepresentante.rm_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "medico_codigo"],
                             [f"{ESQUEMA}.dimmedico.pais_codigo", f"{ESQUEMA}.dimmedico.medico_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "gerente_codigo"],
                             [f"{ESQUEMA}.dimgerente.pais_codigo", f"{ESQUEMA}.dimgerente.gerente_codigo"]),
        Index("ux_fvm_origen", "pais_codigo", "origen_id", unique=True),
        Index("ix_fvm_ciclo_rm", "pais_codigo", "ciclo_codigo", "rm_codigo"),
        Index("ix_fvm_lote", "lote_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origen_id: Mapped[str] = mapped_column(String(60), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    ciclo_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    rm_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    medico_codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    fecha_visita: Mapped[date] = mapped_column(Date, nullable=False)
    tipo_visita: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    ejecutada: Mapped[bool] = mapped_column(Boolean, nullable=False)
    acompanado: Mapped[bool] = mapped_column(Boolean, nullable=False)
    gerente_codigo: Mapped[str | None] = mapped_column(String(30))
    causa_no_visita: Mapped[str | None] = mapped_column(String(80))
    productos: Mapped[str | None] = mapped_column(String(300))


class ExtTargetFarmacia(Base):
    """Universo de farmacias programadas: denominador de COB_FARMACIAS."""
    __tablename__ = "targetfarmacia"
    __table_args__ = (
        ForeignKeyConstraint(["lote_id"], [f"{ESQUEMA}.controlcarga.lote_id"]),
        ForeignKeyConstraint(["pais_codigo", "ciclo_codigo"],
                             [f"{ESQUEMA}.dimciclo.pais_codigo", f"{ESQUEMA}.dimciclo.ciclo_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "rm_codigo"],
                             [f"{ESQUEMA}.dimrepresentante.pais_codigo", f"{ESQUEMA}.dimrepresentante.rm_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "farmacia_codigo"],
                             [f"{ESQUEMA}.dimfarmacia.pais_codigo", f"{ESQUEMA}.dimfarmacia.farmacia_codigo"]),
        Index("ux_tf_clave", "pais_codigo", "ciclo_codigo", "rm_codigo", "farmacia_codigo", unique=True),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    ciclo_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    rm_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    farmacia_codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    visitas_programadas: Mapped[int | None] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtFactVisitaFarmacia(Base):
    """Detalle transaccional de las visitas a farmacia (numerador de COB_FARMACIAS)."""
    __tablename__ = "factvisitafarmacia"
    __table_args__ = (
        ForeignKeyConstraint(["lote_id"], [f"{ESQUEMA}.controlcarga.lote_id"]),
        ForeignKeyConstraint(["pais_codigo", "ciclo_codigo"],
                             [f"{ESQUEMA}.dimciclo.pais_codigo", f"{ESQUEMA}.dimciclo.ciclo_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "rm_codigo"],
                             [f"{ESQUEMA}.dimrepresentante.pais_codigo", f"{ESQUEMA}.dimrepresentante.rm_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "farmacia_codigo"],
                             [f"{ESQUEMA}.dimfarmacia.pais_codigo", f"{ESQUEMA}.dimfarmacia.farmacia_codigo"]),
        Index("ux_fvf_origen", "pais_codigo", "origen_id", unique=True),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origen_id: Mapped[str] = mapped_column(String(60), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    ciclo_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    rm_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    farmacia_codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    fecha_visita: Mapped[date] = mapped_column(Date, nullable=False)
    ejecutada: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ExtFactVenta(Base):
    """Ventas con su cuota. Alimenta VENTAS y los ingresos del ROI de Visita.

    `cuota` es obligatoria junto a la venta: enviar una sin la otra deja el
    indicador sin poder compararse con la meta (§11.6). La dependencia del ROI
    es fácil de omitir al planificar porque el dato no «parece» de Visita (§11.7)."""
    __tablename__ = "factventa"
    __table_args__ = (
        ForeignKeyConstraint(["lote_id"], [f"{ESQUEMA}.controlcarga.lote_id"]),
        ForeignKeyConstraint(["pais_codigo", "ciclo_codigo"],
                             [f"{ESQUEMA}.dimciclo.pais_codigo", f"{ESQUEMA}.dimciclo.ciclo_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "rm_codigo"],
                             [f"{ESQUEMA}.dimrepresentante.pais_codigo", f"{ESQUEMA}.dimrepresentante.rm_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "producto_codigo"],
                             [f"{ESQUEMA}.dimproducto.pais_codigo", f"{ESQUEMA}.dimproducto.producto_codigo"]),
        Index("ux_fv_origen", "pais_codigo", "origen_id", unique=True),
        Index("ix_fv_ciclo_rm", "pais_codigo", "ciclo_codigo", "rm_codigo"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origen_id: Mapped[str] = mapped_column(String(60), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    ciclo_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    rm_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    producto_codigo: Mapped[str | None] = mapped_column(String(50))
    fecha: Mapped[date | None] = mapped_column(Date)
    unidades: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    valor_venta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cuota: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    moneda: Mapped[str | None] = mapped_column(String(10))


class ExtFactEvaluacionConocimiento(Base):
    """Notas externas de evaluación. Solo se usa si Mallén decide enviarlas en
    lugar de aplicar los exámenes dentro de VISTA (opción B, pendiente 2 de §10).
    Con el módulo de exámenes activo esta tabla queda vacía."""
    __tablename__ = "factevaluacionconocimiento"
    __table_args__ = (
        ForeignKeyConstraint(["lote_id"], [f"{ESQUEMA}.controlcarga.lote_id"]),
        ForeignKeyConstraint(["pais_codigo", "ciclo_codigo"],
                             [f"{ESQUEMA}.dimciclo.pais_codigo", f"{ESQUEMA}.dimciclo.ciclo_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "rm_codigo"],
                             [f"{ESQUEMA}.dimrepresentante.pais_codigo", f"{ESQUEMA}.dimrepresentante.rm_codigo"]),
        Index("ux_fec_origen", "pais_codigo", "origen_id", unique=True),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origen_id: Mapped[str] = mapped_column(String(60), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    ciclo_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    rm_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    fecha_evaluacion: Mapped[date] = mapped_column(Date, nullable=False)
    nota: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    tema: Mapped[str | None] = mapped_column(String(200))


class ExtFactPrescripcionDetalle(Base):
    """Detalle de prescripción de Close-Up. ESTRUCTURA PRELIMINAR: se ajusta
    cuando Mallén envíe la definición del indicador y el formato real del archivo
    (pendiente 1 de §10).

    `version_fuente` existe porque Close-Up reenvía períodos ya entregados: sin
    él no se puede auditar qué versión produjo cada cifra."""
    __tablename__ = "factprescripciondetalle"
    __table_args__ = (
        ForeignKeyConstraint(["lote_id"], [f"{ESQUEMA}.controlcarga.lote_id"]),
        ForeignKeyConstraint(["pais_codigo", "periodo_codigo"],
                             [f"{ESQUEMA}.dimperiodoir.pais_codigo", f"{ESQUEMA}.dimperiodoir.periodo_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "producto_ir_codigo"],
                             [f"{ESQUEMA}.dimproductoir.pais_codigo", f"{ESQUEMA}.dimproductoir.producto_ir_codigo"]),
        ForeignKeyConstraint(["mercado_codigo"], [f"{ESQUEMA}.dimmercadoir.mercado_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "territorio_codigo"],
                             [f"{ESQUEMA}.dimterritorio.pais_codigo", f"{ESQUEMA}.dimterritorio.territorio_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "medico_ir_codigo"],
                             [f"{ESQUEMA}.dimmedicoir.pais_codigo", f"{ESQUEMA}.dimmedicoir.medico_ir_codigo"]),
        ForeignKeyConstraint(["pais_codigo", "rm_codigo"],
                             [f"{ESQUEMA}.dimrepresentante.pais_codigo", f"{ESQUEMA}.dimrepresentante.rm_codigo"]),
        Index("ux_fp_origen", "pais_codigo", "origen_id", unique=True),
        Index("ix_fp_periodo", "pais_codigo", "periodo_codigo"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origen_id: Mapped[str] = mapped_column(String(60), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    periodo_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    producto_ir_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    mercado_codigo: Mapped[str | None] = mapped_column(String(40))
    territorio_codigo: Mapped[str | None] = mapped_column(String(40))
    medico_ir_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    rm_codigo: Mapped[str | None] = mapped_column(String(30))
    unidades: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    version_fuente: Mapped[str | None] = mapped_column(String(30))
