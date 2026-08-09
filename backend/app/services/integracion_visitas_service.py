"""Integra los hechos de visita que Mallén deja en `ext` con las tablas de VISTA.

QUÉ ALIMENTA CADA COSA
-----------------------
Poblar `DIM_TargetMedico` y `DW.FACT_Visita` alimenta el módulo de Cobertura
Predictiva (4DX) y sus dashboards en vivo. **No alimenta los ocho indicadores del
Score**: esos los calcula `integracion_indicadores_service` a partir de `ext`,
porque VISTA nunca los derivó de visitas — llegaban ya calculados en un Excel.

Una fila cuya dimensión no esté sincronizada se OMITE con hallazgo, nunca se
resuelve al vuelo: adoptar o crear dimensiones es trabajo del sub-proyecto 2 y
duplicar esa lógica aquí llevaría a dos verdades sobre la misma identidad.

Tampoco se integra una fila cuyo LOTE no esté en VALIDADO/INTEGRADO (ver
`_ESTADOS_LOTE_INTEGRABLES`): el sub-proyecto 1 valida el lote y lo puede
marcar RECHAZADO, y un integrador que no mirara ese estado se tragaría las
filas de un lote que la validación ya descartó.
"""
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.dimensiones import TargetMedico
from app.models.hechos import Visita as FactVisita
from app.models.integracion_ext import (
    ExtControlCarga, ExtFactVisitaFarmacia, ExtFactVisitaMedico, ExtPanelMedico,
    ExtTargetFarmacia,
)
from app.models.mapeo_externo import (
    ENT_CICLO, ENT_FARMACIA, ENT_MEDICO, ENT_REPRESENTANTE, MapeoExterno,
)
from app.models.visita import FactVisitaFarmacia, FarmaciaVisita
from app.services import integracion_mapeo as mapeo

SEVERIDAD_ERROR = "error"
SEVERIDAD_AVISO = "aviso"

#: Entidades propias de este sub-proyecto en `MapeoExterno`.
ENT_TARGET_MEDICO = "target_medico"
ENT_VISITA_MEDICO = "visita_medico"

#: `MapeoExterno.codigo_externo` es String(60). Las claves compuestas que arman
#: `integrar_panel_medico`/`integrar_target_farmacia` (ciclo/rm/entidad) pueden
#: superarlo, y los `origen_id` que usan los otros dos integradores también se
#: comprueban contra el mismo límite (defensivo: hoy coincide con el largo de
#: columna de `ext`, pero no hay que asumirlo).
LARGO_CODIGO_EXTERNO = 60

#: Solo se integran filas cuyo lote esté en uno de estos dos estados. Un lote
#: RECIBIDO (todavía sin validar), RECHAZADO, o sin fila de control en
#: absoluto (nulo/vacío), se omite — ver `_resolver_estados_lotes`.
_ESTADOS_LOTE_INTEGRABLES = {"VALIDADO", "INTEGRADO"}


@dataclass
class Hallazgo:
    hecho: str
    origen_id: str | None
    problema: str
    severidad: str


@dataclass
class ConteoHecho:
    hecho: str
    en_ext: int = 0
    integrados: int = 0
    actualizados: int = 0
    omitidos: int = 0
    #: Qué lotes aportaron al menos una fila efectivamente creada o actualizada
    #: en esta corrida. `_cerrar_lotes` lo usa (condición 1 del §7.1 paso 4):
    #: un lote cuyas filas se omitieron TODAS no debe pasar a INTEGRADO.
    lotes_aportados: set[int] = field(default_factory=set)

    def anotar(self, resultado: str, lote_id: int) -> None:
        if resultado == mapeo.RESULTADO_CREADO:
            self.integrados += 1
        else:
            # Adoptado y actualizado se cuentan igual: para un hecho no existe la
            # distinción del maestro (nadie los cargó antes a mano).
            self.actualizados += 1
        self.lotes_aportados.add(lote_id)


def _refs(db: Session, pais_codigo: str, ciclo_codigo: str, rm_codigo: str
          ) -> tuple[int | None, int | None]:
    """Ids internos de ciclo y representante, o None si falta el mapeo."""
    return (mapeo.id_mapeado(db, ENT_CICLO, pais_codigo, ciclo_codigo),
            mapeo.id_mapeado(db, ENT_REPRESENTANTE, pais_codigo, rm_codigo))


def _falta_ref(hallazgos: list, hecho: str, origen_id: str | None,
               que: str, codigo: str) -> None:
    hallazgos.append(Hallazgo(
        hecho, origen_id,
        f"No se pudo resolver {que} «{codigo}»; sincroniza dimensiones primero.",
        SEVERIDAD_ERROR))


def _cabe(valor: str, largo: int) -> bool:
    return len(valor) <= largo


def _omitir_por_largo(conteo: ConteoHecho, hallazgos: list, hecho: str,
                      origen_id: str | None, columna: str, largo: int) -> None:
    """Mismo patrón que `integracion_dimensiones_service._omitir_por_largo`
    (sub-proyecto 2): una clave que no cabe en `columna` se OMITE, nunca se
    trunca — truncar podría colapsar dos entidades distintas en una sola
    clave y confundirlas."""
    conteo.omitidos += 1
    hallazgos.append(Hallazgo(
        hecho, origen_id,
        f"La clave de integración supera los {largo} caracteres de {columna}; "
        f"la fila se omitió.", SEVERIDAD_ERROR))


def _resolver_estados_lotes(db: Session, lote_ids: set[int]) -> dict[int, str]:
    """El estado normalizado (`.strip().upper()`, tolerante a la caja que
    mande el origen — igual que ya hacía `_cerrar_lotes` para VALIDADO) de
    cada lote, resuelto en UNA sola consulta.

    Se llama una vez por corrida (desde `integrar_todo`, que ya conoce de
    antemano los lotes del ciclo) o, en el peor caso, una vez por integrador
    cuando se invoca suelto — nunca dentro del bucle de filas, que sería una
    consulta a `ExtControlCarga` por fila.
    """
    if not lote_ids:
        return {}
    filas = (db.query(ExtControlCarga.lote_id, ExtControlCarga.estado)
             .filter(ExtControlCarga.lote_id.in_(lote_ids)).all())
    return {lote_id: (estado or "").strip().upper() for lote_id, estado in filas}


def _lote_habilitado(estados_lote: dict[int, str], lote_id: int) -> bool:
    return estados_lote.get(lote_id) in _ESTADOS_LOTE_INTEGRABLES


def _omitir_por_lote(conteo: ConteoHecho, hallazgos: list, hecho: str,
                     origen_id: str | None, lote_id: int,
                     estados_lote: dict[int, str]) -> None:
    conteo.omitidos += 1
    estado = estados_lote.get(lote_id)
    hallazgos.append(Hallazgo(
        hecho, origen_id,
        f"El lote {lote_id} está en estado «{estado or 'sin control de carga'}», "
        f"no VALIDADO/INTEGRADO; la fila se omitió.", SEVERIDAD_ERROR))


def integrar_panel_medico(db: Session, pais_codigo: str, ciclo_codigo: str,
                          hallazgos: list,
                          estados_lote: dict[int, str] | None = None) -> ConteoHecho:
    """`ext.panelmedico` → `Config.DIM_TargetMedico` (universo del módulo 4DX).

    La frecuencia (F1/F2) NO se guarda: `DIM_TargetMedico` no tiene esa columna y
    no se le añade. El motor de indicadores la lee de `ext`, que es su origen.
    """
    conteo = ConteoHecho("panelmedico")
    filas = (db.query(ExtPanelMedico)
             .filter(ExtPanelMedico.pais_codigo == pais_codigo,
                     ExtPanelMedico.ciclo_codigo == ciclo_codigo).all())
    conteo.en_ext = len(filas)
    if estados_lote is None:
        estados_lote = _resolver_estados_lotes(db, {f.lote_id for f in filas})
    for fila in filas:
        clave = f"{fila.rm_codigo}/{fila.medico_codigo}"
        if not _lote_habilitado(estados_lote, fila.lote_id):
            _omitir_por_lote(conteo, hallazgos, "panelmedico", clave,
                             fila.lote_id, estados_lote)
            continue
        clave_mapeo = f"{ciclo_codigo}/{fila.rm_codigo}/{fila.medico_codigo}"
        if not _cabe(clave_mapeo, LARGO_CODIGO_EXTERNO):
            _omitir_por_largo(conteo, hallazgos, "panelmedico", clave,
                              "MapeoExterno.codigo_externo", LARGO_CODIGO_EXTERNO)
            continue
        ciclo_id, rm_id = _refs(db, pais_codigo, ciclo_codigo, fila.rm_codigo)
        if ciclo_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "panelmedico", clave, "el ciclo", ciclo_codigo)
            continue
        if rm_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "panelmedico", clave, "el representante",
                       fila.rm_codigo)
            continue

        def _buscar(f=fila, cid=ciclo_id, rid=rm_id):
            return (db.query(TargetMedico)
                    .filter(TargetMedico.rm_id == rid,
                            TargetMedico.ciclo_id == cid,
                            TargetMedico.medico_codigo == f.medico_codigo)
                    .first())

        def _crear(f=fila, cid=ciclo_id, rid=rm_id):
            # `potencial` NO se escribe: significa categoría A/B/C, no la
            # prioridad TOP/REGULAR de `ext` (§11.5 del requerimiento).
            nuevo = TargetMedico(
                pais_codigo=f.pais_codigo, rm_id=rid, ciclo_id=cid,
                medico_codigo=f.medico_codigo,
                programado=f.activo, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_TARGET_MEDICO, pais_codigo, clave_mapeo,
            TargetMedico, _buscar, _crear)
        registro.programado = fila.activo
        registro.activo = fila.activo
        conteo.anotar(resultado, fila.lote_id)
    return conteo


def integrar_visitas_medico(db: Session, pais_codigo: str, ciclo_codigo: str,
                            hallazgos: list,
                            estados_lote: dict[int, str] | None = None) -> ConteoHecho:
    """`ext.factvisitamedico` → `DW.FACT_Visita` (bitácora del módulo 4DX).

    `origen_id` es la clave de idempotencia que garantiza el contrato: reenviar
    el mismo registro corrige la fila, no la duplica.
    """
    conteo = ConteoHecho("factvisitamedico")
    filas = (db.query(ExtFactVisitaMedico)
             .filter(ExtFactVisitaMedico.pais_codigo == pais_codigo,
                     ExtFactVisitaMedico.ciclo_codigo == ciclo_codigo).all())
    conteo.en_ext = len(filas)
    if estados_lote is None:
        estados_lote = _resolver_estados_lotes(db, {f.lote_id for f in filas})
    for fila in filas:
        if not _lote_habilitado(estados_lote, fila.lote_id):
            _omitir_por_lote(conteo, hallazgos, "factvisitamedico", fila.origen_id,
                             fila.lote_id, estados_lote)
            continue
        if not _cabe(fila.origen_id, LARGO_CODIGO_EXTERNO):
            _omitir_por_largo(conteo, hallazgos, "factvisitamedico", fila.origen_id,
                              "MapeoExterno.codigo_externo", LARGO_CODIGO_EXTERNO)
            continue
        ciclo_id, rm_id = _refs(db, pais_codigo, ciclo_codigo, fila.rm_codigo)
        if ciclo_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factvisitamedico", fila.origen_id,
                       "el ciclo", ciclo_codigo)
            continue
        if rm_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factvisitamedico", fila.origen_id,
                       "el representante", fila.rm_codigo)
            continue
        # El médico se referencia por CÓDIGO en FACT_Visita, no por id, pero se
        # exige que esté sincronizado: una visita a un médico que VISTA no conoce
        # inflaría la cobertura con un contacto que no se puede auditar.
        if mapeo.id_mapeado(db, ENT_MEDICO, pais_codigo, fila.medico_codigo) is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factvisitamedico", fila.origen_id,
                       "el médico", fila.medico_codigo)
            continue

        def _buscar():
            return None  # la identidad la lleva el mapeo por origen_id

        def _crear(f=fila, cid=ciclo_id, rid=rm_id):
            nuevo = FactVisita(
                pais_codigo=f.pais_codigo, rm_id=rid, ciclo_id=cid,
                medico_codigo=f.medico_codigo, fecha_visita=f.fecha_visita,
                tipo_contacto=f.tipo_visita,
                estado_visita="Realizada" if f.ejecutada else "Cancelada",
                carga_excel_id=None)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_VISITA_MEDICO, pais_codigo, fila.origen_id,
            FactVisita, _buscar, _crear)
        registro.fecha_visita = fila.fecha_visita
        registro.tipo_contacto = fila.tipo_visita
        registro.estado_visita = "Realizada" if fila.ejecutada else "Cancelada"
        conteo.anotar(resultado, fila.lote_id)
    logger.info(f"Visitas médicas {pais_codigo}/{ciclo_codigo}: "
                f"{conteo.integrados} nuevas, {conteo.omitidos} omitidas")
    return conteo


#: Entidades propias de este sub-proyecto (farmacia) en `MapeoExterno`.
ENT_TARGET_FARMACIA = "target_farmacia"
ENT_VISITA_FARMACIA = "visita_farmacia"


def integrar_target_farmacia(db: Session, pais_codigo: str, ciclo_codigo: str,
                             hallazgos: list,
                             estados_lote: dict[int, str] | None = None) -> ConteoHecho:
    """`ext.targetfarmacia` → `Visita.DIM_FarmaciaVisita` (panel del VM).

    Entra como APROBADO: el flujo de aprobación VM→GD existe para las altas que
    solicita un representante, y esto es maestro oficial del SFA.

    `ciclos_sin_visita` NO se toca: lo lleva el rodaje de cierre de ciclo.
    """
    conteo = ConteoHecho("targetfarmacia")
    filas = (db.query(ExtTargetFarmacia)
             .filter(ExtTargetFarmacia.pais_codigo == pais_codigo,
                     ExtTargetFarmacia.ciclo_codigo == ciclo_codigo).all())
    conteo.en_ext = len(filas)
    if estados_lote is None:
        estados_lote = _resolver_estados_lotes(db, {f.lote_id for f in filas})
    for fila in filas:
        clave = f"{fila.rm_codigo}/{fila.farmacia_codigo}"
        if not _lote_habilitado(estados_lote, fila.lote_id):
            _omitir_por_lote(conteo, hallazgos, "targetfarmacia", clave,
                             fila.lote_id, estados_lote)
            continue
        clave_mapeo = f"{ciclo_codigo}/{fila.rm_codigo}/{fila.farmacia_codigo}"
        if not _cabe(clave_mapeo, LARGO_CODIGO_EXTERNO):
            _omitir_por_largo(conteo, hallazgos, "targetfarmacia", clave,
                              "MapeoExterno.codigo_externo", LARGO_CODIGO_EXTERNO)
            continue
        ciclo_id, rm_id = _refs(db, pais_codigo, ciclo_codigo, fila.rm_codigo)
        if rm_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "targetfarmacia", clave, "el representante",
                       fila.rm_codigo)
            continue
        maestro_id = mapeo.id_mapeado(db, ENT_FARMACIA, pais_codigo,
                                      fila.farmacia_codigo)
        if maestro_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "targetfarmacia", clave, "la farmacia",
                       fila.farmacia_codigo)
            continue

        def _buscar(f=fila, rid=rm_id, mid=maestro_id):
            return (db.query(FarmaciaVisita)
                    .filter(FarmaciaVisita.vm_id == rid,
                            FarmaciaVisita.maestro_farmacia_id == mid).first())

        def _crear(f=fila, rid=rm_id, mid=maestro_id, cid=ciclo_id):
            nuevo = FarmaciaVisita(
                vm_id=rid, maestro_farmacia_id=mid,
                estado_aprobacion="APROBADO", ciclo_alta_id=cid,
                activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_TARGET_FARMACIA, pais_codigo, clave_mapeo,
            FarmaciaVisita, _buscar, _crear)
        registro.activo = fila.activo
        # El panel puede haber sido ADOPTADO desde un alta que el VM ya había
        # solicitado a mano (PENDIENTE_ALTA/RECHAZADO): el SFA es maestro oficial
        # y no pasa por la cola VM→GD, así que se reafirma APROBADO también en el
        # camino de adopción/actualización, no solo al crear.
        registro.estado_aprobacion = "APROBADO"
        # `motivo` guarda el texto con que el GD rechazó el alta. Sin limpiarlo,
        # un panel que el SFA acaba de aprobar seguiría mostrando el motivo de
        # rechazo viejo en el panel del VM (`GET /farmacias/panel` lo pinta sin
        # mirar el estado).
        registro.motivo = None
        conteo.anotar(resultado, fila.lote_id)
    return conteo


def integrar_visitas_farmacia(db: Session, pais_codigo: str, ciclo_codigo: str,
                              hallazgos: list,
                              estados_lote: dict[int, str] | None = None) -> ConteoHecho:
    """`ext.factvisitafarmacia` → `Visita.FactVisitaFarmacia`.

    `registrado_por` queda nulo (no la capturó un usuario de VISTA) y la hora
    es 00:00 porque el contrato solo trae fecha.
    """
    conteo = ConteoHecho("factvisitafarmacia")
    filas = (db.query(ExtFactVisitaFarmacia)
             .filter(ExtFactVisitaFarmacia.pais_codigo == pais_codigo,
                     ExtFactVisitaFarmacia.ciclo_codigo == ciclo_codigo).all())
    conteo.en_ext = len(filas)
    if estados_lote is None:
        estados_lote = _resolver_estados_lotes(db, {f.lote_id for f in filas})
    for fila in filas:
        if not _lote_habilitado(estados_lote, fila.lote_id):
            _omitir_por_lote(conteo, hallazgos, "factvisitafarmacia", fila.origen_id,
                             fila.lote_id, estados_lote)
            continue
        if not _cabe(fila.origen_id, LARGO_CODIGO_EXTERNO):
            _omitir_por_largo(conteo, hallazgos, "factvisitafarmacia", fila.origen_id,
                              "MapeoExterno.codigo_externo", LARGO_CODIGO_EXTERNO)
            continue
        ciclo_id, rm_id = _refs(db, pais_codigo, ciclo_codigo, fila.rm_codigo)
        if ciclo_id is None or rm_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factvisitafarmacia", fila.origen_id,
                       "el ciclo o el representante",
                       f"{ciclo_codigo}/{fila.rm_codigo}")
            continue
        panel_id = mapeo.id_mapeado(
            db, ENT_TARGET_FARMACIA, pais_codigo,
            f"{ciclo_codigo}/{fila.rm_codigo}/{fila.farmacia_codigo}")
        if panel_id is None:
            # Una visita a una farmacia fuera del target del ciclo es ruido
            # normal (el VM puede visitar una farmacia no programada), no un
            # error de integración: se informa, no se marca como fallo.
            conteo.omitidos += 1
            hallazgos.append(Hallazgo(
                "factvisitafarmacia", fila.origen_id,
                f"La farmacia «{fila.farmacia_codigo}» visitada no está en el "
                f"target del representante para este ciclo; la visita quedó "
                f"fuera de plan y no se integró.", SEVERIDAD_AVISO))
            continue

        def _buscar():
            return None  # la identidad la lleva el mapeo por origen_id

        def _crear(f=fila, cid=ciclo_id, rid=rm_id, pid=panel_id):
            nuevo = FactVisitaFarmacia(
                vm_id=rid, ciclo_id=cid, farmacia_id=pid,
                fecha_hora=datetime(f.fecha_visita.year, f.fecha_visita.month,
                                    f.fecha_visita.day),
                ejecutada=f.ejecutada, registrado_por=None)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_VISITA_FARMACIA, pais_codigo, fila.origen_id,
            FactVisitaFarmacia, _buscar, _crear)
        registro.ejecutada = fila.ejecutada
        conteo.anotar(resultado, fila.lote_id)
    return conteo


#: En orden: los hechos de farmacia dependen del target, que dependen del panel.
_INTEGRADORES = (
    ("panelmedico", integrar_panel_medico),
    ("factvisitamedico", integrar_visitas_medico),
    ("targetfarmacia", integrar_target_farmacia),
    ("factvisitafarmacia", integrar_visitas_farmacia),
)

#: El tercer elemento reconstruye, en SQL, la misma `codigo_externo` que los
#: cuatro integradores de arriba le pasan a `mapeo.resolver` para ese hecho —
#: ver las llamadas a `mapeo.resolver` en `integrar_panel_medico` /
#: `integrar_visitas_medico` / `integrar_target_farmacia` /
#: `integrar_visitas_farmacia`. Se usa para el JOIN de `resumen_visitas`, no
#: para integrar (eso lo siguen haciendo los integradores, sin tocar).
_ORIGEN_CONTEO = {
    "panelmedico": (
        ExtPanelMedico, ENT_TARGET_MEDICO,
        lambda m: func.concat(m.ciclo_codigo, "/", m.rm_codigo, "/", m.medico_codigo)),
    "factvisitamedico": (
        ExtFactVisitaMedico, ENT_VISITA_MEDICO, lambda m: m.origen_id),
    "targetfarmacia": (
        ExtTargetFarmacia, ENT_TARGET_FARMACIA,
        lambda m: func.concat(m.ciclo_codigo, "/", m.rm_codigo, "/", m.farmacia_codigo)),
    "factvisitafarmacia": (
        ExtFactVisitaFarmacia, ENT_VISITA_FARMACIA, lambda m: m.origen_id),
}


def _lotes_del_ciclo(db: Session, pais_codigo: str, ciclo_codigo: str) -> list[int]:
    """Los `lote_id` que aportaron filas a este ciclo, en cualquiera de los
    cuatro hechos. Es la reconciliación lote ↔ ciclo: la integración trabaja
    por ciclo, pero el estado del §7.1 vive en el lote."""
    lotes: set[int] = set()
    for modelo, _, _ in _ORIGEN_CONTEO.values():
        lotes |= {f[0] for f in db.query(modelo.lote_id)
                  .filter(modelo.pais_codigo == pais_codigo,
                          modelo.ciclo_codigo == ciclo_codigo).distinct().all()}
    return sorted(lotes)


def _lote_tiene_filas_de_otro_ciclo(db: Session, lote_id: int,
                                    ciclo_codigo: str) -> bool:
    """¿El lote todavía tiene filas de un ciclo DISTINTO al que se acaba de
    integrar, en cualquiera de los cuatro hechos? Un mismo lote puede traer
    filas de más de un ciclo (p. ej. un corte de mes a mitad del envío); si
    las tiene, cerrarlo como INTEGRADO dejaría esas otras filas huérfanas —y
    como `validar_lote` (sub-proyecto 1) rechaza re-validar un lote ya
    INTEGRADO, ese resto ya no se podría ni reintentar."""
    for modelo, _, _ in _ORIGEN_CONTEO.values():
        existe = (db.query(modelo.lote_id)
                  .filter(modelo.lote_id == lote_id,
                          modelo.ciclo_codigo != ciclo_codigo)
                  .first())
        if existe is not None:
            return True
    return False


def _cerrar_lotes(db: Session, lotes: list[int], detalle: str, ciclo_codigo: str,
                  lotes_con_filas_aportadas: set[int]) -> list[int]:
    """§7.1 paso 4: marca como INTEGRADO los lotes que estaban en VALIDADO.

    Solo VALIDADO → INTEGRADO. Un lote RECHAZADO no se rescata por la puerta
    de atrás, y uno ya INTEGRADO se deja como está (la re-ejecución del
    proceso es idempotente por diseño del contrato).

    Dos condiciones adicionales, ambas necesarias para que INTEGRADO signifique
    lo que dice:
    1. El lote aportó al menos una fila efectivamente creada o actualizada en
       ESTA corrida (`lotes_con_filas_aportadas`, construido en `integrar_todo`
       a partir de `ConteoHecho.lotes_aportados`). Sin esto, un lote cuyas
       filas se omitieron TODAS (p. ej. dimensión sin sincronizar) quedaba
       INTEGRADO con «0 nuevas, 0 actualizadas» en el mensaje.
    2. El lote no tiene filas de OTRO ciclo pendientes
       (`_lote_tiene_filas_de_otro_ciclo`). Sin esto, un lote con filas de dos
       ciclos quedaba INTEGRADO al procesar solo uno, dejando el resto
       huérfano y sin forma de reintentarse.

    Escribir `estado`/`mensaje` no viola la prohibición sobre `ext`: esa
    prohibición es sobre el ESQUEMA. El contrato asigna esos dos campos a
    VISTA y el sub-proyecto 1 ya los escribe.
    """
    if not lotes:
        return []
    cerrados = []
    for lote in (db.query(ExtControlCarga)
                 .filter(ExtControlCarga.lote_id.in_(lotes)).all()):
        if (lote.estado or "").strip().upper() != "VALIDADO":
            continue
        if lote.lote_id not in lotes_con_filas_aportadas:
            continue
        if _lote_tiene_filas_de_otro_ciclo(db, lote.lote_id, ciclo_codigo):
            continue
        lote.estado = "INTEGRADO"
        lote.mensaje = detalle[:500]
        cerrados.append(lote.lote_id)
    return sorted(cerrados)


def integrar_todo(db: Session, pais_codigo: str, ciclo_codigo: str) -> dict:
    """Los cuatro pasos del §7.1 para un ciclo: integrar, calcular, recalcular
    el Score y cerrar los lotes.

    Un solo commit para la integración: o entra el ciclo coherente o no entra
    nada. Las filas problemáticas no abortan —se omiten con su hallazgo—, así
    que el commit confirma solo lo que sí se pudo resolver.

    El cálculo de indicadores va DESPUÉS de integrar, aunque lea de `ext` y no de
    las tablas internas: así una sola acción del operador deja el ciclo completo,
    sin un segundo paso que se olvide.
    """
    from app.services import integracion_indicadores_service as indicadores
    from app.services import recalculo_service

    hallazgos: list[Hallazgo] = []
    conteos: list[ConteoHecho] = []
    # Los lotes del ciclo (y sus estados) se resuelven UNA sola vez para las
    # cuatro llamadas de abajo — no una consulta a `ExtControlCarga` por fila
    # ni una por integrador. `_lotes_del_ciclo` solo lee `ext`, así que da
    # igual calcularlo antes o después de integrar.
    lotes_del_ciclo = _lotes_del_ciclo(db, pais_codigo, ciclo_codigo)
    estados_lote = _resolver_estados_lotes(db, set(lotes_del_ciclo))
    for _, integrar in _INTEGRADORES:
        conteos.append(integrar(db, pais_codigo, ciclo_codigo, hallazgos,
                                estados_lote))

    # `calcular_indicadores` ya se protege solo contra el ciclo cerrado: devuelve
    # `omitido_ciclo_cerrado=True` sin borrar ni escribir nada (si borrara, se
    # llevaría por delante los `puntos_obtenidos` del snapshot histórico y el
    # recálculo posterior abortaría sin reponerlos). Ese dict viaja tal cual al
    # llamador, así que la UI distingue "no había nada que calcular" de "el
    # ciclo está cerrado y no se tocó". Aquí NO se duplica el guard.
    try:
        resumen_ind = indicadores.calcular_indicadores(
            db, pais_codigo, ciclo_codigo, hallazgos)
    except ValueError as exc:
        resumen_ind = {"rms": 0, "filas": 0, "omitido_ciclo_cerrado": False}
        hallazgos.append(Hallazgo("indicador", None, str(exc), SEVERIDAD_ERROR))

    detalle = "; ".join(
        f"{c.hecho}: {c.integrados} nuevas, {c.actualizados} actualizadas"
        for c in conteos)
    lotes_con_filas_aportadas: set[int] = set()
    for c in conteos:
        lotes_con_filas_aportadas |= c.lotes_aportados
    cerrados = _cerrar_lotes(
        db, lotes_del_ciclo, f"Integrado en VISTA. {detalle}",
        ciclo_codigo, lotes_con_filas_aportadas)

    db.commit()

    # §7.1 paso 3 — DESPUÉS del commit, a propósito: el recálculo es un paso
    # independiente que debe operar sobre datos ya confirmados (el motor recibe
    # esta misma `Session` y comitea sobre ella, no abre una transacción
    # propia). Si se llamara antes del commit y el motor fallara, se llevaría
    # por delante — con el rollback — la integración de los hechos, que es
    # información de origen y debe conservarse aunque el recálculo no corra.
    # Sin esta llamada, integrar un ciclo tampoco movería el Score, el ranking
    # ni los reconocimientos: seguirían mostrando el cálculo anterior.
    ciclo_id = mapeo.id_mapeado(db, ENT_CICLO, pais_codigo, ciclo_codigo)
    if ciclo_id is None:
        recalculo = {"abortado": True, "motivo": "El ciclo no está sincronizado."}
    else:
        recalculo = recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)
        if recalculo.get("abortado"):
            # Ciclo cerrado: los hechos entran (son historia) pero el Score no
            # se toca. No es un error de la integración; se informa y ya.
            logger.warning(
                f"Integración {pais_codigo}/{ciclo_codigo}: hechos integrados "
                f"pero el recálculo se abortó ({recalculo.get('motivo')})")

    return {
        "pais_codigo": pais_codigo, "ciclo_codigo": ciclo_codigo,
        "hechos": [{
            "hecho": c.hecho, "en_ext": c.en_ext, "integrados": c.integrados,
            "actualizados": c.actualizados, "omitidos": c.omitidos,
        } for c in conteos],
        "indicadores": resumen_ind,
        "recalculo": recalculo,
        "lotes_cerrados": cerrados,
        "hallazgos": [{
            "hecho": h.hecho, "origen_id": h.origen_id,
            "problema": h.problema, "severidad": h.severidad,
        } for h in hallazgos],
    }


def resumen_visitas(db: Session, pais_codigo: str, ciclo_codigo: str) -> list[dict]:
    """Filas en `ext` frente a filas ya integradas, por hecho — ambos conteos
    acotados a este mismo `(pais_codigo, ciclo_codigo)`.

    `MapeoExterno` no tiene columna `ciclo_codigo` (la clave de mapeo es
    `entidad + pais_codigo + codigo_externo`), así que "integradas" no se
    puede pedir filtrando la tabla de mapeo por ciclo directamente. En vez de
    eso se hace un JOIN, en el servidor, entre las filas de `ext` de ESTE
    ciclo y `MapeoExterno` por la misma `codigo_externo` que construyó el
    integrador (ver `_ORIGEN_CONTEO`) — así una fila de otro ciclo del mismo
    país nunca cuenta aquí, y no se traen miles de filas a Python para armar
    un `IN` en memoria.
    """
    salida = []
    for hecho, (modelo, entidad, clave_externa) in _ORIGEN_CONTEO.items():
        base = (db.query(modelo)
                .filter(modelo.pais_codigo == pais_codigo,
                        modelo.ciclo_codigo == ciclo_codigo))
        en_ext = base.count()
        integradas = base.join(
            MapeoExterno,
            (MapeoExterno.entidad == entidad)
            & (MapeoExterno.pais_codigo == pais_codigo)
            & (MapeoExterno.codigo_externo == clave_externa(modelo)),
        ).count()
        salida.append({"hecho": hecho, "en_ext": en_ext,
                       "integradas": integradas})
    return salida
