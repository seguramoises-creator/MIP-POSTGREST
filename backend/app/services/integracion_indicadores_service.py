"""Calcula los cuatro indicadores de visita a partir de los hechos de Mallén.

POR QUÉ EXISTE ESTE MÓDULO
---------------------------
VISTA nunca derivó estos indicadores de las visitas: llegaban ya calculados en el
Excel `KPI_RM` y el motor solo los convertía a puntos. El contrato con Mallén no
trae indicadores calculados —trae hechos—, así que al retirar el Excel alguien
tiene que producirlos. Es este módulo.

SE CALCULA SOBRE `ext`, NO SOBRE LAS TABLAS INTERNAS
-----------------------------------------------------
`ext.panelmedico` trae `frecuencia_objetivo` (F1/F2), que es justo lo que separa
COB_MD_F1 de COB_MD_F2. `DIM_TargetMedico` no tiene esa columna, y añadírsela
sería deformar una tabla interna para que quepa un dato del contrato.

DEFINICIÓN DE «CUBIERTO»: MÉDICOS DISTINTOS VISITADOS
------------------------------------------------------
§2.1 del requerimiento v2, literal: «calcula la cobertura dividiendo la cantidad
de MÉDICOS DISTINTOS VISITADOS entre la cantidad de médicos programados para cada
frecuencia». Un médico cuenta cuando tiene AL MENOS UNA visita ejecutada;
visitarlo cinco veces no lo cuenta cinco veces.

`visitas_programadas` NO participa en esta fórmula. Se integra igual a
`DIM_TargetMedico` porque lo consume el módulo 4DX, pero aquí no se lee.

Una versión anterior de este módulo exigía la frecuencia completa
(`>= visitas_programadas`). Venía del RFI del 22-jul, que el requerimiento v2
reemplazó. Se corrigió porque los números de VISTA deben cuadrar con los de
Mallén, y el documento acordado es el v2.

UNIDAD DE `resultado_real`: FRACCIÓN 0-1, NO PORCENTAJE 0-100
----------------------------------------------------------------
Los 4 indicadores están dados de alta con `DIM_Indicador.escala == 1`. Con esa
escala, `motor_calculo_service._calc_puntajes_filas` hace
`valor_pct = resultado_real * 100` antes de acotar a [0,100]. Si aquí se
escribiera ya en porcentaje (p. ej. `50.0` por 50%), el motor la multiplicaría
otra vez (`5000`) y la acotaría a 100: cualquier cobertura por encima del 1%
saturaba a puntaje perfecto. Por eso `_pct` y `_promedio_diario` devuelven
fracciones 0-1 — la multiplicación por 100 es responsabilidad exclusiva del
motor, una sola vez.

PROM_DIARIO: TASA CRUDA, SIN NORMALIZAR CONTRA NINGUNA META
----------------------------------------------------------------
Una versión anterior dividía la tasa (médicos distintos / días laborables)
entre `DIM_MetaIndicador.meta_100`/`objetivo`, asumiendo que esa fila traía el
objetivo propio de PROM_DIARIO. Fue un error de análisis, revertido: medido
contra la base real, `meta_100 = 100` para los OCHO indicadores por igual — es
el marcador de escala que usa el motor (`escala == 1` → ×100), no un objetivo
por indicador — y los históricos que cargaba el Excel para PROM_DIARIO van de
0.50 a 1.11, con su `resultado_porcentaje` correspondiente de 50 a 100: el
sistema siempre esperó la tasa cruda, tal cual la interpreta el motor. Dividir
entre `meta_100 = 100` hundía el valor (un RM con ~45 médicos en un ciclo de
~40 días, ~100% de logro real, caía a ~1%) sin emitir un solo hallazgo, porque
la meta SÍ existía — solo que no era la meta correcta para este indicador. Por
eso `_promedio_diario` ya no recibe ni busca ninguna meta: médicos distintos
visitados ÷ días laborables, tal cual, igual que las tres coberturas no dividen
entre nada más que su propio universo.

«SIN UNIVERSO» NO ES «COBERTURA CERO»: NO SE ESCRIBE LA FILA
--------------------------------------------------------------
Un lote parcial (por ejemplo, dimensiones+panel sin visitas todavía, o un RM
que legítimamente no tiene panel F2 o target de farmacias) deja el
DENOMINADOR de un indicador en cero. Escribir `0` ahí no es medir cobertura
cero: es afirmar «no cubrió nada» sobre algo que no había que medir, y ese
cero pesa igual que una cobertura real en el Score. Peor aún: como el
delete-then-insert de más abajo primero borra, ese cero también se comía
cualquier valor previo del indicador (p. ej. el histórico cargado por Excel).

Por eso `_cobertura_medicos`/`_cobertura_farmacias` devuelven `None` (no
`Decimal("0")`) cuando el universo (panel o target) está vacío, y
`calcular_indicadores` NO escribe esa fila — deja intacto lo que hubiera antes
en `FACT_ResultadoIndicador` para ese indicador — y en vez de eso reporta un
`Hallazgo` de severidad aviso. El delete-then-insert se acota, por RM, a los
indicadores que sí se van a reemplazar: nunca borra uno que no va a reponer.

Distinto es el caso de universo CON entidades pero ninguna visitada
(denominador > 0, numerador 0): eso sí es cobertura cero real y sí se
escribe `0` — penaliza, como debe.

TAMBIÉN RESPETA EL GATE DE LOTE (VALIDADO/INTEGRADO)
--------------------------------------------------------------
`integracion_visitas_service` ya omite las filas de un lote que no esté en
VALIDADO/INTEGRADO (`_ESTADOS_LOTE_INTEGRABLES`). Este módulo lee los MISMOS
cuatro hechos de `ext` directamente —no pasa por esos integradores— así que
tenía su propio agujero: un lote RECHAZADO, sin una sola fila integrada en las
tablas internas, igual alimentaba estos cuatro indicadores y el Score.

Se reutilizan `_ESTADOS_LOTE_INTEGRABLES`/`_resolver_estados_lotes` de
`integracion_visitas_service` en vez de escribir un segundo criterio: dos
definiciones de «lote integrable» sobre el mismo dato es justo lo que hay que
evitar. `_lotes_integrables` los resuelve UNA sola vez por corrida (no una
consulta por fila) y el resultado se filtra en cada consulta a `ext`,
INCLUIDO el universo de RM con actividad (`rms`, más abajo): un RM cuya única
fuente sea un lote no integrable no debe ni entrar al bucle, para que la regla
de «sin universo no se pisa lo que hubiera antes» (ver la nota de arriba)
también lo proteja a él — de lo contrario PROM_DIARIO, que no tiene noción de
universo, escribiría una tasa cruda de `0` real y pisaría su valor previo.

VENTAS (sub-proyecto 5, Tarea 2): QUINTO INDICADOR, DE OTRA FUENTE
--------------------------------------------------------------------
`VENTAS` se calcula aquí también --comparte gate de lote, guard de ciclo
cerrado y patron `candidatos`/delete-then-insert con los otros cuatro--, pero
su origen NO es visita: sale de `ext.factventa` (venta + cuota por RM/ciclo),
la misma tabla que agrega `integracion_visitas_service.integrar_ventas` hacia
`DW.FACT_Ventas`. Es una lectura independiente de esa: este modulo no
depende de que `integrar_ventas` ya haya corrido, ni pisa su tabla.

Misma unidad que el resto: `_cumplimiento_ventas` devuelve una FRACCION 0-1
(`venta/cuota`), no un porcentaje -- `VENTAS` esta dado de alta con
`escala == 1`, asi que el motor la multiplica por 100 una sola vez (ver la
nota de modulo de mas arriba sobre la unidad de `resultado_real`). Y la misma
regla de «sin universo no es cero»: sin `cuota` no hay meta con la que medir
cumplimiento, asi que no se escribe la fila (se avisa) en vez de escribir un
`0` que penalizaria a un RM al que nadie le fijo cuota.
"""
from decimal import Decimal

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.dimensiones import Ciclo, Indicador, RepresentanteMedico
from app.models.hechos import ResultadoIndicador
from app.models.integracion_ext import (
    ExtDimCiclo, ExtFactVenta, ExtFactVisitaFarmacia, ExtFactVisitaMedico,
    ExtPanelMedico, ExtTargetFarmacia,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE
from app.services import integracion_mapeo as mapeo
from app.services.integracion_visitas_service import (
    SEVERIDAD_AVISO, SEVERIDAD_ERROR, Hallazgo,
    _ESTADOS_LOTE_INTEGRABLES, _resolver_estados_lotes,
)

COB_MD_F1 = "COB_MD_F1"
COB_MD_F2 = "COB_MD_F2"
PROM_DIARIO = "PROM_DIARIO"
COB_FARMACIAS = "COB_FARMACIAS"
VENTAS = "VENTAS"
CODIGOS: tuple[str, ...] = (COB_MD_F1, COB_MD_F2, PROM_DIARIO, COB_FARMACIAS, VENTAS)


def _pct(cubiertos: int, universo: int) -> Decimal:
    """Cobertura como FRACCIÓN 0-1 (no 0-100): ver la nota de módulo sobre la
    unidad de `resultado_real`.

    Los llamadores (`_cobertura_medicos`/`_cobertura_farmacias`) ya filtran el
    universo vacío antes de llegar aquí y devuelven `None` en ese caso — un
    universo vacío no es cobertura cero, es «nada que medir» (ver la nota de
    módulo «SIN UNIVERSO NO ES COBERTURA CERO»). El `if universo <= 0` que
    sigue es solo un resguardo defensivo contra división por cero, no la vía
    normal para llegar a `0`.

    Se quantiza a 4 decimales, no a 2: el porcentaje viejo usaba 2 decimales
    (granularidad de 0.01%). Una fracción 0-1 necesita 4 decimales para
    conservar esa misma granularidad — con 2 decimales, 50% y 50.4% colapsan
    los dos en `0.50`.
    """
    if universo <= 0:
        return Decimal("0")
    return (Decimal(cubiertos) / Decimal(universo)).quantize(Decimal("0.0001"))


def _indicadores_del_pais(db: Session, pais_codigo: str) -> dict[str, int]:
    """`codigo → indicador_id`. Los que no estén dados de alta se reportan una
    sola vez y su indicador se omite: dar de alta un indicador es configuración
    (lleva ponderación y tabla de rangos), no algo que se improvise aquí."""
    filas = (db.query(Indicador)
             .filter(Indicador.pais_codigo == pais_codigo,
                     Indicador.codigo.in_(CODIGOS)).all())
    return {f.codigo: f.id for f in filas}


def _medicos_visitados(db: Session, pais_codigo: str, ciclo_codigo: str,
                       rm_codigo: str, lotes_integrables: set[int]) -> set[str]:
    """Códigos de los médicos con AL MENOS UNA visita ejecutada en el ciclo, en
    un lote VALIDADO/INTEGRADO.

    Un `set` es la estructura que expresa la regla: «distintos visitados». Da
    igual cuántas veces aparezca cada médico. Tanto `V` (visita) como `R`
    (revisita) cuentan: ambas son presencia frente al médico.
    """
    filas = (db.query(ExtFactVisitaMedico.medico_codigo)
             .filter(ExtFactVisitaMedico.pais_codigo == pais_codigo,
                     ExtFactVisitaMedico.ciclo_codigo == ciclo_codigo,
                     ExtFactVisitaMedico.rm_codigo == rm_codigo,
                     ExtFactVisitaMedico.ejecutada.is_(True),
                     ExtFactVisitaMedico.lote_id.in_(lotes_integrables))
             .distinct().all())
    return {f[0] for f in filas}


def _cobertura_medicos(db: Session, pais_codigo: str, ciclo_codigo: str,
                       rm_codigo: str, frecuencia: str, visitados: set[str],
                       lotes_integrables: set[int]) -> Decimal | None:
    """Médicos distintos visitados de esa frecuencia / médicos de esa
    frecuencia en el panel.

    El numerador se intersecta con el panel de ESTA frecuencia: una visita a
    un médico F2 no puede sumar a la cobertura F1. Los no visitados siguen en
    el denominador — no visitar no reduce el universo.

    Devuelve `None`, no `Decimal("0")`, si el panel de esta frecuencia está
    vacío: sin universo no hay nada que medir (ver la nota de módulo «SIN
    UNIVERSO NO ES COBERTURA CERO»). El llamador es quien decide qué hacer con
    ese `None` (no escribir la fila, avisar). Un panel cuyas únicas filas
    vengan de un lote no VALIDADO/INTEGRADO cuenta como universo vacío, igual
    que si no existiera: `lotes_integrables` filtra eso antes de llegar aquí.
    """
    panel = {f[0] for f in db.query(ExtPanelMedico.medico_codigo)
             .filter(ExtPanelMedico.pais_codigo == pais_codigo,
                     ExtPanelMedico.ciclo_codigo == ciclo_codigo,
                     ExtPanelMedico.rm_codigo == rm_codigo,
                     ExtPanelMedico.frecuencia_objetivo == frecuencia,
                     ExtPanelMedico.activo.is_(True),
                     ExtPanelMedico.lote_id.in_(lotes_integrables)).distinct().all()}
    if not panel:
        return None
    return _pct(len(panel & visitados), len(panel))


def _promedio_diario(visitados: set[str], dias_laborables: int) -> Decimal:
    """§2.1: «MÉDICOS visitados dividido entre los días laborables del ciclo».
    Tasa CRUDA, sin normalizar contra ninguna meta — ver la nota de módulo
    «PROM_DIARIO: TASA CRUDA».

    Médicos distintos, no visitas: un médico visitado tres veces aporta 1. Se
    reutiliza el mismo conjunto que la cobertura, así los dos indicadores no
    pueden divergir en qué cuenta como visitado.

    NO se acota el resultado: un RM que sobrecumple debe verse en los datos
    como sobrecumplimiento real. El motor ya acota a [0,100] después de
    multiplicar por 100 — acotar aquí lo escondería antes de que llegue ahí.
    """
    if dias_laborables <= 0:
        return Decimal("0")
    return (Decimal(len(visitados)) / Decimal(dias_laborables)).quantize(Decimal("0.0001"))


def _cobertura_farmacias(db: Session, pais_codigo: str, ciclo_codigo: str,
                         rm_codigo: str,
                         lotes_integrables: set[int]) -> Decimal | None:
    """Farmacias distintas visitadas / farmacias en el target.

    `None`, no `Decimal("0")`, si el RM no tiene target de farmacias — mismo
    criterio que `_cobertura_medicos` (ver la nota de módulo), incluido el
    filtro de lote integrable en las dos consultas (target y visitadas).
    """
    target = {f[0] for f in db.query(ExtTargetFarmacia.farmacia_codigo)
              .filter(ExtTargetFarmacia.pais_codigo == pais_codigo,
                      ExtTargetFarmacia.ciclo_codigo == ciclo_codigo,
                      ExtTargetFarmacia.rm_codigo == rm_codigo,
                      ExtTargetFarmacia.activo.is_(True),
                      ExtTargetFarmacia.lote_id.in_(lotes_integrables)).distinct().all()}
    if not target:
        return None

    visitadas = {f[0] for f in db.query(ExtFactVisitaFarmacia.farmacia_codigo)
                 .filter(ExtFactVisitaFarmacia.pais_codigo == pais_codigo,
                         ExtFactVisitaFarmacia.ciclo_codigo == ciclo_codigo,
                         ExtFactVisitaFarmacia.rm_codigo == rm_codigo,
                         ExtFactVisitaFarmacia.ejecutada.is_(True),
                         ExtFactVisitaFarmacia.lote_id.in_(lotes_integrables))
                 .distinct().all()}
    return _pct(len(target & visitadas), len(target))


def _cumplimiento_ventas(db: Session, pais_codigo: str, ciclo_codigo: str,
                         rm_codigo: str, lotes_integrables: list[int]
                         ) -> Decimal | None:
    """`SUM(valor_venta) / SUM(cuota)` del RM en el ciclo, como FRACCIÓN 0-1.

    Devuelve None —y por tanto NO se escribe la fila— cuando no hay cuota: sin
    meta no hay cumplimiento que medir, y un 0 penalizaría a un representante al
    que nadie se la fijó. Misma regla que el universo vacío de las coberturas.

    Se acota por abajo a 0 (una venta negativa por devoluciones no resta
    cumplimiento) pero NO por arriba: sobrecumplir debe verse en el dato crudo,
    y el motor ya acota a 100 al puntuar.
    """
    fila = (db.query(func.sum(ExtFactVenta.valor_venta),
                     func.sum(ExtFactVenta.cuota))
            .filter(ExtFactVenta.pais_codigo == pais_codigo,
                    ExtFactVenta.ciclo_codigo == ciclo_codigo,
                    ExtFactVenta.rm_codigo == rm_codigo,
                    ExtFactVenta.lote_id.in_(lotes_integrables)).one())
    venta, cuota = fila[0], fila[1]
    if cuota is None or Decimal(cuota) == 0:
        return None
    bruto = Decimal(venta or 0) / Decimal(cuota)
    return max(bruto, Decimal(0)).quantize(Decimal("0.0001"))


def _lotes_integrables(db: Session, pais_codigo: str, ciclo_codigo: str) -> set[int]:
    """Los `lote_id` en VALIDADO/INTEGRADO (`_ESTADOS_LOTE_INTEGRABLES`, de
    `integracion_visitas_service`) entre los que aportan filas a este
    país/ciclo, en cualquiera de los 5 hechos de `ext` que lee este módulo
    (los 4 de visita más `ExtFactVenta`, para VENTAS -- ver la nota de módulo
    «VENTAS: QUINTO INDICADOR»).

    Resuelto UNA sola vez por corrida (no una consulta por fila ni por RM):
    primero los `lote_id` presentes en `ext` para este país/ciclo, luego su
    estado en una sola consulta a `ExtControlCarga` vía
    `_resolver_estados_lotes`. El resultado se pasa a cada helper de más abajo
    para filtrar sus consultas. Sin `ExtFactVenta` aquí, un lote que solo
    trajera ventas (sin ningún hecho de visita) nunca se reconocería como
    integrable y `_cumplimiento_ventas` nunca vería sus filas, pese a que el
    lote esté VALIDADO/INTEGRADO.
    """
    modelos = (ExtFactVisitaMedico, ExtPanelMedico, ExtTargetFarmacia,
              ExtFactVisitaFarmacia, ExtFactVenta)
    lote_ids: set[int] = set()
    for modelo in modelos:
        lote_ids |= {f[0] for f in db.query(modelo.lote_id)
                     .filter(modelo.pais_codigo == pais_codigo,
                             modelo.ciclo_codigo == ciclo_codigo).distinct().all()}
    estados = _resolver_estados_lotes(db, lote_ids)
    return {lid for lid, estado in estados.items()
            if estado in _ESTADOS_LOTE_INTEGRABLES}


def calcular_indicadores(db: Session, pais_codigo: str, ciclo_codigo: str,
                         hallazgos: list) -> dict:
    """Calcula los 4 indicadores de cada RM con actividad en el ciclo.

    Escribe SOLO `resultado_real`: la conversión a puntos la sigue haciendo
    `motor_calculo_service`, igual que con los datos que llegaban por Excel. Así
    el camino de puntuación sigue siendo uno solo.

    Delete-then-insert acotado, por RM, a los indicadores que SÍ se van a
    reemplazar: ni los otros códigos del ciclo, ni los indicadores de este RM
    sin universo (panel/target vacío, ver la nota de módulo) se rozan — un
    universo vacío no borra ni pisa lo que hubiera antes.

    REGLA DE NEGOCIO: los ciclos cerrados son snapshots históricos inmutables
    (misma regla que aplica `recalculo_service.validar_ciclo_abierto` en el
    resto del sistema). Si el ciclo interno ya está cerrado, no se borra ni se
    escribe nada — el delete-then-insert de más abajo borraría `puntos_obtenidos`
    ya calculados por el motor y los dejaría sin reponer, porque el recálculo
    posterior también rechaza el ciclo cerrado.
    """
    ciclo_ext = (db.query(ExtDimCiclo)
                 .filter(ExtDimCiclo.pais_codigo == pais_codigo,
                         ExtDimCiclo.ciclo_codigo == ciclo_codigo).first())
    if ciclo_ext is None:
        raise ValueError(f"El ciclo {ciclo_codigo} no está en ext.dimciclo")
    ciclo_id = mapeo.id_mapeado(db, ENT_CICLO, pais_codigo, ciclo_codigo)
    if ciclo_id is None:
        raise ValueError(
            f"El ciclo {ciclo_codigo} no está sincronizado; corre dimensiones primero.")

    ciclo_interno = db.get(Ciclo, ciclo_id)
    if ciclo_interno is not None and ciclo_interno.cerrado:
        hallazgos.append(Hallazgo(
            "indicador", ciclo_codigo,
            f"El ciclo {ciclo_codigo} está cerrado; no se recalcularon los "
            f"indicadores de visita (los ciclos cerrados son snapshots "
            f"inmutables).", SEVERIDAD_AVISO))
        return {"rms": 0, "filas": 0, "omitido_ciclo_cerrado": True}

    ids = _indicadores_del_pais(db, pais_codigo)
    faltantes = [c for c in CODIGOS if c not in ids]
    for codigo in faltantes:
        hallazgos.append(Hallazgo(
            "indicador", codigo,
            f"El indicador {codigo} no está dado de alta en {pais_codigo}; "
            f"no se calculó. Créalo en Administración → Indicadores.",
            SEVERIDAD_ERROR))

    # Gate de lote (ver la nota de módulo «TAMBIÉN RESPETA EL GATE DE LOTE»):
    # resuelto UNA sola vez para toda la corrida, no por fila ni por RM.
    lotes_integrables = _lotes_integrables(db, pais_codigo, ciclo_codigo)

    # Los RM con actividad: los del panel más los que solo tienen farmacias o
    # solo ventas, acotados a lotes VALIDADO/INTEGRADO -- un RM cuya única
    # fuente sea un lote no integrable no debe ni entrar al bucle (ver la nota
    # de módulo). Sin la unión de ventas, un RM sin panel médico (solo SFA de
    # ventas) nunca llegaría a calcularse.
    rms = {f[0] for f in db.query(ExtPanelMedico.rm_codigo)
           .filter(ExtPanelMedico.pais_codigo == pais_codigo,
                   ExtPanelMedico.ciclo_codigo == ciclo_codigo,
                   ExtPanelMedico.lote_id.in_(lotes_integrables)).distinct()}
    rms |= {f[0] for f in db.query(ExtTargetFarmacia.rm_codigo)
            .filter(ExtTargetFarmacia.pais_codigo == pais_codigo,
                    ExtTargetFarmacia.ciclo_codigo == ciclo_codigo,
                    ExtTargetFarmacia.lote_id.in_(lotes_integrables)).distinct()}
    rms |= {f[0] for f in db.query(ExtFactVenta.rm_codigo)
            .filter(ExtFactVenta.pais_codigo == pais_codigo,
                    ExtFactVenta.ciclo_codigo == ciclo_codigo,
                    ExtFactVenta.lote_id.in_(lotes_integrables)).distinct()}

    filas_escritas = 0
    rms_calculados = 0
    for rm_codigo in sorted(rms):
        rm_id = mapeo.id_mapeado(db, ENT_REPRESENTANTE, pais_codigo, rm_codigo)
        if rm_id is None:
            hallazgos.append(Hallazgo(
                "indicador", rm_codigo,
                f"El representante «{rm_codigo}» no está sincronizado; sus "
                f"indicadores no se calcularon.", SEVERIDAD_ERROR))
            continue
        # `linea_id` es NOT NULL en FACT_ResultadoIndicador (igual que en
        # coaching_more_consolidacion.consolidar_indicador): se lee del maestro
        # interno del RM, no de `ext` (que no trae ese dato en el hecho).
        rm = db.get(RepresentanteMedico, rm_id)
        if rm is None:
            hallazgos.append(Hallazgo(
                "indicador", rm_codigo,
                f"El representante «{rm_codigo}» está mapeado pero su ficha "
                f"interna no existe; sus indicadores no se calcularon.",
                SEVERIDAD_ERROR))
            continue

        rms_calculados += 1
        visitados = _medicos_visitados(db, pais_codigo, ciclo_codigo, rm_codigo,
                                       lotes_integrables)

        # `None` = sin universo (panel/target vacío para este RM, ya filtrado
        # por lote integrable): no hay nada que medir, así que el código queda
        # fuera de `valores` y, más abajo, fuera de lo que se borra e inserta.
        # Se reporta como aviso, no error: no es una falla de configuración, es
        # una carga parcial o un RM legítimamente sin ese universo.
        candidatos: dict[str, tuple[Decimal | None, str]] = {
            COB_MD_F1: (_cobertura_medicos(db, pais_codigo, ciclo_codigo,
                                           rm_codigo, "F1", visitados,
                                           lotes_integrables),
                        "no tiene panel médico F1"),
            COB_MD_F2: (_cobertura_medicos(db, pais_codigo, ciclo_codigo,
                                           rm_codigo, "F2", visitados,
                                           lotes_integrables),
                        "no tiene panel médico F2"),
            COB_FARMACIAS: (_cobertura_farmacias(db, pais_codigo, ciclo_codigo,
                                                 rm_codigo, lotes_integrables),
                            "no tiene target de farmacias"),
            VENTAS: (_cumplimiento_ventas(db, pais_codigo, ciclo_codigo,
                                          rm_codigo, lotes_integrables),
                     "no tiene cuota de ventas cargada"),
        }
        valores: dict[str, Decimal] = {}
        for codigo, (valor, motivo) in candidatos.items():
            if valor is None:
                hallazgos.append(Hallazgo(
                    "indicador", rm_codigo,
                    f"El representante «{rm_codigo}» {motivo} en "
                    f"{pais_codigo}/{ciclo_codigo}; no se calculó {codigo} "
                    f"(sin universo, no se pisa lo que hubiera antes).",
                    SEVERIDAD_AVISO))
            else:
                valores[codigo] = valor
        if PROM_DIARIO in ids:
            valores[PROM_DIARIO] = _promedio_diario(
                visitados, ciclo_ext.dias_laborables)

        # Delete-then-insert acotado a los códigos que SÍ se van a reemplazar
        # ahora: un indicador sin universo no se borra, porque no se repone.
        codigos_a_escribir = [c for c in CODIGOS if c in valores and c in ids]
        indicador_ids = [ids[c] for c in codigos_a_escribir]
        if indicador_ids:
            (db.query(ResultadoIndicador)
             .filter(ResultadoIndicador.rm_id == rm_id,
                     ResultadoIndicador.ciclo_id == ciclo_id,
                     ResultadoIndicador.indicador_id.in_(indicador_ids))
             .delete(synchronize_session=False))
        for codigo in codigos_a_escribir:
            db.add(ResultadoIndicador(
                rm_id=rm_id, pais_codigo=rm.pais_codigo, linea_id=rm.linea_id,
                gerente_id=rm.gerente_id, ciclo_id=ciclo_id,
                indicador_id=ids[codigo], resultado_real=valores[codigo],
                activo=True))
            filas_escritas += 1

    logger.info(f"Indicadores de visita {pais_codigo}/{ciclo_codigo}: "
                f"{rms_calculados} representantes, {filas_escritas} filas")
    return {"rms": rms_calculados, "filas": filas_escritas,
            "omitido_ciclo_cerrado": False}
