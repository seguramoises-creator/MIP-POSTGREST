"""Equivalencias del módulo de Prescripción IR (Close-Up) con VISTA.

QUÉ CONSTRUYE Y QUÉ NO
----------------------
Construye los tres puentes que la atribución de una receta necesita —
prescriptor, producto y período — y un diagnóstico que mide qué tan bien
resuelven. NO construye el indicador `EVO_IR`: el requerimiento reserva por
escrito la estructura del IR como la única que todavía puede cambiar
(pendiente 1 de §10) y manda verificar el exequátur con muestra real antes de
desarrollar (§11.9). Este módulo produce esa verificación.

POR QUÉ ENLAZA SIN CREAR
------------------------
Las nueve dimensiones de `integracion_dimensiones_service` crean el registro
interno cuando falta, y está bien: son el maestro de la operación. Aquí no.
`dimmedicoir` trae el universo de Close-Up, que es TODO el mercado (≈10.000
médicos, §9.1). Crear en `Config.DIM_Medico` a un prescriptor que ningún
representante trabaja lo metería en los denominadores de cobertura y
categorización, que es un daño silencioso: las cifras bajan y nada explica por
qué. Una receta cuyo prescriptor no se puede enlazar se cuenta para el mercado
y no se atribuye a nadie — literalmente lo que dice el §3.2 del contrato.
"""
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Ciclo, Medico, Producto
from app.models.integracion_ext import (
    ExtDimMedicoIR, ExtDimPeriodoIR, ExtDimProductoIR,
)
from app.models.mapeo_externo import (
    ENT_CICLO, ENT_MEDICO_IR, ENT_PERIODO_IR, ENT_PRODUCTO_IR, MapeoExterno,
)
from app.services import integracion_mapeo as mapeo
from app.services import maestro_medico_service
from app.services.integracion_dimensiones_service import (
    SEVERIDAD_AVISO, SEVERIDAD_ERROR, Hallazgo,
)

#: Los tres códigos externos caben de sobra en `MapeoExterno.codigo_externo`
#: (60): `medico_ir_codigo` y `producto_ir_codigo` son String(50) y
#: `periodo_codigo` String(20). Por eso aquí no hay guarda de longitud, a
#: diferencia de los integradores que construyen claves compuestas.

RESULTADO_ENLAZADO = "enlazado"
RESULTADO_YA_ENLAZADO = "ya_enlazado"
RESULTADO_NO_ENLAZADO = "no_enlazado"


@dataclass
class ConteoIR:
    """Distinto de `Conteo` de dimensiones a propósito: aquí nada se CREA.

    `omitidos` es el no-enlace ESPERADO (un producto de la competencia);
    `no_enlazados` es el que puede doler. Separarlos es lo que permite leer el
    resultado de un vistazo.
    """
    entidad: str
    en_ext: int = 0
    enlazados: int = 0
    ya_enlazados: int = 0
    no_enlazados: int = 0
    casi_enlazados: int = 0
    omitidos: int = 0

    def anotar(self, resultado: str) -> None:
        if resultado == RESULTADO_ENLAZADO:
            self.enlazados += 1
        elif resultado == RESULTADO_YA_ENLAZADO:
            self.ya_enlazados += 1
        else:
            self.no_enlazados += 1

    def como_dict(self) -> dict:
        return {"entidad": self.entidad, "en_ext": self.en_ext,
                "enlazados": self.enlazados, "ya_enlazados": self.ya_enlazados,
                "no_enlazados": self.no_enlazados,
                "casi_enlazados": self.casi_enlazados,
                "omitidos": self.omitidos}


def _enlazar(db: Session, entidad: str, pais_codigo: str, codigo_externo: str,
             modelo, buscar) -> tuple[object | None, str]:
    """Enlaza contra lo que ya existe; si no hay contraparte, devuelve `None`.

    NO es `integracion_mapeo.resolver`: aquél CREA el registro interno cuando no
    lo encuentra, que es lo correcto para las nueve dimensiones y exactamente lo
    que aquí no se debe hacer. Sí comparte su manejo del mapeo huérfano: si el
    registro interno se borró a mano, el mapeo se descarta y se resuelve de nuevo
    en vez de quedar bloqueado para siempre.
    """
    m = (db.query(MapeoExterno)
         .filter(MapeoExterno.entidad == entidad,
                 MapeoExterno.pais_codigo == pais_codigo,
                 MapeoExterno.codigo_externo == codigo_externo).first())
    if m is not None:
        registro = db.get(modelo, m.id_interno)
        if registro is not None:
            return registro, RESULTADO_YA_ENLAZADO
        db.delete(m)
        db.flush()

    existente = buscar()
    if existente is None:
        return None, RESULTADO_NO_ENLAZADO
    db.add(MapeoExterno(entidad=entidad, pais_codigo=pais_codigo,
                        codigo_externo=codigo_externo, id_interno=existente.id))
    db.flush()
    return existente, RESULTADO_ENLAZADO


def _solo_alfanumerico(valor: str | None) -> str:
    """Para detectar el CASI-enlace, nunca para enlazar."""
    return "".join(c for c in (valor or "") if c.isalnum()).upper()


def _indice_exequatur(db: Session, pais_codigo: str) -> dict[str, set[str]]:
    """Los exequátur del maestro, agrupados por su forma sin puntuación.

    Se construye UNA vez por corrida. La versión ingenua —consultar el maestro
    por cada prescriptor no enlazado— lo recorre entero miles de veces:
    `dimmedicoir` trae TODO el mercado (≈10.000 médicos, §9.1 del requerimiento),
    así que el coste sería el producto de los dos universos.
    """
    indice: dict[str, set[str]] = {}
    for (ex,) in (db.query(Medico.exequatur)
                  .filter(Medico.pais_codigo == pais_codigo,
                          Medico.activo == True,  # noqa: E712
                          Medico.exequatur.isnot(None)).all()):
        indice.setdefault(_solo_alfanumerico(ex), set()).add(ex)
    return indice


def _es_casi_enlace(indice: dict[str, set[str]], exequatur: str | None) -> bool:
    """¿Hay en el maestro un exequátur que solo difiere en formato?

    Es «casi» y no «enlace» a propósito: se cuenta y se muestra, nunca se
    enlaza. Si la única coincidencia es el propio valor, no hay casi-enlace —
    ese caso ya habría enlazado por la vía normal.
    """
    clave = _solo_alfanumerico(exequatur)
    if not clave:
        return False
    otros = indice.get(clave)
    return bool(otros) and otros != {exequatur}


def sincronizar_medico_ir(db: Session, pais_codigo: str,
                          hallazgos: list) -> ConteoIR:
    """`ext.dimmedicoir` → `Config.DIM_Medico`, por exequátur EXACTO.

    Reutiliza `maestro_medico_service.detectar_duplicados`, que es el criterio
    con el que el maestro decide si dos médicos son el mismo: compara el
    exequátur exacto, filtra por país y por activo. No se inventa aquí una
    normalización propia, aunque subiría la tasa de enlace — enlazaría como el
    mismo médico a dos que la deduplicación del maestro considera distintos, y
    el desacuerdo solo se descubriría cuando las cifras no cuadraran.

    NO emite hallazgo por prescriptor no enlazado: son miles y enterrarían los
    pocos que sí exigen acción. Se cuentan y el diagnóstico los muestra.
    """
    conteo = ConteoIR(ENT_MEDICO_IR)
    indice = _indice_exequatur(db, pais_codigo)
    filas = (db.query(ExtDimMedicoIR)
             .filter(ExtDimMedicoIR.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        duros = maestro_medico_service.detectar_duplicados(
            db, pais_codigo, exequatur=fila.exequatur)["duros"]
        if len(duros) > 1:
            # Acotado y accionable: es un defecto del maestro, no de Close-Up.
            conteo.no_enlazados += 1
            hallazgos.append(Hallazgo(
                ENT_MEDICO_IR, fila.medico_ir_codigo,
                f"El exequátur «{fila.exequatur}» aparece en {len(duros)} médicos "
                f"del maestro; no se puede decidir a cuál enlazar. Deduplica el "
                f"maestro y vuelve a sincronizar.", SEVERIDAD_ERROR))
            continue

        def _buscar(ids=[d["id"] for d in duros]):
            return db.get(Medico, ids[0]) if ids else None

        registro, resultado = _enlazar(db, ENT_MEDICO_IR, pais_codigo,
                                       fila.medico_ir_codigo, Medico, _buscar)
        conteo.anotar(resultado)
        if registro is None and _es_casi_enlace(indice, fila.exequatur):
            conteo.casi_enlazados += 1
    return conteo


def sincronizar_producto_ir(db: Session, pais_codigo: str,
                            hallazgos: list) -> ConteoIR:
    """`ext.dimproductoir` → `Config.DIM_Producto`, por la equivalencia que la
    propia dimensión trae en `producto_codigo`.

    Los productos de la competencia llegan a propósito y sin equivalencia
    (§11.8): hacen falta para medir participación de mercado. Que no mapeen es
    lo ESPERADO y no genera hallazgo. Lo que sí es error es un producto marcado
    `es_propio` sin equivalencia: sus recetas no las va a poder contar nadie.
    """
    conteo = ConteoIR(ENT_PRODUCTO_IR)
    filas = (db.query(ExtDimProductoIR)
             .filter(ExtDimProductoIR.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not fila.producto_codigo:
            if fila.es_propio:
                conteo.no_enlazados += 1
                hallazgos.append(Hallazgo(
                    ENT_PRODUCTO_IR, fila.producto_ir_codigo,
                    f"El producto «{fila.nombre}» está marcado como propio pero no "
                    f"trae equivalencia con el catálogo de Mallén; sus recetas no "
                    f"se podrán contar.", SEVERIDAD_ERROR))
            else:
                conteo.omitidos += 1
            continue

        def _buscar(f=fila):
            return db.query(Producto).filter(
                Producto.codigo == f.producto_codigo).first()

        registro, resultado = _enlazar(db, ENT_PRODUCTO_IR, pais_codigo,
                                       fila.producto_ir_codigo, Producto, _buscar)
        conteo.anotar(resultado)
        if registro is None and fila.es_propio:
            hallazgos.append(Hallazgo(
                ENT_PRODUCTO_IR, fila.producto_ir_codigo,
                f"El producto propio «{fila.nombre}» declara la equivalencia "
                f"«{fila.producto_codigo}», que no existe en el catálogo de VISTA.",
                SEVERIDAD_ERROR))
    return conteo


def sincronizar_periodo_ir(db: Session, pais_codigo: str,
                           hallazgos: list) -> ConteoIR:
    """`ext.dimperiodoir` → `Config.DIM_Ciclo`, por el `ciclo_codigo` que la
    dimensión declara.

    Si viene nulo, el mes de Close-Up no pertenece a ningún ciclo y sus recetas
    no se pueden ubicar en el tiempo de VISTA. NO se adivina por fechas: la
    dimensión trae `fecha_inicio`/`fecha_fin`, pero derivar de ahí sustituiría
    una decisión de Mallén por una inferencia nuestra, y un mes puede solapar
    dos ciclos.
    """
    conteo = ConteoIR(ENT_PERIODO_IR)
    filas = (db.query(ExtDimPeriodoIR)
             .filter(ExtDimPeriodoIR.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not fila.ciclo_codigo:
            conteo.no_enlazados += 1
            hallazgos.append(Hallazgo(
                ENT_PERIODO_IR, fila.periodo_codigo,
                f"El período «{fila.periodo_codigo}» no declara a qué ciclo "
                f"pertenece; sus recetas no se pueden ubicar en el tiempo.",
                SEVERIDAD_AVISO))
            continue

        def _buscar(f=fila):
            cid = mapeo.id_mapeado(db, ENT_CICLO, pais_codigo, f.ciclo_codigo)
            return db.get(Ciclo, cid) if cid else None

        registro, resultado = _enlazar(db, ENT_PERIODO_IR, pais_codigo,
                                       fila.periodo_codigo, Ciclo, _buscar)
        conteo.anotar(resultado)
        if registro is None:
            hallazgos.append(Hallazgo(
                ENT_PERIODO_IR, fila.periodo_codigo,
                f"El ciclo «{fila.ciclo_codigo}» del período no está sincronizado; "
                f"corre primero la sincronización de dimensiones.",
                SEVERIDAD_AVISO))
    return conteo


_PUENTES = (sincronizar_medico_ir, sincronizar_producto_ir, sincronizar_periodo_ir)


def sincronizar_ir(db: Session, pais_codigo: str) -> dict:
    """Los tres puentes, un solo commit al final.

    El orden no importa: a diferencia de las nueve dimensiones, ninguno de los
    tres resuelve claves contra los otros. Se mantiene fijo solo para que la
    salida sea estable.
    """
    hallazgos: list[Hallazgo] = []
    conteos = [puente(db, pais_codigo, hallazgos) for puente in _PUENTES]
    db.commit()

    errores = sum(1 for h in hallazgos if h.severidad == SEVERIDAD_ERROR)
    logger.info(f"Equivalencias IR de {pais_codigo}: "
                f"{sum(c.enlazados for c in conteos)} enlazadas, "
                f"{sum(c.no_enlazados for c in conteos)} sin enlazar, "
                f"{errores} con error")
    return {
        "pais_codigo": pais_codigo,
        "entidades": [c.como_dict() for c in conteos],
        "hallazgos": [{"entidad": h.entidad, "codigo_externo": h.codigo_externo,
                       "problema": h.problema, "severidad": h.severidad}
                      for h in hallazgos],
    }
