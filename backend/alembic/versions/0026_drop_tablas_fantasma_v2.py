"""Elimina 4 tablas fantasma "V2" — modelos huérfanos de una Fase 1 nunca continuada.

Hallazgo de auditoría (jul-2026): `Config.DIM_RM_V2`, `Config.DIM_Indicador_V2`,
`Config.DIM_MedicoCobertura_V2` y `DW.FACT_Visita_V2` se creaban físicamente en cada
`alembic upgrade head` (vía el `Base.metadata.create_all()` de `0001_baseline_postgres`),
pero documentaban en su docstring una migración (`5f3a9c7e1b46`) que **nunca existió** en
este repo, y ningún `app/services/*.py` ni `app/api/v1/routers/*.py` las consulta o
escribe (grep exhaustivo, cero resultados) — puro bloat de esquema heredado de una
"Fase 1" que no se continuó. Se retiran también sus 4 modelos ORM
(`RepresentanteMedicoV2`, `IndicadorV2`, `MedicoCoberturaV2`, `VisitaV2` — y la constante
`MODULOS_INDICADOR_V2`, huérfana junto con `IndicadorV2`) en el mismo cambio.

Orden de DROP: `FACT_Visita_V2` primero (FK hacia `DIM_MedicoCobertura_V2`), luego las
3 tablas de Config sin dependientes.

Revision ID: 0026_drop_tablas_fantasma_v2
Revises: 0025_indices_cat_fk
"""
from alembic import op

revision = "0026_drop_tablas_fantasma_v2"
down_revision = "0025_indices_cat_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "DW"."FACT_Visita_V2"')
    op.execute('DROP TABLE IF EXISTS "Config"."DIM_MedicoCobertura_V2"')
    op.execute('DROP TABLE IF EXISTS "Config"."DIM_RM_V2"')
    op.execute('DROP TABLE IF EXISTS "Config"."DIM_Indicador_V2"')


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade no soportado: recrear estas tablas requeriría restaurar el DDL "
        "completo de los modelos ya retirados (RepresentanteMedicoV2/IndicadorV2/"
        "MedicoCoberturaV2/VisitaV2). Restaurar desde backup si de verdad se necesitan."
    )
