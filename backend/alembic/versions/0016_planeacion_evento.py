"""planeacion: bitacora de publicacion/desbloqueo (congela el dato base de cobertura)

Revision ID: 0016_planeacion_evento
Revises: 0015_usuario_pais_backfill
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0016_planeacion_evento'
down_revision: Union[str, Sequence[str], None] = '0015_usuario_pais_backfill'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """`Visita.PlaneacionEvento`: bitácora append-only del estado de la planeación.

    La planeación es el denominador de la cobertura (`visitados / planeados`). Si se pudiera
    editar a mitad de ciclo, un VM subiría su cobertura quitando del plan a los médicos que no
    visitó. El estado se deriva del ÚLTIMO evento del (vm, ciclo): sin eventos = borrador
    (editable), PUBLICADA = congelada, DESBLOQUEADA = vuelve a borrador (solo ADMIN, con motivo).

    No se crea ninguna fila: todas las planeaciones existentes quedan como BORRADOR, que es el
    comportamiento actual. Nadie pierde acceso a lo que ya podía editar.
    """
    op.create_table(
        'PlaneacionEvento',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('vm_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('evento', sa.String(length=14), nullable=False),   # PUBLICADA | DESBLOQUEADA
        sa.Column('fecha', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('motivo', sa.String(length=300), nullable=True),
        sa.Column('items', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['vm_id'], ['Config.DIM_RM.id']),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['Security.DIM_Usuario.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='Visita',
    )
    op.create_index('IX_PlaneacionEvento_vm_ciclo', 'PlaneacionEvento',
                    ['vm_id', 'ciclo_id'], schema='Visita')


def downgrade() -> None:
    op.drop_index('IX_PlaneacionEvento_vm_ciclo', table_name='PlaneacionEvento', schema='Visita')
    op.drop_table('PlaneacionEvento', schema='Visita')
