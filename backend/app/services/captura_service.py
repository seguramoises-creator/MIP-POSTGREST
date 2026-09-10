"""¿Puede esta instalación CAPTURAR visitas, o solo consultarlas?

POR QUÉ EXISTE. En Mallén las visitas entran por su propio SFA (esquema `ext`) y
VISTA no debe ser una segunda fuente de verdad: dos puertas para el mismo dato
terminan duplicándolo o pisándolo. Por eso la captura se cerró — devolviendo 409 en
los cinco endpoints de escritura, sin tocar servicio ni base.

Pero cerrarla *en el código* la cerró para TODOS. Y hay instalaciones donde la fuerza
de ventas registra su trabajo en VISTA y no existe ningún SFA del que traerlo: ahí la
captura no es una segunda puerta, es la única. Es exactamente el caso de la app móvil
del visitador médico.

Así que la decisión no es del código sino de la INSTALACIÓN, y ya hay un interruptor
para eso — el mismo que decide qué menús existen:

    MODO_INGESTA = integracion   los datos llegan del SFA del cliente → captura CERRADA
    MODO_INGESTA = excel|vista   los datos se capturan aquí          → captura ABIERTA

El valor de fábrica es `excel`, así que una instalación que nunca configuró nada
puede capturar; y Mallén, que sí lo tiene en `integracion`, sigue recibiendo el mismo
409 con el mismo texto que antes. Ese texto se conserva palabra por palabra a
propósito: un cliente que ya lo mostraba en pantalla no debe cambiar de mensaje
porque nosotros movimos un archivo.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.services import config_service as _cfg

#: El único modo que cierra la captura. Cualquier otro valor la deja abierta —incluido
#: uno escrito a mano por error—, y es deliberado: ante la duda, que el visitador pueda
#: registrar su trabajo. Perder una jornada de campo por un valor mal tecleado es peor
#: que aceptar un dato de más, que al menos se ve y se corrige.
MODO_CERRADO = "integracion"

MENSAJE_CERRADA = (
    "El registro de visitas está cerrado: las visitas provienen del SFA del "
    "cliente y se integran automáticamente. Lo ya registrado sigue disponible "
    "para consulta."
)


def captura_habilitada(db: Session) -> bool:
    """¿Se pueden escribir visitas en esta instalación?"""
    modo = (_cfg.obtener(db, "MODO_INGESTA") or "excel").strip().lower()
    return modo != MODO_CERRADO


def exigir_captura_habilitada(db: Session) -> None:
    """Guard de los endpoints de escritura de visitas. 409 y no 403: no es que al
    usuario le falte permiso —es que en esta instalación esa puerta no existe—, y un
    403 mandaría a buscar el permiso que falta durante media tarde."""
    if not captura_habilitada(db):
        raise HTTPException(status.HTTP_409_CONFLICT, MENSAJE_CERRADA)
