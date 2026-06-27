"""exam check evaluado_tipo coherente

Revision ID: 798c1fe1eff9
Revises: ab0868ac76db
Create Date: 2026-06-27 05:23:22.902271

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '798c1fe1eff9'
down_revision: Union[str, Sequence[str], None] = 'ab0868ac76db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace the loose evaluado_unico CHECK with the stricter evaluado_coherente CHECK
    that ties evaluado_tipo to the populated FK column.  Idempotent — safe to re-run."""
    conn = op.get_bind()
    # Drop old constraint if it still exists
    conn.execute(text(
        "IF EXISTS ("
        "  SELECT 1 FROM sys.check_constraints"
        "  WHERE name = 'CK_AsignacionExamen_evaluado_unico'"
        "  AND parent_object_id = OBJECT_ID('exam.FactAsignacionExamen')"
        ") "
        "ALTER TABLE [exam].[FactAsignacionExamen]"
        " DROP CONSTRAINT [CK_AsignacionExamen_evaluado_unico]"
    ))
    # Add new constraint if not already present
    conn.execute(text(
        "IF NOT EXISTS ("
        "  SELECT 1 FROM sys.check_constraints"
        "  WHERE name = 'CK_AsignacionExamen_evaluado_coherente'"
        "  AND parent_object_id = OBJECT_ID('exam.FactAsignacionExamen')"
        ") "
        "ALTER TABLE [exam].[FactAsignacionExamen]"
        " ADD CONSTRAINT [CK_AsignacionExamen_evaluado_coherente]"
        " CHECK ("
        "  (evaluado_tipo = 'RM' AND evaluado_rm_id IS NOT NULL AND evaluado_gerente_id IS NULL)"
        "  OR"
        "  (evaluado_tipo = 'GERENTE' AND evaluado_gerente_id IS NOT NULL AND evaluado_rm_id IS NULL)"
        ")"
    ))


def downgrade() -> None:
    """Restore the original loose CHECK constraint."""
    conn = op.get_bind()
    conn.execute(text(
        "IF EXISTS ("
        "  SELECT 1 FROM sys.check_constraints"
        "  WHERE name = 'CK_AsignacionExamen_evaluado_coherente'"
        "  AND parent_object_id = OBJECT_ID('exam.FactAsignacionExamen')"
        ") "
        "ALTER TABLE [exam].[FactAsignacionExamen]"
        " DROP CONSTRAINT [CK_AsignacionExamen_evaluado_coherente]"
    ))
    conn.execute(text(
        "ALTER TABLE [exam].[FactAsignacionExamen]"
        " ADD CONSTRAINT [CK_AsignacionExamen_evaluado_unico]"
        " CHECK ("
        "  (evaluado_rm_id IS NOT NULL AND evaluado_gerente_id IS NULL)"
        "  OR"
        "  (evaluado_rm_id IS NULL AND evaluado_gerente_id IS NOT NULL)"
        ")"
    ))
