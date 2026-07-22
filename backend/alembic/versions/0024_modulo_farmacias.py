"""Módulo de Farmacias — maestro único, panel del VM y registro de visita.

Espejo del módulo de Médicos: maestro `Config.DIM_Farmacia` (país-level) ↔ panel
`Visita.DIM_FarmaciaVisita` (referencia al maestro, sin F1/F2 — cobertura simple) ↔
registro `Visita.FactVisitaFarmacia` (tabla PARALELA a `Visita.FactVisita`, Opción A:
cero regresión sobre el registro de visita a médicos).

`direccion` y `encargado` son bloqueantes (NOT NULL) en el maestro — F23/F24. `estado`
nace en `PENDIENTE_APROBACION` (el alta originada por un VM pasa por aprobación del GD;
el rol admin/config puede crear directo). Nombre visible = cadena+sucursal o nombre
suelto, según `es_cadena` (F20) — resuelto en el servicio, no en la BD.

NOTA: escrita a mano a propósito (igual que 0021). El autogenerate arrastra renombres
de índices ajenos (deriva de la convención de nombres en Security/Config) que no tienen
que ver con este cambio.

Revision ID: 0024_modulo_farmacias
Revises: 0023_activacion_cuenta
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_modulo_farmacias"
down_revision = "0023_activacion_cuenta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Maestro país-level.
    op.create_table(
        "DIM_Farmacia",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pais_codigo", sa.String(length=10), nullable=False),
        sa.Column("es_cadena", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cadena", sa.String(length=120), nullable=True),
        sa.Column("sucursal", sa.String(length=120), nullable=True),
        sa.Column("nombre", sa.String(length=200), nullable=True),
        sa.Column("nombre_completo", sa.String(length=250), nullable=False, server_default=""),
        sa.Column("direccion", sa.String(length=300), nullable=False),   # F23 bloqueante
        sa.Column("provincia", sa.String(length=100), nullable=True),
        sa.Column("municipio", sa.String(length=100), nullable=True),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("latitud", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitud", sa.Numeric(10, 7), nullable=True),
        sa.Column("encargado", sa.String(length=200), nullable=False),  # F24 bloqueante
        sa.Column("telefono", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="PENDIENTE_APROBACION"),
        sa.Column("origen", sa.String(length=12), nullable=False, server_default="VM"),
        sa.Column("solicitado_por", sa.Integer(), nullable=True),
        sa.Column("aprobado_por", sa.Integer(), nullable=True),
        sa.Column("fecha_solicitud", sa.DateTime(), nullable=True),
        sa.Column("fecha_aprobacion", sa.DateTime(), nullable=True),
        sa.Column("motivo_rechazo", sa.String(length=300), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pais_codigo"], ["Config.DIM_Pais.codigo"]),
        sa.ForeignKeyConstraint(["solicitado_por"], ["Security.DIM_Usuario.id"]),
        sa.ForeignKeyConstraint(["aprobado_por"], ["Security.DIM_Usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="Config",
    )
    op.create_index("IX_Farmacia_cadena_sucursal", "DIM_Farmacia",
                    ["pais_codigo", "cadena", "sucursal"], schema="Config")
    op.create_index("IX_Farmacia_estado", "DIM_Farmacia", ["estado"], schema="Config")

    # 2) Panel del VM (referencia al maestro, F19). Sin planeación: ciclos_sin_visita informativo.
    op.create_table(
        "DIM_FarmaciaVisita",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vm_id", sa.Integer(), nullable=False),
        sa.Column("maestro_farmacia_id", sa.Integer(), nullable=False),
        sa.Column("estado_aprobacion", sa.String(length=16), nullable=False, server_default="PENDIENTE_ALTA"),
        sa.Column("ciclo_alta_id", sa.Integer(), nullable=True),
        sa.Column("ciclo_baja_id", sa.Integer(), nullable=True),
        sa.Column("ciclos_sin_visita", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("solicitado_por", sa.Integer(), nullable=True),
        sa.Column("aprobado_por", sa.Integer(), nullable=True),
        sa.Column("fecha_solicitud", sa.DateTime(), nullable=True),
        sa.Column("fecha_aprobacion", sa.DateTime(), nullable=True),
        sa.Column("motivo", sa.String(length=300), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fecha_registro", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["vm_id"], ["Config.DIM_RM.id"]),
        sa.ForeignKeyConstraint(["maestro_farmacia_id"], ["Config.DIM_Farmacia.id"]),
        sa.ForeignKeyConstraint(["ciclo_alta_id"], ["Config.DIM_Ciclo.id"]),
        sa.ForeignKeyConstraint(["ciclo_baja_id"], ["Config.DIM_Ciclo.id"]),
        sa.ForeignKeyConstraint(["solicitado_por"], ["Security.DIM_Usuario.id"]),
        sa.ForeignKeyConstraint(["aprobado_por"], ["Security.DIM_Usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="Visita",
    )
    op.create_index("IX_FarmaciaVisita_vm", "DIM_FarmaciaVisita", ["vm_id"], schema="Visita")
    op.create_index("ix_Visita_DIM_FarmaciaVisita_maestro_farmacia_id", "DIM_FarmaciaVisita",
                    ["maestro_farmacia_id"], schema="Visita")

    # 3) Registro de visita a farmacia — tabla PARALELA a Visita.FactVisita (Opción A).
    op.create_table(
        "FactVisitaFarmacia",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vm_id", sa.Integer(), nullable=False),
        sa.Column("ciclo_id", sa.Integer(), nullable=False),
        sa.Column("farmacia_id", sa.Integer(), nullable=False),
        sa.Column("fecha_hora", sa.DateTime(), nullable=False),
        sa.Column("comentario", sa.String(length=1000), nullable=True),
        sa.Column("ejecutada", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("causa_no_visita", sa.String(length=80), nullable=True),
        sa.Column("latitud", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitud", sa.Numeric(10, 7), nullable=True),
        sa.Column("foto", sa.LargeBinary(), nullable=True),
        sa.Column("foto_mime", sa.String(length=40), nullable=True),
        sa.Column("registrado_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["vm_id"], ["Config.DIM_RM.id"]),
        sa.ForeignKeyConstraint(["ciclo_id"], ["Config.DIM_Ciclo.id"]),
        sa.ForeignKeyConstraint(["farmacia_id"], ["Visita.DIM_FarmaciaVisita.id"]),
        sa.ForeignKeyConstraint(["registrado_por"], ["Security.DIM_Usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="Visita",
    )
    op.create_index("IX_FactVisitaFarm_vm_ciclo", "FactVisitaFarmacia",
                    ["vm_id", "ciclo_id"], schema="Visita")


def downgrade() -> None:
    # Orden inverso: registro -> panel -> maestro.
    op.drop_index("IX_FactVisitaFarm_vm_ciclo", "FactVisitaFarmacia", schema="Visita")
    op.drop_table("FactVisitaFarmacia", schema="Visita")

    op.drop_index("ix_Visita_DIM_FarmaciaVisita_maestro_farmacia_id", "DIM_FarmaciaVisita", schema="Visita")
    op.drop_index("IX_FarmaciaVisita_vm", "DIM_FarmaciaVisita", schema="Visita")
    op.drop_table("DIM_FarmaciaVisita", schema="Visita")

    op.drop_index("IX_Farmacia_estado", "DIM_Farmacia", schema="Config")
    op.drop_index("IX_Farmacia_cadena_sucursal", "DIM_Farmacia", schema="Config")
    op.drop_table("DIM_Farmacia", schema="Config")
