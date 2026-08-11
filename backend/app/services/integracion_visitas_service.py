"""Integra los hechos de visita que Mallén deja en `ext` con las tablas de VISTA.

QUÉ ALIMENTA CADA COSA
-----------------------
VISTA tiene DOS tablas de visita distintas, y cada hecho de `ext` alimenta a
las DOS (fix del defecto CRITICAL: antes solo se escribía la primera).

- `panelmedico` → `Config.DIM_TargetMedico` (universo del módulo Cobertura
  Predictiva/4DX) **y** `Visita.DIM_MedicoVisita` (panel del módulo de Visita).
- `factvisitamedico` → `DW.FACT_Visita` (bitácora de 4DX) **y**
  `Visita.FactVisita` (registro que consume el módulo de Visita: Cobertura,
  Costo/ROI, parrilla y las visitas acompañadas que alimentan Coaching MORE).

Sin el segundo destino de cada par, Cobertura Predictiva mostraba actividad
normal mientras el módulo de Visita se quedaba congelado en cero — los dos
endpoints de captura manual que antes escribían `Visita.DIM_MedicoVisita`/
`Visita.FactVisita` se apagaron, y nada más los reemplazó hasta este fix.

**No alimenta los ocho indicadores del Score**: esos los calcula
`integracion_indicadores_service` a partir de `ext`, porque VISTA nunca los
derivó de visitas — llegaban ya calculados en un Excel.

Una fila cuya dimensión no esté sincronizada se OMITE con hallazgo, nunca se
resuelve al vuelo: adoptar o crear dimensiones es trabajo del sub-proyecto 2 y
duplicar esa lógica aquí llevaría a dos verdades sobre la misma identidad. Lo
mismo aplica al panel de Visita: `integrar_visitas_medico` exige que el médico
ya tenga fila en `Visita.DIM_MedicoVisita` (la deja `integrar_panel_medico`,
que corre antes en `_INTEGRADORES`) — si no la encuentra, omite solo ese
segundo destino con hallazgo; el numerador de 4DX (`DW.FACT_Visita`) entra
igual, porque no depende del panel de Visita.

Tampoco se integra una fila cuyo LOTE no esté en VALIDADO/INTEGRADO (ver
`_ESTADOS_LOTE_INTEGRABLES`): el sub-proyecto 1 valida el lote y lo puede
marcar RECHAZADO, y un integrador que no mirara ese estado se tragaría las
filas de un lote que la validación ya descartó.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.dimensiones import Medico, RepresentanteMedico, TargetMedico
from app.models.hechos import Visita as FactVisita
from app.models.hechos import Ventas
from app.models.integracion_ext import (
    ExtControlCarga, ExtFactVenta, ExtFactVisitaFarmacia, ExtFactVisitaMedico,
    ExtPanelMedico, ExtTargetFarmacia,
)
from app.models.mapeo_externo import (
    ENT_CICLO, ENT_FARMACIA, ENT_MEDICO, ENT_REPRESENTANTE, MapeoExterno,
)
from app.models.visita import (
    FactVisitaFarmacia, FarmaciaVisita, MedicoVisita, VisitaRegistro,
)
from app.services import integracion_mapeo as mapeo
from app.services.puntaje_service import calcular_cumplimiento

SEVERIDAD_ERROR = "error"
SEVERIDAD_AVISO = "aviso"

#: Entidades propias de este sub-proyecto en `MapeoExterno`.
ENT_TARGET_MEDICO = "target_medico"
ENT_VISITA_MEDICO = "visita_medico"

#: Entidades NUEVAS para el segundo destino de cada hecho de médico (el fix del
#: defecto CRITICAL, ver docstring del módulo). NO reutilizan
#: `ENT_TARGET_MEDICO`/`ENT_VISITA_MEDICO`: esas ya apuntan a
#: `Config.DIM_TargetMedico`/`DW.FACT_Visita` con las mismas claves naturales
#: (ciclo/rm/médico y origen_id respectivamente); compartir la entidad haría que
#: `mapeo.resolver` buscara el `id_interno` en la tabla equivocada y corrompería
#: el mapeo de ambos destinos.
ENT_PANEL_MEDICO_VISITA = "panel_medico_visita"
ENT_VISITA_MEDICO_REGISTRO = "visita_medico_registro"

#: Entidad propia para la fila AGREGADA de `DW.FACT_Ventas`. Nueva y no
#: reutilizada, por lo mismo que las de los hechos de médico: `MapeoExterno` es
#: único por `(entidad, país, código)` con un solo `id_interno`, así que
#: compartirla haría que `resolver` buscara el id en la tabla equivocada.
#: Es además la ÚNICA idempotencia que tiene `FACT_Ventas`: esa tabla no lleva
#: ningún UNIQUE, y como el ROI suma `ventas_reales`, duplicar una fila
#: inventaría ingresos que nadie podría rastrear.
ENT_VENTAS_RM_CICLO = "ventas_rm_ciclo"

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

    def anotar(self, resultado: str, *lotes: int) -> None:
        if resultado == mapeo.RESULTADO_CREADO:
            self.integrados += 1
        else:
            # Adoptado y actualizado se cuentan igual: para un hecho no existe la
            # distinción del maestro (nadie los cargó antes a mano).
            self.actualizados += 1
        self.lotes_aportados.update(lotes)


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


def _es_top(prioridad: str | None) -> bool:
    """`ext.panelmedico.prioridad` → booleano. Tolerante a la caja: el origen ya
    ha demostrado mandar variaciones."""
    return (prioridad or "").strip().upper() == "TOP"


def integrar_panel_medico(db: Session, pais_codigo: str, ciclo_codigo: str,
                          hallazgos: list,
                          estados_lote: dict[int, str] | None = None) -> ConteoHecho:
    """`ext.panelmedico` → DOS destinos: `Config.DIM_TargetMedico` (universo del
    módulo 4DX) y, si el médico está sincronizado, `Visita.DIM_MedicoVisita`
    (panel del módulo de Visita, fix del defecto CRITICAL — ver docstring del
    módulo).

    El primer destino se escribe SIEMPRE que ciclo y representante estén
    resueltos — igual que antes de añadir el segundo destino (`git show
    b899e87`): 4DX no debe perder universo por un médico que el maestro
    todavía no sincronizó, justo el escenario del estreno con el maestro
    incompleto. Una regresión posterior hizo depender los DOS destinos de
    resolver el médico, y omitía la fila entera —incluido `DIM_TargetMedico`—
    cuando el maestro le faltaba: se revirtió. Solo el segundo destino, que sí
    necesita el maestro para tomar `nombre_completo`, se omite —con su propio
    hallazgo— cuando no se puede resolver; mismo patrón, a propósito, que
    `integrar_visitas_medico` ya usa para su propio segundo destino.

    La frecuencia (F1/F2) NO se guarda en ninguno de los dos: ni
    `DIM_TargetMedico` ni `DIM_MedicoVisita` tienen esa columna y no se les
    añade. El motor de indicadores la lee de `ext`, que es su origen.

    El segundo destino entra como APROBADO, igual que `integrar_target_farmacia`
    con `DIM_FarmaciaVisita`: es maestro oficial del SFA y no pasa por la cola
    de aprobación VM→GD que existe para las altas que pide un representante.
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
        # Se cuenta por el destino "primario" (`TargetMedico`, igual que antes
        # de añadir el segundo destino): entra siempre que ciclo/representante
        # estén resueltos, sin depender de si el médico también lo está.
        conteo.anotar(resultado, fila.lote_id)

        # Segundo destino: `Visita.DIM_MedicoVisita.nombre_completo` es NOT
        # NULL y sale del maestro (`Config.DIM_Medico`), no de `ext` (§ "el
        # maestro es la fuente"). Sin el médico sincronizado no hay de dónde
        # tomar ese nombre, así que SOLO este destino se omite -- el universo
        # de 4DX ya quedó a salvo arriba -- con su propio hallazgo; mismo
        # patrón que `integrar_visitas_medico` usa para su segundo destino.
        maestro_medico_id = mapeo.id_mapeado(db, ENT_MEDICO, pais_codigo,
                                             fila.medico_codigo)
        maestro_medico = (db.get(Medico, maestro_medico_id)
                          if maestro_medico_id is not None else None)
        if maestro_medico is None:
            hallazgos.append(Hallazgo(
                "panelmedico", clave,
                f"El médico «{fila.medico_codigo}» no está sincronizado; se "
                f"integró a Cobertura Predictiva (Config.DIM_TargetMedico) "
                f"pero NO al panel del módulo de Visita "
                f"(Visita.DIM_MedicoVisita). Sincroniza el maestro de "
                f"médicos primero.", SEVERIDAD_ERROR))
            continue

        def _buscar_panel(rid=rm_id, mid=maestro_medico_id):
            return (db.query(MedicoVisita)
                    .filter(MedicoVisita.vm_id == rid,
                            MedicoVisita.maestro_medico_id == mid)
                    .first())

        def _crear_panel(f=fila, rid=rm_id, mid=maestro_medico_id, cid=ciclo_id,
                         nombre=maestro_medico.nombre):
            # Los campos sin origen claro (frecuencia_visita, especialidad,
            # ubicación, contacto...) quedan NULL/default: `ext.panelmedico` no
            # los trae y adivinarlos sería peor que dejarlos vacíos.
            nuevo = MedicoVisita(
                vm_id=rid, maestro_medico_id=mid, codigo=f.medico_codigo,
                nombre_completo=(nombre or "").strip().upper(),
                activo=f.activo, estado_aprobacion="APROBADO",
                ciclo_alta_id=cid, es_top=_es_top(f.prioridad))
            db.add(nuevo)
            db.flush()
            return nuevo

        panel, _resultado_panel = mapeo.resolver(
            db, ENT_PANEL_MEDICO_VISITA, pais_codigo, clave_mapeo,
            MedicoVisita, _buscar_panel, _crear_panel)
        panel.activo = fila.activo
        # El panel puede haber sido ADOPTADO desde un alta que el VM ya había
        # solicitado a mano (PENDIENTE_ALTA/RECHAZADO): el SFA es maestro
        # oficial y no pasa por la cola VM→GD, así que se reafirma APROBADO
        # también en el camino de adopción/actualización, no solo al crear —
        # mismo patrón que `integrar_target_farmacia` con `DIM_FarmaciaVisita`.
        panel.estado_aprobacion = "APROBADO"
        # `motivo` guarda el texto con que el GD rechazó el alta. Sin
        # limpiarlo, un panel que el SFA acaba de aprobar seguiría mostrando el
        # motivo de rechazo viejo en el panel del VM.
        panel.motivo = None
        # Se reafirma SIEMPRE, como `activo` y `estado_aprobacion`: la prioridad
        # es dato maestro del SFA. Un médico que pasa de TOP a REGULAR entre
        # ciclos tiene que dejar de serlo. (A diferencia de `nombre_completo`,
        # que solo se escribe al crear para no pisar correcciones del GD.)
        panel.es_top = _es_top(fila.prioridad)
        # `ciclos_sin_visita` NO se toca aquí (ni al crear ni al adoptar): lo
        # calcula el rodaje de cierre de ciclo (Ruptura de Secuencia), no la
        # integración. `nombre_completo` tampoco se reafirma en el camino de
        # adopción/actualización a propósito: si el GD ya corrigió el nombre a
        # mano, un re-envío del mismo panel no debe pisarlo — solo se toma del
        # maestro la primera vez, al crear.
        # `conteo.anotar` ya se llamó arriba, sobre el destino primario
        # (`TargetMedico`): no se repite aquí para no duplicar el número de
        # "integradas"/"actualizadas" de una sola fila de `ext`.
    return conteo


def integrar_visitas_medico(db: Session, pais_codigo: str, ciclo_codigo: str,
                            hallazgos: list,
                            estados_lote: dict[int, str] | None = None) -> ConteoHecho:
    """`ext.factvisitamedico` → DOS destinos: `DW.FACT_Visita` (bitácora del
    módulo 4DX) y `Visita.FactVisita` (registro que consume el módulo de
    Visita: Cobertura, Costo/ROI, parrilla y acompañadas de Coaching MORE — fix
    del defecto CRITICAL, ver docstring del módulo).

    `origen_id` es la clave de idempotencia que garantiza el contrato: reenviar
    el mismo registro corrige la fila, no la duplica (para los dos destinos,
    cada uno con su propia entidad de `MapeoExterno`).

    El segundo destino exige que el médico ya tenga panel en
    `Visita.DIM_MedicoVisita` — lo deja `integrar_panel_medico`, que corre
    antes en `_INTEGRADORES`, así que la fila normalmente existirá. Si no la
    encuentra, esa mitad se omite con hallazgo de error (no se crea el panel al
    vuelo desde aquí: saltarse el flujo de aprobación VM→GD sería peor que
    perder la fila); el primer destino (`DW.FACT_Visita`, que no depende del
    panel) entra igual.

    `gerente_codigo` del contrato se descarta a propósito: `Visita.FactVisita`
    no tiene columna para "quién acompañó" y no se le añade aquí. No se pierde
    función — Coaching resuelve el gerente de una visita acompañada por
    `RepresentanteMedico.gerente_id`, no por lo que reporte el contrato de
    Mallén.
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
        maestro_medico_id = mapeo.id_mapeado(db, ENT_MEDICO, pais_codigo,
                                             fila.medico_codigo)
        if maestro_medico_id is None:
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
        # Se cuenta por el destino de 4DX (igual que antes de este fix): las
        # dos escrituras son una sola acción lógica sobre la misma fila de
        # `ext`, así que un solo `anotar` evita duplicar "integradas". El
        # segundo destino, si falla por falta de panel, se informa aparte con
        # su propio hallazgo más abajo, sin tocar este conteo — 4DX sí recibió
        # el dato, la omisión es solo del módulo de Visita.
        conteo.anotar(resultado, fila.lote_id)

        panel = (db.query(MedicoVisita)
                .filter(MedicoVisita.vm_id == rm_id,
                        MedicoVisita.maestro_medico_id == maestro_medico_id)
                .first())
        if panel is None:
            hallazgos.append(Hallazgo(
                "factvisitamedico", fila.origen_id,
                f"El médico «{fila.medico_codigo}» no tiene panel en "
                f"Visita.DIM_MedicoVisita para el representante «{fila.rm_codigo}»"
                f"; la visita se integró a Cobertura Predictiva pero NO al "
                f"módulo de Visita. Sincroniza el panel (panelmedico) primero.",
                SEVERIDAD_ERROR))
            continue

        def _buscar_registro():
            return None  # la identidad la lleva el mapeo por origen_id

        def _crear_registro(f=fila, cid=ciclo_id, rid=rm_id, mid=panel.id):
            nuevo = VisitaRegistro(
                vm_id=rid, ciclo_id=cid, medico_id=mid,
                tipo_visita=f.tipo_visita,
                fecha_hora=datetime(f.fecha_visita.year, f.fecha_visita.month,
                                    f.fecha_visita.day),
                ejecutada=f.ejecutada, acompanado=f.acompanado,
                causa_no_visita=f.causa_no_visita,
                # No lo capturó un usuario de VISTA y el contrato no lo manda:
                # registrado_por/comentario/productos/latitud/longitud/foto/
                # foto_mime quedan todos NULL (sin origen).
                registrado_por=None)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro_v, _resultado_v = mapeo.resolver(
            db, ENT_VISITA_MEDICO_REGISTRO, pais_codigo, fila.origen_id,
            VisitaRegistro, _buscar_registro, _crear_registro)
        registro_v.medico_id = panel.id
        registro_v.tipo_visita = fila.tipo_visita
        registro_v.fecha_hora = datetime(
            fila.fecha_visita.year, fila.fecha_visita.month, fila.fecha_visita.day)
        registro_v.ejecutada = fila.ejecutada
        registro_v.acompanado = fila.acompanado
        registro_v.causa_no_visita = fila.causa_no_visita
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


def integrar_ventas(db: Session, pais_codigo: str, ciclo_codigo: str,
                    hallazgos: list,
                    estados_lote: dict[int, str] | None = None) -> ConteoHecho:
    """`ext.factventa` → `DW.FACT_Ventas`, AGREGANDO por (país, ciclo, RM).

    La granularidad no coincide: el contrato manda detalle (con `producto_codigo`
    opcional) y `FACT_Ventas` es una fila por país+línea+RM+ciclo, sin columna de
    producto. Se suma `valor_venta` y `cuota`; el detalle se descarta porque no
    hay dónde ponerlo y ningún consumidor lo pide.

    Alimenta dos cosas: el indicador VENTAS (vía `integracion_indicadores_service`)
    y los INGRESOS DEL ROI del módulo de Visita, que lee esta tabla — de ahí que
    duplicar una fila sea especialmente dañino.

    Rellena `cumplimiento_pct` (criterio del ETL legacy, para no dejar la fila a
    medias) pero **NO** `FACT_Ventas.puntaje`, a propósito: ese campo legacy se
    calculaba con `convertir_a_puntaje` contra `DIM_IndicadorTabla`, y poblarlo
    aquí abriría un segundo camino de puntuación en paralelo al de
    `FACT_ResultadoIndicador` — justo lo que el sistema lleva dos rediseños
    evitando. Su único lector es `comercial.py`, código muerto no registrado en
    `router.py`. No es un olvido: no rellenarlo es la decisión correcta.
    """
    conteo = ConteoHecho("factventa")
    filas = (db.query(ExtFactVenta)
             .filter(ExtFactVenta.pais_codigo == pais_codigo,
                     ExtFactVenta.ciclo_codigo == ciclo_codigo).all())
    conteo.en_ext = len(filas)
    if estados_lote is None:
        estados_lote = _resolver_estados_lotes(db, {f.lote_id for f in filas})

    # Agregación por RM. Se agrupa DESPUÉS de filtrar por lote: una fila de un
    # lote rechazado no debe sumar al total de nadie.
    por_rm: dict[str, list] = {}
    for fila in filas:
        if not _lote_habilitado(estados_lote, fila.lote_id):
            _omitir_por_lote(conteo, hallazgos, "factventa", fila.origen_id,
                             fila.lote_id, estados_lote)
            continue
        por_rm.setdefault(fila.rm_codigo, []).append(fila)

    for rm_codigo, grupo in sorted(por_rm.items()):
        clave = f"{ciclo_codigo}/{rm_codigo}"
        if not _cabe(clave, LARGO_CODIGO_EXTERNO):
            _omitir_por_largo(conteo, hallazgos, "factventa", clave,
                              "MapeoExterno.codigo_externo", LARGO_CODIGO_EXTERNO)
            continue
        ciclo_id, rm_id = _refs(db, pais_codigo, ciclo_codigo, rm_codigo)
        if ciclo_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factventa", clave, "el ciclo", ciclo_codigo)
            continue
        if rm_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factventa", clave, "el representante", rm_codigo)
            continue
        rm = db.query(RepresentanteMedico).filter(
            RepresentanteMedico.id == rm_id).first()
        if rm is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factventa", clave, "la ficha del representante",
                       rm_codigo)
            continue

        total_venta = sum((f.valor_venta or Decimal(0) for f in grupo), Decimal(0))
        total_cuota = sum((f.cuota or Decimal(0) for f in grupo), Decimal(0))

        # La cuota se SUMA (decisión del cliente), pero varias filas con la cuota
        # EXACTAMENTE igual son la firma de un ERP que repite el total del RM en
        # cada producto en vez de repartirlo. Sumarla ahí la multiplicaría por el
        # número de productos y hundiría el cumplimiento de todos sin que nada lo
        # delatara. No se corrige automáticamente —adivinar haría el número
        # impredecible—: se avisa.
        cuotas = {f.cuota for f in grupo}
        if len(grupo) > 1 and len(cuotas) == 1:
            hallazgos.append(Hallazgo(
                "factventa", clave,
                f"El representante «{rm_codigo}» trae {len(grupo)} filas con la "
                f"MISMA cuota ({next(iter(cuotas))}). Se sumaron, pero si el "
                f"origen repite la cuota total por producto en vez de "
                f"repartirla, el total quedaría multiplicado por "
                f"{len(grupo)}. Confirmar con el laboratorio.",
                SEVERIDAD_AVISO))

        def _buscar(cid=ciclo_id, rid=rm_id):
            # `.order_by(Ventas.id)`: sin orden explícito, cuál fila devuelve
            # PostgreSQL con `.first()` no está garantizado y puede cambiar de
            # una corrida a otra sobre los MISMOS datos -- eso volvía no
            # determinista tanto la adopción (qué fila se actualiza) como el
            # listado de "sobrantes" del hallazgo de más abajo. Se adopta la
            # fila más ANTIGUA (id menor), estable entre corridas.
            return (db.query(Ventas)
                    .filter(Ventas.pais_codigo == pais_codigo,
                            Ventas.ciclo_id == cid, Ventas.rm_id == rid)
                    .order_by(Ventas.id).first())

        def _crear(cid=ciclo_id, rid=rm_id, r=rm):
            nuevo = Ventas(pais_codigo=pais_codigo, linea_id=r.linea_id,
                           rm_id=rid, ciclo_id=cid,
                           ventas_reales=Decimal(0), cuota=Decimal(0))
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_VENTAS_RM_CICLO, pais_codigo, clave, Ventas, _buscar, _crear)

        # `FACT_Ventas` no tiene ningún UNIQUE y el ETL legacy de Excel es
        # *append-only* (`etl_service.py` agrega una fila por cada fila del
        # Excel, sin buscar ni deduplicar) -- nada garantiza una sola fila
        # legacy por (país, ciclo, RM), y como el ciclo es un biciclo mientras
        # el Excel de ventas era mensual, dos filas del mismo RM en el mismo
        # ciclo es un escenario esperable. `_buscar` (arriba) hace `.first()`:
        # adopta o actualiza UNA sola fila; las demás seguirían sumando en
        # silencio al ROI un ingreso que ya no corresponde.
        #
        # Esta comprobación NO puede vivir dentro de `_buscar`: una vez que
        # existe el mapeo, `mapeo.resolver` (`integracion_mapeo.py`) ya NO
        # vuelve a llamar `buscar_natural` en las corridas siguientes -- el
        # aviso se emitiría una sola vez en la vida y nunca más, aunque el
        # duplicado siga ahí. Por eso se repite aquí, en cada corrida, sobre
        # la misma clave natural que usa `_buscar`.
        otras = (db.query(Ventas.id)
                 .filter(Ventas.pais_codigo == pais_codigo,
                         Ventas.ciclo_id == ciclo_id, Ventas.rm_id == rm_id,
                         Ventas.id != registro.id).all())
        if otras:
            ids_otras = sorted(o[0] for o in otras)
            hallazgos.append(Hallazgo(
                "factventa", clave,
                f"El representante «{rm_codigo}» tiene {len(ids_otras)} "
                f"fila(s) adicionales en FACT_Ventas para este ciclo (ids: "
                f"{', '.join(str(i) for i in ids_otras)}), anteriores a la "
                f"integración. Se actualizó una sola; las demás siguen "
                f"sumando al ROI un ingreso que ya no corresponde. Bórralas "
                f"o consolídalas.",
                SEVERIDAD_ERROR))

        registro.ventas_reales = total_venta
        registro.cuota = total_cuota
        registro.linea_id = rm.linea_id
        # `cumplimiento_pct` en 0-100 (criterio del ETL legacy, para no dejar la
        # tabla a medias). El Score NO lo usa: su camino es FACT_ResultadoIndicador.
        registro.cumplimiento_pct = (
            calcular_cumplimiento(total_venta, total_cuota) if total_cuota else None)
        # Un mismo RM/ciclo puede traer filas de VARIOS lotes (un reenvío parcial
        # de Mallén). Todos aportaron a la suma, así que todos deben poder cerrar:
        # acreditar solo el primero dejaría al resto atascado en VALIDADO aunque
        # sus datos ya estén integrados. El conteo de integrados/actualizados
        # sigue siendo uno por RM — lo que se multiplica son los lotes, no las filas.
        conteo.anotar(resultado, *{f.lote_id for f in grupo})

    return conteo


#: En orden: los hechos de farmacia dependen del target, que dependen del panel.
#: Las ventas no dependen de los otros hechos, pero el orden fija el de la
#: respuesta.
_INTEGRADORES = (
    ("panelmedico", integrar_panel_medico),
    ("factvisitamedico", integrar_visitas_medico),
    ("targetfarmacia", integrar_target_farmacia),
    ("factvisitafarmacia", integrar_visitas_farmacia),
    ("factventa", integrar_ventas),
)

#: El tercer elemento reconstruye, en SQL, la misma `codigo_externo` que los
#: cinco integradores de arriba le pasan a `mapeo.resolver` para ese hecho —
#: ver las llamadas a `mapeo.resolver` en `integrar_panel_medico` /
#: `integrar_visitas_medico` / `integrar_target_farmacia` /
#: `integrar_visitas_farmacia` / `integrar_ventas`. Se usa para el JOIN de
#: `resumen_visitas`, no para integrar (eso lo siguen haciendo los
#: integradores, sin tocar).
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
    "factventa": (
        ExtFactVenta, ENT_VENTAS_RM_CICLO,
        lambda m: func.concat(m.ciclo_codigo, "/", m.rm_codigo)),
}


def _lotes_del_ciclo(db: Session, pais_codigo: str, ciclo_codigo: str) -> list[int]:
    """Los `lote_id` que aportaron filas a este ciclo, en cualquiera de los
    cinco hechos. Es la reconciliación lote ↔ ciclo: la integración trabaja
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
    integrar, en cualquiera de los cinco hechos? Un mismo lote puede traer
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
    # cinco llamadas de abajo — no una consulta a `ExtControlCarga` por fila
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
