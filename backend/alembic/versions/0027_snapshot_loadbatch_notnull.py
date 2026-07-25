"""cat.FactMedicoCategoriaSnapshot.LoadBatchKey → NOT NULL (arrastre de un duplicado ORM).

Hallazgo de auditoría (jul-2026): `FactMedicoCategoriaSnapshot` declaraba `load_batch_key`
DOS VECES en el cuerpo de la clase (`cat_models.py`): una arriba con `nullable=False` —en su
posición correcta de columna— y otra al final, junto al `relationship`, con
`Mapped[Optional[int]]` y sin `nullable`. En Python la segunda asignación pisa a la primera
antes de que SQLAlchemy la vea, así que la definición efectiva era la nullable; y como el
baseline crea esta tabla con `Base.metadata.create_all()`, la columna quedó **nullable en la
BD real**, contradiciendo la intención declarada.

Ningún dato se corrompió: todo el flujo de escritura de la tabla usa SQL crudo, y el único
INSERT (`categorizacion_service.calcular_categorias_py`) siempre setea `LoadBatchKey` desde
un parámetro obligatorio de la función. La columna importa además porque el borrado por lote
(`DELETE ... WHERE "LoadBatchKey" IN (...)`) es la vía de limpieza: una fila con NULL sería
un huérfano que ninguna recarga podría barrer.

Retirado el duplicado del modelo, este `SET NOT NULL` alinea la BD con la semántica correcta.
Si la tabla tuviera filas con NULL, PostgreSQL aborta con un error explícito y no se aplica
nada (el DDL es transaccional) — verificar antes con:
    SELECT COUNT(*) FROM "cat"."FactMedicoCategoriaSnapshot" WHERE "LoadBatchKey" IS NULL;

Revision ID: 0027_snapshot_loadbatch_notnull
Revises: 0026_drop_tablas_fantasma_v2
"""
from alembic import op

revision = "0027_snapshot_loadbatch_notnull"
down_revision = "0026_drop_tablas_fantasma_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "cat"."FactMedicoCategoriaSnapshot" '
        'ALTER COLUMN "LoadBatchKey" SET NOT NULL'
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE "cat"."FactMedicoCategoriaSnapshot" '
        'ALTER COLUMN "LoadBatchKey" DROP NOT NULL'
    )
