"""Plan de Cierre de Brechas (§12).

Motor de REGLAS sobre los datos ya calculados del KPI (§11), no generación por
IA: el §20.7 lo excluye explícitamente de la capa de proveedores porque aquí no
hay nada que redactar, hay condiciones que evaluar.

QUÉ APORTA QUE NO APORTE EL KPI SOLO
-------------------------------------
El valor está en CRUZAR los cuatro desgloses. La misma pregunta fallada en
muchos segmentos es un vacío de contenido que afecta a todos; fallada en uno
solo, es un problema de ese equipo; y fallada incluso por quienes aciertan todo
lo demás, es que el material está mal escrito. Son tres causas distintas con
tres acciones distintas, y **ninguna vista aislada las distingue** — hay que
poder comparar el mismo dato entre segmentos.

LOS UMBRALES NO ESTÁN EN EL CÓDIGO
-----------------------------------
El §12.3 los marca como valores ilustrativos del mockup, pendientes de confirmar
con Capacitación (punto abierto 6). Viven en `formacion.ParametroFormacion` y
aquí solo están los valores de arranque, para que cambiarlos sea un dato y no un
despliegue.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.formacion import ParametroFormacion, PlanCierreBrecha
from app.models.hechos import EvaluacionReceptividad
from app.services import formacion_kpi_refuerzo_service as kpi

#: Valores de arranque del §12.2. Cualquiera puede sobrescribirse por país sin
#: tocar código, escribiendo una fila en `formacion.ParametroFormacion`.
UMBRALES_DEFECTO: dict[str, float] = {
    # Regla 1 — fracción de segmentos en que debe repetirse una pregunta para
    # considerarla brecha generalizada ("más de la mitad").
    "brecha_generalizada_fraccion": 0.5,
    # Regla 3 — a partir de qué % de aciertos general se considera que el
    # representante domina el tema y el problema es del material.
    "material_dominio_pct": 85.0,
    # Regla 4 — umbrales de las métricas para el escalamiento individual.
    "escalamiento_aciertos_pct": 70.0,
    "escalamiento_tiempo_seg": 1800.0,        # 30 minutos
    "escalamiento_participacion_pct": 70.0,
    # Cuántas métricas deben estar en rojo a la vez para escalar.
    "escalamiento_metricas_min": 2.0,
}

PRIORIDAD_ALTA = "alta"
PRIORIDAD_MEDIA = "media"
PRIORIDAD_INFO = "informativa"


def umbrales(db: Session, pais_codigo: str) -> dict[str, float]:
    """Los de arranque, con las sobrescrituras que haya configurado el país."""
    valores = dict(UMBRALES_DEFECTO)
    for p in (db.query(ParametroFormacion)
              .filter(ParametroFormacion.pais_codigo == pais_codigo).all()):
        if p.clave in valores:
            valores[p.clave] = float(p.valor)
    return valores


def fijar_umbral(db: Session, pais_codigo: str, clave: str, valor: float,
                 descripcion: str | None = None) -> ParametroFormacion:
    if clave not in UMBRALES_DEFECTO:
        raise ValueError(
            f"Umbral desconocido: {clave}. Válidos: {', '.join(sorted(UMBRALES_DEFECTO))}.")
    p = (db.query(ParametroFormacion)
         .filter(ParametroFormacion.pais_codigo == pais_codigo,
                 ParametroFormacion.clave == clave).first())
    if p is None:
        p = ParametroFormacion(pais_codigo=pais_codigo, clave=clave,
                               valor=Decimal(str(valor)), descripcion=descripcion)
        db.add(p)
    else:
        p.valor = Decimal(str(valor))
        if descripcion:
            p.descripcion = descripcion
    db.commit()
    db.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Utilidades sobre el reporte
# ---------------------------------------------------------------------------

def _menos_acertadas_por_segmento(reporte: dict) -> dict[int, list[tuple[str, object]]]:
    """Para cada pregunta, en qué segmentos salió como la menos acertada.

    Se recorren los tres desgloses que el §12.2 nombra —representante, producto
    y país— porque son los que permiten distinguir "le pasa a todos" de "le pasa
    a este". El desglose por GD se usa aparte, en la regla 2.
    """
    ocurrencias: dict[int, list[tuple[str, object]]] = {}
    for desglose, clave in (("por_representante", "rm_id"),
                            ("por_producto", "producto_id"),
                            ("por_pais", "pais_codigo")):
        for fila in reporte.get(desglose, []):
            peor = fila.get("pregunta_menos_acertada")
            if peor:
                ocurrencias.setdefault(peor["capsula_id"], []).append(
                    (desglose, fila[clave]))
    return ocurrencias


def _total_segmentos(reporte: dict) -> int:
    return sum(len(reporte.get(d, []))
               for d in ("por_representante", "por_producto", "por_pais"))


def _enunciado(reporte: dict, capsula_id: int) -> str:
    for desglose in ("por_representante", "por_producto", "por_pais", "por_gd"):
        for fila in reporte.get(desglose, []):
            for extremo in ("pregunta_menos_acertada", "pregunta_mas_acertada"):
                p = fila.get(extremo)
                if p and p["capsula_id"] == capsula_id:
                    return p["enunciado"]
    return f"pregunta {capsula_id}"


# ---------------------------------------------------------------------------
# Las 5 reglas del §12.2
# ---------------------------------------------------------------------------

def _regla_contenido_generalizado(reporte: dict, u: dict) -> list[dict]:
    """REGLA 1 (Alta) — la misma pregunta falla en medio mundo.

    Cuando el fallo se reparte por muchos segmentos, la causa no está en las
    personas: está en lo que se enseñó. La acción es una campaña dirigida a todo
    el equipo, no un seguimiento individual."""
    total = _total_segmentos(reporte)
    if total == 0:
        return []
    minimo = total * u["brecha_generalizada_fraccion"]
    alertas = []
    for capsula_id, segmentos in _menos_acertadas_por_segmento(reporte).items():
        if len(segmentos) > minimo:
            alertas.append({
                "regla_aplicada": "contenido_generalizado",
                "prioridad": PRIORIDAD_ALTA,
                "alcance": "toda la organización",
                "descripcion": (
                    f"«{_enunciado(reporte, capsula_id)}» es la pregunta menos "
                    f"acertada en {len(segmentos)} de {total} segmentos evaluados. "
                    "Cuando el fallo se reparte así, la causa está en el contenido, "
                    "no en los representantes."),
                "accion_sugerida": (
                    "Programar una campaña de Refuerzo dirigida a TODO el equipo "
                    "sobre este tema, no un seguimiento individual."),
                "link_accion": "/formacion/refuerzo",
                "_capsula_id": capsula_id,
            })
    return alertas


def _regla_concentrada(reporte: dict, generalizadas: set[int]) -> list[dict]:
    """REGLA 2 (Media) — falla solo en un equipo o país.

    Se excluyen las ya marcadas como generalizadas: si le pasa a todos, señalar
    además a un equipo concreto sería ruido que desvía la atención."""
    alertas = []
    for desglose, clave, etiqueta in (("por_gd", "gerente_id", "equipo del gerente"),
                                      ("por_pais", "pais_codigo", "país")):
        for fila in reporte.get(desglose, []):
            peor = fila.get("pregunta_menos_acertada")
            if not peor or peor["capsula_id"] in generalizadas:
                continue
            alertas.append({
                "regla_aplicada": "concentrada_equipo_pais",
                "prioridad": PRIORIDAD_MEDIA,
                "alcance": f"{etiqueta} {fila[clave]}",
                "descripcion": (
                    f"«{peor['enunciado']}» falla en este segmento "
                    f"({peor['pct_aciertos']}% de aciertos) pero no en los demás. "
                    "Es un problema localizado, no del contenido."),
                "accion_sugerida": (
                    "Reforzar con un caso clínico supervisado en la próxima sesión "
                    "de Coaching presencial de ese Gerente de Distrito."),
                "link_accion": "/coaching/calendario",
                "_capsula_id": peor["capsula_id"],
            })
    return alertas


def _regla_material(reporte: dict, u: dict) -> list[dict]:
    """REGLA 3 (Media) — falla incluso a quien domina todo lo demás.

    Es la regla más útil de las cinco y la menos evidente: si alguien acierta el
    85% del temario y aun así falla esta pregunta, lo más probable es que la
    pregunta —o el material del que salió— esté mal planteada. Mandarle más
    refuerzo a esa persona no arregla nada."""
    alertas = []
    for fila in reporte.get("por_representante", []):
        aciertos = fila.get("pct_aciertos")
        peor = fila.get("pregunta_menos_acertada")
        if aciertos is None or peor is None:
            continue
        if aciertos >= u["material_dominio_pct"] and peor["pct_aciertos"] < 100:
            alertas.append({
                "regla_aplicada": "material_no_personas",
                "prioridad": PRIORIDAD_MEDIA,
                "alcance": f"representante {fila['rm_id']}",
                "descripcion": (
                    f"Este representante acierta el {aciertos}% del temario y aun "
                    f"así falla «{peor['enunciado']}». Cuando falla quien domina "
                    "el resto, la causa probable es el material, no la persona."),
                "accion_sugerida": (
                    "Revisar y simplificar el material fuente en Biblioteca junto "
                    "a Gerencia Médica ANTES de programar más refuerzo del tema."),
                "link_accion": "/formacion/biblioteca",
                "_capsula_id": peor["capsula_id"],
            })
    return alertas


def _regla_escalamiento(db: Session, reporte: dict, u: dict) -> list[dict]:
    """REGLA 4 (Alta) — dos o más métricas en rojo a la vez.

    Con una sola métrica baja puede ser una mala semana; con dos, más cápsulas
    automáticas no van a resolverlo. Si además la Matriz LSII ya lo tenía en
    D1/D2, se señala esa coincidencia: dos sistemas independientes apuntando al
    mismo representante es una señal mucho más fuerte que cualquiera por
    separado."""
    alertas = []
    for fila in reporte.get("por_representante", []):
        rojos = []
        if (fila.get("pct_aciertos") is not None
                and fila["pct_aciertos"] < u["escalamiento_aciertos_pct"]):
            rojos.append(f"aciertos {fila['pct_aciertos']}%")
        if fila.get("tiempo_promedio_seg", 0) > u["escalamiento_tiempo_seg"]:
            rojos.append(f"tiempo de respuesta {round(fila['tiempo_promedio_seg']/60)} min")
        if fila.get("pct_participacion", 100) < u["escalamiento_participacion_pct"]:
            rojos.append(f"participación {fila['pct_participacion']}%")
        if len(rojos) < u["escalamiento_metricas_min"]:
            continue

        descripcion = (f"Representante {fila['rm_id']} por debajo del umbral en "
                       f"{len(rojos)} métricas a la vez: {', '.join(rojos)}.")
        nivel = _nivel_lsii(db, fila["rm_id"])
        if nivel in ("D1", "D2"):
            descripcion += (f" La Matriz LSII ya lo había clasificado en {nivel}: "
                            "dos sistemas independientes coinciden.")
        alertas.append({
            "regla_aplicada": "escalamiento_individual",
            "prioridad": PRIORIDAD_ALTA,
            "alcance": f"representante {fila['rm_id']}",
            "descripcion": descripcion,
            "accion_sugerida": (
                "No basta con más cápsulas automáticas: programar Coaching "
                "presencial con este representante."),
            "link_accion": f"/lsii?rm_id={fila['rm_id']}",
            "_capsula_id": None,
        })
    return alertas


def _nivel_lsii(db: Session, rm_id: int) -> str | None:
    """Cuadrante vigente del representante, para la validación cruzada."""
    fila = (db.query(EvaluacionReceptividad)
            .filter(EvaluacionReceptividad.rm_id == rm_id)
            .order_by(EvaluacionReceptividad.id.desc())
            .first())
    return fila.nivel_lsii if fila else None


def _regla_operativa(reporte: dict) -> list[dict]:
    """REGLA 5 (Informativa) — un equipo entero por debajo en las TRES métricas.

    Que fallen las tres a la vez, y no un tema concreto, apunta a que las
    notificaciones no están llegando o nadie las abre. Subir la frecuencia de
    cápsulas en ese escenario solo genera más ruido sin resolver la causa."""
    general = reporte.get("general", {})
    if not general or general.get("respuestas", 0) == 0:
        return []
    alertas = []
    for desglose, clave, etiqueta in (("por_gd", "gerente_id", "equipo del gerente"),
                                      ("por_pais", "pais_codigo", "país")):
        for fila in reporte.get(desglose, []):
            peor_participacion = fila["pct_participacion"] < general["pct_participacion"]
            peor_tiempo = fila["tiempo_promedio_seg"] > general["tiempo_promedio_seg"]
            peor_aciertos = (fila.get("pct_aciertos") is not None
                             and general.get("pct_aciertos") is not None
                             and fila["pct_aciertos"] < general["pct_aciertos"])
            if peor_participacion and peor_tiempo and peor_aciertos:
                alertas.append({
                    "regla_aplicada": "operativa_gestion",
                    "prioridad": PRIORIDAD_INFO,
                    "alcance": f"{etiqueta} {fila[clave]}",
                    "descripcion": (
                        "Este segmento está por debajo del promedio general en las "
                        "TRES métricas a la vez, no en un tema concreto. Eso apunta "
                        "a adopción, no a contenido."),
                    "accion_sugerida": (
                        "Auditar con el Gerente de Distrito si las notificaciones "
                        "(correo y VISTA Móvil) están llegando y se abren, ANTES de "
                        "aumentar la frecuencia de cápsulas."),
                    "link_accion": "/formacion/refuerzo/kpi",
                    "_capsula_id": None,
                })
    return alertas


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

def generar(db: Session, pais_codigo: str, campana_id: int | None = None,
            ciclo_id: int | None = None, persistir: bool = True) -> list[dict]:
    """Evalúa las 5 reglas y devuelve las alertas priorizadas.

    Al persistir se BORRA lo anterior del mismo país y ciclo antes de insertar:
    el plan es una foto del estado actual, no un historial. Acumular corridas
    dejaría a Capacitación mirando brechas ya cerradas.
    """
    reporte = kpi.reporte(db, campana_id=campana_id, pais_codigo=pais_codigo)
    u = umbrales(db, pais_codigo)

    generalizadas = _regla_contenido_generalizado(reporte, u)
    ids_generalizados = {a["_capsula_id"] for a in generalizadas}
    alertas = (generalizadas
               + _regla_concentrada(reporte, ids_generalizados)
               + _regla_material(reporte, u)
               + _regla_escalamiento(db, reporte, u)
               + _regla_operativa(reporte))

    orden = {PRIORIDAD_ALTA: 0, PRIORIDAD_MEDIA: 1, PRIORIDAD_INFO: 2}
    alertas.sort(key=lambda a: orden[a["prioridad"]])

    if persistir:
        (db.query(PlanCierreBrecha)
         .filter(PlanCierreBrecha.pais_codigo == pais_codigo,
                 PlanCierreBrecha.ciclo_id == ciclo_id)
         .delete(synchronize_session=False))
        for a in alertas:
            db.add(PlanCierreBrecha(
                pais_codigo=pais_codigo, ciclo_id=ciclo_id,
                regla_aplicada=a["regla_aplicada"], prioridad=a["prioridad"],
                alcance=a["alcance"], descripcion=a["descripcion"],
                accion_sugerida=a["accion_sugerida"], link_accion=a["link_accion"]))
        db.commit()
    return alertas


def listar(db: Session, pais_codigo: str, ciclo_id: int | None = None,
           incluir_atendidas: bool = False) -> list[PlanCierreBrecha]:
    q = (db.query(PlanCierreBrecha)
         .filter(PlanCierreBrecha.pais_codigo == pais_codigo))
    if ciclo_id is not None:
        q = q.filter(PlanCierreBrecha.ciclo_id == ciclo_id)
    if not incluir_atendidas:
        q = q.filter(PlanCierreBrecha.atendida.is_(False))
    return q.order_by(PlanCierreBrecha.generado_en.desc()).all()


def marcar_atendida(db: Session, alerta_id: int) -> PlanCierreBrecha:
    a = db.get(PlanCierreBrecha, alerta_id)
    if a is None:
        raise ValueError("Alerta no encontrada")
    a.atendida = True
    db.commit()
    db.refresh(a)
    return a
