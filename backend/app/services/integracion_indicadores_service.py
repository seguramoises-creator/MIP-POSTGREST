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
"""
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Ciclo, Indicador, MetaIndicador, RepresentanteMedico
from app.models.hechos import ResultadoIndicador
from app.models.integracion_ext import (
    ExtDimCiclo, ExtFactVisitaFarmacia, ExtFactVisitaMedico, ExtPanelMedico,
    ExtTargetFarmacia,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE
from app.services import integracion_mapeo as mapeo
from app.services.integracion_visitas_service import (
    SEVERIDAD_AVISO, SEVERIDAD_ERROR, Hallazgo,
)

COB_MD_F1 = "COB_MD_F1"
COB_MD_F2 = "COB_MD_F2"
PROM_DIARIO = "PROM_DIARIO"
COB_FARMACIAS = "COB_FARMACIAS"
CODIGOS: tuple[str, ...] = (COB_MD_F1, COB_MD_F2, PROM_DIARIO, COB_FARMACIAS)


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
                       rm_codigo: str) -> set[str]:
    """Códigos de los médicos con AL MENOS UNA visita ejecutada en el ciclo.

    Un `set` es la estructura que expresa la regla: «distintos visitados». Da
    igual cuántas veces aparezca cada médico. Tanto `V` (visita) como `R`
    (revisita) cuentan: ambas son presencia frente al médico.
    """
    filas = (db.query(ExtFactVisitaMedico.medico_codigo)
             .filter(ExtFactVisitaMedico.pais_codigo == pais_codigo,
                     ExtFactVisitaMedico.ciclo_codigo == ciclo_codigo,
                     ExtFactVisitaMedico.rm_codigo == rm_codigo,
                     ExtFactVisitaMedico.ejecutada.is_(True))
             .distinct().all())
    return {f[0] for f in filas}


def _cobertura_medicos(db: Session, pais_codigo: str, ciclo_codigo: str,
                       rm_codigo: str, frecuencia: str,
                       visitados: set[str]) -> Decimal | None:
    """Médicos distintos visitados de esa frecuencia / médicos de esa
    frecuencia en el panel.

    El numerador se intersecta con el panel de ESTA frecuencia: una visita a
    un médico F2 no puede sumar a la cobertura F1. Los no visitados siguen en
    el denominador — no visitar no reduce el universo.

    Devuelve `None`, no `Decimal("0")`, si el panel de esta frecuencia está
    vacío: sin universo no hay nada que medir (ver la nota de módulo «SIN
    UNIVERSO NO ES COBERTURA CERO»). El llamador es quien decide qué hacer con
    ese `None` (no escribir la fila, avisar).
    """
    panel = {f[0] for f in db.query(ExtPanelMedico.medico_codigo)
             .filter(ExtPanelMedico.pais_codigo == pais_codigo,
                     ExtPanelMedico.ciclo_codigo == ciclo_codigo,
                     ExtPanelMedico.rm_codigo == rm_codigo,
                     ExtPanelMedico.frecuencia_objetivo == frecuencia,
                     ExtPanelMedico.activo.is_(True)).distinct().all()}
    if not panel:
        return None
    return _pct(len(panel & visitados), len(panel))


def _meta_base_prom_diario(db: Session, indicador_id: int) -> Decimal | None:
    """Base de normalización para PROM_DIARIO, leída de `Config.DIM_MetaIndicador`.

    Mismo orden de preferencia que `motor_calculo_service.completar_puntajes`
    (líneas ~66-74): `meta_100` si está, si no `objetivo`. Sin meta activa, sin
    ninguno de los dos campos, o con un valor <= 0 → no hay base utilizable
    (None): no se puede construir un ratio con eso.
    """
    m = (db.query(MetaIndicador)
         .filter(MetaIndicador.indicador_id == indicador_id,
                 MetaIndicador.activo.is_(True)).first())
    if m is None:
        return None
    base = None
    if m.meta_100 is not None:
        base = Decimal(str(m.meta_100))
    elif m.objetivo is not None:
        base = Decimal(str(m.objetivo))
    if base is None or base <= 0:
        return None
    return base


def _promedio_diario(visitados: set[str], dias_laborables: int,
                     meta: Decimal) -> Decimal:
    """§2.1: «MÉDICOS visitados dividido entre los días laborables del ciclo»,
    normalizado contra la meta configurada (`meta`, ver `_meta_base_prom_diario`).

    La tasa cruda (médicos/día) no es una fracción de logro por sí sola — con
    `escala == 1` el motor la interpretaría como tal (0.05 médicos/día → «5%
    de cumplimiento»; 2.25 médicos/día saturaría al 100%). Dividir entre la
    meta la convierte en la fracción de logro que el motor sí espera.

    Médicos distintos, no visitas: un médico visitado tres veces aporta 1. Se
    reutiliza el mismo conjunto que la cobertura, así los dos indicadores no
    pueden divergir en qué cuenta como visitado.

    NO se acota el resultado: un RM que sobrecumple la meta debe verse en los
    datos como sobrecumplimiento real. El motor ya acota a [0,100] después de
    multiplicar por 100 — acotar aquí lo escondería antes de que llegue ahí.
    """
    if dias_laborables <= 0:
        return Decimal("0")
    tasa = Decimal(len(visitados)) / Decimal(dias_laborables)
    return (tasa / meta).quantize(Decimal("0.0001"))


def _cobertura_farmacias(db: Session, pais_codigo: str, ciclo_codigo: str,
                         rm_codigo: str) -> Decimal | None:
    """Farmacias distintas visitadas / farmacias en el target.

    `None`, no `Decimal("0")`, si el RM no tiene target de farmacias — mismo
    criterio que `_cobertura_medicos` (ver la nota de módulo).
    """
    target = {f[0] for f in db.query(ExtTargetFarmacia.farmacia_codigo)
              .filter(ExtTargetFarmacia.pais_codigo == pais_codigo,
                      ExtTargetFarmacia.ciclo_codigo == ciclo_codigo,
                      ExtTargetFarmacia.rm_codigo == rm_codigo,
                      ExtTargetFarmacia.activo.is_(True)).distinct().all()}
    if not target:
        return None

    visitadas = {f[0] for f in db.query(ExtFactVisitaFarmacia.farmacia_codigo)
                 .filter(ExtFactVisitaFarmacia.pais_codigo == pais_codigo,
                         ExtFactVisitaFarmacia.ciclo_codigo == ciclo_codigo,
                         ExtFactVisitaFarmacia.rm_codigo == rm_codigo,
                         ExtFactVisitaFarmacia.ejecutada.is_(True))
                 .distinct().all()}
    return _pct(len(target & visitadas), len(target))


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

    # PROM_DIARIO necesita una meta configurada para convertirse en fracción
    # de logro (ver `_promedio_diario`). Se resuelve una sola vez para todo el
    # país/ciclo -- la meta no varía por RM -- y si falta, ningún RM escribe
    # esa fila: una tasa cruda sin normalizar sería peor que no escribir nada
    # (se leería como un cumplimiento ridículamente bajo).
    prom_diario_meta = None
    if PROM_DIARIO in ids:
        prom_diario_meta = _meta_base_prom_diario(db, ids[PROM_DIARIO])
        if prom_diario_meta is None:
            hallazgos.append(Hallazgo(
                "indicador", PROM_DIARIO,
                f"Falta configurar la meta de {PROM_DIARIO} en {pais_codigo} "
                f"(Administración → Metas); no se calculó para ningún "
                f"representante.", SEVERIDAD_ERROR))

    # Los RM con actividad: los del panel más los que solo tienen farmacias.
    rms = {f[0] for f in db.query(ExtPanelMedico.rm_codigo)
           .filter(ExtPanelMedico.pais_codigo == pais_codigo,
                   ExtPanelMedico.ciclo_codigo == ciclo_codigo).distinct()}
    rms |= {f[0] for f in db.query(ExtTargetFarmacia.rm_codigo)
            .filter(ExtTargetFarmacia.pais_codigo == pais_codigo,
                    ExtTargetFarmacia.ciclo_codigo == ciclo_codigo).distinct()}

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
        visitados = _medicos_visitados(db, pais_codigo, ciclo_codigo, rm_codigo)

        # `None` = sin universo (panel/target vacío para este RM): no hay
        # nada que medir, así que el código queda fuera de `valores` y, más
        # abajo, fuera de lo que se borra e inserta. Se reporta como aviso,
        # no error: no es una falla de configuración, es una carga parcial o
        # un RM legítimamente sin ese universo.
        candidatos: dict[str, tuple[Decimal | None, str]] = {
            COB_MD_F1: (_cobertura_medicos(db, pais_codigo, ciclo_codigo,
                                           rm_codigo, "F1", visitados),
                        "no tiene panel médico F1"),
            COB_MD_F2: (_cobertura_medicos(db, pais_codigo, ciclo_codigo,
                                           rm_codigo, "F2", visitados),
                        "no tiene panel médico F2"),
            COB_FARMACIAS: (_cobertura_farmacias(db, pais_codigo, ciclo_codigo,
                                                 rm_codigo),
                            "no tiene target de farmacias"),
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
        # Sin meta utilizable no hay ratio que calcular: PROM_DIARIO se queda
        # fuera de `valores` y, más abajo, fuera de lo que se escribe.
        if prom_diario_meta is not None:
            valores[PROM_DIARIO] = _promedio_diario(
                visitados, ciclo_ext.dias_laborables, prom_diario_meta)

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
