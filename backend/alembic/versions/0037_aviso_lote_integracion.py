"""Registro de avisos enviados por lote de integración.

Mallén abre sus lotes en `ext.controlcarga` con estado RECIBIDO y ahí se quedan
hasta que alguien de VISTA los valida. Hoy nadie se entera: no hay aviso de
ningún tipo, así que un lote subido un viernes por la noche espera hasta que
alguien abre la pantalla.

Esta tabla es la memoria del aviso: sin ella, el trabajo programado reenviaría
el mismo correo cada vez que corre.

POR QUÉ NO VA EN `ext`: ese esquema es contrato firmado con un tercero y solo se
permite escribir `estado`/`mensaje`. Añadirle una columna obligaría a reeditar el
DDL entregado y a repetir los permisos de `mallen_etl`. Vive en `Audit`, igual
que `IntegracionHallazgo` y por la misma razón.

Revision ID: 0037_aviso_lote_integracion
Revises: 0036_alcance_linea_pais
"""
import sqlalchemy as sa
from alembic import op

revision = "0037_aviso_lote_integracion"
down_revision = "0036_alcance_linea_pais"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "IntegracionAvisoLote",
        # `lote_id` es la clave: un lote se avisa UNA vez. Sin clave primaria, dos
        # ejecuciones solapadas del trabajo programado insertarían dos filas y
        # mandarían dos correos por el mismo lote.
        sa.Column("lote_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("enviado_en", sa.DateTime(), nullable=False),
        sa.Column("destinatarios", sa.Integer(), nullable=False, server_default="0"),
        # SIN clave foránea hacia `ext.controlcarga` a propósito: una FK obligaría a
        # `Audit` a depender del esquema del tercero, y si Mallén reconstruyera su
        # tabla el borrado en cascada se llevaría el historial de avisos.
        schema="Audit",
    )


def downgrade() -> None:
    op.drop_table("IntegracionAvisoLote", schema="Audit")
