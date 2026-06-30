"""Visita Fase 1 — esquema Visita + tabla DIM_MedicoVisita (Panel Médico)

Revision ID: a9d3e6b1c742
Revises: f3a7c2e9b108
Create Date: 2026-06-30

Crea el esquema [Visita] y la tabla del catálogo de médicos del universo de visita
(Módulo de Visita Médica, Parte 2). Idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "a9d3e6b1c742"
down_revision = "f3a7c2e9b108"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Crear el esquema [Visita] si no existe (SQL Server)
    op.execute("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'Visita') EXEC('CREATE SCHEMA [Visita]')")

    insp = sa.inspect(bind)
    if not insp.has_table("DIM_MedicoVisita", schema="Visita"):
        op.create_table(
            "DIM_MedicoVisita",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("vm_id", sa.Integer(), sa.ForeignKey("Config.DIM_RM.id"), nullable=False),
            sa.Column("nombre_completo", sa.String(length=200), nullable=False),
            sa.Column("especialidad_id", sa.Integer(), sa.ForeignKey("Config.DIM_Especialidad.id"), nullable=True),
            sa.Column("categoria", sa.CHAR(length=1), nullable=False),
            sa.Column("tipo_consultorio", sa.String(length=60), nullable=True),
            sa.Column("direccion", sa.String(length=300), nullable=True),
            sa.Column("telefono", sa.String(length=40), nullable=True),
            sa.Column("ciclos_sin_visita", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("fecha_registro", sa.DateTime(), nullable=True),
            sa.Column("registrado_por", sa.Integer(), sa.ForeignKey("Security.DIM_Usuario.id"), nullable=True),
            schema="Visita",
        )
        op.create_index("IX_MedicoVisita_vm", "DIM_MedicoVisita", ["vm_id"], schema="Visita")
        op.create_index("IX_MedicoVisita_nombre", "DIM_MedicoVisita", ["nombre_completo"], schema="Visita")


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("DIM_MedicoVisita", schema="Visita"):
        op.drop_table("DIM_MedicoVisita", schema="Visita")
