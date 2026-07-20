"""Cambios de médico propuestos por el representante, pendientes de validar.

Requerimiento jul-2026: cuando el REPRESENTANTE modifica un médico ya aprobado de su
panel, el médico **sigue activo con los datos anteriores** (la operación del ciclo no se
interrumpe) y la propuesta espera la validación del Gerente de Distrito. Al aprobarla se
vuelca sobre `DIM_MedicoVisita` y se recalcula la categoría.

Escrita a mano: el autogenerate arrastra renombrados de índices ajenos a este cambio.

Revision ID: 0022_medico_solicitud_cambio
Revises: 0021_medico_clasificacion
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_medico_solicitud_cambio"
down_revision = "0021_medico_clasificacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "MedicoSolicitudCambio",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("medico_visita_id", sa.Integer(), nullable=False),
        # Campos generales propuestos (patrón PATCH: solo lo que cambia).
        sa.Column("cambios_json", sa.String(4000), nullable=True),
        # Clasificación propuesta (los 5 criterios del motor).
        sa.Column("pacientes_semana", sa.Numeric(10, 2), nullable=True),
        sa.Column("costo_consulta", sa.Numeric(12, 2), nullable=True),
        sa.Column("potencial_prescripcion", sa.String(50), nullable=True),
        sa.Column("ubicacion_territorial", sa.String(50), nullable=True),
        sa.Column("kol_nivel", sa.String(100), nullable=True),
        sa.Column("estado", sa.String(12), nullable=False),      # PENDIENTE|APROBADO|RECHAZADO
        sa.Column("solicitado_por", sa.Integer(), nullable=True),
        sa.Column("fecha_solicitud", sa.DateTime(), nullable=False),
        sa.Column("resuelto_por", sa.Integer(), nullable=True),
        sa.Column("fecha_resolucion", sa.DateTime(), nullable=True),
        sa.Column("motivo", sa.String(300), nullable=True),
        sa.ForeignKeyConstraint(["medico_visita_id"], ["Visita.DIM_MedicoVisita.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="Visita",
    )
    op.create_index("IX_SolicitudCambio_estado", "MedicoSolicitudCambio", ["estado"],
                    schema="Visita")
    op.create_index(op.f("ix_Visita_MedicoSolicitudCambio_medico_visita_id"),
                    "MedicoSolicitudCambio", ["medico_visita_id"], schema="Visita")


def downgrade() -> None:
    op.drop_index(op.f("ix_Visita_MedicoSolicitudCambio_medico_visita_id"),
                  table_name="MedicoSolicitudCambio", schema="Visita")
    op.drop_index("IX_SolicitudCambio_estado", table_name="MedicoSolicitudCambio",
                  schema="Visita")
    op.drop_table("MedicoSolicitudCambio", schema="Visita")
