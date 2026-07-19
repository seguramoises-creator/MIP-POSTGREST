"""Bloque B: plantilla de clasificación al dar de alta un médico.

1) `Visita.MedicoClasificacion` — staging 1:1 con el médico del panel donde el
   representante captura los 5 criterios del motor de categorización. La CATEGORÍA no
   se calcula aquí: se revela cuando el Gerente de Distrito aprueba el alta.
2) `Visita.DIM_MedicoVisita.categoria` pasa a NULLABLE — un médico recién dado de alta
   NO tiene categoría hasta la aprobación. Los médicos existentes conservan la suya.

NOTA: escrita a mano a propósito. El autogenerate arrastraba ~40 operaciones de
renombrado de índices (deriva de la convención de nombres en Security/Config) que no
tienen que ver con este cambio y habrían tocado tablas ajenas.

Revision ID: 0021_medico_clasificacion
Revises: 0020_catalogo_error
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_medico_clasificacion"
down_revision = "0020_catalogo_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "MedicoClasificacion",
        sa.Column("medico_visita_id", sa.Integer(), nullable=False),
        # Los 5 criterios, con el vocabulario/rango que exige cat.DimReglaCategoriaMedica.
        sa.Column("pacientes_semana", sa.Numeric(10, 2), nullable=True),
        sa.Column("costo_consulta", sa.Numeric(12, 2), nullable=True),
        sa.Column("potencial_prescripcion", sa.String(50), nullable=True),
        sa.Column("ubicacion_territorial", sa.String(50), nullable=True),
        sa.Column("kol_nivel", sa.String(100), nullable=True),
        sa.Column("capturado_por", sa.Integer(), nullable=True),
        sa.Column("fecha_captura", sa.DateTime(), nullable=False),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["medico_visita_id"], ["Visita.DIM_MedicoVisita.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("medico_visita_id"),
        schema="Visita",
    )
    op.alter_column("DIM_MedicoVisita", "categoria",
                    existing_type=sa.CHAR(length=1), nullable=True, schema="Visita")


def downgrade() -> None:
    # Al revertir, los médicos sin categoría (altas no aprobadas) quedarían inválidos:
    # se les asigna 'D' para poder restaurar el NOT NULL sin perder filas.
    op.execute("""UPDATE "Visita"."DIM_MedicoVisita" SET categoria = 'D' WHERE categoria IS NULL""")
    op.alter_column("DIM_MedicoVisita", "categoria",
                    existing_type=sa.CHAR(length=1), nullable=False, schema="Visita")
    op.drop_table("MedicoClasificacion", schema="Visita")
