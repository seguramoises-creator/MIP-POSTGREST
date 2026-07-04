"""ampliar Periodo cat.LoadBatch/stg/Snapshot de CHAR(7) a VARCHAR(20)

Revision ID: b1d4e7f2a9c3
Revises: a3c7e9f2b4d1
Create Date: 2026-06-24

Motivo: el formato de período ahora usa el nombre del ciclo (ej. C03-2026 = 8 chars)
en lugar de YYYY-MM (7 chars). Se amplía a VARCHAR(20) para flexibilidad futura.
"""
from alembic import op

revision = 'b1d4e7f2a9c3'
down_revision = 'a3c7e9f2b4d1'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE cat.LoadBatch
            ALTER COLUMN Periodo VARCHAR(20) NOT NULL
    """)
    op.execute("""
        ALTER TABLE stg.MedicoCategoriaInput
            ALTER COLUMN Periodo VARCHAR(20) NULL
    """)
    op.execute("""
        ALTER TABLE cat.FactMedicoCategoriaSnapshot
            ALTER COLUMN Periodo VARCHAR(20) NULL
    """)


def downgrade():
    # Solo posible si todos los valores caben en CHAR(7)
    op.execute("ALTER TABLE cat.LoadBatch ALTER COLUMN Periodo CHAR(7) NOT NULL")
    op.execute("ALTER TABLE stg.MedicoCategoriaInput ALTER COLUMN Periodo CHAR(7) NULL")
    op.execute("ALTER TABLE cat.FactMedicoCategoriaSnapshot ALTER COLUMN Periodo CHAR(7) NULL")
