"""Constructor de rutas de Onboarding (§4).

Hoy Formación solo tiene exámenes sueltos. Esto estructura el proceso COMPLETO
de un representante nuevo: contenido, documentos, exámenes, hitos de campo y
checkpoints de aprobación.

EL ORDEN DE LOS 10 PASOS NO SE REORDENA
----------------------------------------
El §4.2 lo marca como confirmado por el cliente tras dos correcciones durante el
diseño, y tiene una lógica pedagógica explícita: primero la base científica
(Farmacología → Anatomía → Patología), después una visión general de TODOS los
productos de la línea con su material, y solo entonces el detalle DAVID de cada
producto principal. Nunca al revés. Por eso la plantilla estándar se genera
desde `PASOS_ESTANDAR` y no se arma a mano cada vez.

EL BLOQUEO ES POR PASO, NO GLOBAL
----------------------------------
El §4.5 dejó ABIERTO si la secuencia debe ser estricta o admite pasos en
paralelo (punto abierto 1). Aquí no se decide por el cliente: cada paso declara
su propio `bloqueante` y el motor lo respeta. El generador crea la plantilla con
todos en bloqueante —el supuesto del mockup— y cambiar uno a False basta para
permitir el paralelo, sin tocar código ni migrar nada.
"""
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.formacion import (
    OnboardingAsignacion, OnboardingPaso, OnboardingPasoProgreso, OnboardingPlantilla,
)
from app.services import formacion_biblioteca_service as biblioteca

TIPOS_PASO = ("contenido", "documento", "examen", "material_examen",
              "hito_campo", "checkpoint")
QUIEN_MARCA = ("representante", "sistema", "gd", "capacitacion")

#: Los 10 pasos del §4.2, en el orden confirmado por el cliente. El paso DAVID
#: se repite una vez por cada producto marcado "Principal" en la línea (§4.3),
#: por eso lleva `por_producto=True` en vez de un título fijo.
PASOS_ESTANDAR: list[dict] = [
    {"titulo": "Introducción a la empresa y políticas", "tipo": "contenido",
     "plazo_sugerido": "Día 1", "quien_lo_marca": "representante"},
    {"titulo": "Firma de código de conducta y compliance", "tipo": "documento",
     "plazo_sugerido": "Día 1", "quien_lo_marca": "representante"},
    {"titulo": "Farmacología general", "tipo": "examen",
     "plazo_sugerido": "Semana 1", "quien_lo_marca": "sistema"},
    {"titulo": "Anatomía relacionada con la línea", "tipo": "examen",
     "plazo_sugerido": "Semana 1", "quien_lo_marca": "sistema"},
    {"titulo": "Patologías relacionadas a productos de línea", "tipo": "examen",
     "plazo_sugerido": "Semana 2", "quien_lo_marca": "sistema"},
    # Paso mixto: primero se confirma la lectura del material de TODOS los
    # productos de la línea, y solo entonces se habilita su examen.
    {"titulo": "Productos de la línea (visión general)", "tipo": "material_examen",
     "plazo_sugerido": "Semana 2", "quien_lo_marca": "sistema",
     "referencia_tipo": "linea"},
    {"titulo": "Producto principal — DAVID", "tipo": "examen",
     "plazo_sugerido": "Semana 3", "quien_lo_marca": "sistema",
     "por_producto": True, "referencia_tipo": "producto"},
    {"titulo": "Hito de Campo: primera visita acompañada por el GD",
     "tipo": "hito_campo", "plazo_sugerido": "Semana 4", "quien_lo_marca": "gd"},
    {"titulo": "Checkpoint final: evaluación y aprobación de Capacitación",
     "tipo": "checkpoint", "plazo_sugerido": "Día 30", "quien_lo_marca": "capacitacion"},
]


class PasoBloqueado(RuntimeError):
    """No se puede completar un paso cuyos requisitos no están satisfechos.
    Lleva el motivo concreto para que el representante sepa qué hacer."""


class RolNoAutorizado(RuntimeError):
    """El §4.6 reparte quién marca cada paso: el hito de campo lo marca el GD y
    el checkpoint final lo aprueba Capacitación. Nadie firma por otro."""


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Constructor de plantillas
# ---------------------------------------------------------------------------

def crear_plantilla_estandar(db: Session, pais_codigo: str, linea_id: int,
                             nombre: str, duracion_dias: int = 30,
                             actor=None) -> OnboardingPlantilla:
    """Genera la ruta de los 10 pasos para una línea.

    El paso DAVID se repite tantas veces como productos principales tenga la
    línea (§4.3). Si la línea no tiene ninguno todavía, ese paso simplemente no
    aparece: es preferible una ruta corta y correcta a un paso que apunta a un
    producto inexistente.
    """
    plantilla = OnboardingPlantilla(
        pais_codigo=pais_codigo, linea_id=linea_id, nombre_plantilla=nombre,
        duracion_dias=duracion_dias, creado_por=getattr(actor, "id", None))
    db.add(plantilla)
    db.flush()  # necesitamos el id para los pasos

    principales = biblioteca.productos_de_linea(db, pais_codigo, linea_id,
                                                solo_principales=True)
    orden = 0
    for plantilla_paso in PASOS_ESTANDAR:
        if plantilla_paso.get("por_producto"):
            for producto in principales:
                orden += 1
                db.add(OnboardingPaso(
                    plantilla_id=plantilla.id, orden=orden, tipo=plantilla_paso["tipo"],
                    titulo=f"{producto.nombre_producto} — DAVID "
                           f"(Descripción, Acción, Ventaja, Desventaja)",
                    plazo_sugerido=plantilla_paso["plazo_sugerido"],
                    bloqueante=True,
                    quien_lo_marca=plantilla_paso["quien_lo_marca"],
                    referencia_tipo="producto", referencia_id=producto.id))
        else:
            orden += 1
            db.add(OnboardingPaso(
                plantilla_id=plantilla.id, orden=orden, tipo=plantilla_paso["tipo"],
                titulo=plantilla_paso["titulo"],
                plazo_sugerido=plantilla_paso["plazo_sugerido"],
                bloqueante=True,
                quien_lo_marca=plantilla_paso["quien_lo_marca"],
                referencia_tipo=plantilla_paso.get("referencia_tipo"),
                referencia_id=None))
    db.commit()
    db.refresh(plantilla)
    return plantilla


def pasos_de(db: Session, plantilla_id: int) -> list[OnboardingPaso]:
    return (db.query(OnboardingPaso)
            .filter(OnboardingPaso.plantilla_id == plantilla_id)
            .order_by(OnboardingPaso.orden)
            .all())


# ---------------------------------------------------------------------------
# Asignación
# ---------------------------------------------------------------------------

def asignar(db: Session, plantilla_id: int, rm_id: int,
            fecha_inicio: date | None = None, actor=None) -> OnboardingAsignacion:
    existente = (db.query(OnboardingAsignacion)
                 .filter(OnboardingAsignacion.plantilla_id == plantilla_id,
                         OnboardingAsignacion.rm_id == rm_id)
                 .first())
    if existente is not None:
        return existente
    pasos = pasos_de(db, plantilla_id)
    a = OnboardingAsignacion(
        plantilla_id=plantilla_id, rm_id=rm_id,
        fecha_inicio=fecha_inicio or date.today(),
        paso_actual_id=pasos[0].id if pasos else None,
        progreso_pct=0, asignada_por=getattr(actor, "id", None))
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def asignaciones_de_rm(db: Session, rm_id: int) -> list[dict]:
    """Las rutas asignadas a un representante, para que descubra la suya (§4).

    `estado_ruta` consulta por id de asignación, que el representante no tiene
    forma de conocer: sin esto, la ruta existe pero él no puede abrirla.
    """
    filas = (db.query(OnboardingAsignacion, OnboardingPlantilla)
             .join(OnboardingPlantilla,
                   OnboardingAsignacion.plantilla_id == OnboardingPlantilla.id)
             .filter(OnboardingAsignacion.rm_id == rm_id)
             .order_by(OnboardingAsignacion.fecha_inicio.desc())
             .all())
    return [{
        "id": a.id, "plantilla_id": a.plantilla_id,
        "nombre_plantilla": p.nombre_plantilla,
        "fecha_inicio": a.fecha_inicio,
        "progreso_pct": float(a.progreso_pct),
        "completada_en": a.completada_en,
    } for a, p in filas]


# ---------------------------------------------------------------------------
# El motor de bloqueo
# ---------------------------------------------------------------------------

def _producto_ids_requeridos(db: Session, plantilla: OnboardingPlantilla,
                             paso: OnboardingPaso) -> list[int]:
    """Qué productos aportan material obligatorio a este paso.

    Un paso `material_examen` referido a la línea exige el material de TODOS sus
    productos (§4.2 paso 6). Un paso DAVID exige solo el de SU producto.
    """
    if paso.referencia_tipo == "linea":
        return [p.id for p in biblioteca.productos_de_linea(
            db, plantilla.pais_codigo, plantilla.linea_id)]
    if paso.referencia_tipo == "producto" and paso.referencia_id:
        return [paso.referencia_id]
    return []


def estado_ruta(db: Session, asignacion_id: int) -> dict:
    """Estado de cada paso de la ruta de un representante.

    Un paso queda BLOQUEADO por dos motivos independientes, y se informan los
    dos a la vez para que el representante no descubra el segundo justo después
    de resolver el primero:
      1. Algún paso anterior marcado como bloqueante sigue pendiente.
      2. Le falta confirmar material obligatorio en Biblioteca (§5.3).
    """
    a = db.get(OnboardingAsignacion, asignacion_id)
    if a is None:
        raise ValueError("Asignación no encontrada")
    plantilla = db.get(OnboardingPlantilla, a.plantilla_id)
    pasos = pasos_de(db, a.plantilla_id)
    completados = {
        p.paso_id for p in db.query(OnboardingPasoProgreso)
        .filter(OnboardingPasoProgreso.asignacion_id == asignacion_id,
                OnboardingPasoProgreso.completado.is_(True)).all()
    }

    detalle, pendientes_previos = [], []
    for paso in pasos:
        if paso.id in completados:
            detalle.append({"paso_id": paso.id, "orden": paso.orden, "titulo": paso.titulo,
                            "tipo": paso.tipo, "quien_lo_marca": paso.quien_lo_marca,
                            "estado": "completado", "bloqueos": []})
        else:
            bloqueos = []
            if pendientes_previos:
                faltan = ", ".join(pendientes_previos)
                bloqueos.append(f"Falta completar antes: {faltan}.")
            producto_ids = _producto_ids_requeridos(db, plantilla, paso)
            progreso_material = biblioteca.progreso_lectura(db, a.rm_id, producto_ids)
            if not progreso_material["completo"]:
                titulos = ", ".join(m["titulo"] for m in progreso_material["pendientes"])
                bloqueos.append(
                    f"Falta confirmar lectura de {len(progreso_material['pendientes'])} "
                    f"material(es) obligatorio(s): {titulos}.")
            detalle.append({
                "paso_id": paso.id, "orden": paso.orden, "titulo": paso.titulo,
                "tipo": paso.tipo, "quien_lo_marca": paso.quien_lo_marca,
                "estado": "bloqueado" if bloqueos else "disponible",
                "bloqueos": bloqueos,
                "material": progreso_material if producto_ids else None,
            })
        # Un paso pendiente solo frena a los siguientes si es bloqueante.
        if paso.id not in completados and paso.bloqueante:
            pendientes_previos.append(f"«{paso.titulo}»")

    total = len(pasos)
    return {
        "asignacion_id": a.id, "rm_id": a.rm_id, "plantilla_id": a.plantilla_id,
        "total_pasos": total, "completados": len(completados),
        "progreso_pct": round(len(completados) * 100 / total, 2) if total else 0.0,
        "pasos": detalle,
    }


def completar_paso(db: Session, asignacion_id: int, paso_id: int,
                   rol_actor: str, actor=None,
                   observaciones: str | None = None) -> OnboardingPasoProgreso:
    """Marca un paso como completado, si quien lo marca puede y si no está
    bloqueado.

    Las dos comprobaciones son distintas y ambas necesarias: la de rol responde
    "¿le toca a esta persona?" (§4.6) y la de bloqueo responde "¿ya se puede?"
    (§4.5 y §5.3). Saltarse la segunda dejaría avanzar la ruta sin haber leído
    el material, que es justo lo que el cliente pidió impedir.
    """
    paso = db.get(OnboardingPaso, paso_id)
    if paso is None:
        raise ValueError("Paso no encontrado")
    # "admin" pasa a propósito y de forma explícita: hace falta para destrabar
    # una ruta en soporte. Es una excepción declarada, no un agujero — queda
    # registrada en `completado_por`, así que se sabe que no lo firmó el GD.
    if paso.quien_lo_marca not in (rol_actor, "sistema") and rol_actor != "admin":
        raise RolNoAutorizado(
            f"Este paso lo marca «{paso.quien_lo_marca}», no «{rol_actor}».")

    estado = estado_ruta(db, asignacion_id)
    fila = next((p for p in estado["pasos"] if p["paso_id"] == paso_id), None)
    if fila is None:
        raise ValueError("El paso no pertenece a esta asignación")
    if fila["estado"] == "completado":
        return (db.query(OnboardingPasoProgreso)
                .filter(OnboardingPasoProgreso.asignacion_id == asignacion_id,
                        OnboardingPasoProgreso.paso_id == paso_id).first())
    if fila["estado"] == "bloqueado":
        raise PasoBloqueado(" ".join(fila["bloqueos"]))

    progreso = (db.query(OnboardingPasoProgreso)
                .filter(OnboardingPasoProgreso.asignacion_id == asignacion_id,
                        OnboardingPasoProgreso.paso_id == paso_id).first())
    if progreso is None:
        progreso = OnboardingPasoProgreso(asignacion_id=asignacion_id, paso_id=paso_id)
        db.add(progreso)
    progreso.completado = True
    progreso.completado_en = _ahora()   # hora del servidor, no del cliente
    progreso.completado_por = getattr(actor, "id", None)
    progreso.observaciones = observaciones
    db.commit()
    _actualizar_avance(db, asignacion_id)
    db.refresh(progreso)
    return progreso


def _actualizar_avance(db: Session, asignacion_id: int) -> None:
    """Recalcula progreso y sitúa el paso actual en el primero no completado."""
    a = db.get(OnboardingAsignacion, asignacion_id)
    if a is None:
        return
    pasos = pasos_de(db, a.plantilla_id)
    completados = {
        p.paso_id for p in db.query(OnboardingPasoProgreso)
        .filter(OnboardingPasoProgreso.asignacion_id == asignacion_id,
                OnboardingPasoProgreso.completado.is_(True)).all()
    }
    pendiente = next((p for p in pasos if p.id not in completados), None)
    a.paso_actual_id = pendiente.id if pendiente else None
    a.progreso_pct = round(len(completados) * 100 / len(pasos), 2) if pasos else 0
    if pendiente is None and a.completada_en is None:
        a.completada_en = _ahora()
    db.commit()
