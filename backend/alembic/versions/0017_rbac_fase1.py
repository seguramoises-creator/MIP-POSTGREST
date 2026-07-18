"""RBAC Fase 1 — roles nuevos + DIM_Recurso + FACT_RolPermiso + FACT_AuditoriaSeguridad
+ Usuario.roles_actualizado_en.

Aditivo y NO destructivo: no cambia el RBAC de ningún endpoint existente. Solo agrega los 4
valores nuevos al enum PG `rol`, la columna de revocación y las 3 tablas del módulo de
autorización. La matriz se siembra aparte (scripts/seed_authz.py).

Revision ID: 0017_rbac_fase1
Revises: 0016_planeacion_evento
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_rbac_fase1"
down_revision = "0016_planeacion_evento"
branch_labels = None
depends_on = None

_NUEVOS_ROLES = ["GERENTE_MARKETING", "GERENTE_MEDICO", "ANALISTA_DATOS", "FINANZAS"]


def upgrade():
    # 1) Nuevos valores del enum PG `rol`. En PG 12+ ADD VALUE se permite dentro de la
    #    transacción de la migración (solo no se puede USAR el valor en la misma tx; aquí solo
    #    lo añadimos). IF NOT EXISTS = idempotente.
    for r in _NUEVOS_ROLES:
        op.execute(f"ALTER TYPE rol ADD VALUE IF NOT EXISTS '{r}'")

    # 2) Columna de revocación de permisos por cambio de rol
    op.add_column("DIM_Usuario",
                  sa.Column("roles_actualizado_en", sa.DateTime(), nullable=True),
                  schema="Security")

    # 3) Catálogo de recursos
    op.create_table(
        "DIM_Recurso",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("modulo", sa.String(60), nullable=False),
        sa.UniqueConstraint("slug", name="UQ_Recurso_slug"),
        schema="Security",
    )
    op.create_index("IX_Recurso_slug", "DIM_Recurso", ["slug"], schema="Security")

    # 4) Matriz rol→permiso
    op.create_table(
        "FACT_RolPermiso",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("rol", sa.String(40), nullable=False),
        sa.Column("recurso", sa.String(80), nullable=False),
        sa.Column("accion", sa.String(20), nullable=False),
        sa.Column("alcance", sa.String(10), nullable=False),
        sa.UniqueConstraint("rol", "recurso", "accion", name="UQ_RolPermiso"),
        schema="Security",
    )
    op.create_index("IX_RolPermiso_rol", "FACT_RolPermiso", ["rol"], schema="Security")
    op.create_index("IX_RolPermiso_recurso", "FACT_RolPermiso", ["recurso"], schema="Security")

    # 5) Auditoría de seguridad (append-only)
    op.create_table(
        "FACT_AuditoriaSeguridad",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("actor_usuario_id", sa.Integer, nullable=True),
        sa.Column("actor_rol", sa.String(40), nullable=True),
        sa.Column("evento", sa.String(40), nullable=False),
        sa.Column("recurso", sa.String(80), nullable=True),
        sa.Column("accion", sa.String(20), nullable=True),
        sa.Column("alcance", sa.String(10), nullable=True),
        sa.Column("objetivo", sa.String(160), nullable=True),
        sa.Column("detalle", sa.String(500), nullable=True),
        sa.Column("resultado", sa.String(20), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        schema="Security",
    )
    op.create_index("IX_AudSeg_evento", "FACT_AuditoriaSeguridad", ["evento"], schema="Security")
    op.create_index("IX_AudSeg_creado", "FACT_AuditoriaSeguridad", ["creado_en"], schema="Security")


def downgrade():
    op.drop_table("FACT_AuditoriaSeguridad", schema="Security")
    op.drop_table("FACT_RolPermiso", schema="Security")
    op.drop_table("DIM_Recurso", schema="Security")
    op.drop_column("DIM_Usuario", "roles_actualizado_en", schema="Security")
    # PostgreSQL no soporta DROP VALUE de un enum; los 4 valores nuevos permanecen (inofensivo).
