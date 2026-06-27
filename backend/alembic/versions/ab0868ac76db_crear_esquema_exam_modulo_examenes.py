"""crear esquema exam (modulo examenes)

Revision ID: ab0868ac76db
Revises: 7e53fc5995ef
Create Date: 2026-06-27 04:16:54.846860

Crea el esquema `exam` y las 7 tablas del Módulo de Exámenes (Fase 1).
Idempotente: cada tabla solo se crea si no existe.
FKs externas: Security.DIM_Usuario, Config.DIM_Ciclo, Config.DIM_RM, Config.DIM_Gerente.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'ab0868ac76db'
down_revision: Union[str, Sequence[str], None] = '7e53fc5995ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tabla_existe(conn, tabla: str) -> bool:
    return conn.execute(text(
        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='exam' AND TABLE_NAME=:t"
    ), {"t": tabla}).fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name='exam') EXEC('CREATE SCHEMA [exam]')"
    ))

    if not _tabla_existe(conn, "DimExamen"):
        op.create_table(
            "DimExamen",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("nombre", sa.String(200), nullable=False),
            sa.Column("producto", sa.String(200), nullable=True),
            sa.Column("nota_minima", sa.Integer, nullable=False, server_default="70"),
            sa.Column("tiempo_limite_min", sa.Integer, nullable=True),
            sa.Column("estado", sa.String(20), nullable=False, server_default="borrador"),
            sa.Column("fuente", sa.String(10), nullable=False, server_default="manual"),
            sa.Column("rand_preguntas", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("rand_opciones", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("creado_por_usuario_id", sa.Integer,
                      sa.ForeignKey("Security.DIM_Usuario.id"), nullable=False),
            sa.Column("indicador_codigo", sa.String(50), nullable=True),
            sa.Column("ciclo_id", sa.Integer, sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime, nullable=True),
            sa.Column("fecha_publicacion", sa.DateTime, nullable=True),
            sa.Column("activo", sa.Boolean, nullable=True, server_default="1"),
            schema="exam",
        )

    if not _tabla_existe(conn, "DimPregunta"):
        op.create_table(
            "DimPregunta",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("examen_id", sa.Integer, sa.ForeignKey("exam.DimExamen.id"), nullable=False),
            sa.Column("tipo", sa.String(10), nullable=False, server_default="multi"),
            sa.Column("escenario", sa.Text, nullable=True),
            sa.Column("texto", sa.Text, nullable=False),
            sa.Column("explicacion", sa.Text, nullable=True),
            sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean, nullable=True, server_default="1"),
            schema="exam",
        )

    if not _tabla_existe(conn, "DimPreguntaOpcion"):
        op.create_table(
            "DimPreguntaOpcion",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("pregunta_id", sa.Integer, sa.ForeignKey("exam.DimPregunta.id"), nullable=False),
            sa.Column("texto_opcion", sa.Text, nullable=False),
            sa.Column("indice_original", sa.Integer, nullable=False),
            sa.Column("es_correcta", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean, nullable=True, server_default="1"),
            schema="exam",
        )

    if not _tabla_existe(conn, "FactAsignacionExamen"):
        op.create_table(
            "FactAsignacionExamen",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("examen_id", sa.Integer, sa.ForeignKey("exam.DimExamen.id"), nullable=False),
            sa.Column("evaluado_tipo", sa.String(10), nullable=False),
            sa.Column("evaluado_rm_id", sa.Integer, sa.ForeignKey("Config.DIM_RM.id"), nullable=True),
            sa.Column("evaluado_gerente_id", sa.Integer,
                      sa.ForeignKey("Config.DIM_Gerente.id"), nullable=True),
            sa.Column("fecha_asignacion", sa.DateTime, nullable=True),
            sa.Column("fecha_limite", sa.DateTime, nullable=True),
            sa.Column("intentos_max", sa.Integer, nullable=True),
            sa.Column("intentos_usados", sa.Integer, nullable=False, server_default="0"),
            sa.Column("estado", sa.String(15), nullable=False, server_default="pendiente"),
            sa.Column("notif_activa", sa.Boolean, nullable=False, server_default="0"),
            sa.CheckConstraint(
                "(evaluado_rm_id IS NOT NULL AND evaluado_gerente_id IS NULL) OR "
                "(evaluado_rm_id IS NULL AND evaluado_gerente_id IS NOT NULL)",
                name="CK_AsignacionExamen_evaluado_unico"),
            schema="exam",
        )

    if not _tabla_existe(conn, "FactIntentoExamen"):
        op.create_table(
            "FactIntentoExamen",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("asignacion_id", sa.Integer,
                      sa.ForeignKey("exam.FactAsignacionExamen.id"), nullable=False),
            sa.Column("evaluado_tipo", sa.String(10), nullable=False),
            sa.Column("evaluado_rm_id", sa.Integer, sa.ForeignKey("Config.DIM_RM.id"), nullable=True),
            sa.Column("evaluado_gerente_id", sa.Integer,
                      sa.ForeignKey("Config.DIM_Gerente.id"), nullable=True),
            sa.Column("fecha_inicio", sa.DateTime, nullable=True),
            sa.Column("fecha_fin", sa.DateTime, nullable=True),
            sa.Column("score", sa.Numeric(5, 2), nullable=True),
            sa.Column("aprobado", sa.Boolean, nullable=True),
            sa.Column("tiempo_usado_seg", sa.Integer, nullable=True),
            sa.Column("orden_preguntas_json", sa.Text, nullable=True),
            sa.Column("user_agent", sa.String(400), nullable=True),
            sa.Column("device_type", sa.String(40), nullable=True),
            sa.Column("plataforma", sa.String(40), nullable=True),
            sa.Column("ip_cliente", sa.String(50), nullable=True),
            schema="exam",
        )

    if not _tabla_existe(conn, "FactIntentoRespuesta"):
        op.create_table(
            "FactIntentoRespuesta",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("intento_id", sa.Integer,
                      sa.ForeignKey("exam.FactIntentoExamen.id"), nullable=False),
            sa.Column("pregunta_id", sa.Integer, sa.ForeignKey("exam.DimPregunta.id"), nullable=False),
            sa.Column("opcion_elegida_id", sa.Integer,
                      sa.ForeignKey("exam.DimPreguntaOpcion.id"), nullable=True),
            sa.Column("indice_opcion_presentada", sa.Integer, nullable=True),
            sa.Column("indice_original_elegido", sa.Integer, nullable=True),
            sa.Column("es_correcta", sa.Boolean, nullable=True),
            sa.Column("mapa_opciones_json", sa.Text, nullable=True),
            sa.Column("fecha_respuesta", sa.DateTime, nullable=True),
            schema="exam",
        )

    if not _tabla_existe(conn, "FactFuenteIA"):
        op.create_table(
            "FactFuenteIA",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("examen_id", sa.Integer, sa.ForeignKey("exam.DimExamen.id"), nullable=True),
            sa.Column("tipo_archivo", sa.String(20), nullable=True),
            sa.Column("nombre_archivo", sa.String(300), nullable=True),
            sa.Column("ruta_archivo", sa.String(400), nullable=True),
            sa.Column("texto_extraido_hash", sa.String(64), nullable=True),
            sa.Column("prompt_usado", sa.Text, nullable=True),
            sa.Column("estado_generacion", sa.String(15), nullable=False, server_default="pendiente"),
            sa.Column("mensaje_error", sa.Text, nullable=True),
            sa.Column("cargado_por_usuario_id", sa.Integer,
                      sa.ForeignKey("Security.DIM_Usuario.id"), nullable=True),
            sa.Column("fecha_carga", sa.DateTime, nullable=True),
            schema="exam",
        )


def downgrade() -> None:
    for t in ("FactFuenteIA", "FactIntentoRespuesta", "FactIntentoExamen",
              "FactAsignacionExamen", "DimPreguntaOpcion", "DimPregunta", "DimExamen"):
        op.execute(f"IF OBJECT_ID('exam.{t}') IS NOT NULL DROP TABLE [exam].[{t}]")
