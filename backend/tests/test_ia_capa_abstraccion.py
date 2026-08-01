"""Capa de abstracción de IA (§20).

Lo que se protege aquí es la propiedad que el cliente pidió: que cambiar de
proveedor sea configuración y no código, y que las credenciales nunca se
guarden ni se devuelvan en claro.

Ninguna prueba sale a la red.
"""
import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.services.ia import adaptadores, cifrado, conexion_service
from app.services.ia.base import (
    AdaptadorTexto, AdaptadorVoz, ConfigProveedor, Credenciales, ProveedorNoSoportado,
)


@pytest.fixture
def con_llave(monkeypatch):
    monkeypatch.setattr(settings, "IA_CRED_KEY", Fernet.generate_key().decode())


@pytest.fixture
def sin_llave(monkeypatch):
    monkeypatch.setattr(settings, "IA_CRED_KEY", "")


# ---------------------------------------------------------------------------
# Cifrado (§20.6)
# ---------------------------------------------------------------------------

def test_la_credencial_va_y_vuelve_intacta(con_llave):
    secreto = "sk-proj-ABC123xyz"
    guardado = cifrado.cifrar(secreto)
    assert guardado != secreto, "se guardó en claro"
    assert cifrado.descifrar(guardado) == secreto


def test_sin_llave_no_se_guarda_y_el_error_dice_como_arreglarlo(sin_llave):
    """Quien va a leer este error es quien despliega, no quien programó esto."""
    with pytest.raises(cifrado.LlaveCifradoNoConfigurada) as e:
        cifrado.cifrar("algo")
    mensaje = str(e.value)
    assert "IA_CRED_KEY" in mensaje
    assert "Fernet.generate_key" in mensaje


def test_una_llave_distinta_no_puede_leer_lo_cifrado_con_otra(con_llave, monkeypatch):
    """Es el escenario real de rotar la llave: debe fallar de forma explícita y
    decir qué pasó, no devolver basura silenciosamente."""
    guardado = cifrado.cifrar("secreto")
    monkeypatch.setattr(settings, "IA_CRED_KEY", Fernet.generate_key().decode())
    with pytest.raises(cifrado.CredencialIlegible) as e:
        cifrado.descifrar(guardado)
    assert "IA_CRED_KEY" in str(e.value)


def test_el_enmascarado_no_revela_la_credencial(con_llave):
    secreto = "sk-proj-SUPERSECRETO-9999"
    mascara = cifrado.enmascarar(cifrado.cifrar(secreto))
    assert secreto not in mascara
    assert mascara.endswith("9999"), "debe dejar reconocer cuál clave está puesta"
    assert len(mascara) < len(secreto)


def test_una_credencial_corta_se_oculta_por_completo(con_llave):
    """Con un valor corto, dejar las últimas 4 posiciones lo revelaría entero."""
    assert cifrado.enmascarar(cifrado.cifrar("abc")) == "••••••••"


def test_sin_llave_el_enmascarado_no_revienta(sin_llave):
    """La pantalla de configuración tiene que poder listar las conexiones aunque
    falte la llave — si no, no habría forma de entrar a arreglarlo."""
    assert cifrado.enmascarar("loquesea") == "••••••••"
    assert cifrado.hay_llave() is False


# ---------------------------------------------------------------------------
# Adaptadores (§20.3 y §20.8)
# ---------------------------------------------------------------------------

def test_hay_mas_de_un_adaptador_por_capacidad():
    """§20.8: una abstracción con un solo proveedor real detrás no está probada.
    Con dos o más se verifica que la interfaz no filtra detalles de uno."""
    assert len(adaptadores.ADAPTADORES_TEXTO) >= 2
    assert len(adaptadores.ADAPTADORES_VOZ) >= 2


@pytest.mark.parametrize("tipo", sorted(adaptadores.ADAPTADORES_TEXTO))
def test_todo_adaptador_de_texto_cumple_la_interfaz(tipo):
    a = adaptadores.construir("texto", ConfigProveedor(proveedor_tipo=tipo))
    assert isinstance(a, AdaptadorTexto)


@pytest.mark.parametrize("tipo", sorted(adaptadores.ADAPTADORES_VOZ))
def test_todo_adaptador_de_voz_cumple_la_interfaz(tipo):
    a = adaptadores.construir("voz", ConfigProveedor(proveedor_tipo=tipo))
    assert isinstance(a, AdaptadorVoz)


def test_un_proveedor_sin_adaptador_falla_diciendo_cuales_hay():
    with pytest.raises(ProveedorNoSoportado) as e:
        adaptadores.construir("texto", ConfigProveedor(proveedor_tipo="inventado"))
    assert "anthropic" in str(e.value), "el error debe listar los disponibles"


def test_el_detalle_de_claude_vive_dentro_de_su_adaptador(monkeypatch):
    """La desactivación del razonamiento extendido es una rareza de Claude. Que
    esté DENTRO del adaptador es lo que permite cambiar de proveedor sin
    arrastrarla: ningún otro adaptador la conoce."""
    capturado = {}

    class _Mensajes:
        def create(self, **kw):
            capturado.update(kw)
            return type("R", (), {"content": [type("B", (), {"text": "hola"})()]})()

    class _Cliente:
        def __init__(self, **kw):
            capturado["cliente_kw"] = kw
            self.messages = _Mensajes()

    monkeypatch.setitem(__import__("sys").modules, "anthropic",
                        type("M", (), {"Anthropic": _Cliente}))
    a = adaptadores.TextoAnthropic(ConfigProveedor(
        proveedor_tipo="anthropic", modelo="claude-opus-5",
        credenciales=Credenciales(credencial_1="k")))
    assert a.generar_texto("hola", max_tokens=99) == "hola"
    assert capturado["extra_body"] == {"thinking": {"type": "disabled"}}
    assert capturado["model"] == "claude-opus-5"
    assert capturado["max_tokens"] == 99


def test_claude_ignora_los_bloques_sin_texto(monkeypatch):
    """Los bloques de razonamiento traen `.text` en None y reventarían el join."""
    class _Mensajes:
        def create(self, **kw):
            bloques = [type("B", (), {"text": None})(), type("B", (), {"text": "ok"})()]
            return type("R", (), {"content": bloques})()

    monkeypatch.setitem(
        __import__("sys").modules, "anthropic",
        type("M", (), {"Anthropic": lambda **kw: type("C", (), {"messages": _Mensajes()})()}))
    a = adaptadores.TextoAnthropic(ConfigProveedor(proveedor_tipo="anthropic"))
    assert a.generar_texto("x") == "ok"


def test_azure_exige_su_endpoint_propio():
    """No existe una URL genérica de Azure OpenAI: cada cuenta tiene la suya, y
    por eso el §20.4.4 pide que el campo quede editable."""
    a = adaptadores.TextoAzureOpenAI(ConfigProveedor(proveedor_tipo="azure_openai"))
    with pytest.raises(adaptadores.ErrorProveedorIA) as e:
        a.generar_texto("x")
    assert "endpoint" in str(e.value).lower()


def test_la_voz_de_navegador_avisa_de_su_limitacion():
    """§9.4: no hay voz dominicana auténtica en el navegador. La limitación
    viaja en el contrato, no escondida."""
    audio = adaptadores.VozNavegador(ConfigProveedor(proveedor_tipo="navegador")).sintetizar("hola")
    assert audio.en_navegador is True
    assert audio.contenido is None
    assert "dominicano" in (audio.aviso or "")


# ---------------------------------------------------------------------------
# Servicio de conexiones (§20.4)
# ---------------------------------------------------------------------------

def test_no_se_admite_un_proveedor_sin_adaptador():
    with pytest.raises(ValueError) as e:
        conexion_service._validar("texto", "api_key", "inventado")
    assert "Disponibles" in str(e.value)


def test_no_se_admite_una_capacidad_inventada():
    with pytest.raises(ValueError):
        conexion_service._validar("imagen", "api_key", "openai")


def test_la_lista_de_proveedores_sale_de_los_adaptadores_construidos():
    """Para que el desplegable de la interfaz no se desactualice respecto al
    código."""
    disponibles = conexion_service.proveedores_disponibles()
    assert set(disponibles) == {"texto", "voz"}
    assert sorted(adaptadores.ADAPTADORES_TEXTO) == disponibles["texto"]


def test_el_respaldo_del_entorno_evita_apagar_lo_que_ya_funcionaba(monkeypatch):
    """Introducir esta capa no debe dejar sin generación de exámenes a quien ya
    tenía su clave en el .env y aún no configuró una conexión."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-viejo")
    cfg = conexion_service._respaldo_entorno("texto")
    assert cfg is not None
    assert cfg.proveedor_tipo == "anthropic"
    assert cfg.credenciales.credencial_1 == "sk-viejo"


def test_sin_clave_en_el_entorno_no_hay_respaldo(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    assert conexion_service._respaldo_entorno("texto") is None


def test_la_voz_no_hereda_respaldo_del_entorno(monkeypatch):
    """La voz nunca estuvo configurada por entorno: inventarle un respaldo daría
    una conexión que no existe."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-viejo")
    assert conexion_service._respaldo_entorno("voz") is None


def test_sin_conexion_ni_respaldo_el_error_dice_donde_configurarlo(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    with pytest.raises(conexion_service.SinConexionIA) as e:
        conexion_service.adaptador_texto(None)
    assert "Conexiones de IA" in str(e.value)


def test_lo_que_sale_por_la_api_nunca_trae_la_credencial(con_llave):
    """§20.6: una vez guardada, la credencial solo se puede reemplazar, nunca
    revelar."""
    from app.models.ia_conexion import IAConexion
    c = IAConexion(
        id=1, nombre="OpenAI - Principal", capacidad="texto", proveedor_tipo="openai",
        metodo_auth="api_key",
        credencial_1_cifrada=cifrado.cifrar("sk-proj-NODEBEAPARECER"),
        credencial_2_cifrada=None, activa=True, verificada=True)
    d = conexion_service.a_dict(c)
    assert "sk-proj-NODEBEAPARECER" not in str(d)
    assert d["credencial_1"].endswith("ARECER"[-4:])
    assert d["credencial_2"] is None
