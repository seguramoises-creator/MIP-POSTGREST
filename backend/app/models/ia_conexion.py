"""VISTA — Conexiones a proveedores de IA, configurables por el cliente (§20).

Requisito explícito de Laboratorio Mallén: la conexión a servicios de IA no debe
quedar programada de forma rígida contra un solo proveedor. Cambiar de proveedor
tiene que ser una operación de CONFIGURACIÓN, nunca un cambio de código ni un
despliegue nuevo.

Vive en el esquema `Security` y no en `Config` porque guarda credenciales: el
§20.6 exige cifrado en reposo, enmascaramiento permanente en la interfaz y
registro de auditoría de toda creación, edición o activación.

POR QUÉ DOS CAMPOS DE CREDENCIAL Y NO UNO
------------------------------------------
El cliente pidió poder escribir "el nombre de la IA, su URL y su usuario". La
mayoría de proveedores de IA (OpenAI, Anthropic, Google) NO usan usuario y
contraseña: usan una única API Key. Forzar un campo "usuario" en ellos sería
pedir un dato que no existe. Por eso `metodo_auth` decide qué credenciales
aplican, y el formulario muestra solo las que corresponden: una clave para el
caso común, o Client ID + Client Secret para gateways corporativos y motores de
IA propios, que sí autentican con dos partes (§20.4 punto 5).

`nombre` y `proveedor_tipo` tampoco son lo mismo, aunque lo parezcan: el primero
es una etiqueta humana para distinguir conexiones ("OpenAI - Principal"), y el
segundo es lo que decide qué adaptador de código procesa la petición.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class IAConexion(Base):
    """Una conexión guardada a un proveedor de IA.

    Se permite tener varias a la vez (una de texto y otra de voz, o una activa y
    otra de respaldo lista antes de migrar), pero solo una activa por capacidad.
    """
    __tablename__ = "DIM_IAConexion"
    __table_args__ = (
        UniqueConstraint("nombre", name="UQ_IAConexion_nombre"),
        {"schema": "Security"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    capacidad: Mapped[str] = mapped_column(String(10), nullable=False)      # texto | voz
    # openai | anthropic | azure_openai | google_gemini | elevenlabs | otro
    proveedor_tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    # Editable incluso para proveedores conocidos: Azure OpenAI exige un endpoint
    # propio por cuenta, y algunos clientes usan instancias regionales (§20.4.4).
    endpoint_url: Mapped[str | None] = mapped_column(Text)
    metodo_auth: Mapped[str] = mapped_column(String(20), nullable=False)    # api_key | usuario_password
    # SIEMPRE cifradas en reposo (§20.6). Nunca se devuelven en claro por la API:
    # se muestran enmascaradas y solo se pueden reemplazar, no revelar.
    credencial_1_cifrada: Mapped[str | None] = mapped_column(Text)
    credencial_2_cifrada: Mapped[str | None] = mapped_column(Text)
    # Texto libre y no un desplegable fijo: los proveedores lanzan modelos nuevos
    # con frecuencia y no debe hacer falta un despliegue de VISTA para usarlos.
    modelo: Mapped[str | None] = mapped_column(String(100))
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # No se permite activar una conexión que nunca pasó "Probar conexión" (§20.4.8).
    verificada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ultima_verificacion: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_error: Mapped[str | None] = mapped_column(Text)
    creado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=_ahora, nullable=False)
    modificado_en: Mapped[datetime | None] = mapped_column(DateTime, onupdate=_ahora)
