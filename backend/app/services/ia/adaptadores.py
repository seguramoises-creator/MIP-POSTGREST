"""Adaptadores concretos por proveedor (§20.3).

Cada clase absorbe las rarezas de SU proveedor y expone la misma interfaz de
`base.py`. El resto de VISTA no sabe cuál está detrás.

Hay varios a propósito, no uno solo con la interfaz "por si acaso": el §20.8 pide
arrancar con al menos dos por capacidad, porque una abstracción con un único
proveedor real detrás no está probada — se descubre que filtraba detalles del
proveedor justo el día que hay que cambiarlo.

Se usa `httpx` (ya es dependencia) para los que hablan REST, y el SDK de
Anthropic solo donde ya estaba en uso, para no alterar un comportamiento que hoy
funciona en producción.
"""
import json

import httpx

from app.services.ia.base import (
    AdaptadorTexto, AdaptadorVoz, Audio, ConfigProveedor, ErrorProveedorIA,
    ProveedorNoSoportado,
)

TIEMPO_LIMITE = 120.0  # generar un examen completo puede tardar bastante


def _pedir(metodo: str, url: str, proveedor: str, **kwargs) -> httpx.Response:
    """Llamada HTTP con el error del proveedor conservado tal cual.

    El cuerpo de la respuesta se incluye en el mensaje porque es donde los
    proveedores explican de verdad qué pasó ("model not found", "invalid api
    key"); sin él, "Probar conexión" solo podría decir '401' y dejar al
    administrador adivinando.
    """
    try:
        r = httpx.request(metodo, url, timeout=TIEMPO_LIMITE, **kwargs)
    except httpx.HTTPError as exc:
        raise ErrorProveedorIA(f"No se pudo contactar el endpoint: {exc}", proveedor, exc) from exc
    if r.status_code >= 400:
        detalle = (r.text or "")[:500]
        raise ErrorProveedorIA(f"HTTP {r.status_code}: {detalle}", proveedor)
    return r


# ===========================================================================
# TEXTO
# ===========================================================================

class TextoAnthropic(AdaptadorTexto):
    """Claude, vía el SDK oficial que el proyecto ya usaba."""
    tipo = "anthropic"
    endpoint_por_defecto = "https://api.anthropic.com"

    def generar_texto(self, prompt: str, max_tokens: int = 4000) -> str:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise ErrorProveedorIA("Falta el paquete `anthropic`.", self.tipo, exc) from exc
        cliente_kw = {"api_key": self.config.credenciales.credencial_1}
        if self.config.endpoint_url:
            cliente_kw["base_url"] = self.config.endpoint_url
        cliente = anthropic.Anthropic(**cliente_kw)
        try:
            respuesta = cliente.messages.create(
                model=self.config.modelo or "claude-sonnet-5",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                # Detalle EXCLUSIVO de Claude, y por eso vive aquí dentro: en los
                # modelos nuevos el "extended thinking" viene activo y se come el
                # presupuesto de tokens, devolviendo el bloque de texto vacío o
                # truncado. Va por extra_body porque el SDK instalado no acepta
                # el kwarg nativo.
                extra_body={"thinking": {"type": "disabled"}})
        except Exception as exc:  # noqa: BLE001
            raise ErrorProveedorIA(str(exc), self.tipo, exc) from exc
        # Algunos bloques traen `.text` en None (razonamiento): `or ""` los ignora
        # en vez de reventar el join con un TypeError.
        return "".join((getattr(b, "text", "") or "") for b in respuesta.content)


class TextoOpenAI(AdaptadorTexto):
    """OpenAI y cualquier servicio que hable su API de chat."""
    tipo = "openai"
    endpoint_por_defecto = "https://api.openai.com/v1/chat/completions"

    def generar_texto(self, prompt: str, max_tokens: int = 4000) -> str:
        url = self.config.endpoint_url or self.endpoint_por_defecto
        r = _pedir("POST", url, self.tipo,
                   headers={"Authorization": f"Bearer {self.config.credenciales.credencial_1}",
                            "Content-Type": "application/json"},
                   json={"model": self.config.modelo or "gpt-4o",
                         "max_tokens": max_tokens,
                         "messages": [{"role": "user", "content": prompt}]})
        try:
            return r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ErrorProveedorIA(f"Respuesta inesperada: {r.text[:300]}", self.tipo, exc) from exc


class TextoAzureOpenAI(AdaptadorTexto):
    """Azure OpenAI: misma forma de cuerpo que OpenAI, pero autentica con la
    cabecera `api-key` y **exige un endpoint propio de la cuenta** — por eso el
    §20.4.4 insiste en que la URL quede editable aunque el proveedor sea
    conocido: aquí no existe una URL genérica que sirva."""
    tipo = "azure_openai"
    endpoint_por_defecto = None

    def generar_texto(self, prompt: str, max_tokens: int = 4000) -> str:
        if not self.config.endpoint_url:
            raise ErrorProveedorIA(
                "Azure OpenAI requiere el endpoint propio de tu cuenta "
                "(https://<recurso>.openai.azure.com/...).", self.tipo)
        r = _pedir("POST", self.config.endpoint_url, self.tipo,
                   headers={"api-key": self.config.credenciales.credencial_1 or "",
                            "Content-Type": "application/json"},
                   json={"max_tokens": max_tokens,
                         "messages": [{"role": "user", "content": prompt}]})
        try:
            return r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ErrorProveedorIA(f"Respuesta inesperada: {r.text[:300]}", self.tipo, exc) from exc


class TextoGemini(AdaptadorTexto):
    """Google Gemini. Estructura de cuerpo y de respuesta distinta a las
    anteriores (`contents`/`parts` en vez de `messages`), que es exactamente el
    tipo de diferencia que esta capa existe para ocultar."""
    tipo = "google_gemini"
    endpoint_por_defecto = "https://generativelanguage.googleapis.com/v1beta/models"

    def generar_texto(self, prompt: str, max_tokens: int = 4000) -> str:
        base = self.config.endpoint_url or self.endpoint_por_defecto
        modelo = self.config.modelo or "gemini-1.5-pro"
        url = f"{base}/{modelo}:generateContent"
        r = _pedir("POST", url, self.tipo,
                   params={"key": self.config.credenciales.credencial_1},
                   headers={"Content-Type": "application/json"},
                   json={"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"maxOutputTokens": max_tokens}})
        try:
            partes = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") or "" for p in partes)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ErrorProveedorIA(f"Respuesta inesperada: {r.text[:300]}", self.tipo, exc) from exc


class TextoRestGenerico(AdaptadorTexto):
    """"Otro / Compatible con API REST" (§20.4.3).

    Es la opción que permite conectar un motor de IA propio de Laboratorio
    Mallén o un gateway corporativo sin que nadie tenga que escribir un
    adaptador nuevo. Asume el formato de chat de OpenAI, que es el de facto, y
    soporta los dos métodos de autenticación del §20.4.5.
    """
    tipo = "otro"
    endpoint_por_defecto = None

    def generar_texto(self, prompt: str, max_tokens: int = 4000) -> str:
        if not self.config.endpoint_url:
            raise ErrorProveedorIA("Este proveedor requiere una URL de endpoint.", self.tipo)
        cred = self.config.credenciales
        cabeceras = {"Content-Type": "application/json"}
        auth = None
        if cred.credencial_2:
            # Client ID + Client Secret → autenticación básica, el esquema
            # habitual de los gateways corporativos.
            auth = (cred.credencial_1 or "", cred.credencial_2)
        elif cred.credencial_1:
            cabeceras["Authorization"] = f"Bearer {cred.credencial_1}"
        r = _pedir("POST", self.config.endpoint_url, self.tipo,
                   headers=cabeceras, auth=auth,
                   json={"model": self.config.modelo,
                         "max_tokens": max_tokens,
                         "messages": [{"role": "user", "content": prompt}]})
        cuerpo = r.json()
        # Se aceptan varias formas de respuesta porque un motor propio no tiene
        # por qué copiar exactamente la de OpenAI.
        for extraer in (lambda d: d["choices"][0]["message"]["content"],
                        lambda d: d["choices"][0]["text"],
                        lambda d: d["output"],
                        lambda d: d["text"]):
            try:
                valor = extraer(cuerpo)
                if isinstance(valor, str):
                    return valor
            except (KeyError, IndexError, TypeError):
                continue
        raise ErrorProveedorIA(
            f"No se reconoció el formato de la respuesta: {r.text[:300]}", self.tipo)


# ===========================================================================
# VOZ
# ===========================================================================

class VozElevenLabs(AdaptadorVoz):
    """ElevenLabs. Es el único camino hoy para una voz con acento dominicano
    real: el §9.4 documenta que ningún navegador la ofrece."""
    tipo = "elevenlabs"
    endpoint_por_defecto = "https://api.elevenlabs.io/v1/text-to-speech"

    def sintetizar(self, texto: str, voz: str | None = None) -> Audio:
        base = self.config.endpoint_url or self.endpoint_por_defecto
        voz_id = voz or self.config.modelo
        if not voz_id:
            raise ErrorProveedorIA(
                "Falta el identificador de la voz (campo Modelo).", self.tipo)
        r = _pedir("POST", f"{base}/{voz_id}", self.tipo,
                   headers={"xi-api-key": self.config.credenciales.credencial_1 or "",
                            "Content-Type": "application/json"},
                   json={"text": texto, "model_id": "eleven_multilingual_v2"})
        return Audio(contenido=r.content, mime="audio/mpeg")


class VozRestGenerico(AdaptadorVoz):
    """Cualquier servicio de voz que devuelva audio por REST."""
    tipo = "otro"
    endpoint_por_defecto = None

    def sintetizar(self, texto: str, voz: str | None = None) -> Audio:
        if not self.config.endpoint_url:
            raise ErrorProveedorIA("Este proveedor requiere una URL de endpoint.", self.tipo)
        cred = self.config.credenciales
        cabeceras = {"Content-Type": "application/json"}
        auth = (cred.credencial_1 or "", cred.credencial_2) if cred.credencial_2 else None
        if not auth and cred.credencial_1:
            cabeceras["Authorization"] = f"Bearer {cred.credencial_1}"
        r = _pedir("POST", self.config.endpoint_url, self.tipo,
                   headers=cabeceras, auth=auth,
                   json={"text": texto, "voice": voz or self.config.modelo})
        return Audio(contenido=r.content,
                     mime=r.headers.get("content-type", "audio/mpeg"))


class VozNavegador(AdaptadorVoz):
    """Web Speech API — la síntesis ocurre en el navegador del usuario.

    Es el comportamiento del mockup y sirve para desarrollo, pero **no es apto
    para producción con clientes reales**: el §9.4 deja claro que ningún
    navegador ofrece hoy una voz con acento dominicano auténtico, y que resolver
    eso con configuración del navegador no es posible. Este adaptador existe
    para que esa limitación viaje explícita en el contrato —con su aviso— en vez
    de esconderse tras una voz genérica que suena mal y nadie sabe por qué.
    """
    tipo = "navegador"
    endpoint_por_defecto = None

    def sintetizar(self, texto: str, voz: str | None = None) -> Audio:
        return Audio(
            en_navegador=True,
            aviso="La voz se sintetiza en el navegador (Web Speech API). Ningún "
                  "navegador ofrece acento dominicano auténtico: para producción "
                  "hay que configurar un proveedor de voz por IA.")

    def probar(self) -> str:
        return "OK (no requiere conexión: la síntesis ocurre en el navegador)"


# ===========================================================================
# Registro
# ===========================================================================

ADAPTADORES_TEXTO: dict[str, type[AdaptadorTexto]] = {
    a.tipo: a for a in (TextoAnthropic, TextoOpenAI, TextoAzureOpenAI,
                        TextoGemini, TextoRestGenerico)
}
ADAPTADORES_VOZ: dict[str, type[AdaptadorVoz]] = {
    a.tipo: a for a in (VozElevenLabs, VozRestGenerico, VozNavegador)
}


def construir(capacidad: str, config: ConfigProveedor) -> AdaptadorTexto | AdaptadorVoz:
    """Devuelve el adaptador que corresponde. Es el ÚNICO punto donde
    `proveedor_tipo` se traduce a una clase concreta."""
    registro = ADAPTADORES_TEXTO if capacidad == "texto" else ADAPTADORES_VOZ
    clase = registro.get(config.proveedor_tipo)
    if clase is None:
        disponibles = ", ".join(sorted(registro))
        raise ProveedorNoSoportado(
            f"No hay adaptador de {capacidad} para '{config.proveedor_tipo}'. "
            f"Disponibles: {disponibles}.")
    return clase(config)
