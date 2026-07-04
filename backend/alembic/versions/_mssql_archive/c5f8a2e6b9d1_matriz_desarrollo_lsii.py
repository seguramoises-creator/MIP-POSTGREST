"""agregar tablas Matriz de Desarrollo LSII (receptividad/compromiso)

Revision ID: c5f8a2e6b9d1
Revises: f3g6h9j2k5l8
Create Date: 2026-06-16 00:00:00.000000

NUEVO MÓDULO: Matriz de Desarrollo LSII (Liderazgo Situacional II).

Cruza dos ejes para clasificar a cada RM en un nivel de desarrollo D1-D4
y sugerir el estilo de liderazgo que su Gerente de Distrito debe aplicar:

  - Eje Y = Desempeño/Competencia (0-100): se toma de
    DW.FACT_RankingRM.score_total (motor de score ya existente, sin
    tablas nuevas para este eje).
  - Eje X = Receptividad/Compromiso (0-100): se calcula con un modelo de
    comportamiento OCULTO al evaluador (el GD nunca ve un puntaje ni un
    peso, solo selecciona el texto de comportamiento observado, para
    evitar sesgo).

Se crean 3 tablas:

  - Config.DIM_ReceptividadOpcion (catálogo): 5 dimensiones de
    receptividad x 5 opciones de comportamiento cada una = 25 filas.
    Cada opción tiene un score_oculto (1-5) y un peso_dimension (0.20
    cada una, suman 1.0). Es la única tabla con datos semilla.
  - DW.FACT_EvaluacionReceptividad (cabecera): una fila por evaluación
    de un RM en un ciclo — guarda el score_receptividad calculado, el
    score_desempeno tomado como snapshot de FACT_RankingRM, el nivel
    LSII resultante (D1-D4) y el estilo de liderazgo sugerido.
  - DW.FACT_EvaluacionReceptividadDetalle (detalle): una fila por cada
    una de las 5 dimensiones evaluadas, referenciando la opción de
    comportamiento elegida.

Modelos correspondientes:
  - app/models/dimensiones.py -> ReceptividadOpcion
  - app/models/hechos.py -> EvaluacionReceptividad, EvaluacionReceptividadDetalle
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5f8a2e6b9d1'
down_revision: Union[str, Sequence[str], None] = 'f3g6h9j2k5l8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Datos semilla: 5 dimensiones x 5 opciones de comportamiento ────────────
# score_oculto y peso_dimension NUNCA se exponen al evaluador (GD); el
# router /lsii solo entrega dimension_nombre + texto_comportamiento.
_DIMENSIONES_SEED = [
    {
        "dimension_codigo": "ACEPTA_RESPONSABILIDADES",
        "dimension_nombre": "Acepta nuevas responsabilidades",
        "dimension_descripcion": "Disposición del colaborador para asumir tareas y responsabilidades adicionales a las habituales.",
        "orden_dimension": 1,
        "opciones": [
            "Rechaza o evita nuevas responsabilidades, incluso cuando están dentro de su rol.",
            "Acepta nuevas responsabilidades solo cuando se le asignan de forma directa y sin posibilidad de negociar.",
            "Acepta nuevas responsabilidades tras recibir explicación y acompañamiento del gerente.",
            "Acepta nuevas responsabilidades con disposición y pide los recursos necesarios para cumplirlas.",
            "Busca proactivamente nuevas responsabilidades y propone cómo asumirlas antes de que se le asignen.",
        ],
    },
    {
        "dimension_codigo": "INTERACCION_GERENTE",
        "dimension_nombre": "Interacción con Gerente/Coordinador",
        "dimension_descripcion": "Calidad y frecuencia de la comunicación del colaborador con su Gerente de Distrito o Coordinador.",
        "orden_dimension": 2,
        "opciones": [
            "Evita el contacto con su Gerente/Coordinador y responde con resistencia a sus indicaciones.",
            "Interactúa con su Gerente/Coordinador solo cuando es citado o requerido formalmente.",
            "Responde de manera abierta a las indicaciones de su Gerente/Coordinador y participa cuando se le convoca.",
            "Mantiene comunicación frecuente con su Gerente/Coordinador y comparte avances sin que se lo solicite.",
            "Busca activamente retroalimentación de su Gerente/Coordinador y propone temas de conversación para mejorar su gestión.",
        ],
    },
    {
        "dimension_codigo": "INTERACCION_PARES",
        "dimension_nombre": "Interacción con compañeros",
        "dimension_descripcion": "Forma en que el colaborador se relaciona y colabora con los demás miembros del equipo.",
        "orden_dimension": 3,
        "opciones": [
            "Se aísla del equipo y evita colaborar con sus compañeros.",
            "Interactúa con sus compañeros únicamente en actividades obligatorias del equipo.",
            "Colabora con sus compañeros cuando se le solicita y mantiene una relación cordial.",
            "Comparte buenas prácticas con sus compañeros y colabora sin que se lo pidan.",
            "Es referente para sus compañeros, comparte conocimiento de forma activa y fortalece la dinámica de equipo.",
        ],
    },
    {
        "dimension_codigo": "MOTIVACION",
        "dimension_nombre": "Motivación",
        "dimension_descripcion": "Nivel de entusiasmo y energía que el colaborador muestra frente a las metas y actividades de su rol.",
        "orden_dimension": 4,
        "opciones": [
            "Muestra desinterés evidente por las metas y actividades del rol.",
            "Cumple únicamente lo mínimo requerido, sin mostrar entusiasmo por las metas.",
            "Muestra interés estable por alcanzar las metas y mantiene un desempeño constante.",
            "Muestra entusiasmo visible por las metas y motiva a otros con su actitud.",
            "Demuestra alta motivación, supera consistentemente las metas y contagia energía positiva al equipo.",
        ],
    },
    {
        "dimension_codigo": "MODIFICACION_COMPORTAMIENTO",
        "dimension_nombre": "Modificación de comportamientos sugeridos",
        "dimension_descripcion": "Capacidad del colaborador para ajustar su comportamiento a partir de la retroalimentación recibida.",
        "orden_dimension": 5,
        "opciones": [
            "No modifica su comportamiento pese a retroalimentación reiterada.",
            "Modifica su comportamiento solo de forma parcial y requiere seguimiento constante.",
            "Modifica su comportamiento cuando recibe retroalimentación clara y acompañamiento.",
            "Modifica su comportamiento de forma sostenida tras una sola retroalimentación.",
            "Ajusta su comportamiento de manera proactiva, anticipándose a la retroalimentación.",
        ],
    },
]


def upgrade() -> None:
    # ── 1) Config.DIM_ReceptividadOpcion (catálogo) ─────────────────────
    op.create_table(
        'DIM_ReceptividadOpcion',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('dimension_codigo', sa.String(length=50), nullable=False),
        sa.Column('dimension_nombre', sa.String(length=200), nullable=False),
        sa.Column('dimension_descripcion', sa.Text(), nullable=True),
        sa.Column('orden_dimension', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('orden_opcion', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('texto_comportamiento', sa.Text(), nullable=False),
        sa.Column('score_oculto', sa.Integer(), nullable=False),
        sa.Column('peso_dimension', sa.Numeric(precision=5, scale=4), nullable=False, server_default='0.20'),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint('dimension_codigo', 'orden_opcion', name='UQ_ReceptividadOpcion_Dim_Orden'),
        sa.PrimaryKeyConstraint('id'),
        schema='Config',
    )

    # ── 2) DW.FACT_EvaluacionReceptividad (cabecera) ────────────────────
    op.create_table(
        'FACT_EvaluacionReceptividad',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('rm_id', sa.Integer(), nullable=False),
        sa.Column('gerente_id', sa.Integer(), nullable=True),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('evaluador_usuario_id', sa.Integer(), nullable=True),
        sa.Column('score_receptividad', sa.Numeric(precision=6, scale=2), nullable=False, server_default='0'),
        sa.Column('score_desempeno', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('nivel_lsii', sa.String(length=5), nullable=False),
        sa.Column('estilo_liderazgo', sa.String(length=50), nullable=False),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fecha_evaluacion', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['gerente_id'], ['Config.DIM_Gerente.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_EvaluacionReceptividad_pais_id'), 'FACT_EvaluacionReceptividad', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_EvaluacionReceptividad_rm_id'), 'FACT_EvaluacionReceptividad', ['rm_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_EvaluacionReceptividad_ciclo_id'), 'FACT_EvaluacionReceptividad', ['ciclo_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_EvaluacionReceptividad_fecha_evaluacion'), 'FACT_EvaluacionReceptividad', ['fecha_evaluacion'], unique=False, schema='DW')

    # ── 3) DW.FACT_EvaluacionReceptividadDetalle (detalle) ──────────────
    op.create_table(
        'FACT_EvaluacionReceptividadDetalle',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('evaluacion_id', sa.BigInteger(), nullable=False),
        sa.Column('dimension_codigo', sa.String(length=50), nullable=False),
        sa.Column('opcion_id', sa.Integer(), nullable=False),
        sa.Column('score_oculto', sa.Integer(), nullable=False),
        sa.Column('peso_dimension', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.ForeignKeyConstraint(['evaluacion_id'], ['DW.FACT_EvaluacionReceptividad.id'], ),
        sa.ForeignKeyConstraint(['opcion_id'], ['Config.DIM_ReceptividadOpcion.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_EvaluacionReceptividadDetalle_evaluacion_id'), 'FACT_EvaluacionReceptividadDetalle', ['evaluacion_id'], unique=False, schema='DW')

    # ── 4) Seed: 25 filas de catálogo (5 dimensiones x 5 opciones) ──────
    tabla_receptividad = sa.table(
        'DIM_ReceptividadOpcion',
        sa.column('dimension_codigo', sa.String),
        sa.column('dimension_nombre', sa.String),
        sa.column('dimension_descripcion', sa.Text),
        sa.column('orden_dimension', sa.Integer),
        sa.column('orden_opcion', sa.Integer),
        sa.column('texto_comportamiento', sa.Text),
        sa.column('score_oculto', sa.Integer),
        sa.column('peso_dimension', sa.Numeric),
        sa.column('activo', sa.Boolean),
        schema='Config',
    )

    filas = []
    for dim in _DIMENSIONES_SEED:
        for idx, texto in enumerate(dim["opciones"], start=1):
            filas.append({
                "dimension_codigo": dim["dimension_codigo"],
                "dimension_nombre": dim["dimension_nombre"],
                "dimension_descripcion": dim["dimension_descripcion"],
                "orden_dimension": dim["orden_dimension"],
                "orden_opcion": idx,
                "texto_comportamiento": texto,
                "score_oculto": idx,
                "peso_dimension": 0.20,
                "activo": True,
            })

    op.bulk_insert(tabla_receptividad, filas)


def downgrade() -> None:
    op.drop_index(op.f('ix_DW_FACT_EvaluacionReceptividadDetalle_evaluacion_id'), table_name='FACT_EvaluacionReceptividadDetalle', schema='DW')
    op.drop_table('FACT_EvaluacionReceptividadDetalle', schema='DW')

    op.drop_index(op.f('ix_DW_FACT_EvaluacionReceptividad_fecha_evaluacion'), table_name='FACT_EvaluacionReceptividad', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_EvaluacionReceptividad_ciclo_id'), table_name='FACT_EvaluacionReceptividad', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_EvaluacionReceptividad_rm_id'), table_name='FACT_EvaluacionReceptividad', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_EvaluacionReceptividad_pais_id'), table_name='FACT_EvaluacionReceptividad', schema='DW')
    op.drop_table('FACT_EvaluacionReceptividad', schema='DW')

    op.drop_table('DIM_ReceptividadOpcion', schema='Config')
