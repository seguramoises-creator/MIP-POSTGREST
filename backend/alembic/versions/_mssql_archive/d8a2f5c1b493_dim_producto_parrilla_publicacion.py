"""Config.DIM_Producto + Visita.ParrillaPromocional: producto_id, segmento_target,
publicación (Gerente de Producto)

Revision ID: d8a2f5c1b493
Revises: b1d3e6f9c274
Create Date: 2026-07-01

Aditiva e idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "d8a2f5c1b493"
down_revision = "b1d3e6f9c274"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("DIM_Producto", schema="Config"):
        op.create_table(
            "DIM_Producto",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("codigo", sa.String(length=40), nullable=False, unique=True),
            sa.Column("nombre", sa.String(length=120), nullable=False),
            sa.Column("area_terapeutica", sa.String(length=80), nullable=True),
            sa.Column("descripcion", sa.String(length=150), nullable=True),
            sa.Column("segmento_target", sa.String(length=120), nullable=True),
            sa.Column("meta_muestras_visita", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("gerente_producto", sa.String(length=150), nullable=True),
            sa.Column("linea_id", sa.Integer(), sa.ForeignKey("Config.DIM_Linea.id"), nullable=True),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            schema="Config",
        )

    cols = {c["name"] for c in insp.get_columns("ParrillaPromocional", schema="Visita")}
    add = [
        ("producto_id", sa.Integer(), None),
        ("segmento_target", sa.String(length=120), None),
        ("publicada", sa.Boolean(), "0"),
        ("fecha_publicacion", sa.DateTime(), None),
        ("publicada_por", sa.Integer(), None),
    ]
    for nombre, tipo, sdef in add:
        if nombre not in cols:
            kwargs = {"nullable": (nombre != "publicada")}
            if sdef is not None:
                kwargs["server_default"] = sa.text(sdef)
            op.add_column("ParrillaPromocional", sa.Column(nombre, tipo, **kwargs), schema="Visita")


def downgrade():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("ParrillaPromocional", schema="Visita")}
    for nombre in ("publicada_por", "fecha_publicacion", "publicada", "segmento_target", "producto_id"):
        if nombre in cols:
            op.drop_column("ParrillaPromocional", nombre, schema="Visita")
    if insp.has_table("DIM_Producto", schema="Config"):
        op.drop_table("DIM_Producto", schema="Config")
