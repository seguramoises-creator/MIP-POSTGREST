"""Interfaz única hacia los proveedores de IA (§20.3).

El resto de VISTA llama SOLO a lo que hay aquí. Ningún módulo de negocio importa
el SDK de un proveedor: si lo hiciera, cambiar de proveedor volvería a ser un
cambio de código, que es justamente lo que el cliente pidió evitar (§20.2).

La prueba de que la capa realmente desacopla no es que exista la interfaz, sino
que haya varios adaptadores detrás cumpliéndola — por eso el §20.8 pide arrancar
con al menos dos por capacidad, no con uno solo y la interfaz "por si acaso".
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


class ErrorProveedorIA(RuntimeError):
    """Fallo al hablar con el proveedor.

    Conserva el mensaje REAL del proveedor (§20.4.8): "Probar conexión" tiene que
    poder decir *por qué* falló —clave inválida, modelo inexistente, endpoint mal
    escrito— y no un genérico que obligue a adivinar.
    """

    def __init__(self, mensaje: str, proveedor: str = "", original: Exception | None = None):
        self.proveedor = proveedor
        self.original = original
        super().__init__(mensaje)


class ProveedorNoSoportado(RuntimeError):
    """No hay adaptador construido para ese `proveedor_tipo`."""


@dataclass(frozen=True)
class Credenciales:
    """Lo que un adaptador necesita para autenticarse, ya descifrado.

    Dos campos y no uno porque los esquemas del mercado son dos (§20.4.5): la
    mayoría de proveedores usa una única API Key, y los gateways corporativos o
    un motor propio del cliente usan Client ID + Client Secret. `credencial_2`
    es None en el caso común.
    """
    credencial_1: str | None = None
    credencial_2: str | None = None


@dataclass(frozen=True)
class ConfigProveedor:
    """Configuración resuelta de una conexión, lista para que el adaptador
    trabaje. Es lo que sale de `Security.DIM_IAConexion` una vez descifrada."""
    proveedor_tipo: str
    endpoint_url: str | None = None
    modelo: str | None = None
    credenciales: Credenciales = Credenciales()


# ---------------------------------------------------------------------------
# Capacidad TEXTO
# ---------------------------------------------------------------------------

class AdaptadorTexto(ABC):
    """Genera texto. Lo usan la generación de exámenes (ya existente) y las
    cápsulas del Refuerzo de Memoria (§10.2)."""

    #: Valor de `proveedor_tipo` que activa este adaptador.
    tipo: str = ""
    #: Endpoint por defecto, editable por el usuario (§20.4.4).
    endpoint_por_defecto: str | None = None

    def __init__(self, config: ConfigProveedor):
        self.config = config

    @abstractmethod
    def generar_texto(self, prompt: str, max_tokens: int = 4000) -> str:
        """Devuelve la respuesta como texto plano.

        Cada adaptador absorbe las rarezas de su proveedor y entrega siempre lo
        mismo: una cadena. Ahí es donde vive, por ejemplo, la necesidad de
        desactivar el razonamiento extendido en Claude — un detalle de ese
        proveedor que el resto de la aplicación no tiene por qué conocer.
        """

    def probar(self) -> str:
        """Verificación mínima para el botón "Probar conexión" (§20.4.8).

        Se pide una respuesta de una palabra a propósito: confirma credencial,
        endpoint y modelo gastando lo mínimo posible.
        """
        return self.generar_texto("Responde unicamente: OK", max_tokens=16)


# ---------------------------------------------------------------------------
# Capacidad VOZ
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Audio:
    """Resultado de sintetizar voz.

    `en_navegador=True` es el caso especial del §9.4: no hay audio que devolver
    porque la síntesis ocurre en el navegador del usuario con la Web Speech API.
    Se modela explícitamente en vez de devolver bytes vacíos para que quien
    consuma sepa que debe sintetizar del lado del cliente, y para que la
    limitación quede visible en el contrato y no escondida en un `if`.
    """
    contenido: bytes | None = None
    mime: str | None = None
    en_navegador: bool = False
    aviso: str | None = None


class AdaptadorVoz(ABC):
    """Sintetiza voz para el Simulacro de venta (§9.3/9.4)."""

    tipo: str = ""
    endpoint_por_defecto: str | None = None

    def __init__(self, config: ConfigProveedor):
        self.config = config

    @abstractmethod
    def sintetizar(self, texto: str, voz: str | None = None) -> Audio:
        """Convierte texto en audio."""

    def probar(self) -> str:
        self.sintetizar("Prueba de conexion")
        return "OK"
