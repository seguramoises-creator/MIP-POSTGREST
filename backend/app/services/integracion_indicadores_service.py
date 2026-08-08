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
"""
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Indicador, RepresentanteMedico
from app.models.hechos import ResultadoIndicador
from app.models.integracion_ext import (
    ExtDimCiclo, ExtFactVisitaFarmacia, ExtFactVisitaMedico, ExtPanelMedico,
    ExtTargetFarmacia,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE
from app.services import integracion_mapeo as mapeo
from app.services.integracion_visitas_service import SEVERIDAD_ERROR, Hallazgo

COB_MD_F1 = "COB_MD_F1"
COB_MD_F2 = "COB_MD_F2"
PROM_DIARIO = "PROM_DIARIO"
COB_FARMACIAS = "COB_FARMACIAS"
CODIGOS: tuple[str, ...] = (COB_MD_F1, COB_MD_F2, PROM_DIARIO, COB_FARMACIAS)


def _pct(cubiertos: int, universo: int) -> Decimal:
    """Cobertura en porcentaje. Universo vacío → 0, no división por cero: un RM
    sin panel no tiene cobertura, no tiene cobertura indefinida."""
    if universo <= 0:
        return Decimal("0")
    return (Decimal(cubiertos) * 100 / Decimal(universo)).quantize(Decimal("0.01"))


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
                       visitados: set[str]) -> Decimal:
    """Médicos distintos visitados de esa frecuencia / médicos de esa
    frecuencia en el panel × 100.

    El numerador se intersecta con el panel de ESTA frecuencia: una visita a
    un médico F2 no puede sumar a la cobertura F1. Los no visitados siguen en
    el denominador — no visitar no reduce el universo.
    """
    panel = {f[0] for f in db.query(ExtPanelMedico.medico_codigo)
             .filter(ExtPanelMedico.pais_codigo == pais_codigo,
                     ExtPanelMedico.ciclo_codigo == ciclo_codigo,
                     ExtPanelMedico.rm_codigo == rm_codigo,
                     ExtPanelMedico.frecuencia_objetivo == frecuencia,
                     ExtPanelMedico.activo.is_(True)).distinct().all()}
    if not panel:
        return Decimal("0")
    return _pct(len(panel & visitados), len(panel))


def _promedio_diario(db: Session, visitados: set[str],
                     dias_laborables: int) -> Decimal:
    """§2.1: «MÉDICOS visitados dividido entre los días laborables del ciclo».

    Médicos distintos, no visitas: un médico visitado tres veces aporta 1.
    Se reutiliza el mismo conjunto que la cobertura, así los dos indicadores
    no pueden divergir en qué cuenta como visitado.
    """
    if dias_laborables <= 0:
        return Decimal("0")
    return (Decimal(len(visitados)) / Decimal(dias_laborables)).quantize(Decimal("0.01"))


def _cobertura_farmacias(db: Session, pais_codigo: str, ciclo_codigo: str,
                         rm_codigo: str) -> Decimal:
    """Farmacias distintas visitadas / farmacias en el target × 100."""
    target = {f[0] for f in db.query(ExtTargetFarmacia.farmacia_codigo)
              .filter(ExtTargetFarmacia.pais_codigo == pais_codigo,
                      ExtTargetFarmacia.ciclo_codigo == ciclo_codigo,
                      ExtTargetFarmacia.rm_codigo == rm_codigo,
                      ExtTargetFarmacia.activo.is_(True)).distinct().all()}
    if not target:
        return Decimal("0")

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

    Delete-then-insert acotado a estos 4 códigos y a los RM procesados: los otros
    indicadores del ciclo no se rozan.
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

    ids = _indicadores_del_pais(db, pais_codigo)
    faltantes = [c for c in CODIGOS if c not in ids]
    for codigo in faltantes:
        hallazgos.append(Hallazgo(
            "indicador", codigo,
            f"El indicador {codigo} no está dado de alta en {pais_codigo}; "
            f"no se calculó. Créalo en Administración → Indicadores.",
            SEVERIDAD_ERROR))

    # Los RM con actividad: los del panel más los que solo tienen farmacias.
    rms = {f[0] for f in db.query(ExtPanelMedico.rm_codigo)
           .filter(ExtPanelMedico.pais_codigo == pais_codigo,
                   ExtPanelMedico.ciclo_codigo == ciclo_codigo).distinct()}
    rms |= {f[0] for f in db.query(ExtTargetFarmacia.rm_codigo)
            .filter(ExtTargetFarmacia.pais_codigo == pais_codigo,
                    ExtTargetFarmacia.ciclo_codigo == ciclo_codigo).distinct()}

    filas_escritas = 0
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

        visitados = _medicos_visitados(db, pais_codigo, ciclo_codigo, rm_codigo)
        valores = {
            COB_MD_F1: _cobertura_medicos(db, pais_codigo, ciclo_codigo,
                                          rm_codigo, "F1", visitados),
            COB_MD_F2: _cobertura_medicos(db, pais_codigo, ciclo_codigo,
                                          rm_codigo, "F2", visitados),
            PROM_DIARIO: _promedio_diario(db, visitados,
                                          ciclo_ext.dias_laborables),
            COB_FARMACIAS: _cobertura_farmacias(db, pais_codigo, ciclo_codigo,
                                                rm_codigo),
        }

        indicador_ids = [ids[c] for c in CODIGOS if c in ids]
        if indicador_ids:
            (db.query(ResultadoIndicador)
             .filter(ResultadoIndicador.rm_id == rm_id,
                     ResultadoIndicador.ciclo_id == ciclo_id,
                     ResultadoIndicador.indicador_id.in_(indicador_ids))
             .delete(synchronize_session=False))
        for codigo, valor in valores.items():
            if codigo not in ids:
                continue
            db.add(ResultadoIndicador(
                rm_id=rm_id, pais_codigo=pais_codigo, linea_id=rm.linea_id,
                gerente_id=rm.gerente_id, ciclo_id=ciclo_id,
                indicador_id=ids[codigo], resultado_real=valor, activo=True))
            filas_escritas += 1

    logger.info(f"Indicadores de visita {pais_codigo}/{ciclo_codigo}: "
                f"{len(rms)} representantes, {filas_escritas} filas")
    return {"rms": len(rms), "filas": filas_escritas}
