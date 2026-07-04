"""Drop de los 5 stored procedures del motor (movidos a Python)

El motor de cálculo (Score/Ranking, Categorización y Cobertura Predictiva) se movió
a Python (motor_calculo_service / categorizacion_service / cobertura_predictiva_service),
verificado por caracterización (SP == Python). Estos SPs quedan como código muerto y se
eliminan para dejar Python como única fuente de verdad y el core agnóstico de BD.

downgrade: no-op documentado. Los SPs son obsoletos (nada en el código los invoca en esta
revisión ni posteriores). Si se necesitara restaurarlos, su definición vive en git y en las
migraciones que los crearon (e7a91f4c2b58, cat001_schema_categorizacion_medica,
a2c5e8f1b3d7 y sus correcciones b8c4d2e1f5a9 / e2f5b9c4a1d8 / 2c771e676bd7).

Revision ID: e8f1a2c3d4b5
Revises: d4b8f1a6c290
Create Date: 2026-07-04
"""
from alembic import op

revision = "e8f1a2c3d4b5"
down_revision = "d4b8f1a6c290"
branch_labels = None
depends_on = None

_SPS = [
    "DW.sp_RecalcularCiclo",
    "DW.sp_CompletarPuntajesCiclo",
    "DW.sp_GenerarRankingCiclo",
    "cat.sp_CalcularCategoriaMedica",
    "cat.sp_CalcularCoberturaPredictiva",
]


def upgrade():
    for sp in _SPS:
        op.execute(f"DROP PROCEDURE IF EXISTS {sp}")


def downgrade():
    # No-op intencional: los SPs son código muerto (el motor vive en Python). Su fuente
    # se conserva en git y en las migraciones originales que los crearon.
    pass
