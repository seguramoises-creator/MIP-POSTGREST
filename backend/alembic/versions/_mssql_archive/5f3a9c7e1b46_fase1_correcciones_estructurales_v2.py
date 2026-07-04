"""Fase 1 - Correcciones estructurales criticas (F1, F2, F3, F4, F9)

Revision ID: 5f3a9c7e1b46
Revises: a7c3f9e1b4d6
Create Date: 2026-06-21

Implementa los 5 hallazgos CRITICOS del documento
MSM_Analisis_Estructura_DIM_FACT.docx (alcance "Fase 1", aprobado por el
usuario), bajo la convencion "_V2 = tabla paralela nueva": las tablas con
un defecto de diseno estructural (no solo una FK faltante) se duplican
como tablas _V2 nuevas, SIN tocar ni borrar las tablas originales. El
cutover de los servicios hacia las tablas _V2 (remapear FKs de FACT_* que
hoy apuntan a DIM_RM/DIM_Indicador, migrar etl_service.py/dims.py a la
nueva DIM_RM_V2, etc.) es trabajo posterior, fuera de esta migracion.

F4 (FK faltante en gerente_id) es la unica excepcion: es un ALTER directo
sobre las tablas existentes (agregar una FK no rompe nada que ya
funcione, no amerita tabla paralela).

--------------------------------------------------------------------------
F4 - FK faltante en gerente_id (ALTER directo, 6 columnas)
--------------------------------------------------------------------------
  Security.DIM_Usuario.gerente_id          -> FK Config.DIM_Gerente.id
  DW.FACT_ResultadoIndicador.gerente_id    -> FK Config.DIM_Gerente.id
  DW.FACT_CategorizacionMedica.gerente_id  -> FK Config.DIM_Gerente.id
  DW.FACT_ScoreIntegralRM.gerente_id       -> FK Config.DIM_Gerente.id
  DW.FACT_RankingRM.gerente_id             -> FK Config.DIM_Gerente.id
  DW.FACT_ReconocimientoRM.gerente_id      -> FK Config.DIM_Gerente.id
  (DW.FACT_RankingGerente.gerente_id YA tiene FK correcta -> se excluye)
  Antes de cada ALTER se nulifican huerfanos (gerente_id que no existe en
  DIM_Gerente) para que la creacion de la FK no falle por datos sucios.

--------------------------------------------------------------------------
F2 + F9 - Config.DIM_RM_V2 (PK surrogate real, codigo unico por pais)
--------------------------------------------------------------------------
  v1 (DIM_RM) fuerza el RM_CODIGO del Excel como PK via IDENTITY_INSERT
  (dims.py) y declara `codigo` UNIQUE global (no por pais) -> colision
  garantizada en escenarios multipais (F2) y bloquea que dos paises
  reusen el mismo codigo de negocio (F9).
  DIM_RM_V2 usa autoincrement real (sin IDENTITY_INSERT), conserva el
  codigo de origen del Excel en `codigo_origen_excel` (trazabilidad) y
  reemplaza el UNIQUE global por UNIQUE(pais_id, codigo).
  Backfill: 1 fila por cada fila de DIM_RM; los id nuevos los genera la BD
  (por eso DIM_RM_V2.id NO coincide con DIM_RM.id - ver nota de cutover
  en el changelog entregado al usuario).

--------------------------------------------------------------------------
F3 - Config.DIM_MedicoCobertura_V2 + DW.FACT_Visita_V2
--------------------------------------------------------------------------
  FACT_Visita.medico_codigo es texto libre sin FK.
  DESVIACION DELIBERADA respecto al hallazgo original del documento de
  analisis: el plan inicial proponia FK contra Config.DIM_Medico, pero
  esa tabla pertenece al modulo Categorizacion Medica (otro Excel fuente,
  deduplicada por `nombre`, sin codigo estable) - es un universo medico
  DISTINTO al de Cobertura Predictiva. El propio docstring de FACT_Visita
  indica que el cruce real es contra Config.DIM_TargetMedico (comparten
  `medico_codigo`). Por eso se crea Config.DIM_MedicoCobertura_V2, con
  codigo estable y UNIQUE(pais_id, codigo), poblada desde la union de
  DIM_TargetMedico + FACT_Visita, y FACT_Visita_V2.medico_id apunta ahi
  (se conserva medico_codigo en la tabla para trazabilidad/auditoria).

--------------------------------------------------------------------------
F1 - Config.DIM_Indicador_V2 (CHECK constraint en modulo)
--------------------------------------------------------------------------
  DIM_Indicador.modulo no tiene validacion alguna. El comentario del
  modelo dice "GESTION | RESULTADOS" pero iup_service.py opera con
  PRODUCTIVIDAD/COACHING/CAPACITACION, y "GESTION" sigue siendo
  consultado en vivo en productividad.py (3 ocurrencias); dashboard.py
  tiene fallback dual GESTION/PRODUCTIVIDAD y RESULTADOS/COMERCIAL. Por
  eso el CHECK de DIM_Indicador_V2 no se limita a 3 valores: incluye los
  6 valores realmente vigentes en el codigo para no romper esas rutas.
  Angostar esta lista es trabajo de Fase 2, coordinado con actualizar
  productividad.py/dashboard.py a un solo esquema de nombres.
  Filas con `modulo` fuera de ese conjunto (si existen) NO se copian a la
  V2 y se reportan con PRINT durante el upgrade para correccion manual.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5f3a9c7e1b46'
down_revision = 'a7c3f9e1b4d6'
branch_labels = None
depends_on = None


# Valores de `modulo` realmente vigentes en el codigo (ver docstring F1 arriba).
MODULOS_VALIDOS = (
    'PRODUCTIVIDAD', 'COMERCIAL', 'COACHING', 'CAPACITACION',
    'GESTION', 'RESULTADOS',
)

# F4: (esquema, tabla, columna, nombre_de_la_FK)
F4_TABLAS = [
    ('Security', 'DIM_Usuario', 'gerente_id', 'FK_Usuario_Gerente'),
    ('DW', 'FACT_ResultadoIndicador', 'gerente_id', 'FK_ResultadoIndicador_Gerente'),
    ('DW', 'FACT_CategorizacionMedica', 'gerente_id', 'FK_CategorizacionMedica_Gerente'),
    ('DW', 'FACT_ScoreIntegralRM', 'gerente_id', 'FK_ScoreIntegralRM_Gerente'),
    ('DW', 'FACT_RankingRM', 'gerente_id', 'FK_RankingRM_Gerente'),
    ('DW', 'FACT_ReconocimientoRM', 'gerente_id', 'FK_ReconocimientoRM_Gerente'),
]


def upgrade() -> None:
    # ======================================================================
    # F4 - FK faltante en gerente_id (ALTER directo sobre tablas existentes)
    # ======================================================================
    for schema, tabla, columna, fk_name in F4_TABLAS:
        op.execute(
            f"UPDATE [{schema}].[{tabla}] SET {columna} = NULL "
            f"WHERE {columna} IS NOT NULL "
            f"AND {columna} NOT IN (SELECT id FROM [Config].[DIM_Gerente])"
        )
        op.create_foreign_key(
            fk_name,
            tabla, 'DIM_Gerente',
            [columna], ['id'],
            source_schema=schema, referent_schema='Config',
        )

    # ======================================================================
    # F2 + F9 - Config.DIM_RM_V2
    # ======================================================================
    op.create_table(
        'DIM_RM_V2',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('codigo_origen_excel', sa.String(length=20), nullable=True),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('linea_id', sa.Integer(), nullable=False),
        sa.Column('gerente_id', sa.Integer(), nullable=True),
        sa.Column('codigo', sa.String(length=20), nullable=False),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('cedula', sa.String(length=30), nullable=True),
        sa.Column('email', sa.String(length=200), nullable=True),
        sa.Column('zona', sa.String(length=100), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fecha_ingreso', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['linea_id'], ['Config.DIM_Linea.id'], ),
        sa.ForeignKeyConstraint(['gerente_id'], ['Config.DIM_Gerente.id'], ),
        sa.UniqueConstraint('pais_id', 'codigo', name='UQ_RM_V2_Pais_Codigo'),
        schema='Config',
    )
    op.execute("""
        INSERT INTO [Config].[DIM_RM_V2]
            (codigo_origen_excel, pais_id, linea_id, gerente_id, codigo,
             nombre, cedula, email, zona, activo, fecha_ingreso)
        SELECT codigo, pais_id, linea_id, gerente_id, codigo,
               nombre, cedula, email, zona, activo, fecha_ingreso
        FROM [Config].[DIM_RM]
    """)

    # ======================================================================
    # F3 - Config.DIM_MedicoCobertura_V2 + DW.FACT_Visita_V2
    # ======================================================================
    op.create_table(
        'DIM_MedicoCobertura_V2',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=200), nullable=True),
        sa.Column('especialidad', sa.String(length=100), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.UniqueConstraint('pais_id', 'codigo', name='UQ_MedicoCobertura_V2_Pais_Codigo'),
        schema='Config',
    )
    # Universo medico = union de DIM_TargetMedico y FACT_Visita; nombre y
    # especialidad se toman de DIM_TargetMedico cuando el codigo coincide.
    op.execute("""
        INSERT INTO [Config].[DIM_MedicoCobertura_V2] (pais_id, codigo, nombre, especialidad)
        SELECT u.pais_id, u.medico_codigo,
               MAX(t.medico_nombre) AS nombre,
               MAX(t.especialidad) AS especialidad
        FROM (
            SELECT pais_id, medico_codigo FROM [Config].[DIM_TargetMedico]
            UNION
            SELECT pais_id, medico_codigo FROM [DW].[FACT_Visita]
        ) u
        LEFT JOIN [Config].[DIM_TargetMedico] t
               ON t.pais_id = u.pais_id AND t.medico_codigo = u.medico_codigo
        GROUP BY u.pais_id, u.medico_codigo
    """)

    op.create_table(
        'FACT_Visita_V2',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('rm_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('medico_id', sa.Integer(), nullable=False),
        sa.Column('medico_codigo', sa.String(length=50), nullable=False),
        sa.Column('fecha_visita', sa.Date(), nullable=False),
        sa.Column('tipo_contacto', sa.String(length=50), nullable=True),
        sa.Column('estado_visita', sa.String(length=20), nullable=False, server_default='Realizada'),
        sa.Column('producto_foco', sa.String(length=100), nullable=True),
        sa.Column('carga_excel_id', sa.Integer(), nullable=True),
        sa.Column('fecha_carga', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['medico_id'], ['Config.DIM_MedicoCobertura_V2.id'], ),
        schema='DW',
    )
    op.create_index(
        'IX_FACT_Visita_V2_medico_id', 'FACT_Visita_V2', ['medico_id'], schema='DW',
    )
    op.execute("""
        INSERT INTO [DW].[FACT_Visita_V2]
            (pais_id, rm_id, ciclo_id, medico_id, medico_codigo, fecha_visita,
             tipo_contacto, estado_visita, producto_foco, carga_excel_id, fecha_carga)
        SELECT v.pais_id, v.rm_id, v.ciclo_id, m.id, v.medico_codigo, v.fecha_visita,
               v.tipo_contacto, v.estado_visita, v.producto_foco, v.carga_excel_id, v.fecha_carga
        FROM [DW].[FACT_Visita] v
        INNER JOIN [Config].[DIM_MedicoCobertura_V2] m
                ON m.pais_id = v.pais_id AND m.codigo = v.medico_codigo
    """)

    # ======================================================================
    # F1 - Config.DIM_Indicador_V2 (CHECK constraint en modulo)
    # ======================================================================
    valores_sql = ", ".join(f"'{v}'" for v in MODULOS_VALIDOS)
    op.create_table(
        'DIM_Indicador_V2',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('rol', sa.String(length=20), nullable=False, server_default='RM'),
        sa.Column('modulo', sa.String(length=50), nullable=False),
        sa.Column('tipo_periodo', sa.String(length=10), nullable=False, server_default='CICLO'),
        sa.Column('ponderacion_pct', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('escala', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('valor_min', sa.Numeric(10, 4), nullable=True),
        sa.Column('valor_max', sa.Numeric(10, 4), nullable=True),
        sa.Column('formula', sa.Text(), nullable=True),
        sa.Column('peso_iup', sa.Numeric(5, 4), nullable=False, server_default='0'),
        sa.Column('unidad', sa.String(length=30), nullable=True),
        sa.Column('meta_global', sa.Numeric(10, 4), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.UniqueConstraint('pais_id', 'codigo', name='UQ_Indicador_V2_Pais_Codigo'),
        sa.CheckConstraint(f"modulo IN ({valores_sql})", name='CK_Indicador_V2_Modulo'),
        schema='Config',
    )
    op.execute(f"""
        INSERT INTO [Config].[DIM_Indicador_V2]
            (pais_id, codigo, nombre, descripcion, rol, modulo, tipo_periodo,
             ponderacion_pct, escala, valor_min, valor_max, formula, peso_iup,
             unidad, meta_global, activo, orden)
        SELECT pais_id, codigo, nombre, descripcion, rol, modulo, tipo_periodo,
               ponderacion_pct, escala, valor_min, valor_max, formula, peso_iup,
               unidad, meta_global, activo, orden
        FROM [Config].[DIM_Indicador]
        WHERE modulo IN ({valores_sql})
    """)
    op.execute(f"""
        IF EXISTS (
            SELECT 1 FROM [Config].[DIM_Indicador] WHERE modulo NOT IN ({valores_sql})
        )
        PRINT 'ADVERTENCIA: hay filas en Config.DIM_Indicador con modulo invalido que NO se copiaron a DIM_Indicador_V2. Revisar manualmente con: SELECT * FROM Config.DIM_Indicador WHERE modulo NOT IN (''PRODUCTIVIDAD'',''COMERCIAL'',''COACHING'',''CAPACITACION'',''GESTION'',''RESULTADOS'')'
    """)


def downgrade() -> None:
    op.drop_table('DIM_Indicador_V2', schema='Config')
    op.drop_index('IX_FACT_Visita_V2_medico_id', table_name='FACT_Visita_V2', schema='DW')
    op.drop_table('FACT_Visita_V2', schema='DW')
    op.drop_table('DIM_MedicoCobertura_V2', schema='Config')
    op.drop_table('DIM_RM_V2', schema='Config')

    for schema, tabla, columna, fk_name in reversed(F4_TABLAS):
        op.drop_constraint(fk_name, tabla, schema=schema, type_='foreignkey')
