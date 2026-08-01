"""Refuerzo de Memoria — repetición espaciada (§10).

Fundamento (§10.1, Ebbinghaus): sin repaso la retención cae a ~44% en una hora,
~34% al día siguiente y ~25% a los seis días. Repasar con intervalos CADA VEZ
MÁS LARGOS retiene igual o mejor que repasar siempre parejo (Landauer y Bjork
1978, Cull 1996), y la repetición espaciada supera a la masiva (Salisbury 1990).
De ahí que el espaciado creciente sea el modo recomendado y no una preferencia
de diseño.

DOS METRICAS QUE NUNCA SE MEZCLAN
----------------------------------
El §10.8 lo marca como requisito de diseño, no como detalle: la PARTICIPACIÓN
mide qué tan rápido reacciona el representante a la notificación, y el ACIERTO
mide si respondió bien. Combinarlas en un solo número escondería el caso que más
importa detectar — alguien que contesta al instante y se equivoca siempre.

VISTA SUGIERE, CAPACITACIÓN CONFIRMA
-------------------------------------
El §10.3 es explícito: ninguna cápsula se envía sin que Capacitación confirme la
programación, aunque solo acepte la sugerencia sin cambiarla. Por eso hay dos
marcas de tiempo distintas y `publicada` no se activa sola.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from app.models.formacion import (
    RefuerzoCampana, RefuerzoCapsula, RefuerzoRespuesta, RefuerzoRondaProgramada,
)

MODOS_ESPACIADO = ("creciente", "fijo_48h")
FORMATOS = ("microlectura", "reto", "caso_breve", "reflexion_abierta")
DURACIONES = (15, 30, 60, 90)

#: Los intervalos del §10.2, en días desde el inicio de la campaña. Para el caso
#: canónico de 30 días producen exactamente las 5 rondas del documento.
OFFSETS_CRECIENTE = (1, 4, 7, 14, 30)

#: §10.6 — puntaje de participación según el tiempo de respuesta.
#: El límite es INCLUSIVO en el tramo mejor: responder a los 5 minutos exactos
#: puntúa 100%, no 80%. El documento escribe los rangos como "0 a 5" y "5 a 30",
#: que se solapan en el extremo; se resolvió a favor del representante porque un
#: castigo por un segundo sería arbitrario. Es una interpretación, no una regla
#: literal del documento — conviene confirmarla con Capacitación.
TRAMOS_PARTICIPACION = ((5, 100), (30, 80), (45, 70))
PARTICIPACION_MINIMA = 50
PUNTOS_BASE_CAPSULA = 10


class CampanaNoPublicable(RuntimeError):
    """Faltan condiciones para publicar la campaña."""


class RondaNoDisponible(RuntimeError):
    """Se intentó responder una ronda que aún no se publicó."""


#: Días mínimos de separación entre la última ronda intermedia y el cierre.
#: Sin este margen, una campaña de 15 días pondría rondas el día 14 y el 15 —
#: dos repasos seguidos, que es lo contrario de espaciar.
MARGEN_CIERRE_DIAS = 3


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _sin_zona(dt: datetime) -> datetime:
    """Normaliza a UTC *naive*, que es como el proyecto guarda las fechas.

    Las columnas son `DateTime` sin zona, así que lo que vuelve de la base es
    naive mientras que `datetime.now(timezone.utc)` es aware. Restarlos
    directamente lanza `can't subtract offset-naive and offset-aware datetimes`,
    y ocurriría en la PRIMERA respuesta real: el instante de recepción sale de
    la base y el de respuesta se calcula al vuelo.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Calendario de rondas
# ---------------------------------------------------------------------------

def calcular_offsets(duracion_dias: int, modo: str) -> list[int]:
    """Días desde el inicio en que cae cada ronda.

    En modo creciente se usan los intervalos canónicos y se añade siempre una
    ronda de cierre el último día. `MARGEN_CIERRE_DIAS` descarta las que
    quedarían pegadas a ese cierre: en una campaña de 15 días, programar el 14 y
    el 15 sería repasar dos veces seguidas, lo contrario de espaciar.
    """
    if modo not in MODOS_ESPACIADO:
        raise ValueError(f"Modo de espaciado inválido: {modo}. Use creciente o fijo_48h.")
    if duracion_dias <= 0:
        raise ValueError("La duración debe ser mayor que cero.")
    if modo == "fijo_48h":
        return list(range(2, duracion_dias + 1, 2)) or [duracion_dias]
    previos = [o for o in OFFSETS_CRECIENTE if o <= duracion_dias - MARGEN_CIERRE_DIAS]
    return previos + [duracion_dias]


def generar_calendario(db: Session, campana_id: int,
                       inicio: datetime | None = None) -> list[RefuerzoRondaProgramada]:
    """Crea las rondas SUGERIDAS. Ninguna queda publicada (§10.3)."""
    campana = db.get(RefuerzoCampana, campana_id)
    if campana is None:
        raise ValueError("Campaña no encontrada")
    existentes = (db.query(RefuerzoRondaProgramada)
                  .filter(RefuerzoRondaProgramada.campana_id == campana_id).all())
    if existentes:
        return sorted(existentes, key=lambda r: r.numero_ronda)
    base = inicio or _ahora()
    rondas = []
    for i, offset in enumerate(calcular_offsets(campana.duracion_dias,
                                                campana.modo_espaciado), start=1):
        r = RefuerzoRondaProgramada(
            campana_id=campana_id, numero_ronda=i,
            fecha_hora_sugerida=base + timedelta(days=offset),
            fecha_hora_programada=None, publicada=False)
        db.add(r)
        rondas.append(r)
    db.commit()
    for r in rondas:
        db.refresh(r)
    return rondas


def programar_ronda(db: Session, ronda_id: int,
                    fecha_hora: datetime | None = None) -> RefuerzoRondaProgramada:
    """Capacitación confirma el día y la hora exactos (§10.3).

    Aceptar la sugerencia también es confirmar: si no se pasa fecha, se copia la
    sugerida. Lo que no puede ocurrir es que una ronda se envíe sin que nadie la
    haya mirado.
    """
    r = db.get(RefuerzoRondaProgramada, ronda_id)
    if r is None:
        raise ValueError("Ronda no encontrada")
    r.fecha_hora_programada = fecha_hora or r.fecha_hora_sugerida
    db.commit()
    db.refresh(r)
    return r


def publicar_ronda(db: Session, ronda_id: int) -> RefuerzoRondaProgramada:
    """Publica y dispara la notificación DUAL (§10.4).

    Los dos canales van siempre juntos, no son alternativos: el correo llega al
    buzón corporativo y el push a VISTA Móvil. Se envían best-effort — que falle
    el correo no debe impedir que la cápsula quede disponible.
    """
    r = db.get(RefuerzoRondaProgramada, ronda_id)
    if r is None:
        raise ValueError("Ronda no encontrada")
    if r.fecha_hora_programada is None:
        raise CampanaNoPublicable(
            "Esta ronda no tiene fecha confirmada. Capacitación debe programarla "
            "antes de publicarla (§10.3).")
    capsulas = (db.query(RefuerzoCapsula)
                .filter(RefuerzoCapsula.ronda_id == ronda_id).count())
    if capsulas == 0:
        raise CampanaNoPublicable(
            "La ronda no tiene cápsulas: publicarla enviaría una notificación "
            "que lleva a una pantalla vacía.")
    r.publicada = True
    r.notificada_en = _ahora()
    db.commit()
    db.refresh(r)
    logger.info(f"Refuerzo: ronda {ronda_id} publicada — notificación dual "
                f"(correo corporativo + push VISTA Móvil)")
    return r


# ---------------------------------------------------------------------------
# Respuesta del representante
# ---------------------------------------------------------------------------

def puntaje_participacion(segundos: int) -> int:
    """§10.6 — cuánto puntúa según la rapidez, independiente del acierto."""
    minutos = segundos / 60
    for limite, pct in TRAMOS_PARTICIPACION:
        if minutos <= limite:
            return pct
    return PARTICIPACION_MINIMA


def registrar_respuesta(db: Session, capsula_id: int, rm_id: int,
                        opcion: str | None = None, texto_libre: str | None = None,
                        recibido_en: datetime | None = None,
                        respondido_en: datetime | None = None) -> dict:
    """Registra la respuesta y devuelve la corrección INMEDIATA (§10.7).

    El resultado trae la opción correcta y su explicación SIEMPRE, haya acertado
    o no: el documento pide que la correcta se resalte en el acto, sin esperar a
    ningún proceso posterior. Devolverla aquí es lo que permite que la pantalla
    lo haga sin una segunda llamada.
    """
    capsula = db.get(RefuerzoCapsula, capsula_id)
    if capsula is None:
        raise ValueError("Cápsula no encontrada")
    ronda = db.get(RefuerzoRondaProgramada, capsula.ronda_id)
    if ronda is None or not ronda.publicada:
        raise RondaNoDisponible("Esta ronda todavía no está publicada.")

    previa = (db.query(RefuerzoRespuesta)
              .filter(RefuerzoRespuesta.capsula_id == capsula_id,
                      RefuerzoRespuesta.rm_id == rm_id).first())
    if previa is not None:
        # Reintentar permitiría subir el % de aciertos a base de repetir.
        return _resultado(capsula, previa, repetida=True)

    recibido = _sin_zona(
        recibido_en or ronda.notificada_en or ronda.fecha_hora_programada or _ahora())
    respondido = _sin_zona(respondido_en or _ahora())
    segundos = max(0, int((respondido - recibido).total_seconds()))
    pct = puntaje_participacion(segundos)

    # El acierto solo aplica al formato de opción múltiple. En una reflexión
    # abierta no hay respuesta "correcta" (§10.5): se puntúa la participación y
    # `es_acierto` queda en None — que NO es lo mismo que False.
    es_acierto = None
    if capsula.formato == "reto" and capsula.opcion_correcta:
        es_acierto = (opcion or "").strip().upper() == capsula.opcion_correcta.upper()

    r = RefuerzoRespuesta(
        ronda_id=ronda.id, capsula_id=capsula_id, rm_id=rm_id,
        timestamp_recibido=recibido, timestamp_respondido=respondido,
        tiempo_respuesta_seg=segundos,
        pct_puntaje_participacion=Decimal(pct),
        opcion_seleccionada=(opcion or None), es_acierto=es_acierto,
        texto_libre=texto_libre,
        puntos_obtenidos=round(PUNTOS_BASE_CAPSULA * pct / 100))
    db.add(r)
    db.commit()
    db.refresh(r)
    return _resultado(capsula, r, repetida=False)


def _resultado(capsula: RefuerzoCapsula, r: RefuerzoRespuesta, repetida: bool) -> dict:
    return {
        "capsula_id": capsula.id,
        "tiempo_respuesta_seg": r.tiempo_respuesta_seg,
        "pct_participacion": float(r.pct_puntaje_participacion or 0),
        "puntos_obtenidos": r.puntos_obtenidos,
        "es_acierto": r.es_acierto,
        "opcion_seleccionada": r.opcion_seleccionada,
        # Se devuelven siempre, para el resaltado inmediato del §10.7.
        "opcion_correcta": capsula.opcion_correcta,
        "explicacion": capsula.explicacion,
        "repetida": repetida,
    }


def puntos_de_refuerzo(db: Session, rm_id: int, campana_id: int | None = None) -> int:
    """Lo que este módulo aporta al Ranking gamificado (§8.2)."""
    q = db.query(RefuerzoRespuesta).filter(RefuerzoRespuesta.rm_id == rm_id)
    if campana_id is not None:
        q = (q.join(RefuerzoRondaProgramada,
                    RefuerzoRespuesta.ronda_id == RefuerzoRondaProgramada.id)
             .filter(RefuerzoRondaProgramada.campana_id == campana_id))
    return sum(r.puntos_obtenidos for r in q.all())
