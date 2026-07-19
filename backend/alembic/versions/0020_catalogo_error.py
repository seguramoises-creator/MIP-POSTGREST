"""Matriz de errores: Config.DIM_CatalogoError + siembra de errores comunes.

Catálogo mantenible desde Administración para documentar cada error del sistema
(código, descripción, causa, solución). Ver app/models/dimensiones.py CatalogoError.

Revision ID: 0020_catalogo_error
Revises: 0019_rolpermiso_actualizado_en
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_catalogo_error"
down_revision = "0019_rolpermiso_actualizado_en"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "DIM_CatalogoError",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("descripcion", sa.String(length=600), nullable=True),
        sa.Column("causa", sa.String(length=600), nullable=True),
        sa.Column("solucion", sa.String(length=600), nullable=True),
        sa.Column("categoria", sa.String(length=60), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="1"),
        sa.UniqueConstraint("codigo", name="UQ_CatalogoError_codigo"),
        schema="Config",
    )
    op.create_index("IX_CatalogoError_codigo", "DIM_CatalogoError", ["codigo"], schema="Config")

    # Siembra de errores frecuentes (mantenible después desde la UI).
    tabla = sa.table(
        "DIM_CatalogoError",
        sa.column("codigo", sa.String), sa.column("titulo", sa.String),
        sa.column("descripcion", sa.String), sa.column("causa", sa.String),
        sa.column("solucion", sa.String), sa.column("categoria", sa.String),
        sa.column("http_status", sa.Integer), sa.column("activo", sa.Boolean),
        schema="Config",
    )
    op.bulk_insert(tabla, [
        {"codigo": "AUTH-401", "titulo": "No autenticado", "http_status": 401, "categoria": "Permisos",
         "descripcion": "La sesión expiró o no hay sesión iniciada.",
         "causa": "Token vencido o ausente.", "solucion": "Vuelve a iniciar sesión.", "activo": True},
        {"codigo": "AUTH-403", "titulo": "Acceso denegado", "http_status": 403, "categoria": "Permisos",
         "descripcion": "Tu rol no tiene permiso para esta acción o sección.",
         "causa": "La matriz de Roles y Permisos no concede este recurso a tu rol.",
         "solucion": "Solicita al administrador el permiso, o revisa Administración → Roles y Permisos.", "activo": True},
        {"codigo": "AUTH-423", "titulo": "Cuenta bloqueada", "http_status": 423, "categoria": "Permisos",
         "descripcion": "La cuenta está bloqueada temporalmente por intentos fallidos.",
         "causa": "3 intentos de contraseña incorrectos (30 min).",
         "solucion": "Espera 30 min, recupera la contraseña por correo, o pide al ADMIN desbloquearla.", "activo": True},
        {"codigo": "VAL-400", "titulo": "Datos inválidos", "http_status": 400, "categoria": "Validación",
         "descripcion": "Falta un campo obligatorio o un valor no es válido.",
         "causa": "El formulario tiene datos incompletos o con formato incorrecto.",
         "solucion": "Revisa los campos marcados y corrígelos (el mensaje indica cuál).", "activo": True},
        {"codigo": "USR-PAIS", "titulo": "País obligatorio (Representante)", "http_status": 400, "categoria": "Validación",
         "descripcion": "El rol Representante requiere un país asignado.",
         "causa": "Se creó/editó un Representante sin seleccionar el país.",
         "solucion": "Elige el País en el formulario de usuario y guarda.", "activo": True},
        {"codigo": "MED-DUP-DURO", "titulo": "Médico duplicado (exequátur/cédula)", "http_status": 409, "categoria": "Datos",
         "descripcion": "Ya existe un médico con ese exequátur o cédula en el país.",
         "causa": "Exequátur o cédula repetidos (llave dura del maestro).",
         "solucion": "Busca el médico existente y edítalo, o corrige el exequátur/cédula.", "activo": True},
        {"codigo": "MED-DUP-BLANDO", "titulo": "Posible médico duplicado", "http_status": 409, "categoria": "Datos",
         "descripcion": "Hay un médico con el mismo nombre y ubicación.",
         "causa": "Coincidencia de nombre + centro/provincia.",
         "solucion": "Confirma que es otro médico para crearlo de todas formas, o usa el existente.", "activo": True},
        {"codigo": "CICLO-409", "titulo": "Ciclo cerrado (solo lectura)", "http_status": 409, "categoria": "Datos",
         "descripcion": "No se puede escribir sobre un ciclo cerrado.",
         "causa": "El ciclo en consulta no es el ciclo abierto/de trabajo.",
         "solucion": "Cambia al ciclo abierto en la barra superior para capturar/editar.", "activo": True},
        {"codigo": "SYS-500", "titulo": "Error interno del sistema", "http_status": 500, "categoria": "Sistema",
         "descripcion": "Ocurrió un error no esperado en el servidor.",
         "causa": "Fallo interno (bug, dato inconsistente o servicio no disponible).",
         "solucion": "Reintenta; si persiste, reporta al equipo técnico con la pantalla y la hora.", "activo": True},
        {"codigo": "MAIL-OFF", "titulo": "Correo no configurado / no llega", "http_status": None, "categoria": "Correo",
         "descripcion": "Un correo no se envió o el destinatario no lo recibe.",
         "causa": "SMTP sin configurar, o el usuario no tiene un correo real (los @example.com no llegan).",
         "solucion": "Configura Administración → Servidor de Correo (SMTP) y registra el correo real del usuario.", "activo": True},
    ])


def downgrade():
    op.drop_index("IX_CatalogoError_codigo", table_name="DIM_CatalogoError", schema="Config")
    op.drop_table("DIM_CatalogoError", schema="Config")
