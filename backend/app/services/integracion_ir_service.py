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
    ExtDimMedicoIR, ExtDimPeriodoIR, ExtDimProductoIR, ExtFactPrescripcionDetalle,
)
from app.models.mapeo_externo import (
    ENT_CICLO, ENT_MEDICO_IR, ENT_PERIODO_IR, ENT_PRODUCTO_IR, MapeoExterno,
)
from app.services import integracion_mapeo as mapeo
from app.services import maestro_medico_service
from app.services.integracion_dimensiones_service import (
    SEVERIDAD_AVISO, SEVERIDAD_ERROR, Hallazgo,
)
#: Módulo-level y no dentro de `atribuir` (Ronda de correcciones 1, hallazgo
#: menor): un import dentro de una función que corre una vez POR RECETA se
#: resuelve una vez por receta. `visita_aprobacion_service` no importa nada de
#: este módulo, así que no hay ciclo que evitar con un import perezoso.
from app.services.visita_aprobacion_service import cuenta_en_ciclo

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


# ===========================================================================
# La cadena de atribución
# ===========================================================================

ATR_DIRECTA = "directa"
ATR_CADENA = "por_cadena"
ATR_AMBIGUA = "ambigua"
ATR_HUERFANA = "huerfana"


@dataclass
class ContextoAtribucion:
    """Todo lo que la atribución necesita, resuelto UNA vez por corrida.

    Sin esto, cada receta dispararía media docena de consultas: `ext` puede
    traer cientos de miles de filas por período.
    """
    pais_codigo: str
    #: código externo → id interno, de los tres puentes
    medicos: dict = field(default_factory=dict)
    productos: dict = field(default_factory=dict)
    periodos: dict = field(default_factory=dict)
    #: rm_codigo de Mallén → id interno
    representantes: dict = field(default_factory=dict)
    #: id de DIM_Producto → linea_id (puede ser None)
    linea_de_producto: dict = field(default_factory=dict)
    #: id de DIM_Medico → [(vm_id, linea_id del vm, fila de panel)]
    paneles: dict = field(default_factory=dict)
    #: id de DIM_Ciclo → orden (anio*1000+numero), de `ordenes_ciclo`
    ordenes: dict = field(default_factory=dict)


def _mapa(db: Session, entidad: str, pais_codigo: str) -> dict:
    return {m.codigo_externo: m.id_interno
            for m in db.query(MapeoExterno).filter(
                MapeoExterno.entidad == entidad,
                MapeoExterno.pais_codigo == pais_codigo).all()}


def _contexto(db: Session, pais_codigo: str) -> ContextoAtribucion:
    from app.models.dimensiones import RepresentanteMedico
    from app.models.mapeo_externo import ENT_REPRESENTANTE
    from app.models.visita import MedicoVisita
    from app.services.visita_aprobacion_service import ordenes_ciclo

    ctx = ContextoAtribucion(pais_codigo=pais_codigo)
    ctx.medicos = _mapa(db, ENT_MEDICO_IR, pais_codigo)
    ctx.productos = _mapa(db, ENT_PRODUCTO_IR, pais_codigo)
    ctx.periodos = _mapa(db, ENT_PERIODO_IR, pais_codigo)
    ctx.representantes = _mapa(db, ENT_REPRESENTANTE, pais_codigo)
    ctx.ordenes = ordenes_ciclo(db)

    for p in db.query(Producto).all():
        ctx.linea_de_producto[p.id] = p.linea_id

    lineas_rm = {r.id: r.linea_id for r in
                 db.query(RepresentanteMedico).filter(
                     RepresentanteMedico.pais_codigo == pais_codigo).all()}
    for m in (db.query(MedicoVisita)
              .filter(MedicoVisita.maestro_medico_id.isnot(None)).all()):
        if m.vm_id not in lineas_rm:      # panel de otro país
            continue
        ctx.paneles.setdefault(m.maestro_medico_id, []).append(
            (m.vm_id, lineas_rm[m.vm_id], m))
    return ctx


def atribuir(fila, ctx: ContextoAtribucion) -> tuple[int | None, str]:
    """¿De qué representante es esta receta?

    1. Si `rm_codigo` viene informado, Mallén ya atribuyó y su decisión manda.
    2. Si no, exequátur → maestro → filas de panel de ESE médico.
    3. El período de la receta DEBE tener ciclo mapeado. Sin esto, `ciclo_orden`
       quedaría en `None`, y `cuenta_en_ciclo(ciclo_orden=None, ...)` ADMITE a
       cualquier médico activo (ver su firma): el filtro de pertenencia no se
       relajaría, se apagaría entero, y la receta se acreditaría a un
       representante cuya pertenencia al panel nunca se evaluó para ningún
       ciclo (Ronda de correcciones 1, Important 1). El diagnóstico lo separa
       en `recetas.sin_ciclo` para que se sepa que la causa es el período, no
       el prescriptor.
    4. Los candidatos se filtran por pertenencia al panel EN EL CICLO de la
       receta, con `cuenta_en_ciclo` — el mismo criterio que usan la
       planeación y la cobertura. Admite `PENDIENTE_BAJA` a propósito: una
       baja solicitada sigue contando el ciclo actual. NO se usa
       `estado_aprobacion == "APROBADO"`, que responde otra pregunta
       («¿se le puede registrar una visita hoy?») y dejaría sin atribuir las
       recetas de todo médico en proceso de baja.
    5. Si el producto tiene línea, se desempata por ella.
    6. La decisión final se toma sobre REPRESENTANTES DISTINTOS, no sobre
       filas de panel: `Visita.DIM_MedicoVisita` no tiene restricción única
       sobre `(vm_id, maestro_medico_id)`, así que dos altas del mismo médico
       bajo el mismo VM no deben leerse como dos candidatos (Ronda de
       correcciones 1, Important 4). Un solo representante → atribuida. Cero
       o varios → no se atribuye: cuenta para el mercado, que es lo que dice
       el §3.2 del contrato.
    """
    if fila.rm_codigo:
        rm_id = ctx.representantes.get(fila.rm_codigo)
        if rm_id is not None:
            return rm_id, ATR_DIRECTA
        # Mallén atribuyó a un representante que VISTA no conoce: no se cae al
        # panel, porque contradecir la atribución de la fuente sería inventar.
        # El diagnóstico distingue esta causa (interna, de sincronización) en
        # `recetas.rm_no_enlazado` — ver `_motivo_huerfana`.
        return None, ATR_HUERFANA

    medico_id = ctx.medicos.get(fila.medico_ir_codigo)
    if medico_id is None:
        return None, ATR_HUERFANA

    ciclo_id = ctx.periodos.get(fila.periodo_codigo)
    if ciclo_id is None:
        return None, ATR_HUERFANA
    ciclo_orden = ctx.ordenes.get(ciclo_id)

    candidatos = ctx.paneles.get(medico_id, [])
    candidatos = [c for c in candidatos
                  if cuenta_en_ciclo(c[2], ciclo_orden, ctx.ordenes)]
    if not candidatos:
        return None, ATR_HUERFANA

    if len(candidatos) > 1:
        producto_id = ctx.productos.get(fila.producto_ir_codigo)
        linea = ctx.linea_de_producto.get(producto_id) if producto_id else None
        if linea is not None:
            candidatos = [c for c in candidatos if c[1] == linea]

    vms = {c[0] for c in candidatos}
    if len(vms) == 1:
        return candidatos[0][0], ATR_CADENA
    if not vms:
        return None, ATR_HUERFANA
    return None, ATR_AMBIGUA


def _motivo_huerfana(fila, ctx: ContextoAtribucion) -> str | None:
    """Sub-causa de una huérfana, SOLO para el diagnóstico.

    Deliberadamente separada de `atribuir`: la firma pública
    (`atribuir(fila, ctx) -> (id|None, balde)`) no se acopla a un detalle que
    solo el diagnóstico necesita, y estos son chequeos de pertenencia contra
    `ctx` (ya resuelto), no una segunda pasada de la lógica de candidatos.
    Devuelve `None` para las huérfanas "normales" (prescriptor no enlazado,
    médico sin candidato vigente): esas ya las explican `prescriptores.huerfanos`
    y los otros tests de la cadena, y no son un sub-balde con nombre propio.
    """
    if fila.rm_codigo:
        if fila.rm_codigo not in ctx.representantes:
            return "rm_no_enlazado"
        return None
    if fila.medico_ir_codigo not in ctx.medicos:
        return None
    if fila.periodo_codigo not in ctx.periodos:
        return "sin_ciclo"
    return None


# ===========================================================================
# El diagnóstico
# ===========================================================================

#: Cuántos ejemplos se muestran de cada clase. Una lista de miles no la lee
#: nadie; lo que el operador necesita es reconocer el patrón.
EJEMPLOS = 10


def diagnosticar_ir(db: Session, pais_codigo: str) -> dict:
    """Qué tan bien enlaza el IR, ANTES de construir el indicador.

    Es lo que el §11.9 del requerimiento manda comprobar con muestra real: si
    la mayoría de las recetas cae en huérfanas, el problema es del archivo de
    Close-Up y no se arregla con código.

    De SOLO LECTURA: no escribe, no hace commit, no cierra lotes. Correrlo dos
    veces devuelve lo mismo.
    """
    ctx = _contexto(db, pais_codigo)

    indice = _indice_exequatur(db, pais_codigo)
    prescriptores = (db.query(ExtDimMedicoIR)
                     .filter(ExtDimMedicoIR.pais_codigo == pais_codigo).all())
    enlazados, casi, huerfanos = [], [], []
    for p in prescriptores:
        if p.medico_ir_codigo in ctx.medicos:
            enlazados.append(p)
        elif _es_casi_enlace(indice, p.exequatur):
            casi.append(p)
        else:
            huerfanos.append(p)
    # Descriptivo, NO aplica `cuenta_en_ciclo`: mide "tiene alguna fila de
    # panel alguna vez", no "panel efectivo para un ciclo". El nombre invita a
    # leerlo como lo segundo — no lo es (Ronda de correcciones 1, menor).
    con_panel = sum(1 for p in enlazados
                    if ctx.paneles.get(ctx.medicos[p.medico_ir_codigo]))

    productos = (db.query(ExtDimProductoIR)
                 .filter(ExtDimProductoIR.pais_codigo == pais_codigo).all())
    propios = [p for p in productos if p.es_propio]
    propios_sin_equivalencia = [p for p in propios
                                if p.producto_ir_codigo not in ctx.productos]
    # Cuenta sobre las FILAS de `ext.dimproductoir`, no sobre `len(ctx.productos)`:
    # `ctx.productos` es el mapeo COMPLETO del país, así que si la dimensión deja
    # de traer un producto ya mapeado el conteo por mapeos queda desfasado
    # (Ronda de correcciones 1, menor — mismo motivo para `periodos` abajo).
    productos_enlazados = sum(1 for p in productos
                              if p.producto_ir_codigo in ctx.productos)

    periodos = (db.query(ExtDimPeriodoIR)
                .filter(ExtDimPeriodoIR.pais_codigo == pais_codigo).all())
    periodos_con_ciclo = sum(1 for p in periodos if p.periodo_codigo in ctx.periodos)

    baldes = {ATR_DIRECTA: 0, ATR_CADENA: 0, ATR_AMBIGUA: 0, ATR_HUERFANA: 0}
    #: Sub-conteos de `huerfanas` — NO son un quinto/sexto balde: la invariante
    #: de que los cuatro baldes suman `recetas.total` sigue intacta. Existen
    #: para que el diagnóstico diga DÓNDE está el problema (¿el período de
    #: Close-Up, la sincronización de representantes, o de verdad el
    #: prescriptor?) en vez de amontonar todo bajo "huérfana" (Ronda de
    #: correcciones 1, Important 1 e Important 2).
    sin_ciclo = 0
    rm_no_enlazado = 0
    ejemplos_rm_no_enlazado: list[dict] = []

    # SOLO las columnas que `atribuir`/`_motivo_huerfana` leen, y en streaming:
    # `ext.factprescripciondetalle` puede traer cientos de miles de filas por
    # período (ver docstring del módulo), y `ux_fp_origen` es por
    # `(pais, origen_id)` — las filas de TODOS los períodos ya entregados
    # conviven en la tabla, no solo las del período en curso (Ronda de
    # correcciones 1, Important 3).
    consulta = (db.query(ExtFactPrescripcionDetalle.origen_id,
                         ExtFactPrescripcionDetalle.rm_codigo,
                         ExtFactPrescripcionDetalle.medico_ir_codigo,
                         ExtFactPrescripcionDetalle.producto_ir_codigo,
                         ExtFactPrescripcionDetalle.periodo_codigo)
                .filter(ExtFactPrescripcionDetalle.pais_codigo == pais_codigo))
    total = 0
    for fila in consulta.yield_per(1000):
        total += 1
        _, balde = atribuir(fila, ctx)
        baldes[balde] += 1
        if balde == ATR_HUERFANA:
            motivo = _motivo_huerfana(fila, ctx)
            if motivo == "sin_ciclo":
                sin_ciclo += 1
            elif motivo == "rm_no_enlazado":
                rm_no_enlazado += 1
                if len(ejemplos_rm_no_enlazado) < EJEMPLOS:
                    ejemplos_rm_no_enlazado.append(
                        {"origen_id": fila.origen_id, "rm_codigo": fila.rm_codigo})

    return {
        "pais_codigo": pais_codigo,
        "prescriptores": {
            "en_ext": len(prescriptores),
            "enlazados": len(enlazados),
            "con_panel": con_panel,
            "casi_enlazados": len(casi),
            "huerfanos": len(huerfanos),
            "ejemplos_casi_enlazados": [
                {"codigo": p.medico_ir_codigo, "exequatur": p.exequatur,
                 "nombre": p.nombre} for p in casi[:EJEMPLOS]],
            "ejemplos_huerfanos": [
                {"codigo": p.medico_ir_codigo, "exequatur": p.exequatur,
                 "nombre": p.nombre} for p in huerfanos[:EJEMPLOS]],
        },
        "productos": {
            "en_ext": len(productos),
            "propios": len(propios),
            "enlazados": productos_enlazados,
            "propios_sin_equivalencia": len(propios_sin_equivalencia),
            "ejemplos_propios_sin_equivalencia": [
                {"codigo": p.producto_ir_codigo, "nombre": p.nombre}
                for p in propios_sin_equivalencia[:EJEMPLOS]],
        },
        "periodos": {
            "en_ext": len(periodos),
            "con_ciclo": periodos_con_ciclo,
            "sin_ciclo": len(periodos) - periodos_con_ciclo,
        },
        "recetas": {
            "total": total,
            "directas": baldes[ATR_DIRECTA],
            "por_cadena": baldes[ATR_CADENA],
            "ambiguas": baldes[ATR_AMBIGUA],
            "huerfanas": baldes[ATR_HUERFANA],
            # Sub-conteos de `huerfanas` (no participan de la suma de los
            # cuatro baldes de arriba, que ya cierra `total` por sí sola).
            "sin_ciclo": sin_ciclo,
            "rm_no_enlazado": rm_no_enlazado,
            "ejemplos_rm_no_enlazado": ejemplos_rm_no_enlazado,
        },
    }
