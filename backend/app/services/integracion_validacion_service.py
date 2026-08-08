"""Validación de los lotes que Laboratorio Mallén deja en el esquema `ext`.

LA REGLA QUE MANDA ESTE DISEÑO (§7.1 del Requerimiento de Datos)
-----------------------------------------------------------------
«Las inconsistencias se registran sin detener el lote completo.» Por eso el
contrato deliberadamente NO lleva CHECK en los campos acotados: un CHECK
rechazaría el INSERT de Mallén y abortaría su envío entero por una fila mala.
Al validar aquí, VISTA acepta el lote y devuelve un informe de qué corregir.

Consecuencia directa: ninguna función de este módulo levanta excepción por datos
malos. Anota el hallazgo y sigue con la fila siguiente. Las únicas excepciones
son de operación (lote inexistente, lote ya integrado), no de contenido.

LO QUE NO SE VALIDA AQUÍ
------------------------
- Duplicidad de `origen_id`: los índices `ux_*_origen` del contrato ya la
  impiden a nivel de base. Re-verificarla sería trabajo muerto.
- Que los códigos existan en los catálogos internos de VISTA (`Config.DIM_*`):
  eso pertenece a la sincronización de dimensiones, no al contrato.
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.integracion_ext import (
    ExtControlCarga, ExtFactEvaluacionConocimiento, ExtFactPrescripcionDetalle,
    ExtFactVenta, ExtFactVisitaFarmacia, ExtFactVisitaMedico, ExtPanelMedico,
    ExtTargetFarmacia,
)
from app.models.integracion_hallazgo import (
    SEVERIDAD_AVISO, SEVERIDAD_ERROR, IntegracionHallazgo,
)

ESTADOS_LOTE = {"RECIBIDO", "VALIDADO", "INTEGRADO", "RECHAZADO"}

#: Las 7 tablas de datos del contrato (las 8 «de hechos» menos `controlcarga`,
#: que es la cabecera). El orden es el del documento.
TABLAS_DATOS: list[tuple[str, type]] = [
    ("panelmedico", ExtPanelMedico),
    ("factvisitamedico", ExtFactVisitaMedico),
    ("targetfarmacia", ExtTargetFarmacia),
    ("factvisitafarmacia", ExtFactVisitaFarmacia),
    ("factventa", ExtFactVenta),
    ("factevaluacionconocimiento", ExtFactEvaluacionConocimiento),
    ("factprescripciondetalle", ExtFactPrescripcionDetalle),
]

#: Los campos que el contrato señala como «los que rompen indicadores en
#: silencio» (§11.6). La comparación es EXACTA: 'v' no es 'V'.
DOMINIOS: dict[tuple[str, str], set[str]] = {
    ("factvisitamedico", "tipo_visita"): {"V", "R"},
    ("panelmedico", "frecuencia_objetivo"): {"F1", "F2"},
    ("panelmedico", "prioridad"): {"TOP", "REGULAR"},
    ("panelmedico", "categoria"): {"A", "B", "C", "D"},
}


class LoteYaIntegrado(RuntimeError):
    """El lote ya se integró a los esquemas internos: re-validarlo daría una
    foto falsa de un dato que ya está en producción."""


def _hallazgo(lote_id: int, tabla: str, problema: str, severidad: str,
              origen_id: str | None = None,
              campo: str | None = None) -> IntegracionHallazgo:
    return IntegracionHallazgo(
        lote_id=lote_id, tabla=tabla, origen_id=origen_id, campo=campo,
        problema=problema, severidad=severidad,
        detectado_en=datetime.now(timezone.utc))


def _validar_dominios(filas: list, tabla: str, lote_id: int) -> list[IntegracionHallazgo]:
    """Revisa los campos acotados de una tabla. Un valor fuera de dominio es un
    hallazgo, nunca una excepción."""
    hallazgos = []
    for campo_tabla, validos in DOMINIOS.items():
        if campo_tabla[0] != tabla:
            continue
        campo = campo_tabla[1]
        for fila in filas:
            valor = getattr(fila, campo, None)
            # Un opcional ausente no es un problema de dominio; su obligatoriedad
            # ya la impone el NOT NULL del contrato.
            if valor is None:
                continue
            if valor not in validos:
                hallazgos.append(_hallazgo(
                    lote_id, tabla,
                    f"«{valor}» no es un valor válido de {campo}. "
                    f"Se esperaba uno de: {', '.join(sorted(validos))}.",
                    SEVERIDAD_ERROR,
                    origen_id=getattr(fila, "origen_id", None), campo=campo))
    return hallazgos


def _contar_filas(db: Session, lote_id: int) -> tuple[int, dict[str, list]]:
    """Trae las filas del lote de las 7 tablas. Se cargan en memoria porque hay
    que recorrerlas campo a campo de todas formas."""
    por_tabla: dict[str, list] = {}
    total = 0
    for tabla, modelo in TABLAS_DATOS:
        filas = db.query(modelo).filter(modelo.lote_id == lote_id).all()
        por_tabla[tabla] = filas
        total += len(filas)
    return total, por_tabla


def validar_lote(db: Session, lote_id: int) -> dict:
    """Valida (o re-valida) un lote y lo deja en VALIDADO o RECHAZADO.

    Re-ejecutable: borra los hallazgos previos del lote y los recalcula. Es lo
    que hace seguro el flujo real de corrección, en el que Mallén reenvía el
    registro con el mismo `origen_id` (nunca borra: no tiene ese permiso).
    """
    lote = db.get(ExtControlCarga, lote_id)
    if lote is None:
        raise ValueError(f"Lote {lote_id} no encontrado")
    if lote.estado == "INTEGRADO":
        raise LoteYaIntegrado(
            f"El lote {lote_id} ya fue integrado; no se re-valida.")

    (db.query(IntegracionHallazgo)
     .filter(IntegracionHallazgo.lote_id == lote_id)
     .delete(synchronize_session=False))

    filas_reales, por_tabla = _contar_filas(db, lote_id)
    hallazgos: list[IntegracionHallazgo] = []
    for tabla, filas in por_tabla.items():
        hallazgos.extend(_validar_dominios(filas, tabla, lote_id))

    if lote.filas_enviadas != filas_reales:
        hallazgos.append(_hallazgo(
            lote_id, "controlcarga",
            f"El lote declara {lote.filas_enviadas} fila(s) y se recibieron "
            f"{filas_reales}. Suele indicar una carga interrumpida.",
            SEVERIDAD_ERROR))
    elif filas_reales == 0:
        hallazgos.append(_hallazgo(
            lote_id, "controlcarga",
            "El lote no trae ninguna fila de datos.", SEVERIDAD_AVISO))

    for h in hallazgos:
        db.add(h)

    errores = sum(1 for h in hallazgos if h.severidad == SEVERIDAD_ERROR)
    avisos = len(hallazgos) - errores
    tablas_con_error = len({h.tabla for h in hallazgos
                            if h.severidad == SEVERIDAD_ERROR})
    lote.estado = "RECHAZADO" if errores else "VALIDADO"
    mensaje = (f"{filas_reales} fila(s), {errores} error(es) en "
               f"{tablas_con_error} tabla(s), {avisos} aviso(s)")
    lote.mensaje = mensaje[:500]
    db.commit()

    logger.info(f"Lote {lote_id} validado: {lote.estado} — {mensaje}")
    return {"lote_id": lote_id, "estado": lote.estado,
            "filas_declaradas": lote.filas_enviadas, "filas_reales": filas_reales,
            "errores": errores, "avisos": avisos, "mensaje": mensaje}


def _lote_publico(lote: ExtControlCarga) -> dict:
    return {
        "lote_id": lote.lote_id, "sistema_origen": lote.sistema_origen,
        "modulo": lote.modulo, "pais_codigo": lote.pais_codigo,
        "ciclo_codigo": lote.ciclo_codigo, "periodo": lote.periodo,
        "fecha_extraccion": lote.fecha_extraccion,
        "fecha_recepcion": lote.fecha_recepcion,
        "filas_enviadas": lote.filas_enviadas, "estado": lote.estado,
        "mensaje": lote.mensaje,
    }


def listar_lotes(db: Session, pais_codigo: str | None = None,
                 estado: str | None = None, limite: int = 100) -> list[dict]:
    """Lotes más recientes primero, con su conteo de hallazgos."""
    q = db.query(ExtControlCarga)
    if pais_codigo:
        q = q.filter(ExtControlCarga.pais_codigo == pais_codigo)
    if estado:
        q = q.filter(ExtControlCarga.estado == estado)
    lotes = q.order_by(ExtControlCarga.fecha_recepcion.desc()).limit(limite).all()

    salida = []
    for lote in lotes:
        n = (db.query(IntegracionHallazgo)
             .filter(IntegracionHallazgo.lote_id == lote.lote_id).count())
        salida.append(_lote_publico(lote) | {"hallazgos": n})
    return salida


def detalle_lote(db: Session, lote_id: int) -> dict:
    """Cabecera del lote y sus hallazgos, los errores primero."""
    lote = db.get(ExtControlCarga, lote_id)
    if lote is None:
        raise ValueError(f"Lote {lote_id} no encontrado")
    # severidad DESC porque alfabéticamente 'error' > 'aviso': así los errores
    # (lo que rechaza el lote) salen primero, que es lo que hay que corregir.
    filas = (db.query(IntegracionHallazgo)
             .filter(IntegracionHallazgo.lote_id == lote_id)
             .order_by(IntegracionHallazgo.severidad.desc(),
                       IntegracionHallazgo.tabla.asc(),
                       IntegracionHallazgo.id.asc())
             .all())
    return {
        "lote": _lote_publico(lote),
        "hallazgos": [{
            "id": h.id, "tabla": h.tabla, "origen_id": h.origen_id,
            "campo": h.campo, "problema": h.problema, "severidad": h.severidad,
            "detectado_en": h.detectado_en,
        } for h in filas],
    }


def resumen(db: Session, pais_codigo: str | None = None) -> dict[str, int]:
    """Conteo de lotes por estado. Devuelve SIEMPRE los cuatro estados, aunque
    valgan cero: el tablero necesita las cuatro tarjetas siempre."""
    q = db.query(ExtControlCarga)
    if pais_codigo:
        q = q.filter(ExtControlCarga.pais_codigo == pais_codigo)
    conteo = {e: 0 for e in sorted(ESTADOS_LOTE)}
    for lote in q.all():
        if lote.estado in conteo:
            conteo[lote.estado] += 1
    return conteo
