"""KPI del Refuerzo de Memoria (§11).

Tres métricas por cuatro desgloses, más la pregunta más y menos acertada en
CADA fila de CADA desglose (§11.4).

POR QUÉ LA PREGUNTA MÁS Y MENOS ACERTADA APARECE EN LOS CUATRO
---------------------------------------------------------------
No es repetición: es el insumo del Plan de Cierre de Brechas (§12). Una misma
pregunta fallada en muchos segmentos señala un vacío de contenido que afecta a
todos; fallada en uno solo, señala un problema de ese equipo. Ninguna vista
aislada distingue esas dos cosas — hace falta poder comparar el mismo dato entre
segmentos, y por eso se calcula en todos.

Se agrega en Python y no en SQL a propósito: la lógica de "más y menos acertada
por segmento" son cuatro agrupaciones anidadas distintas, y expresarlas en SQL
las volvería ilegibles sin ganar nada — el volumen es de una campaña por ciclo,
no de millones de filas.
"""
from sqlalchemy.orm import Session

from app.models.dimensiones import RepresentanteMedico
from app.models.formacion import (
    RefuerzoCampana, RefuerzoCapsula, RefuerzoRespuesta, RefuerzoRondaProgramada,
)


def _filas(db: Session, campana_id: int | None = None,
           pais_codigo: str | None = None,
           rm_ids: list[int] | None = None) -> list[dict]:
    """Respuestas enriquecidas con las dimensiones que necesitan los desgloses."""
    q = (db.query(RefuerzoRespuesta, RefuerzoCapsula, RefuerzoCampana,
                  RepresentanteMedico)
         .join(RefuerzoCapsula, RefuerzoRespuesta.capsula_id == RefuerzoCapsula.id)
         .join(RefuerzoRondaProgramada,
               RefuerzoRespuesta.ronda_id == RefuerzoRondaProgramada.id)
         .join(RefuerzoCampana,
               RefuerzoRondaProgramada.campana_id == RefuerzoCampana.id)
         .join(RepresentanteMedico, RefuerzoRespuesta.rm_id == RepresentanteMedico.id))
    if campana_id is not None:
        q = q.filter(RefuerzoCampana.id == campana_id)
    if pais_codigo:
        q = q.filter(RefuerzoCampana.pais_codigo == pais_codigo)
    if rm_ids is not None:
        # Lista vacía = no ve a nadie. Es lo correcto: un GD sin equipo asignado
        # no debe ver el consolidado de la empresa por descuido.
        q = q.filter(RefuerzoRespuesta.rm_id.in_(rm_ids or [-1]))
    return [{
        "rm_id": resp.rm_id,
        "gerente_id": rm.gerente_id,
        "pais_codigo": rm.pais_codigo,
        "linea_id": rm.linea_id,
        "producto_id": campana.producto_id,
        "capsula_id": capsula.id,
        "enunciado": capsula.enunciado,
        "tiempo_seg": resp.tiempo_respuesta_seg or 0,
        "pct_participacion": float(resp.pct_puntaje_participacion or 0),
        "es_acierto": resp.es_acierto,
    } for resp, capsula, campana, rm in q.all()]


def _pregunta_extremos(filas: list[dict]) -> dict:
    """La pregunta con MAYOR y con MENOR % de aciertos del segmento (§11.4).

    Solo entran las de opción múltiple: en una reflexión abierta no hay acierto
    que medir, y contarla como fallo distorsionaría el indicador.
    """
    por_capsula: dict[int, list[dict]] = {}
    for f in filas:
        if f["es_acierto"] is None:
            continue
        por_capsula.setdefault(f["capsula_id"], []).append(f)
    if not por_capsula:
        return {"pregunta_mas_acertada": None, "pregunta_menos_acertada": None}
    resumen = []
    for capsula_id, grupo in por_capsula.items():
        aciertos = sum(1 for g in grupo if g["es_acierto"])
        resumen.append({
            "capsula_id": capsula_id,
            "enunciado": grupo[0]["enunciado"],
            "pct_aciertos": round(aciertos * 100 / len(grupo), 2),
            "respuestas": len(grupo),
        })
    resumen.sort(key=lambda x: (x["pct_aciertos"], x["capsula_id"]))
    return {"pregunta_menos_acertada": resumen[0],
            "pregunta_mas_acertada": resumen[-1]}


def _metricas(filas: list[dict]) -> dict:
    """Las 3 métricas del §11.2.

    `pct_participacion` y `pct_aciertos` se calculan por separado y sobre
    universos distintos: la participación cuenta TODAS las respuestas, el
    acierto solo las de opción múltiple. Mezclarlas daría un número que no
    significa nada (§10.8)."""
    if not filas:
        return {"respuestas": 0, "tiempo_promedio_seg": 0,
                "pct_participacion": 0.0, "pct_aciertos": None}
    calificables = [f for f in filas if f["es_acierto"] is not None]
    return {
        "respuestas": len(filas),
        "tiempo_promedio_seg": round(sum(f["tiempo_seg"] for f in filas) / len(filas)),
        "pct_participacion": round(
            sum(f["pct_participacion"] for f in filas) / len(filas), 2),
        "pct_aciertos": (round(sum(1 for f in calificables if f["es_acierto"])
                               * 100 / len(calificables), 2)
                         if calificables else None),
    }


def _agrupar(filas: list[dict], clave: str) -> list[dict]:
    grupos: dict = {}
    for f in filas:
        grupos.setdefault(f[clave], []).append(f)
    salida = []
    for valor, grupo in grupos.items():
        fila = {clave: valor}
        fila.update(_metricas(grupo))
        fila.update(_pregunta_extremos(grupo))
        salida.append(fila)
    return sorted(salida, key=lambda x: (x[clave] is None, x[clave]))


def reporte(db: Session, campana_id: int | None = None,
            pais_codigo: str | None = None,
            rm_ids: list[int] | None = None,
            incluir_por_gd: bool = True) -> dict:
    """Los 4 desgloses del §11.3.

    `incluir_por_gd` queda fuera para un GD individual (§11.3.c): comparar su
    propio equipo consigo mismo no aporta, y el desglose existe justamente para
    que Capacitación compare equipos entre sí.
    """
    filas = _filas(db, campana_id, pais_codigo, rm_ids)
    reporte_datos = {
        "total_respuestas": len(filas),
        "general": _metricas(filas) | _pregunta_extremos(filas),
        "por_representante": _agrupar(filas, "rm_id"),
        "por_producto": _agrupar(filas, "producto_id"),
        "por_pais": _agrupar(filas, "pais_codigo"),
    }
    if incluir_por_gd:
        reporte_datos["por_gd"] = _agrupar(filas, "gerente_id")
    return reporte_datos
