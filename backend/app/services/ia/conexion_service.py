"""Gestión de las conexiones a proveedores de IA (§20.4 a §20.6).

Es el único lugar que traduce una fila de `Security.DIM_IAConexion` en un
adaptador listo para usar. Los módulos de negocio piden `adaptador_texto(db)` y
no saben —ni deben saber— qué proveedor hay detrás.

COMPATIBILIDAD CON LO QUE YA FUNCIONA
--------------------------------------
Si no hay ninguna conexión activa configurada, se cae al `.env` (la clave de
Anthropic que el módulo de Exámenes usa hoy). Sin ese respaldo, introducir esta
capa habría apagado la generación de exámenes en producción hasta que alguien
entrara a configurar una conexión — un cambio de infraestructura no debe romper
una función que venía andando.
"""
from loguru import logger
from sqlalchemy.orm import Session

from app.core.authz.audit import registrar_evento_seguridad
from app.core.config import settings
from app.models.ia_conexion import IAConexion
from app.services.ia import cifrado
from app.services.ia.adaptadores import ADAPTADORES_TEXTO, ADAPTADORES_VOZ, construir
from app.services.ia.base import (
    AdaptadorTexto, AdaptadorVoz, ConfigProveedor, Credenciales, ErrorProveedorIA,
)

CAPACIDADES = ("texto", "voz")
METODOS_AUTH = ("api_key", "usuario_password")


class ConexionNoVerificada(RuntimeError):
    """No se puede activar una conexión que nunca superó "Probar conexión"
    (§20.4.8): activarla a ciegas rompería la función que la use, y el fallo
    aparecería lejos de aquí."""


class SinConexionIA(RuntimeError):
    """No hay conexión activa ni respaldo en el entorno."""


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def listar(db: Session, capacidad: str | None = None) -> list[IAConexion]:
    q = db.query(IAConexion)
    if capacidad:
        q = q.filter(IAConexion.capacidad == capacidad)
    return q.order_by(IAConexion.capacidad, IAConexion.nombre).all()


def a_dict(c: IAConexion) -> dict:
    """Representación segura para la API: la credencial va SIEMPRE enmascarada
    (§20.6). Nunca existe un camino que la devuelva en claro — solo se puede
    reemplazar."""
    return {
        "id": c.id, "nombre": c.nombre, "capacidad": c.capacidad,
        "proveedor_tipo": c.proveedor_tipo, "endpoint_url": c.endpoint_url,
        "metodo_auth": c.metodo_auth, "modelo": c.modelo,
        "activa": c.activa, "verificada": c.verificada,
        "ultima_verificacion": c.ultima_verificacion,
        "ultimo_error": c.ultimo_error,
        "credencial_1": cifrado.enmascarar(c.credencial_1_cifrada),
        "credencial_2": cifrado.enmascarar(c.credencial_2_cifrada),
    }


def proveedores_disponibles() -> dict[str, list[str]]:
    """Qué adaptadores hay construidos. La interfaz arma su desplegable con
    esto, en vez de con una lista escrita a mano que se desactualiza."""
    return {"texto": sorted(ADAPTADORES_TEXTO), "voz": sorted(ADAPTADORES_VOZ)}


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------

def _validar(capacidad: str, metodo_auth: str, proveedor_tipo: str) -> None:
    if capacidad not in CAPACIDADES:
        raise ValueError(f"Capacidad inválida: {capacidad}. Use texto o voz.")
    if metodo_auth not in METODOS_AUTH:
        raise ValueError(f"Método de autenticación inválido: {metodo_auth}.")
    registro = ADAPTADORES_TEXTO if capacidad == "texto" else ADAPTADORES_VOZ
    if proveedor_tipo not in registro:
        raise ValueError(
            f"No hay adaptador de {capacidad} para '{proveedor_tipo}'. "
            f"Disponibles: {', '.join(sorted(registro))}.")


def crear(db: Session, datos: dict, actor=None) -> IAConexion:
    _validar(datos["capacidad"], datos["metodo_auth"], datos["proveedor_tipo"])
    c = IAConexion(
        nombre=datos["nombre"], capacidad=datos["capacidad"],
        proveedor_tipo=datos["proveedor_tipo"],
        endpoint_url=datos.get("endpoint_url") or None,
        metodo_auth=datos["metodo_auth"],
        credencial_1_cifrada=cifrado.cifrar(datos.get("credencial_1")),
        credencial_2_cifrada=cifrado.cifrar(datos.get("credencial_2")),
        modelo=datos.get("modelo") or None,
        activa=False, verificada=False,
        creado_por=getattr(actor, "id", None))
    db.add(c)
    db.commit()
    db.refresh(c)
    registrar_evento_seguridad(
        db, actor, "IA_CONEXION_CREADA", recurso="ia.conexiones",
        objetivo=c.nombre, detalle=f"{c.capacidad}/{c.proveedor_tipo}")
    return c


def actualizar(db: Session, conexion_id: int, datos: dict, actor=None) -> IAConexion:
    c = db.query(IAConexion).get(conexion_id)
    if c is None:
        raise ValueError("Conexión no encontrada")
    cambios = []
    for campo in ("nombre", "endpoint_url", "modelo"):
        if campo in datos and datos[campo] != getattr(c, campo):
            setattr(c, campo, datos[campo] or None)
            cambios.append(campo)
    if "proveedor_tipo" in datos or "metodo_auth" in datos or "capacidad" in datos:
        capacidad = datos.get("capacidad", c.capacidad)
        metodo = datos.get("metodo_auth", c.metodo_auth)
        proveedor = datos.get("proveedor_tipo", c.proveedor_tipo)
        _validar(capacidad, metodo, proveedor)
        c.capacidad, c.metodo_auth, c.proveedor_tipo = capacidad, metodo, proveedor
        cambios.append("proveedor")
    # Las credenciales solo se tocan si vienen con valor: un formulario que
    # devuelve el enmascarado no debe sobrescribir la credencial real con
    # "sk-…a1b2".
    for campo, columna in (("credencial_1", "credencial_1_cifrada"),
                           ("credencial_2", "credencial_2_cifrada")):
        if datos.get(campo):
            setattr(c, columna, cifrado.cifrar(datos[campo]))
            cambios.append(campo)
    if cambios:
        # Cambiar cualquier cosa invalida la verificación anterior: la prueba que
        # pasó era contra otra configuración.
        c.verificada = False
        c.activa = False
    db.commit()
    db.refresh(c)
    registrar_evento_seguridad(
        db, actor, "IA_CONEXION_MODIFICADA", recurso="ia.conexiones",
        objetivo=c.nombre, detalle=f"campos: {', '.join(cambios) or 'ninguno'}")
    return c


def eliminar(db: Session, conexion_id: int, actor=None) -> None:
    c = db.query(IAConexion).get(conexion_id)
    if c is None:
        return
    nombre = c.nombre
    db.delete(c)
    db.commit()
    registrar_evento_seguridad(
        db, actor, "IA_CONEXION_ELIMINADA", recurso="ia.conexiones", objetivo=nombre)


def probar(db: Session, conexion_id: int, actor=None) -> tuple[bool, str]:
    """Llamada mínima de verificación (§20.4.8).

    Guarda el resultado —incluido el mensaje de error REAL del proveedor— para
    que quien configure vea qué falló y no solo que falló.
    """
    from datetime import datetime, timezone
    c = db.query(IAConexion).get(conexion_id)
    if c is None:
        raise ValueError("Conexión no encontrada")
    try:
        adaptador = construir(c.capacidad, _config_de(c))
        detalle = adaptador.probar()
        c.verificada, c.ultimo_error = True, None
        ok = True
    except Exception as exc:  # noqa: BLE001
        c.verificada, c.ultimo_error = False, str(exc)[:500]
        detalle, ok = str(exc), False
    c.ultima_verificacion = datetime.now(timezone.utc)
    db.commit()
    registrar_evento_seguridad(
        db, actor, "IA_CONEXION_PROBADA", recurso="ia.conexiones",
        objetivo=c.nombre, resultado="OK" if ok else "ERROR", detalle=detalle[:400])
    return ok, detalle


def activar(db: Session, conexion_id: int, actor=None) -> IAConexion:
    """Activa una conexión y desactiva las demás de la MISMA capacidad.

    Una sola activa por capacidad: dos conexiones de texto activas a la vez
    dejarían indeterminado cuál se usa, y el resultado dependería del orden de
    las filas.
    """
    c = db.query(IAConexion).get(conexion_id)
    if c is None:
        raise ValueError("Conexión no encontrada")
    if not c.verificada:
        raise ConexionNoVerificada(
            f"«{c.nombre}» no se puede activar porque no ha superado la prueba "
            "de conexión. Usa «Probar conexión» primero.")
    db.query(IAConexion).filter(
        IAConexion.capacidad == c.capacidad, IAConexion.id != c.id
    ).update({"activa": False})
    c.activa = True
    db.commit()
    db.refresh(c)
    registrar_evento_seguridad(
        db, actor, "IA_CONEXION_ACTIVADA", recurso="ia.conexiones",
        objetivo=c.nombre, detalle=f"capacidad {c.capacidad}")
    return c


# ---------------------------------------------------------------------------
# Resolución — lo que consume el resto de la aplicación
# ---------------------------------------------------------------------------

def _config_de(c: IAConexion) -> ConfigProveedor:
    return ConfigProveedor(
        proveedor_tipo=c.proveedor_tipo,
        endpoint_url=c.endpoint_url,
        modelo=c.modelo,
        credenciales=Credenciales(
            credencial_1=cifrado.descifrar(c.credencial_1_cifrada),
            credencial_2=cifrado.descifrar(c.credencial_2_cifrada)))


def _respaldo_entorno(capacidad: str) -> ConfigProveedor | None:
    """Configuración heredada del `.env`, para no apagar lo que ya funcionaba.

    Solo aplica a texto: la voz nunca estuvo configurada por entorno.
    """
    if capacidad != "texto" or not settings.ANTHROPIC_API_KEY:
        return None
    return ConfigProveedor(
        proveedor_tipo="anthropic",
        modelo=settings.EXAM_AI_MODEL,
        credenciales=Credenciales(credencial_1=settings.ANTHROPIC_API_KEY))


def conexion_activa(db: Session, capacidad: str) -> IAConexion | None:
    return (db.query(IAConexion)
            .filter(IAConexion.capacidad == capacidad, IAConexion.activa.is_(True))
            .first())


def _adaptador(db: Session | None, capacidad: str):
    config = None
    if db is not None:
        c = conexion_activa(db, capacidad)
        if c is not None:
            config = _config_de(c)
    if config is None:
        config = _respaldo_entorno(capacidad)
        if config is not None:
            logger.debug(f"IA/{capacidad}: sin conexión activa, usando el respaldo del entorno")
    if config is None:
        raise SinConexionIA(
            f"No hay ninguna conexión de {capacidad} activa. Configúrala en "
            "Administración → Conexiones de IA.")
    return construir(capacidad, config)


def adaptador_texto(db: Session | None = None) -> AdaptadorTexto:
    return _adaptador(db, "texto")  # type: ignore[return-value]


def adaptador_voz(db: Session | None = None) -> AdaptadorVoz:
    return _adaptador(db, "voz")  # type: ignore[return-value]


__all__ = [
    "CAPACIDADES", "METODOS_AUTH", "ConexionNoVerificada", "SinConexionIA",
    "ErrorProveedorIA", "listar", "a_dict", "proveedores_disponibles",
    "crear", "actualizar", "eliminar", "probar", "activar",
    "conexion_activa", "adaptador_texto", "adaptador_voz",
]
