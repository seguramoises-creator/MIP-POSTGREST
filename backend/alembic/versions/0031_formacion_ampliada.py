"""Esquema formacion — Ampliacion del Modulo de Formacion.

Implementa el modelo de datos de "Ampliacion del Modulo de Formacion" v1.0
(jul-2026, Laboratorio Mallen): Onboarding, Biblioteca con lectura obligatoria,
Calendario de Coaching, Ranking gamificado, Refuerzo de Memoria, Simulacro IA y
Plan de Cierre de Brechas. Mas Security.DIM_IAConexion (seccion 20), que es
transversal porque tambien la usara la generacion de examenes ya existente.

NO crea el "eje Competencia" de la Matriz LSII: ese eje YA existe como
DW.FACT_EvaluacionReceptividad.score_desempeno. Lo que el requerimiento pide es
cambiar su FORMULA, y eso redefine el cuadrante de los RM ya evaluados — decision
del cliente, ver punto abierto 8 del plan.

Escrita a mano a partir del autogenerate, conservando SOLO el bloque nuevo: venia
mezclada con renombrados de indices de Config/Security ajenos a este cambio
(mismo motivo que las migraciones 0021 y 0030).

Revision ID: 0031_formacion_ampliada
Revises: 0030_esquema_ext_integracion
Create Date: 2026-07-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0031_formacion_ampliada"
down_revision: Union[str, Sequence[str], None] = "0030_esquema_ext_integracion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS formacion")
    op.create_table('ParametroFormacion',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('clave', sa.String(length=60), nullable=False),
    sa.Column('valor', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('descripcion', sa.String(length=250), nullable=True),
    sa.ForeignKeyConstraint(['pais_codigo'], ['Config.DIM_Pais.codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pais_codigo', 'clave', name='UQ_ParamFormacion_clave'),
    schema='formacion'
    )
    op.create_table('ParametroFrecuenciaLSII',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('cuadrante', sa.String(length=5), nullable=False),
    sa.Column('visitas_por_ciclo', sa.Integer(), nullable=False),
    sa.Column('descripcion', sa.String(length=120), nullable=True),
    sa.ForeignKeyConstraint(['pais_codigo'], ['Config.DIM_Pais.codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pais_codigo', 'cuadrante', name='UQ_FrecLSII_cuadrante'),
    schema='formacion'
    )
    op.create_table('PlanCierreBrecha',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('ciclo_id', sa.Integer(), nullable=True),
    sa.Column('regla_aplicada', sa.String(length=40), nullable=False),
    sa.Column('prioridad', sa.String(length=15), nullable=False),
    sa.Column('alcance', sa.String(length=200), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('accion_sugerida', sa.Text(), nullable=False),
    sa.Column('link_accion', sa.String(length=250), nullable=True),
    sa.Column('atendida', sa.Boolean(), nullable=False),
    sa.Column('generado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['Config.DIM_Pais.codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='formacion'
    )
    op.create_index('IX_PlanBrecha_ciclo', 'PlanCierreBrecha', ['pais_codigo', 'ciclo_id'], unique=False, schema='formacion')
    op.create_table('ProductoLinea',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('linea_id', sa.Integer(), nullable=False),
    sa.Column('nombre_producto', sa.String(length=200), nullable=False),
    sa.Column('rol_en_ruta', sa.String(length=20), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['linea_id'], ['Config.DIM_Linea.id'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['Config.DIM_Pais.codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pais_codigo', 'linea_id', 'nombre_producto', name='UQ_ProductoLinea_nombre'),
    schema='formacion'
    )
    op.create_index('IX_ProductoLinea_linea', 'ProductoLinea', ['linea_id'], unique=False, schema='formacion')
    op.create_index(op.f('ix_formacion_ProductoLinea_pais_codigo'), 'ProductoLinea', ['pais_codigo'], unique=False, schema='formacion')
    op.create_table('DIM_IAConexion',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('capacidad', sa.String(length=10), nullable=False),
    sa.Column('proveedor_tipo', sa.String(length=30), nullable=False),
    sa.Column('endpoint_url', sa.Text(), nullable=True),
    sa.Column('metodo_auth', sa.String(length=20), nullable=False),
    sa.Column('credencial_1_cifrada', sa.Text(), nullable=True),
    sa.Column('credencial_2_cifrada', sa.Text(), nullable=True),
    sa.Column('modelo', sa.String(length=100), nullable=True),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.Column('verificada', sa.Boolean(), nullable=False),
    sa.Column('ultima_verificacion', sa.DateTime(), nullable=True),
    sa.Column('ultimo_error', sa.Text(), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('modificado_en', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['creado_por'], ['Security.DIM_Usuario.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre', name='UQ_IAConexion_nombre'),
    schema='Security'
    )
    op.create_table('CalendarioCoachingSugerido',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('gd_id', sa.Integer(), nullable=False),
    sa.Column('ciclo_id', sa.Integer(), nullable=False),
    sa.Column('rm_id', sa.Integer(), nullable=False),
    sa.Column('semana', sa.Integer(), nullable=False),
    sa.Column('dia_semana', sa.String(length=10), nullable=False),
    sa.Column('cuadrante_al_generar', sa.String(length=5), nullable=True),
    sa.Column('editado_manualmente', sa.Boolean(), nullable=False),
    sa.Column('publicado', sa.Boolean(), nullable=False),
    sa.Column('publicado_en', sa.DateTime(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
    sa.ForeignKeyConstraint(['gd_id'], ['Config.DIM_Gerente.id'], ),
    sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='formacion'
    )
    op.create_index('IX_CalCoach_gd_ciclo', 'CalendarioCoachingSugerido', ['gd_id', 'ciclo_id'], unique=False, schema='formacion')
    op.create_table('OnboardingPlantilla',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('linea_id', sa.Integer(), nullable=False),
    sa.Column('nombre_plantilla', sa.String(length=200), nullable=False),
    sa.Column('duracion_dias', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['creado_por'], ['Security.DIM_Usuario.id'], ),
    sa.ForeignKeyConstraint(['linea_id'], ['Config.DIM_Linea.id'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['Config.DIM_Pais.codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='formacion'
    )
    op.create_index('IX_OnbPlantilla_linea', 'OnboardingPlantilla', ['pais_codigo', 'linea_id'], unique=False, schema='formacion')
    op.create_table('RankingFormacionPuntos',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('rm_id', sa.Integer(), nullable=False),
    sa.Column('ciclo_id', sa.Integer(), nullable=False),
    sa.Column('puntos_certificacion', sa.Integer(), nullable=False),
    sa.Column('puntos_examenes', sa.Integer(), nullable=False),
    sa.Column('puntos_refuerzo', sa.Integer(), nullable=False),
    sa.Column('puntos_onboarding', sa.Integer(), nullable=False),
    sa.Column('puntos_total', sa.Integer(), nullable=False),
    sa.Column('racha_ciclos', sa.Integer(), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
    sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rm_id', 'ciclo_id', name='UQ_RankingForm_rm_ciclo'),
    schema='formacion'
    )
    op.create_table('SimulacroSesion',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('rm_id', sa.Integer(), nullable=False),
    sa.Column('estilo_social_asignado', sa.String(length=20), nullable=False),
    sa.Column('medico_simulado', sa.String(length=150), nullable=False),
    sa.Column('genero_simulado', sa.String(length=10), nullable=True),
    sa.Column('fecha', sa.DateTime(), nullable=False),
    sa.Column('finalizada', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='formacion'
    )
    op.create_index('IX_SimSesion_rm', 'SimulacroSesion', ['rm_id'], unique=False, schema='formacion')
    op.create_table('BibliotecaMaterial',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('producto_id', sa.Integer(), nullable=True),
    sa.Column('titulo', sa.String(length=250), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('archivo_url', sa.Text(), nullable=False),
    sa.Column('obligatorio', sa.Boolean(), nullable=False),
    sa.Column('usado_en_examen_id', sa.Integer(), nullable=True),
    sa.Column('usado_en_coaching_av', sa.Boolean(), nullable=False),
    sa.Column('subido_por', sa.Integer(), nullable=True),
    sa.Column('aprobado_por_gm', sa.Boolean(), nullable=False),
    sa.Column('aprobado_por', sa.Integer(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['aprobado_por'], ['Security.DIM_Usuario.id'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['Config.DIM_Pais.codigo'], ),
    sa.ForeignKeyConstraint(['producto_id'], ['formacion.ProductoLinea.id'], ),
    sa.ForeignKeyConstraint(['subido_por'], ['Security.DIM_Usuario.id'], ),
    sa.ForeignKeyConstraint(['usado_en_examen_id'], ['exam.DimExamen.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='formacion'
    )
    op.create_index('IX_BibMaterial_producto', 'BibliotecaMaterial', ['producto_id'], unique=False, schema='formacion')
    op.create_index(op.f('ix_formacion_BibliotecaMaterial_pais_codigo'), 'BibliotecaMaterial', ['pais_codigo'], unique=False, schema='formacion')
    op.create_table('OnboardingPaso',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('plantilla_id', sa.Integer(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('titulo', sa.String(length=250), nullable=False),
    sa.Column('plazo_sugerido', sa.String(length=60), nullable=True),
    sa.Column('bloqueante', sa.Boolean(), nullable=False),
    sa.Column('quien_lo_marca', sa.String(length=20), nullable=False),
    sa.Column('referencia_tipo', sa.String(length=30), nullable=True),
    sa.Column('referencia_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['plantilla_id'], ['formacion.OnboardingPlantilla.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plantilla_id', 'orden', name='UQ_OnbPaso_orden'),
    schema='formacion'
    )
    op.create_index(op.f('ix_formacion_OnboardingPaso_plantilla_id'), 'OnboardingPaso', ['plantilla_id'], unique=False, schema='formacion')
    op.create_table('SimulacroResultado',
    sa.Column('sesion_id', sa.BigInteger(), nullable=False),
    sa.Column('calificacion_apertura', sa.Integer(), nullable=True),
    sa.Column('calificacion_desarrollo', sa.Integer(), nullable=True),
    sa.Column('calificacion_cierre', sa.Integer(), nullable=True),
    sa.Column('calificacion_general', sa.Numeric(precision=4, scale=2), nullable=True),
    sa.ForeignKeyConstraint(['sesion_id'], ['formacion.SimulacroSesion.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('sesion_id'),
    schema='formacion'
    )
    op.create_table('SimulacroRonda',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('sesion_id', sa.BigInteger(), nullable=False),
    sa.Column('fase_more', sa.String(length=20), nullable=False),
    sa.Column('tecnica_objecion', sa.String(length=40), nullable=True),
    sa.Column('objecion_texto', sa.Text(), nullable=False),
    sa.Column('opciones', sa.JSON(), nullable=True),
    sa.Column('opcion_seleccionada', sa.String(length=1), nullable=True),
    sa.Column('opcion_correcta', sa.String(length=1), nullable=False),
    sa.Column('es_correcta', sa.Boolean(), nullable=True),
    sa.Column('retroalimentacion', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['sesion_id'], ['formacion.SimulacroSesion.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    schema='formacion'
    )
    op.create_index(op.f('ix_formacion_SimulacroRonda_sesion_id'), 'SimulacroRonda', ['sesion_id'], unique=False, schema='formacion')
    op.create_table('BibliotecaConfirmacion',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('material_id', sa.Integer(), nullable=False),
    sa.Column('rm_id', sa.Integer(), nullable=False),
    sa.Column('timestamp_confirmacion', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['material_id'], ['formacion.BibliotecaMaterial.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('material_id', 'rm_id', name='UQ_BibConfirmacion'),
    schema='formacion'
    )
    op.create_index('IX_BibConfirmacion_rm', 'BibliotecaConfirmacion', ['rm_id'], unique=False, schema='formacion')
    op.create_table('OnboardingAsignacion',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('plantilla_id', sa.Integer(), nullable=False),
    sa.Column('rm_id', sa.Integer(), nullable=False),
    sa.Column('fecha_inicio', sa.Date(), nullable=False),
    sa.Column('paso_actual_id', sa.Integer(), nullable=True),
    sa.Column('progreso_pct', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('completada_en', sa.DateTime(), nullable=True),
    sa.Column('asignada_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['asignada_por'], ['Security.DIM_Usuario.id'], ),
    sa.ForeignKeyConstraint(['paso_actual_id'], ['formacion.OnboardingPaso.id'], ),
    sa.ForeignKeyConstraint(['plantilla_id'], ['formacion.OnboardingPlantilla.id'], ),
    sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plantilla_id', 'rm_id', name='UQ_OnbAsignacion_rm'),
    schema='formacion'
    )
    op.create_index('IX_OnbAsignacion_rm', 'OnboardingAsignacion', ['rm_id'], unique=False, schema='formacion')
    op.create_table('RefuerzoCampana',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('pais_codigo', sa.String(length=10), nullable=False),
    sa.Column('ciclo_id', sa.Integer(), nullable=True),
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('producto_id', sa.Integer(), nullable=True),
    sa.Column('duracion_dias', sa.Integer(), nullable=False),
    sa.Column('modo_espaciado', sa.String(length=20), nullable=False),
    sa.Column('material_fuente_id', sa.Integer(), nullable=True),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('aprobado_por_gm', sa.Boolean(), nullable=False),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
    sa.ForeignKeyConstraint(['creado_por'], ['Security.DIM_Usuario.id'], ),
    sa.ForeignKeyConstraint(['material_fuente_id'], ['formacion.BibliotecaMaterial.id'], ),
    sa.ForeignKeyConstraint(['pais_codigo'], ['Config.DIM_Pais.codigo'], ),
    sa.ForeignKeyConstraint(['producto_id'], ['formacion.ProductoLinea.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='formacion'
    )
    op.create_index('IX_RefCampana_ciclo', 'RefuerzoCampana', ['pais_codigo', 'ciclo_id'], unique=False, schema='formacion')
    op.create_table('OnboardingPasoProgreso',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('asignacion_id', sa.Integer(), nullable=False),
    sa.Column('paso_id', sa.Integer(), nullable=False),
    sa.Column('completado', sa.Boolean(), nullable=False),
    sa.Column('completado_en', sa.DateTime(), nullable=True),
    sa.Column('completado_por', sa.Integer(), nullable=True),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['asignacion_id'], ['formacion.OnboardingAsignacion.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['completado_por'], ['Security.DIM_Usuario.id'], ),
    sa.ForeignKeyConstraint(['paso_id'], ['formacion.OnboardingPaso.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('asignacion_id', 'paso_id', name='UQ_OnbProgreso_paso'),
    schema='formacion'
    )
    op.create_index(op.f('ix_formacion_OnboardingPasoProgreso_asignacion_id'), 'OnboardingPasoProgreso', ['asignacion_id'], unique=False, schema='formacion')
    op.create_table('RefuerzoRondaProgramada',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('campana_id', sa.Integer(), nullable=False),
    sa.Column('numero_ronda', sa.Integer(), nullable=False),
    sa.Column('fecha_hora_sugerida', sa.DateTime(), nullable=False),
    sa.Column('fecha_hora_programada', sa.DateTime(), nullable=True),
    sa.Column('formato', sa.JSON(), nullable=True),
    sa.Column('publicada', sa.Boolean(), nullable=False),
    sa.Column('notificada_en', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['campana_id'], ['formacion.RefuerzoCampana.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('campana_id', 'numero_ronda', name='UQ_RefRonda_numero'),
    schema='formacion'
    )
    op.create_index(op.f('ix_formacion_RefuerzoRondaProgramada_campana_id'), 'RefuerzoRondaProgramada', ['campana_id'], unique=False, schema='formacion')
    op.create_table('RefuerzoCapsula',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('ronda_id', sa.Integer(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('formato', sa.String(length=30), nullable=False),
    sa.Column('enunciado', sa.Text(), nullable=False),
    sa.Column('opciones', sa.JSON(), nullable=True),
    sa.Column('opcion_correcta', sa.String(length=1), nullable=True),
    sa.Column('explicacion', sa.Text(), nullable=True),
    sa.Column('generada_por_ia', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['ronda_id'], ['formacion.RefuerzoRondaProgramada.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    schema='formacion'
    )
    op.create_index(op.f('ix_formacion_RefuerzoCapsula_ronda_id'), 'RefuerzoCapsula', ['ronda_id'], unique=False, schema='formacion')
    op.create_table('RefuerzoRespuesta',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('ronda_id', sa.Integer(), nullable=False),
    sa.Column('capsula_id', sa.BigInteger(), nullable=False),
    sa.Column('rm_id', sa.Integer(), nullable=False),
    sa.Column('timestamp_recibido', sa.DateTime(), nullable=False),
    sa.Column('timestamp_respondido', sa.DateTime(), nullable=True),
    sa.Column('tiempo_respuesta_seg', sa.Integer(), nullable=True),
    sa.Column('pct_puntaje_participacion', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('opcion_seleccionada', sa.String(length=1), nullable=True),
    sa.Column('es_acierto', sa.Boolean(), nullable=True),
    sa.Column('texto_libre', sa.Text(), nullable=True),
    sa.Column('puntos_obtenidos', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['capsula_id'], ['formacion.RefuerzoCapsula.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
    sa.ForeignKeyConstraint(['ronda_id'], ['formacion.RefuerzoRondaProgramada.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('capsula_id', 'rm_id', name='UQ_RefRespuesta'),
    schema='formacion'
    )
    op.create_index('IX_RefRespuesta_rm', 'RefuerzoRespuesta', ['rm_id'], unique=False, schema='formacion')
    op.create_index('IX_RefRespuesta_ronda', 'RefuerzoRespuesta', ['ronda_id'], unique=False, schema='formacion')


def downgrade() -> None:
    # Orden inverso al de creacion: las tablas hijas referencian a las padres.
    op.drop_table('RefuerzoRespuesta', schema='formacion')
    op.drop_table('RefuerzoCapsula', schema='formacion')
    op.drop_table('RefuerzoRondaProgramada', schema='formacion')
    op.drop_table('OnboardingPasoProgreso', schema='formacion')
    op.drop_table('RefuerzoCampana', schema='formacion')
    op.drop_table('OnboardingAsignacion', schema='formacion')
    op.drop_table('BibliotecaConfirmacion', schema='formacion')
    op.drop_table('SimulacroRonda', schema='formacion')
    op.drop_table('SimulacroResultado', schema='formacion')
    op.drop_table('OnboardingPaso', schema='formacion')
    op.drop_table('BibliotecaMaterial', schema='formacion')
    op.drop_table('SimulacroSesion', schema='formacion')
    op.drop_table('RankingFormacionPuntos', schema='formacion')
    op.drop_table('OnboardingPlantilla', schema='formacion')
    op.drop_table('CalendarioCoachingSugerido', schema='formacion')
    op.drop_table('DIM_IAConexion', schema='Security')
    op.drop_table('ProductoLinea', schema='formacion')
    op.drop_table('PlanCierreBrecha', schema='formacion')
    op.drop_table('ParametroFrecuenciaLSII', schema='formacion')
    op.drop_table('ParametroFormacion', schema='formacion')
    op.execute("DROP SCHEMA IF EXISTS formacion")
