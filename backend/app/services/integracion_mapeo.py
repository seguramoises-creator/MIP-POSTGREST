"""Buscar, ADOPTAR o crear: la primitiva que usan los nueve sincronizadores.

EL PASO QUE IMPORTA ES LA ADOPCIÓN
-----------------------------------
VISTA lleva meses en piloto con su maestro cargado por Excel, y esos registros
no tienen ningún identificador de Mallén. Una sincronización que solo supiera
«buscar por código externo; si no está, crear» duplicaría cada representante,
cada médico y cada gerente en la primera corrida.

Por eso el orden es: (1) ¿ya hay mapeo? actualizar; (2) ¿existe por su clave
natural? adoptarlo creando el mapeo; (3) recién entonces, crear.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.mapeo_externo import MapeoExterno

RESULTADO_ACTUALIZADO = "actualizado"
RESULTADO_ADOPTADO = "adoptado"
RESULTADO_CREADO = "creado"


def _buscar_mapeo(db: Session, entidad: str, pais_codigo: str,
                  codigo_externo: str) -> MapeoExterno | None:
    return (db.query(MapeoExterno)
            .filter(MapeoExterno.entidad == entidad,
                    MapeoExterno.pais_codigo == pais_codigo,
                    MapeoExterno.codigo_externo == codigo_externo)
            .first())


def id_mapeado(db: Session, entidad: str, pais_codigo: str,
               codigo_externo: str) -> int | None:
    """El id interno de un código externo ya sincronizado, o None.

    Es lo que usan las dimensiones para resolver sus claves foráneas contra las
    que se sincronizaron antes (un representante contra su gerente, por ejemplo).
    """
    m = _buscar_mapeo(db, entidad, pais_codigo, codigo_externo)
    return m.id_interno if m else None


def resolver(db: Session, entidad: str, pais_codigo: str, codigo_externo: str,
             modelo, buscar_natural, crear) -> tuple[object, str]:
    """Devuelve `(registro_interno, resultado)` y deja el mapeo al día.

    `buscar_natural` y `crear` son callables sin argumentos: cada dimensión sabe
    cuál es su clave natural y cómo construirse, y esta función no necesita
    saberlo. `crear` debe dejar el registro en la sesión con su `id` asignado
    (un `db.flush()` basta).

    No hace commit: el llamador decide la transacción, para que una dimensión
    entera se confirme junta.
    """
    m = _buscar_mapeo(db, entidad, pais_codigo, codigo_externo)
    if m is not None:
        registro = db.get(modelo, m.id_interno)
        if registro is not None:
            m.sincronizado_en = datetime.now(timezone.utc)
            return registro, RESULTADO_ACTUALIZADO
        # Mapeo huérfano: el registro interno se borró a mano. El mapeo es un
        # dato derivado, así que se descarta y se resuelve de nuevo en vez de
        # dejar esta fila bloqueada para siempre.
        db.delete(m)
        db.flush()

    existente = buscar_natural()
    if existente is not None:
        db.add(MapeoExterno(entidad=entidad, pais_codigo=pais_codigo,
                            codigo_externo=codigo_externo,
                            id_interno=existente.id))
        db.flush()
        return existente, RESULTADO_ADOPTADO

    nuevo = crear()
    db.add(MapeoExterno(entidad=entidad, pais_codigo=pais_codigo,
                        codigo_externo=codigo_externo, id_interno=nuevo.id))
    db.flush()
    return nuevo, RESULTADO_CREADO
