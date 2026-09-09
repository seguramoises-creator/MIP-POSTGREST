"""Huella del cliente en las visitas, para que un reintento del móvil no duplique.

La app del visitador captura sin conexión y envía cuando vuelve la red. Si la petición
llega y la respuesta se pierde —un parqueo subterráneo basta—, el teléfono reintenta y
sin esta columna crearía una segunda visita: cobertura inflada y un médico contado dos
veces. Con ella, el servidor reconoce el reenvío y devuelve la visita que ya existe.

ÚNICA POR VM, no global: dos teléfonos distintos no deben poder anularse un envío por
un choque de identificadores, y a la vez el mismo teléfono reintentando no debe crear
dos filas. En PostgreSQL `NULL` no participa del índice único, así que las visitas
creadas desde la web —que no traen huella— no se estorban entre sí.

Escrita a mano y no autogenerada: el autogenerate arrastra renombrados de índices ajenos
a este cambio.

Revision ID: 0038_uuid_cliente_visitas
Revises: 0037_aviso_lote_integracion
"""
from alembic import op
import sqlalchemy as sa

revision = "0038_uuid_cliente_visitas"
down_revision = "0037_aviso_lote_integracion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for tabla, indice in (("FactVisita", "UQ_FactVisita_uuid_cliente"),
                          ("FactVisitaFarmacia", "UQ_FactVisitaFarm_uuid_cliente")):
        op.add_column(tabla, sa.Column("uuid_cliente", sa.String(length=36), nullable=True),
                      schema="Visita")
        op.create_index(indice, tabla, ["vm_id", "uuid_cliente"], unique=True, schema="Visita")


def downgrade() -> None:
    for tabla, indice in (("FactVisita", "UQ_FactVisita_uuid_cliente"),
                          ("FactVisitaFarmacia", "UQ_FactVisitaFarm_uuid_cliente")):
        op.drop_index(indice, table_name=tabla, schema="Visita")
        op.drop_column(tabla, "uuid_cliente", schema="Visita")
