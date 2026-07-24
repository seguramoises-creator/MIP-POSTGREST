"""Índices en las columnas FK del esquema cat.* (Categorización Médica / Cobertura Predictiva).

Hallazgo de auditoría (jul-2026): las 22 columnas FK del esquema `cat` (motor real de
Categorización Médica y Cobertura Predictiva, ver CLAUDE.md §14) nunca tuvieron índice —
a diferencia de `DW.FACT_ResultadoIndicador`, que sí indexa `pais_codigo`/`rm_id`/
`indicador_id`/`ciclo_id`. PostgreSQL NO indexa automáticamente columnas FK (solo la PK
referenciada), y los dashboards en vivo consultan constantemente por país/ciclo/
representante — candidato real a full scans según crece el dato.

Escrita a mano (no autogenerate, mismo criterio que 0021/0024): serían ~22 `CREATE INDEX`
puntuales, sin ningún cambio de columna/tipo que justifique arrastrar el ruido de
autogenerate sobre un esquema con identificadores mixed-case entre comillas dobles.

Revision ID: 0025_indices_cat_fk
Revises: 0024_modulo_farmacias
"""
from alembic import op

revision = "0025_indices_cat_fk"
down_revision = "0024_modulo_farmacias"
branch_labels = None
depends_on = None

# (tabla, columna) — todas en el esquema "cat", identificadores mixed-case entre comillas.
_INDICES = [
    ("DimClasificacionMedica", "PaisKey"),
    ("DimEspecialidad", "PaisKey"),
    ("DimMedico", "PaisKey"),
    ("DimMedico", "EspecialidadKey"),
    ("DimRepresentanteMedico", "PaisKey"),
    ("FactMedicoCategoriaSnapshot", "LoadBatchKey"),
    ("FactMedicoCategoriaSnapshot", "PaisKey"),
    ("FactMedicoCategoriaSnapshot", "MedicoKey"),
    ("FactMedicoCategoriaSnapshot", "ClasificacionKey"),
    ("DimCiclo", "PaisKey"),
    ("DimCalendario", "PaisKey"),
    ("DimCalendario", "CicloKey"),
    ("FactTargetMedicoCiclo", "CicloKey"),
    ("FactTargetMedicoCiclo", "PaisKey"),
    ("FactTargetMedicoCiclo", "RepresentanteKey"),
    ("FactTargetMedicoCiclo", "MedicoKey"),
    ("FactVisitaMedica", "CicloKey"),
    ("FactVisitaMedica", "PaisKey"),
    ("FactVisitaMedica", "RepresentanteKey"),
    ("KpiCoberturaPredictiva", "CicloKey"),
    ("KpiCoberturaPredictiva", "PaisKey"),
    ("KpiCoberturaPredictiva", "RepresentanteKey"),
]


def _ix_name(tabla: str, columna: str) -> str:
    return f"ix_cat_{tabla.lower()}_{columna.lower()}"


def upgrade() -> None:
    for tabla, columna in _INDICES:
        op.execute(
            f'CREATE INDEX IF NOT EXISTS "{_ix_name(tabla, columna)}" '
            f'ON "cat"."{tabla}" ("{columna}")'
        )


def downgrade() -> None:
    for tabla, columna in _INDICES:
        op.execute(f'DROP INDEX IF EXISTS "cat"."{_ix_name(tabla, columna)}"')
