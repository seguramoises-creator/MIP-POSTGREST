"""
SCGCPR — Modelos del Módulo de Exámenes (esquema `exam`).
Módulo autocontenido. Evaluado polimórfico: RM (Config.DIM_RM) o Gerente
(Config.DIM_Gerente). Ver docs/superpowers/specs/2026-06-26-modulo-examenes-design.md
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Integer, String, Boolean, DateTime, Numeric, Text, ForeignKey, CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Examen(Base):
    __tablename__ = "DimExamen"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    producto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nota_minima: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    tiempo_limite_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="borrador")
    fuente: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    rand_preguntas: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rand_opciones: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creado_por_usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=False)
    indicador_codigo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ciclo_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    fecha_publicacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    preguntas: Mapped[list["Pregunta"]] = relationship(
        "Pregunta", back_populates="examen", cascade="all, delete-orphan")


class Pregunta(Base):
    __tablename__ = "DimPregunta"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examen_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.DimExamen.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False, default="multi")
    escenario: Mapped[str | None] = mapped_column(Text, nullable=True)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    explicacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Peso sobre base 100 (estándar VISTA). NULL = reparto automático igual (100 ÷ N).
    # Si se asignan pesos manuales, su suma por examen debe ser 100 (validado al publicar).
    peso: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    examen: Mapped["Examen"] = relationship("Examen", back_populates="preguntas")
    opciones: Mapped[list["PreguntaOpcion"]] = relationship(
        "PreguntaOpcion", back_populates="pregunta", cascade="all, delete-orphan")


class PreguntaOpcion(Base):
    __tablename__ = "DimPreguntaOpcion"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pregunta_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.DimPregunta.id"), nullable=False)
    texto_opcion: Mapped[str] = mapped_column(Text, nullable=False)
    indice_original: Mapped[int] = mapped_column(Integer, nullable=False)
    es_correcta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    pregunta: Mapped["Pregunta"] = relationship("Pregunta", back_populates="opciones")


class AsignacionExamen(Base):
    __tablename__ = "FactAsignacionExamen"
    __table_args__ = (
        CheckConstraint(
            "(evaluado_tipo = 'RM' AND evaluado_rm_id IS NOT NULL AND evaluado_gerente_id IS NULL) OR "
            "(evaluado_tipo = 'GERENTE' AND evaluado_gerente_id IS NOT NULL AND evaluado_rm_id IS NULL)",
            name="CK_AsignacionExamen_evaluado_coherente",
        ),
        {"schema": "exam"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examen_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.DimExamen.id"), nullable=False)
    evaluado_tipo: Mapped[str] = mapped_column(String(10), nullable=False)  # RM | GERENTE
    evaluado_rm_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=True)
    evaluado_gerente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)
    fecha_asignacion: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    fecha_limite: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    intentos_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intentos_usados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estado: Mapped[str] = mapped_column(String(15), nullable=False, default="pendiente")
    notif_activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    intentos: Mapped[list["IntentoExamen"]] = relationship(
        "IntentoExamen", back_populates="asignacion", cascade="all, delete-orphan")


class IntentoExamen(Base):
    __tablename__ = "FactIntentoExamen"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asignacion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.FactAsignacionExamen.id"), nullable=False)
    evaluado_tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    evaluado_rm_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=True)
    evaluado_gerente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    aprobado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tiempo_usado_seg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orden_preguntas_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Persists the per-pregunta option shuffle map so responder can reconstruct
    # indice_presentado → opcion_id without replaying the RNG.
    # Format: { str(pregunta_id): { str(indice_presentado): {"opcion_id": int, "indice_original": int} } }
    mapa_presentacion_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    plataforma: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ip_cliente: Mapped[str | None] = mapped_column(String(50), nullable=True)

    asignacion: Mapped["AsignacionExamen"] = relationship("AsignacionExamen", back_populates="intentos")
    respuestas: Mapped[list["IntentoRespuesta"]] = relationship(
        "IntentoRespuesta", back_populates="intento", cascade="all, delete-orphan")


class IntentoRespuesta(Base):
    __tablename__ = "FactIntentoRespuesta"
    __table_args__ = (
        UniqueConstraint(
            "intento_id", "pregunta_id",
            name="UQ_IntentoRespuesta_intento_pregunta",
        ),
        {"schema": "exam"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intento_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.FactIntentoExamen.id"), nullable=False)
    pregunta_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.DimPregunta.id"), nullable=False)
    opcion_elegida_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("exam.DimPreguntaOpcion.id"), nullable=True)
    indice_opcion_presentada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indice_original_elegido: Mapped[int | None] = mapped_column(Integer, nullable=True)
    es_correcta: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Pregunta abierta / caso-abierto: respuesta de texto libre del evaluado y los
    # puntos otorgados manualmente por el Gerente (NULL = pendiente de calificar).
    respuesta_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    puntos: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    mapa_opciones_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_respuesta: Mapped[datetime] = mapped_column(DateTime, default=_ahora)

    intento: Mapped["IntentoExamen"] = relationship("IntentoExamen", back_populates="respuestas")


class ConsolidacionCiclo(Base):
    """Gate de integración de EVAL_CONOCIMIENTOS por (ciclo, país). Una fila por
    par consolidado; la nota del RM solo llega al KPI cuando esta consolidación
    se ejecuta (ver examen_consolidacion_service)."""
    __tablename__ = "FactConsolidacionCiclo"
    __table_args__ = (
        UniqueConstraint("ciclo_id", "pais_codigo",
                         name="UQ_ConsolidacionCiclo_ciclo_pais"),
        {"schema": "exam"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ciclo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    estado: Mapped[str] = mapped_column(String(15), nullable=False, default="pendiente")
    rms_consolidados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nota_promedio_equipo: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    fecha_consolidacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consolidado_por_usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)


class FuenteIA(Base):
    __tablename__ = "FactFuenteIA"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examen_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("exam.DimExamen.id"), nullable=True)
    tipo_archivo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nombre_archivo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ruta_archivo: Mapped[str | None] = mapped_column(String(400), nullable=True)
    texto_extraido_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_usado: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado_generacion: Mapped[str] = mapped_column(String(15), nullable=False, default="pendiente")
    mensaje_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cargado_por_usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
