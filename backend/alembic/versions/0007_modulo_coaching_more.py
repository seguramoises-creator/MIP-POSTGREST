"""Módulo de Coaching (Modelo de Ventas MORE) — esquema `coaching`.

Crea el esquema autocontenido `coaching` con:
  - ItemCatalogo : catálogo editable de los 26 ítems MORE (sembrado aquí).
  - Sesion       : hoja de coaching GD→RM (APPEND-ONLY, inmutable por trigger).
  - ItemEvaluado : detalle por ítem calificado (APPEND-ONLY, inmutable por trigger).

Inmutabilidad a nivel de BD (Sección 10 del spec): un trigger rechaza UPDATE/DELETE
sobre Sesion e ItemEvaluado. Las correcciones son una hoja NUEVA con `corrige_a_id`
apuntando a la original (que nunca se toca). El catálogo SÍ es editable.

Revision ID: 0007_modulo_coaching_more
Revises: 0006_limpiar_medicos_demo
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_modulo_coaching_more"
down_revision = "0006_limpiar_medicos_demo"
branch_labels = None
depends_on = None


# Los 26 ítems MORE del instrumento fuente (mockup), por sección.
_ITEMS = [
    ("Planificación", 1, [
        "Revisé notas de visitas anteriores, Estilo Social",
        "Establecí objetivos EMORR en base a mi investigación y/o visitas anteriores",
        "Tenía materiales necesarios para apoyar mi visita (Ayuda Visual, Flyers, Estudios, MM)",
        "Conoce el Estilo Social del Médico",
    ]),
    ("Apertura", 2, [
        "Atraje con éxito la atención del médico",
        "Identifiqué la necesidad conocida o supuesta del Médico",
        "Vinculé la visita con visitas anteriores",
        "Verbalicé objetivo",
    ]),
    ("Desarrollo de la Visita", 3, [
        "Escucha: usé técnicas de escucha activa, escuché el lenguaje no verbal",
        "Utilicé preguntas abiertas",
        "Manejo de objeciones",
    ]),
    ("AV: Ayuda Visual", 4, [
        "Utiliza correctamente AV (Mensaje Clave, Gráficos, Eslogan)",
        "Entrega correcta de recordatorios de marca",
        "Mencione la marca del producto, posicionamiento",
        "Conoce Ayuda Visual",
    ]),
    ("Conocimientos Científicos", 5, [
        "Conoce producto (Dosis, presentación, precio, Competencia, etc)",
        "Conoce patología relacionada con el producto",
        "Conoce anatomía relacionada con la indicación del producto",
    ]),
    ("Cierre", 6, [
        "Síntesis de problemas y necesidades expresada por el médico",
        "Resumen de beneficio",
        "Establecimiento del compromiso",
        "Da tranquilidad al médico",
    ]),
    ("Seguimiento", 7, [
        "Determiné Estilo Social del Médico",
        "Verifiqué objetivos establecidos",
        "Tomé notas detalladas inmediatamente después de la visita",
        "Auto evaluación",
    ]),
]


def upgrade():
    op.execute('CREATE SCHEMA IF NOT EXISTS "coaching"')

    op.create_table(
        "ItemCatalogo",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("seccion", sa.String(60), nullable=False),
        sa.Column("orden_seccion", sa.Integer, nullable=False),
        sa.Column("orden_item", sa.Integer, nullable=False),
        sa.Column("texto", sa.Text, nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        schema="coaching",
    )

    op.create_table(
        "Sesion",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("gd_usuario_id", sa.Integer, sa.ForeignKey("Security.DIM_Usuario.id"), nullable=False),
        sa.Column("gd_gerente_id", sa.Integer, sa.ForeignKey("Config.DIM_Gerente.id"), nullable=True),
        sa.Column("rm_id", sa.Integer, sa.ForeignKey("Config.DIM_RM.id"), nullable=False),
        sa.Column("pais_codigo", sa.String(10), nullable=False),
        sa.Column("ciclo_id", sa.Integer, sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=True),
        sa.Column("fecha_coaching", sa.Date, nullable=False),
        sa.Column("medicos_vistos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("evaluacion_promedio", sa.Numeric(5, 2), nullable=False),
        sa.Column("fortalezas", sa.Text, nullable=False),
        sa.Column("areas_perfeccionar", sa.Text, nullable=False),
        sa.Column("plan_que_haras", sa.Text, nullable=False),
        sa.Column("plan_como_haras", sa.Text, nullable=False),
        sa.Column("plan_como_veras", sa.Text, nullable=False),
        sa.Column("plan_fecha_seguimiento", sa.Date, nullable=False),
        sa.Column("rm_acuerdo", sa.String(20), nullable=False),
        sa.Column("rm_justificacion_desacuerdo", sa.Text, nullable=True),
        sa.Column("rm_firma_imagen", sa.Text, nullable=False),
        sa.Column("rm_firma_timestamp", sa.DateTime, nullable=True),
        sa.Column("corrige_a_id", sa.Integer, sa.ForeignKey("coaching.Sesion.id"), nullable=True),
        sa.Column("motivo_correccion", sa.Text, nullable=True),
        sa.Column("pdf_generado", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, nullable=True),
        schema="coaching",
    )
    op.create_index("IX_CoachingSesion_ciclo", "Sesion", ["ciclo_id"], schema="coaching")
    op.create_index("IX_CoachingSesion_rm", "Sesion", ["rm_id"], schema="coaching")
    op.create_index("IX_CoachingSesion_gd", "Sesion", ["gd_usuario_id"], schema="coaching")

    op.create_table(
        "ItemEvaluado",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("sesion_id", sa.Integer, sa.ForeignKey("coaching.Sesion.id"), nullable=False),
        sa.Column("item_catalogo_id", sa.Integer, sa.ForeignKey("coaching.ItemCatalogo.id"), nullable=True),
        sa.Column("seccion", sa.String(60), nullable=False),
        sa.Column("item_texto", sa.Text, nullable=False),
        sa.Column("calificacion", sa.Integer, nullable=False),
        schema="coaching",
    )
    op.create_index("IX_CoachingItemEval_sesion", "ItemEvaluado", ["sesion_id"], schema="coaching")

    # ── Inmutabilidad (append-only): rechazar UPDATE/DELETE en las hojas ──
    op.execute("""
        CREATE OR REPLACE FUNCTION coaching._rechazar_mutacion() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Hoja de coaching inmutable (append-only): % no permitido en %.
Use una hoja de corrección (nuevo registro con corrige_a_id).', TG_OP, TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_coaching_sesion_inmutable
        BEFORE UPDATE OR DELETE ON coaching."Sesion"
        FOR EACH ROW EXECUTE FUNCTION coaching._rechazar_mutacion();
    """)
    op.execute("""
        CREATE TRIGGER trg_coaching_item_inmutable
        BEFORE UPDATE OR DELETE ON coaching."ItemEvaluado"
        FOR EACH ROW EXECUTE FUNCTION coaching._rechazar_mutacion();
    """)

    # ── Seed del catálogo de ítems MORE (26) ──
    filas = []
    for seccion, orden_sec, items in _ITEMS:
        for i, texto in enumerate(items, start=1):
            filas.append({"seccion": seccion, "orden_seccion": orden_sec,
                          "orden_item": i, "texto": texto, "activo": True})
    op.bulk_insert(
        sa.table(
            "ItemCatalogo",
            sa.column("seccion", sa.String),
            sa.column("orden_seccion", sa.Integer),
            sa.column("orden_item", sa.Integer),
            sa.column("texto", sa.Text),
            sa.column("activo", sa.Boolean),
            schema="coaching",
        ),
        filas,
    )


def downgrade():
    op.execute('DROP TRIGGER IF EXISTS trg_coaching_item_inmutable ON coaching."ItemEvaluado"')
    op.execute('DROP TRIGGER IF EXISTS trg_coaching_sesion_inmutable ON coaching."Sesion"')
    op.execute("DROP FUNCTION IF EXISTS coaching._rechazar_mutacion()")
    op.drop_table("ItemEvaluado", schema="coaching")
    op.drop_table("Sesion", schema="coaching")
    op.drop_table("ItemCatalogo", schema="coaching")
    op.execute('DROP SCHEMA IF EXISTS "coaching"')
