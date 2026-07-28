"""Esquema ext — capa de recepcion de la integracion con Laboratorio Mallen.

Implementa el "Requerimiento de Datos · VISTA · Laboratorios Mallen" (v1.0,
25-jul-2026): 22 tablas donde Mallen ESCRIBE y VISTA LEE. Nada del sistema
existente se toca: la capa se anade delante (seccion 7.4 del documento).

Escrita a mano a partir del autogenerate, del que se conservo SOLO el bloque de
`ext`: venia mezclado con ~25 renombrados de indices de Config/Security ajenos
a este cambio (mismo motivo por el que se escribio a mano la migracion 0021).

Tres diferencias deliberadas respecto al DDL del documento, explicadas a fondo
en el docstring de app/models/integracion_ext.py:
  1. Nombres en minusculas sin comillas. El documento crea las tablas sin
     comillas pero luego las referencia entrecomilladas en sus claves foraneas
     e indices; corridas en ese orden fallan con "no existe la relacion".
  2. Se anaden las claves foraneas que el documento omite explicitamente "por
     brevedad" (lote_id, ciclo y representante en el resto de tablas de hecho).
  3. Se anaden los indices unicos (pais_codigo, origen_id) de
     factevaluacionconocimiento y factprescripciondetalle: la seccion 5.2 exige
     idempotencia para TODOS los hechos, pero la 6.5 solo los declaraba para tres.

Revision ID: 0030_esquema_ext_integracion
Revises: 0029_capacitacion_sin_medicos
Create Date: 2026-07-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0030_esquema_ext_integracion"
down_revision: Union[str, Sequence[str], None] = "0029_capacitacion_sin_medicos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ext")
    op.create_table('dimespecialidad',
    sa.Column('especialidad_codigo', sa.String(length=30), nullable=False),
    sa.Column('nombre', sa.String(length=150), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('especialidad_codigo'),
    schema='ext'
    )
    op.create_table('dimmercadoir',
    sa.Column('mercado_codigo', sa.String(length=40), nullable=False),
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('nivel', sa.String(length=30), nullable=True),
    sa.Column('mercado_padre', sa.String(length=40), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('mercado_codigo'),
    schema='ext'
    )
    op.create_table('dimpais',
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('moneda', sa.String(length=10), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('pais_codigo'),
    schema='ext'
    )
    op.create_table('controlcarga',
    sa.Column('lote_id', sa.BigInteger(), autoincrement=False, nullable=False),
    sa.Column('sistema_origen', sa.String(length=30), nullable=False),
    sa.Column('modulo', sa.String(length=40), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('ciclo_codigo', sa.String(length=20), nullable=True),
    sa.Column('periodo', sa.String(length=20), nullable=True),
    sa.Column('fecha_extraccion', sa.DateTime(), nullable=False),
    sa.Column('fecha_recepcion', sa.DateTime(), nullable=False),
    sa.Column('filas_enviadas', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('mensaje', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('lote_id'),
    schema='ext'
    )
    op.create_table('dimciclo',
    sa.Column('ciclo_codigo', sa.String(length=20), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('anio', sa.Integer(), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=True),
    sa.Column('fecha_inicio', sa.Date(), nullable=False),
    sa.Column('fecha_fin', sa.Date(), nullable=False),
    sa.Column('dias_laborables', sa.Integer(), nullable=False),
    sa.Column('cerrado', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'ciclo_codigo'),
    schema='ext'
    )
    op.create_table('dimfarmacia',
    sa.Column('farmacia_codigo', sa.String(length=40), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('tipo', sa.String(length=40), nullable=True),
    sa.Column('provincia', sa.String(length=120), nullable=True),
    sa.Column('municipio', sa.String(length=120), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'farmacia_codigo'),
    schema='ext'
    )
    op.create_table('dimlinea',
    sa.Column('linea_codigo', sa.String(length=30), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'linea_codigo'),
    schema='ext'
    )
    op.create_table('dimmedico',
    sa.Column('medico_codigo', sa.String(length=40), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('especialidad_codigo', sa.String(length=30), nullable=True),
    sa.Column('exequatur', sa.String(length=50), nullable=True),
    sa.Column('centro_trabajo', sa.String(length=200), nullable=True),
    sa.Column('provincia', sa.String(length=120), nullable=True),
    sa.Column('municipio', sa.String(length=120), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['especialidad_codigo'], ['ext.dimespecialidad.especialidad_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'medico_codigo'),
    schema='ext'
    )
    op.create_index('ux_dm_exequatur', 'dimmedico', ['pais_codigo', 'exequatur'], unique=True, schema='ext', postgresql_where='exequatur IS NOT NULL')
    op.create_table('dimterritorio',
    sa.Column('territorio_codigo', sa.String(length=40), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=150), nullable=False),
    sa.Column('provincia', sa.String(length=120), nullable=True),
    sa.Column('region', sa.String(length=120), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'territorio_codigo'),
    schema='ext'
    )
    op.create_table('dimgerente',
    sa.Column('gerente_codigo', sa.String(length=30), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('linea_codigo', sa.String(length=30), nullable=True),
    sa.Column('nombre', sa.String(length=150), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['pais_codigo', 'linea_codigo'], ['ext.dimlinea.pais_codigo', 'ext.dimlinea.linea_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'gerente_codigo'),
    schema='ext'
    )
    op.create_table('dimmedicoir',
    sa.Column('medico_ir_codigo', sa.String(length=50), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('exequatur', sa.String(length=50), nullable=False),
    sa.Column('medico_codigo', sa.String(length=40), nullable=True),
    sa.Column('especialidad_codigo', sa.String(length=30), nullable=True),
    sa.Column('territorio_codigo', sa.String(length=40), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['especialidad_codigo'], ['ext.dimespecialidad.especialidad_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'medico_codigo'], ['ext.dimmedico.pais_codigo', 'ext.dimmedico.medico_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'territorio_codigo'], ['ext.dimterritorio.pais_codigo', 'ext.dimterritorio.territorio_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'medico_ir_codigo'),
    schema='ext'
    )
    op.create_index('ux_dmir_exequatur', 'dimmedicoir', ['pais_codigo', 'exequatur'], unique=True, schema='ext')
    op.create_table('dimperiodoir',
    sa.Column('periodo_codigo', sa.String(length=20), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('anio', sa.Integer(), nullable=False),
    sa.Column('mes', sa.Integer(), nullable=False),
    sa.Column('fecha_inicio', sa.Date(), nullable=False),
    sa.Column('fecha_fin', sa.Date(), nullable=False),
    sa.Column('ciclo_codigo', sa.String(length=20), nullable=True),
    sa.Column('cerrado', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['pais_codigo', 'ciclo_codigo'], ['ext.dimciclo.pais_codigo', 'ext.dimciclo.ciclo_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'periodo_codigo'),
    schema='ext'
    )
    op.create_table('dimproducto',
    sa.Column('producto_codigo', sa.String(length=50), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('linea_codigo', sa.String(length=30), nullable=True),
    sa.Column('presentacion', sa.String(length=120), nullable=True),
    sa.Column('codigo_closeup', sa.String(length=50), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['pais_codigo', 'linea_codigo'], ['ext.dimlinea.pais_codigo', 'ext.dimlinea.linea_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'producto_codigo'),
    schema='ext'
    )
    op.create_table('dimproductoir',
    sa.Column('producto_ir_codigo', sa.String(length=50), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('laboratorio', sa.String(length=150), nullable=True),
    sa.Column('mercado_codigo', sa.String(length=40), nullable=True),
    sa.Column('molecula', sa.String(length=200), nullable=True),
    sa.Column('presentacion', sa.String(length=120), nullable=True),
    sa.Column('producto_codigo', sa.String(length=50), nullable=True),
    sa.Column('es_propio', sa.Boolean(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['mercado_codigo'], ['ext.dimmercadoir.mercado_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'producto_codigo'], ['ext.dimproducto.pais_codigo', 'ext.dimproducto.producto_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'producto_ir_codigo'),
    schema='ext'
    )
    op.create_table('dimrepresentante',
    sa.Column('rm_codigo', sa.String(length=30), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('linea_codigo', sa.String(length=30), nullable=True),
    sa.Column('gerente_codigo', sa.String(length=30), nullable=True),
    sa.Column('nombre', sa.String(length=150), nullable=False),
    sa.Column('cedula', sa.String(length=30), nullable=True),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('zona', sa.String(length=100), nullable=True),
    sa.Column('fecha_ingreso', sa.Date(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['pais_codigo', 'gerente_codigo'], ['ext.dimgerente.pais_codigo', 'ext.dimgerente.gerente_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'linea_codigo'], ['ext.dimlinea.pais_codigo', 'ext.dimlinea.linea_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['ext.dimpais.pais_codigo'], ),
    sa.PrimaryKeyConstraint('pais_codigo', 'rm_codigo'),
    schema='ext'
    )
    op.create_table('factevaluacionconocimiento',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('lote_id', sa.BigInteger(), nullable=False),
    sa.Column('origen_id', sa.String(length=60), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('ciclo_codigo', sa.String(length=20), nullable=False),
    sa.Column('rm_codigo', sa.String(length=30), nullable=False),
    sa.Column('fecha_evaluacion', sa.Date(), nullable=False),
    sa.Column('nota', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('tema', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['lote_id'], ['ext.controlcarga.lote_id'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'ciclo_codigo'], ['ext.dimciclo.pais_codigo', 'ext.dimciclo.ciclo_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'rm_codigo'], ['ext.dimrepresentante.pais_codigo', 'ext.dimrepresentante.rm_codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='ext'
    )
    op.create_index('ux_fec_origen', 'factevaluacionconocimiento', ['pais_codigo', 'origen_id'], unique=True, schema='ext')
    op.create_table('factprescripciondetalle',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('lote_id', sa.BigInteger(), nullable=False),
    sa.Column('origen_id', sa.String(length=60), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('periodo_codigo', sa.String(length=20), nullable=False),
    sa.Column('producto_ir_codigo', sa.String(length=50), nullable=False),
    sa.Column('mercado_codigo', sa.String(length=40), nullable=True),
    sa.Column('territorio_codigo', sa.String(length=40), nullable=True),
    sa.Column('medico_ir_codigo', sa.String(length=50), nullable=False),
    sa.Column('rm_codigo', sa.String(length=30), nullable=True),
    sa.Column('unidades', sa.Numeric(precision=14, scale=4), nullable=False),
    sa.Column('valor', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('version_fuente', sa.String(length=30), nullable=True),
    sa.ForeignKeyConstraint(['lote_id'], ['ext.controlcarga.lote_id'], ),
    sa.ForeignKeyConstraint(['mercado_codigo'], ['ext.dimmercadoir.mercado_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'medico_ir_codigo'], ['ext.dimmedicoir.pais_codigo', 'ext.dimmedicoir.medico_ir_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'periodo_codigo'], ['ext.dimperiodoir.pais_codigo', 'ext.dimperiodoir.periodo_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'producto_ir_codigo'], ['ext.dimproductoir.pais_codigo', 'ext.dimproductoir.producto_ir_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'rm_codigo'], ['ext.dimrepresentante.pais_codigo', 'ext.dimrepresentante.rm_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'territorio_codigo'], ['ext.dimterritorio.pais_codigo', 'ext.dimterritorio.territorio_codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='ext'
    )
    op.create_index('ix_fp_periodo', 'factprescripciondetalle', ['pais_codigo', 'periodo_codigo'], unique=False, schema='ext')
    op.create_index('ux_fp_origen', 'factprescripciondetalle', ['pais_codigo', 'origen_id'], unique=True, schema='ext')
    op.create_table('factventa',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('lote_id', sa.BigInteger(), nullable=False),
    sa.Column('origen_id', sa.String(length=60), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('ciclo_codigo', sa.String(length=20), nullable=False),
    sa.Column('rm_codigo', sa.String(length=30), nullable=False),
    sa.Column('producto_codigo', sa.String(length=50), nullable=True),
    sa.Column('fecha', sa.Date(), nullable=True),
    sa.Column('unidades', sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column('valor_venta', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('cuota', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('moneda', sa.String(length=10), nullable=True),
    sa.ForeignKeyConstraint(['lote_id'], ['ext.controlcarga.lote_id'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'ciclo_codigo'], ['ext.dimciclo.pais_codigo', 'ext.dimciclo.ciclo_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'producto_codigo'], ['ext.dimproducto.pais_codigo', 'ext.dimproducto.producto_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'rm_codigo'], ['ext.dimrepresentante.pais_codigo', 'ext.dimrepresentante.rm_codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='ext'
    )
    op.create_index('ix_fv_ciclo_rm', 'factventa', ['pais_codigo', 'ciclo_codigo', 'rm_codigo'], unique=False, schema='ext')
    op.create_index('ux_fv_origen', 'factventa', ['pais_codigo', 'origen_id'], unique=True, schema='ext')
    op.create_table('factvisitafarmacia',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('lote_id', sa.BigInteger(), nullable=False),
    sa.Column('origen_id', sa.String(length=60), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('ciclo_codigo', sa.String(length=20), nullable=False),
    sa.Column('rm_codigo', sa.String(length=30), nullable=False),
    sa.Column('farmacia_codigo', sa.String(length=40), nullable=False),
    sa.Column('fecha_visita', sa.Date(), nullable=False),
    sa.Column('ejecutada', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['lote_id'], ['ext.controlcarga.lote_id'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'ciclo_codigo'], ['ext.dimciclo.pais_codigo', 'ext.dimciclo.ciclo_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'farmacia_codigo'], ['ext.dimfarmacia.pais_codigo', 'ext.dimfarmacia.farmacia_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'rm_codigo'], ['ext.dimrepresentante.pais_codigo', 'ext.dimrepresentante.rm_codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='ext'
    )
    op.create_index('ux_fvf_origen', 'factvisitafarmacia', ['pais_codigo', 'origen_id'], unique=True, schema='ext')
    op.create_table('factvisitamedico',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('lote_id', sa.BigInteger(), nullable=False),
    sa.Column('origen_id', sa.String(length=60), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('ciclo_codigo', sa.String(length=20), nullable=False),
    sa.Column('rm_codigo', sa.String(length=30), nullable=False),
    sa.Column('medico_codigo', sa.String(length=40), nullable=False),
    sa.Column('fecha_visita', sa.Date(), nullable=False),
    sa.Column('tipo_visita', sa.CHAR(length=1), nullable=False),
    sa.Column('ejecutada', sa.Boolean(), nullable=False),
    sa.Column('acompanado', sa.Boolean(), nullable=False),
    sa.Column('gerente_codigo', sa.String(length=30), nullable=True),
    sa.Column('causa_no_visita', sa.String(length=80), nullable=True),
    sa.Column('productos', sa.String(length=300), nullable=True),
    sa.ForeignKeyConstraint(['lote_id'], ['ext.controlcarga.lote_id'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'ciclo_codigo'], ['ext.dimciclo.pais_codigo', 'ext.dimciclo.ciclo_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'gerente_codigo'], ['ext.dimgerente.pais_codigo', 'ext.dimgerente.gerente_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'medico_codigo'], ['ext.dimmedico.pais_codigo', 'ext.dimmedico.medico_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'rm_codigo'], ['ext.dimrepresentante.pais_codigo', 'ext.dimrepresentante.rm_codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='ext'
    )
    op.create_index('ix_fvm_ciclo_rm', 'factvisitamedico', ['pais_codigo', 'ciclo_codigo', 'rm_codigo'], unique=False, schema='ext')
    op.create_index('ix_fvm_lote', 'factvisitamedico', ['lote_id'], unique=False, schema='ext')
    op.create_index('ux_fvm_origen', 'factvisitamedico', ['pais_codigo', 'origen_id'], unique=True, schema='ext')
    op.create_table('panelmedico',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('lote_id', sa.BigInteger(), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('ciclo_codigo', sa.String(length=20), nullable=False),
    sa.Column('rm_codigo', sa.String(length=30), nullable=False),
    sa.Column('medico_codigo', sa.String(length=40), nullable=False),
    sa.Column('frecuencia_objetivo', sa.CHAR(length=2), nullable=False),
    sa.Column('prioridad', sa.String(length=10), nullable=False),
    sa.Column('categoria', sa.CHAR(length=1), nullable=True),
    sa.Column('visitas_programadas', sa.Integer(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['lote_id'], ['ext.controlcarga.lote_id'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'ciclo_codigo'], ['ext.dimciclo.pais_codigo', 'ext.dimciclo.ciclo_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'medico_codigo'], ['ext.dimmedico.pais_codigo', 'ext.dimmedico.medico_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'rm_codigo'], ['ext.dimrepresentante.pais_codigo', 'ext.dimrepresentante.rm_codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='ext'
    )
    op.create_index('ux_tm_clave', 'panelmedico', ['pais_codigo', 'ciclo_codigo', 'rm_codigo', 'medico_codigo'], unique=True, schema='ext')
    op.create_table('targetfarmacia',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('lote_id', sa.BigInteger(), nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('ciclo_codigo', sa.String(length=20), nullable=False),
    sa.Column('rm_codigo', sa.String(length=30), nullable=False),
    sa.Column('farmacia_codigo', sa.String(length=40), nullable=False),
    sa.Column('visitas_programadas', sa.Integer(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['lote_id'], ['ext.controlcarga.lote_id'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'ciclo_codigo'], ['ext.dimciclo.pais_codigo', 'ext.dimciclo.ciclo_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'farmacia_codigo'], ['ext.dimfarmacia.pais_codigo', 'ext.dimfarmacia.farmacia_codigo'], ),
    sa.ForeignKeyConstraint(['pais_codigo', 'rm_codigo'], ['ext.dimrepresentante.pais_codigo', 'ext.dimrepresentante.rm_codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='ext'
    )
    op.create_index('ux_tf_clave', 'targetfarmacia', ['pais_codigo', 'ciclo_codigo', 'rm_codigo', 'farmacia_codigo'], unique=True, schema='ext')


def downgrade() -> None:
    # Orden inverso al de creacion: las tablas de hecho referencian dimensiones.
    op.drop_table('targetfarmacia', schema='ext')
    op.drop_table('panelmedico', schema='ext')
    op.drop_table('factvisitamedico', schema='ext')
    op.drop_table('factvisitafarmacia', schema='ext')
    op.drop_table('factventa', schema='ext')
    op.drop_table('factprescripciondetalle', schema='ext')
    op.drop_table('factevaluacionconocimiento', schema='ext')
    op.drop_table('dimrepresentante', schema='ext')
    op.drop_table('dimproductoir', schema='ext')
    op.drop_table('dimproducto', schema='ext')
    op.drop_table('dimperiodoir', schema='ext')
    op.drop_table('dimmedicoir', schema='ext')
    op.drop_table('dimgerente', schema='ext')
    op.drop_table('dimterritorio', schema='ext')
    op.drop_table('dimmedico', schema='ext')
    op.drop_table('dimlinea', schema='ext')
    op.drop_table('dimfarmacia', schema='ext')
    op.drop_table('dimciclo', schema='ext')
    op.drop_table('controlcarga', schema='ext')
    op.drop_table('dimpais', schema='ext')
    op.drop_table('dimmercadoir', schema='ext')
    op.drop_table('dimespecialidad', schema='ext')
    op.execute("DROP SCHEMA IF EXISTS ext")
