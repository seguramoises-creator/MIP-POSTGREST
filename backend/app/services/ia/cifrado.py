"""Cifrado en reposo de las credenciales de IA (§20.6, no negociable).

POR QUÉ UNA LLAVE PROPIA Y NO `JWT_SECRET_KEY`
-----------------------------------------------
Sería cómodo derivar la llave de cifrado del secreto JWT que ya existe, y es un
error caro: **rotar `JWT_SECRET_KEY` es una operación normal y esperada** — se
hace al clonar un ambiente, y este proyecto ya la rotó al publicar el servidor de
ensayo. Si las credenciales dependieran de ese secreto, esa rotación las dejaría
imposibles de descifrar, sin aviso y sin forma de recuperarlas.

Por eso `IA_CRED_KEY` es una llave dedicada, con su propio ciclo de vida.

QUÉ PASA SI NO ESTÁ CONFIGURADA
--------------------------------
El módulo NO inventa una llave al vuelo ni cae a un cifrado de juguete: guardar
una credencial falla con un mensaje que dice exactamente cómo generarla. Una
llave efímera daría la ilusión de que todo funciona hasta el primer reinicio,
cuando las credenciales guardadas dejarían de leerse.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class LlaveCifradoNoConfigurada(RuntimeError):
    """Falta `IA_CRED_KEY`. Lleva la instrucción para resolverlo, porque este
    error lo va a ver quien despliega, no quien programó esto."""

    def __init__(self) -> None:
        super().__init__(
            "No se pueden guardar credenciales de IA: falta IA_CRED_KEY en el "
            "entorno. Genera una con:\n"
            "    python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"\n"
            "y agrégala a backend/.env como IA_CRED_KEY=<valor>. Es propia de "
            "cada ambiente y NO debe compartirse entre calidad y producción. "
            "Si se pierde, las credenciales ya guardadas no se pueden recuperar "
            "y hay que volver a cargarlas."
        )


class CredencialIlegible(RuntimeError):
    """La credencial existe pero no se puede descifrar. Casi siempre significa
    que `IA_CRED_KEY` cambió después de haberla guardado."""


def _motor() -> Fernet:
    llave = (getattr(settings, "IA_CRED_KEY", "") or "").strip()
    if not llave:
        raise LlaveCifradoNoConfigurada()
    try:
        return Fernet(llave.encode())
    except Exception as exc:  # noqa: BLE001
        raise LlaveCifradoNoConfigurada() from exc


def hay_llave() -> bool:
    """Para que la interfaz pueda avisar ANTES de que el usuario llene el
    formulario, en vez de fallarle al guardar."""
    try:
        _motor()
        return True
    except LlaveCifradoNoConfigurada:
        return False


def cifrar(valor: str | None) -> str | None:
    if valor is None or valor == "":
        return None
    return _motor().encrypt(valor.encode()).decode()


def descifrar(valor: str | None) -> str | None:
    if not valor:
        return None
    try:
        return _motor().decrypt(valor.encode()).decode()
    except InvalidToken as exc:
        raise CredencialIlegible(
            "La credencial no se pudo descifrar. Lo más probable es que "
            "IA_CRED_KEY haya cambiado desde que se guardó: vuelve a cargar la "
            "credencial en Administración → Conexiones de IA."
        ) from exc


def enmascarar(valor_cifrado: str | None) -> str | None:
    """Lo único que se devuelve por la API (§20.6): una credencial guardada
    nunca se vuelve a mostrar en claro, solo se puede reemplazar.

    Se enmascara a partir del valor real para conservar las últimas 4 posiciones,
    que es lo que permite a un administrador reconocer *cuál* clave tiene puesta
    sin exponerla.
    """
    if not valor_cifrado:
        return None
    try:
        claro = descifrar(valor_cifrado) or ""
    except (CredencialIlegible, LlaveCifradoNoConfigurada):
        return "••••••••"
    if len(claro) <= 4:
        return "••••••••"
    return f"{claro[:3]}…{claro[-4:]}"
