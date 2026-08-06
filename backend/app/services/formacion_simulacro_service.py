"""Simulacro de Venta con IA (§9).

El RM practica contra un médico simulado por IA (estilo social asignado). Por
fase MORE (Apertura/Desarrollo/Cierre) una objeción hablada y respuesta de opción
múltiple, calificada D/P/A/E como Coaching MORE. El escenario lo genera la capa de
IA de la Fase 0 (una sola llamada de texto); aquí no se inventa teoría MORE.
"""
import random

from loguru import logger
from sqlalchemy.orm import Session

from decimal import Decimal

from app.models.formacion import SimulacroResultado, SimulacroRonda, SimulacroSesion
from app.services.examen_ia_service import _extraer_json
from app.services.ia import conexion_service

ESTILOS: tuple[str, ...] = ("Directivo", "Analitico", "Amistoso", "Expresivo")
FASES: tuple[str, ...] = ("Apertura", "Desarrollo", "Cierre")

#: Médicos simulados (nombre, género) — breve, solo para variar la práctica.
_MEDICOS: list[tuple[str, str]] = [
    ("Dra. Reyes", "F"), ("Dr. Peralta", "M"), ("Dra. Fermín", "F"),
    ("Dr. Guzmán", "M"), ("Dra. Objío", "F"),
]


class SimulacroIAError(RuntimeError):
    """La IA no devolvió un escenario válido tras el reintento."""


class PermisoError(RuntimeError):
    """La sesión/ronda no pertenece al RM que intenta operarla."""


def escala(ratio: float) -> int:
    """Ratio de aciertos → escala D/P/A/E (1-4), como Coaching MORE."""
    if ratio >= 0.90:
        return 4
    if ratio >= 0.70:
        return 3
    if ratio >= 0.50:
        return 2
    return 1


def construir_prompt(estilo: str, medico: str, genero: str | None) -> str:
    gen = {"F": "femenino", "M": "masculino"}.get(genero or "", "no especificado")
    return (
        "Eres un generador de simulacros de venta farmacéutica para entrenar a un "
        "Representante Médico con el modelo MORE.\n"
        f"El médico simulado es {medico} (género {gen}) y su estilo social es "
        f"{estilo}. Genera un escenario con EXACTAMENTE una ronda por cada fase: "
        "Apertura, Desarrollo y Cierre.\n"
        "En cada ronda el médico plantea una OBJECIÓN realista acorde a su estilo, "
        "y ofreces de 3 a 4 opciones de respuesta para el representante, UNA sola "
        "correcta según MORE, con una retroalimentación breve del porqué.\n"
        "La ronda de Desarrollo DEBE nombrar la técnica de manejo de objeciones "
        "empleada (campo tecnica_objecion).\n"
        "Responde SOLO con JSON válido, sin texto adicional, con esta forma:\n"
        '{"rondas":[{"fase_more":"Apertura","objecion_texto":"...",'
        '"opciones":{"A":"...","B":"...","C":"..."},"opcion_correcta":"B",'
        '"retroalimentacion":"..."},'
        '{"fase_more":"Desarrollo","tecnica_objecion":"...","objecion_texto":"...",'
        '"opciones":{"A":"...","B":"..."},"opcion_correcta":"A","retroalimentacion":"..."},'
        '{"fase_more":"Cierre","objecion_texto":"...","opciones":{"A":"...","B":"..."},'
        '"opcion_correcta":"A","retroalimentacion":"..."}]}'
    )


def parsear_escenario(texto: str) -> list[dict]:
    """Extrae y valida las rondas del JSON que devolvió la IA."""
    try:
        datos = _extraer_json(texto)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de parseo es IA inválida
        raise SimulacroIAError(f"La IA no devolvió JSON válido: {exc}") from exc
    rondas = datos.get("rondas") if isinstance(datos, dict) else datos
    if not isinstance(rondas, list) or not rondas:
        raise SimulacroIAError("El escenario no trae una lista de rondas.")
    for r in rondas:
        fase = r.get("fase_more")
        opciones = r.get("opciones")
        correcta = r.get("opcion_correcta")
        if fase not in FASES:
            raise SimulacroIAError(f"Fase inválida: {fase!r}.")
        if not isinstance(opciones, dict) or not opciones:
            raise SimulacroIAError("Una ronda no trae opciones.")
        # SimulacroRonda.opcion_correcta/opcion_seleccionada son String(1) — una
        # clave de más de 1 carácter pasaría esta validación y reventaría en el
        # INSERT (500) en vez de dar un 502 controlado.
        if any(len(str(k)) != 1 for k in opciones):
            raise SimulacroIAError("Las claves de opción deben ser de 1 carácter.")
        if len(str(correcta)) != 1:
            raise SimulacroIAError("La opción correcta debe ser de 1 carácter.")
        if correcta not in opciones:
            raise SimulacroIAError("La opción correcta no está entre las opciones.")
        if not r.get("objecion_texto"):
            raise SimulacroIAError("Una ronda no trae objeción.")
        if fase == "Desarrollo" and not r.get("tecnica_objecion"):
            raise SimulacroIAError("La ronda de Desarrollo no nombra la técnica.")
    return rondas


def ronda_publica(r: SimulacroRonda) -> dict:
    """Lo que ve el RM. La correcta y la retro SOLO tras responder (§10.7)."""
    d = {"id": r.id, "fase_more": r.fase_more, "tecnica_objecion": r.tecnica_objecion,
         "objecion_texto": r.objecion_texto, "opciones": r.opciones,
         "opcion_seleccionada": r.opcion_seleccionada, "es_correcta": r.es_correcta}
    if r.opcion_seleccionada is not None:
        d["opcion_correcta"] = r.opcion_correcta
        d["retroalimentacion"] = r.retroalimentacion
    return d


def _sesion_publica(s: SimulacroSesion) -> dict:
    return {"id": s.id, "rm_id": s.rm_id, "estilo": s.estilo_social_asignado,
            "medico": s.medico_simulado, "genero": s.genero_simulado,
            "finalizada": s.finalizada}


def iniciar(db: Session, rm_id: int, estilo: str | None = None,
            medico: str | None = None, genero: str | None = None) -> dict:
    """Genera el escenario con IA y arranca la sesión. 1 reintento si la IA
    devuelve algo inválido; luego SimulacroIAError. SinConexionIA se propaga."""
    if estilo is None:
        estilo = random.choice(ESTILOS)
    if medico is None:
        medico, genero = random.choice(_MEDICOS)
    prompt = construir_prompt(estilo, medico, genero)

    rondas_datos = None
    for intento in (1, 2):
        texto = conexion_service.adaptador_texto(db).generar_texto(prompt)
        try:
            rondas_datos = parsear_escenario(texto)
            break
        except SimulacroIAError:
            logger.warning(f"Simulacro: escenario IA inválido (intento {intento}).")
    if rondas_datos is None:
        raise SimulacroIAError("La IA no produjo un escenario válido tras el reintento.")

    sesion = SimulacroSesion(rm_id=rm_id, estilo_social_asignado=estilo,
                             medico_simulado=medico, genero_simulado=genero)
    db.add(sesion)
    db.flush()
    for r in rondas_datos:
        # SimulacroRonda.tecnica_objecion es String(40): es un metadato
        # descriptivo (no una clave), así que truncamos en vez de rechazar el
        # escenario si la IA devuelve un nombre de técnica más largo.
        _tecnica = r.get("tecnica_objecion")
        db.add(SimulacroRonda(
            sesion_id=sesion.id, fase_more=r["fase_more"],
            tecnica_objecion=(_tecnica[:40] if _tecnica else None),
            objecion_texto=r["objecion_texto"], opciones=r["opciones"],
            opcion_correcta=r["opcion_correcta"],
            retroalimentacion=r.get("retroalimentacion")))
    db.commit()
    filas = (db.query(SimulacroRonda)
             .filter(SimulacroRonda.sesion_id == sesion.id)
             .order_by(SimulacroRonda.id).all())
    return {"sesion": _sesion_publica(sesion), "rondas": [ronda_publica(x) for x in filas]}


def responder(db: Session, ronda_id: int, opcion: str,
              rm_id_scope: int | None = None) -> dict:
    """Registra la elección y revela la correcta + retro. `rm_id_scope`, si se da,
    debe coincidir con el dueño de la sesión (None = privilegiado/ADMIN)."""
    r = db.get(SimulacroRonda, ronda_id)
    if r is None:
        raise ValueError("Ronda no encontrada")
    sesion = db.get(SimulacroSesion, r.sesion_id)
    if rm_id_scope is not None and sesion.rm_id != rm_id_scope:
        raise PermisoError("Esta ronda no es de tu sesión.")
    if r.opcion_seleccionada is not None:
        raise ValueError("Esta ronda ya fue respondida.")
    r.opcion_seleccionada = opcion
    r.es_correcta = (opcion == r.opcion_correcta)
    db.commit()
    return {"es_correcta": r.es_correcta, "opcion_correcta": r.opcion_correcta,
            "retroalimentacion": r.retroalimentacion}


def _fase_escala(rondas: list[SimulacroRonda], fase: str) -> int:
    """Escala D/P/A/E de una fase: aciertos / total (sin responder = incorrecto)."""
    de_fase = [r for r in rondas if r.fase_more == fase]
    if not de_fase:
        return 1
    aciertos = sum(1 for r in de_fase if r.es_correcta)
    return escala(aciertos / len(de_fase))


def finalizar(db: Session, sesion_id: int, rm_id_scope: int | None = None) -> dict:
    sesion = db.get(SimulacroSesion, sesion_id)
    if sesion is None:
        raise ValueError("Sesión no encontrada")
    if rm_id_scope is not None and sesion.rm_id != rm_id_scope:
        raise PermisoError("Esta sesión no es tuya.")
    rondas = (db.query(SimulacroRonda)
              .filter(SimulacroRonda.sesion_id == sesion_id).all())
    ap = _fase_escala(rondas, "Apertura")
    de = _fase_escala(rondas, "Desarrollo")
    ci = _fase_escala(rondas, "Cierre")
    general = round((ap + de + ci) / 3, 2)

    db.query(SimulacroResultado).filter(
        SimulacroResultado.sesion_id == sesion_id).delete(synchronize_session=False)
    db.add(SimulacroResultado(
        sesion_id=sesion_id, calificacion_apertura=ap, calificacion_desarrollo=de,
        calificacion_cierre=ci, calificacion_general=Decimal(str(general))))
    sesion.finalizada = True
    db.commit()
    return {"apertura": ap, "desarrollo": de, "cierre": ci, "general": general}


def voz_ronda(db: Session, ronda_id: int):
    """Audio de la objeción: bytes si hay proveedor real, o Audio(en_navegador)."""
    r = db.get(SimulacroRonda, ronda_id)
    if r is None:
        raise ValueError("Ronda no encontrada")
    return conexion_service.adaptador_voz(db).sintetizar(r.objecion_texto)


def detalle(db: Session, sesion_id: int) -> dict:
    sesion = db.get(SimulacroSesion, sesion_id)
    if sesion is None:
        raise ValueError("Sesión no encontrada")
    rondas = (db.query(SimulacroRonda)
              .filter(SimulacroRonda.sesion_id == sesion_id)
              .order_by(SimulacroRonda.id).all())
    res = db.get(SimulacroResultado, sesion_id)
    resultado = None
    if res is not None:
        resultado = {"apertura": res.calificacion_apertura,
                     "desarrollo": res.calificacion_desarrollo,
                     "cierre": res.calificacion_cierre,
                     "general": float(res.calificacion_general) if res.calificacion_general is not None else None}
    return {"sesion": _sesion_publica(sesion),
            "rondas": [ronda_publica(x) for x in rondas], "resultado": resultado}


def mis_sesiones(db: Session, rm_id: int) -> list[dict]:
    filas = (db.query(SimulacroSesion)
             .filter(SimulacroSesion.rm_id == rm_id)
             .order_by(SimulacroSesion.fecha.desc()).all())
    return [_sesion_publica(s) | {"fecha": s.fecha} for s in filas]


def resumen(db: Session, rm_ids: list[int] | None = None) -> list[dict]:
    """Agregado por RM: nº de prácticas finalizadas y última general."""
    q = db.query(SimulacroSesion)
    if rm_ids is not None:
        q = q.filter(SimulacroSesion.rm_id.in_(rm_ids or [-1]))
    por_rm: dict[int, list[SimulacroSesion]] = {}
    for s in q.all():
        por_rm.setdefault(s.rm_id, []).append(s)
    salida = []
    for rm_id, sesiones in por_rm.items():
        finalizadas = [s for s in sesiones if s.finalizada]
        ultima = None
        if finalizadas:
            reciente = max(finalizadas, key=lambda s: s.fecha)
            res = db.get(SimulacroResultado, reciente.id)
            ultima = float(res.calificacion_general) if res and res.calificacion_general is not None else None
        salida.append({"rm_id": rm_id, "practicas": len(finalizadas), "ultima_general": ultima})
    return sorted(salida, key=lambda x: x["rm_id"])
