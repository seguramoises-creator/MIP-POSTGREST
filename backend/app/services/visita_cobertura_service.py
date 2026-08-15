"""Cobertura del Módulo de Visita Médica (Partes 5-6 del spec) + patrón de
"detalle desplegable por visitador" (ranking de quién cumple/no cumple un indicador).

Todo se calcula en tiempo real a partir de Visita.DIM_MedicoVisita y Visita.FactVisita
(no hay tablas de agregado). Objetivos por defecto: cobertura ≥80%, V+R ≥60%.
"""
from datetime import date, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from app.core.tiempo import hoy_local
from app.models.visita import MedicoVisita, VisitaRegistro
from app.models.dimensiones import RepresentanteMedico, Ciclo

OBJ_COBERTURA = 80.0
OBJ_COMPLETA = 60.0
CICLO_DIAS_DEFAULT = 19  # días hábiles del ciclo (parámetro operativo RD, spec Parte 1)


def _elegir_ciclo(ciclos: list[Ciclo], hoy: date) -> Ciclo | None:
    """De una lista de ciclos, el que CONTIENE `hoy`; si ninguno, el más reciente.

    FIX jul-2026: antes se elegía siempre el ciclo abierto de NÚMERO MÁS ALTO. Con un
    único ciclo abierto acertaba por accidente, pero al abrir un segundo ciclo de número
    mayor (p.ej. reabrir C12 estando en julio) devolvía diciembre, y `_guard_ventana_ciclo`
    rechazaba TODOS los registros de visita del país: los visitadores no podían trabajar
    hasta que un admin cerrara el ciclo intruso. El ciclo de trabajo es el que corresponde
    a HOY, no el de número más alto.

    Fallback al más reciente cuando ninguna ventana cubre hoy: los ciclos van del día 1 al
    28, así que los días 29-31 no caen en ninguno.
    """
    vigentes = [c for c in ciclos
                if c.fecha_inicio and c.fecha_fin and c.fecha_inicio <= hoy <= c.fecha_fin]
    return max(vigentes or ciclos, key=lambda c: (c.anio, c.numero), default=None)


def _ciclo_abierto(db: Session, pais_codigo: str | None) -> Ciclo | None:
    """El ciclo ABIERTO de trabajo (ver `_elegir_ciclo`). Los ciclos abiertos de un país
    son unos pocos, así que se traen y se decide en Python."""
    q = db.query(Ciclo).filter(Ciclo.cerrado == False)  # noqa: E712
    if pais_codigo:
        q = q.filter(Ciclo.pais_codigo == pais_codigo)
    return _elegir_ciclo(q.all(), hoy_local(db, pais_codigo))


def ciclo_por_defecto(db: Session, vm_id: int | None = None, pais_codigo: str | None = None) -> int | None:
    """Ciclo de trabajo por defecto.

    Con `vm_id`: el ciclo abierto del PAÍS del VM que corresponde a hoy — es el ciclo al
    que se registran visitas/muestras y del que se lee la parrilla.
    FIX jul-2026: sin el filtro por país se tomaba el ciclo más reciente GLOBAL (de
    cualquier país, incluso cerrado), y los registros de un VM de DO caían en el ciclo de
    otro país.

    Sin `vm_id` pero con `pais_codigo` (aislamiento multipaís, vista agregada acotada a un
    país): se usa el ciclo abierto de ESE país en vez del ciclo abierto global."""
    if vm_id:
        rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
        if rm and rm.pais_codigo:
            c = _ciclo_abierto(db, rm.pais_codigo)
            if c:
                return c.id
    elif pais_codigo:
        c = _ciclo_abierto(db, pais_codigo)
        if c:
            return c.id
    # Sin vm_id ni pais_codigo (vista agregada global): nunca un ciclo cerrado global (que
    # dejaba el dashboard en blanco cuando el más reciente por (anio,numero) estaba cerrado).
    c = _ciclo_abierto(db, None)
    if c is None:  # si no hay ninguno abierto, cae al más reciente global
        c = db.query(Ciclo).order_by(Ciclo.anio.desc(), Ciclo.numero.desc()).first()
    return c.id if c else None


def _pct(parte: int, total: int) -> float:
    return round(parte / total * 100, 1) if total else 0.0


def _mapa_visitas(db: Session, ciclo_id: int, vm_id: int | None):
    """medico_id -> {'v': bool, 'r': bool} de visitas EJECUTADAS en el ciclo."""
    q = db.query(VisitaRegistro).filter(
        VisitaRegistro.ciclo_id == ciclo_id, VisitaRegistro.ejecutada == True)  # noqa: E712
    if vm_id:
        q = q.filter(VisitaRegistro.vm_id == vm_id)
    mapa: dict[int, dict] = {}
    for v in q.all():
        d = mapa.setdefault(v.medico_id, {"v": False, "r": False})
        if v.tipo_visita == "R":
            d["r"] = True
        else:
            d["v"] = True
    return mapa


def _rm_ids_por(db: Session, gerente_id: int | None, linea_id: int | None,
                pais_codigo: str | None = None,
                permitidos: set[str] | None = None) -> list[int] | None:
    """IDs de RM (visitadores) que pertenecen al Gerente de Distrito, la Línea y/o el País.
    Devuelve None SOLO si no se pidió ningún filtro Y el usuario no tiene país restringido
    (no restringir); si CUALQUIERA de los 3 viene, o si `permitidos` no es None, arma la
    query con los filtros que apliquen y devuelve la lista de ids
    (aislamiento multipaís, jul-2026: sin `pais_codigo` la vista agregada mezclaba VMs de
    TODOS los países cuando no se filtraba por distrito/línea).

    `permitidos` (hallazgo Critical de revisión, ago-2026): `scope.paises_visibles(db, user)`,
    aplicado SIEMPRE como filtro de piso — el cliente puede omitir `pais_codigo` (o mandar un
    `ciclo_id` de otro país) y el guard de endpoint (`exigir_pais`) no se dispara porque no
    valida nada derivado; `permitidos` es lo único que de verdad acota qué RM puede ver el
    caller, la haya pedido explícitamente o no. `None` = usuario sin país asignado (ve todo,
    comportamiento histórico); conjunto = solo esos países, aunque no se haya pedido `pais_codigo`."""
    if not gerente_id and not linea_id and not pais_codigo and permitidos is None:
        return None
    q = db.query(RepresentanteMedico.id)
    if gerente_id:
        q = q.filter(RepresentanteMedico.gerente_id == gerente_id)
    if linea_id:
        q = q.filter(RepresentanteMedico.linea_id == linea_id)
    if pais_codigo:
        q = q.filter(RepresentanteMedico.pais_codigo == pais_codigo)
    if permitidos is not None:
        q = q.filter(RepresentanteMedico.pais_codigo.in_(permitidos))
    return [r[0] for r in q.all()]


def _cobertura_base(db: Session, ciclo_id: int, vm_id: int | None,
                    gerente_id: int | None = None, linea_id: int | None = None,
                    solo_ruptura: bool = False, pais_codigo: str | None = None,
                    permitidos: set[str] | None = None) -> dict:
    """Calcula panel, visitados, completos, sin visitar y desglose por categoría.

    Solo incluye médicos VIGENTES para el ciclo: excluye altas pendientes/rechazadas
    y respeta el ciclo efectivo de alta/baja (aprobación del Gerente de Distrito).

    Filtros: `vm_id` (un visitador) tiene prioridad; si no, `gerente_id`/`linea_id`/
    `pais_codigo` restringen a los médicos de ese distrito/línea/país; `solo_ruptura`
    deja solo los de 3+ ciclos sin visita. `permitidos` (piso de país del usuario, ver
    `_rm_ids_por`) se aplica siempre, con o sin `vm_id` explícito."""
    from app.services.visita_aprobacion_service import ordenes_ciclo, cuenta_en_ciclo
    ordenes = ordenes_ciclo(db)
    ciclo_orden = ordenes.get(ciclo_id)

    mq = db.query(MedicoVisita)
    if vm_id:
        mq = mq.filter(MedicoVisita.vm_id == vm_id)
    else:
        rm_ids = _rm_ids_por(db, gerente_id, linea_id, pais_codigo, permitidos)
        if rm_ids is not None:
            mq = mq.filter(MedicoVisita.vm_id.in_(rm_ids or [-1]))  # [] => sin médicos
    if solo_ruptura:
        mq = mq.filter(MedicoVisita.ciclos_sin_visita >= 3)
    medicos = [m for m in mq.all() if cuenta_en_ciclo(m, ciclo_orden, ordenes)]
    mapa = _mapa_visitas(db, ciclo_id, vm_id)

    total = len(medicos)
    visitados = con_revisita = 0
    cat = {c: {"total": 0, "visitados": 0, "completos": 0} for c in ("A", "B", "C")}
    sin_visita, falta_revisita = [], []
    top_sin_visita, top_falta_revisita = [], []   # TOP: §7.3 regla 2
    for m in medicos:
        d = mapa.get(m.id)
        vis = bool(d and (d["v"] or d["r"]))
        comp = bool(d and d["v"] and d["r"])
        c = cat.get(m.categoria)
        if c:
            c["total"] += 1
            if vis:
                c["visitados"] += 1
            if comp:
                c["completos"] += 1
        if vis:
            visitados += 1
        if comp:
            con_revisita += 1
        elif not vis:
            item = {"id": m.id, "nombre": m.nombre_completo, "categoria": m.categoria,
                    "especialidad_id": m.especialidad_id, "es_top": m.es_top}
            sin_visita.append(item)
            if m.es_top:
                top_sin_visita.append(item)
        if vis and not comp:  # solo Vista, falta Revisita
            item = {"id": m.id, "nombre": m.nombre_completo, "categoria": m.categoria,
                    "es_top": m.es_top}
            falta_revisita.append(item)
            if m.es_top:
                top_falta_revisita.append(item)
    return {
        "panel": total, "visitados": visitados, "con_revisita": con_revisita,
        "sin_visitar": total - visitados,
        "pct_cobertura": _pct(visitados, total),
        "pct_completa": _pct(con_revisita, total),
        "pct_gap": round(100 - _pct(visitados, total), 1),
        "categorias": cat, "sin_visita": sin_visita, "falta_revisita": falta_revisita,
        "top_sin_visita": top_sin_visita, "top_falta_revisita": top_falta_revisita,
    }


def resumen_cobertura(db: Session, ciclo_id: int | None = None, vm_id: int | None = None,
                      gerente_id: int | None = None, linea_id: int | None = None,
                      solo_ruptura: bool = False, pais_codigo: str | None = None,
                      permitidos: set[str] | None = None) -> dict:
    """Datos del Dashboard de Cobertura: gauges, desglose A/B/C, listas y ruptura.
    Filtrable por visitador (vm_id), Gerente de Distrito (gerente_id), Línea (linea_id),
    país (pais_codigo, aislamiento multipaís cuando no hay vm_id/gerente_id/linea_id) y
    solo médicos en ruptura de secuencia (solo_ruptura). `permitidos` = piso de país del
    usuario (ver `_rm_ids_por`): se aplica siempre, la haya pedido el cliente o no."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, pais_codigo=pais_codigo)
    if ciclo_id is None:
        return {"ciclo_id": None, "panel": 0, "visitados": 0, "con_revisita": 0,
                "sin_visitar": 0, "pct_cobertura": 0, "pct_completa": 0, "pct_gap": 0,
                "categorias": {}, "sin_visita": [], "falta_revisita": [], "ruptura": [],
                "top_sin_visita": [], "top_falta_revisita": []}
    base = _cobertura_base(db, ciclo_id, vm_id, gerente_id, linea_id, solo_ruptura, pais_codigo,
                           permitidos)
    # Ruptura de secuencia (≥3 ciclos sin visita) — respeta los mismos filtros de scope.
    rq = db.query(MedicoVisita).filter(
        MedicoVisita.activo == True, MedicoVisita.ciclos_sin_visita >= 3)  # noqa: E712
    if vm_id:
        rq = rq.filter(MedicoVisita.vm_id == vm_id)
    else:
        rm_ids = _rm_ids_por(db, gerente_id, linea_id, pais_codigo, permitidos)
        if rm_ids is not None:
            rq = rq.filter(MedicoVisita.vm_id.in_(rm_ids or [-1]))
    base["ruptura"] = [{"id": m.id, "nombre": m.nombre_completo, "categoria": m.categoria,
                        "ciclos_sin_visita": m.ciclos_sin_visita}
                       for m in rq.order_by(MedicoVisita.ciclos_sin_visita.desc()).all()]
    # KPI de acompañamiento: visitas ejecutadas acompañadas por el GD (respeta el scope).
    aq = db.query(VisitaRegistro).filter(
        VisitaRegistro.ciclo_id == ciclo_id, VisitaRegistro.ejecutada == True,  # noqa: E712
        VisitaRegistro.acompanado == True)  # noqa: E712
    eq = db.query(VisitaRegistro).filter(
        VisitaRegistro.ciclo_id == ciclo_id, VisitaRegistro.ejecutada == True)  # noqa: E712
    if vm_id:
        aq = aq.filter(VisitaRegistro.vm_id == vm_id)
        eq = eq.filter(VisitaRegistro.vm_id == vm_id)
    else:
        rm_ids_a = _rm_ids_por(db, gerente_id, linea_id, pais_codigo, permitidos)
        if rm_ids_a is not None:
            aq = aq.filter(VisitaRegistro.vm_id.in_(rm_ids_a or [-1]))
            eq = eq.filter(VisitaRegistro.vm_id.in_(rm_ids_a or [-1]))
    acomp, total_ejec = aq.count(), eq.count()
    base["acompanadas"] = acomp
    base["visitas_ejecutadas"] = total_ejec
    base["pct_acompanamiento"] = _pct(acomp, total_ejec)
    base["ciclo_id"] = ciclo_id
    base["objetivo_cobertura"] = OBJ_COBERTURA
    base["objetivo_completa"] = OBJ_COMPLETA
    # Cuando se consulta un solo visitador (RM), se agrega cómo va SU LÍNEA COMPLETA — para que el
    # RM compare su programación (panel propio) contra el total de su línea, sin ver el agregado
    # de toda la empresa. Solo cifras agregadas de la línea (sin nombres de médicos de otros VM).
    if vm_id:
        from app.models.dimensiones import RepresentanteMedico, Linea
        rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
        if rm and rm.linea_id:
            lb = _cobertura_base(db, ciclo_id, None, None, rm.linea_id, False)
            ln = db.query(Linea.nombre).filter(Linea.id == rm.linea_id).scalar()
            base["linea_total"] = {
                "linea_id": rm.linea_id, "linea_nombre": ln or f"Línea #{rm.linea_id}",
                "panel": lb["panel"], "visitados": lb["visitados"],
                "sin_visitar": lb["sin_visitar"],
                "pct_cobertura": lb["pct_cobertura"], "pct_completa": lb["pct_completa"],
            }
    return base


def ranking_visitadores(db: Session, ciclo_id: int | None, metrica: str,
                        pais_codigo: str | None = None,
                        permitidos: set[str] | None = None) -> dict:
    """Detalle desplegable: por cada VM con médicos en su panel, el valor de la
    métrica y si cumple el objetivo. metrica: 'cobertura' | 'completa' | 'sin_visitar'.
    `pais_codigo` (aislamiento multipaís): sin filtro, mezclaba VMs de TODOS los países.
    `permitidos` = piso de país del usuario (ver `_rm_ids_por`): se aplica siempre."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db, pais_codigo=pais_codigo)
    vq = db.query(MedicoVisita.vm_id).filter(MedicoVisita.activo == True)  # noqa: E712
    if pais_codigo or permitidos is not None:
        rm_ids_pais = _rm_ids_por(db, None, None, pais_codigo, permitidos) or []
        vq = vq.filter(MedicoVisita.vm_id.in_(rm_ids_pais or [-1]))
    vm_ids = [r[0] for r in vq.distinct().all()]
    if not vm_ids:
        return {"metrica": metrica, "objetivo": None, "items": [], "no_cumplen": 0, "total": 0}
    nombres = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.nombre)
                   .filter(RepresentanteMedico.id.in_(vm_ids)).all())
    zonas = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.zona)
                 .filter(RepresentanteMedico.id.in_(vm_ids)).all())

    filas = []
    total_sin = 0
    for vm in vm_ids:
        b = _cobertura_base(db, ciclo_id, vm)
        total_sin += b["sin_visitar"]
        if metrica == "completa":
            valor, mayor_mejor = b["pct_completa"], True
        elif metrica == "sin_visitar":
            valor, mayor_mejor = b["sin_visitar"], False
        else:
            valor, mayor_mejor = b["pct_cobertura"], True
        filas.append({"vm_id": vm, "nombre": nombres.get(vm, f"VM #{vm}"),
                      "zona": zonas.get(vm), "valor": valor, "_mm": mayor_mejor})

    if metrica == "completa":
        objetivo = OBJ_COMPLETA
    elif metrica == "sin_visitar":
        objetivo = round(total_sin / len(vm_ids), 1)  # promedio del equipo
    else:
        objetivo = OBJ_COBERTURA

    for f in filas:
        f["cumple"] = (f["valor"] >= objetivo) if f["_mm"] else (f["valor"] <= objetivo)
    mayor_mejor = filas[0]["_mm"] if filas else True
    filas.sort(key=lambda f: f["valor"], reverse=not mayor_mejor)  # peor primero
    for f in filas:
        f.pop("_mm", None)
    return {"metrica": metrica, "objetivo": objetivo,
            "no_cumplen": sum(1 for f in filas if not f["cumple"]),
            "total": len(filas), "items": filas}


def _dias_habiles(inicio, fin) -> int:
    if not inicio or not fin:
        return CICLO_DIAS_DEFAULT
    d, cur = 0, inicio
    while cur <= fin:
        if cur.weekday() < 5:  # lun-vie
            d += 1
        cur += timedelta(days=1)
    return d or CICLO_DIAS_DEFAULT


# El módulo "Proyección Visita" fue retirado (jul-2026): Cobertura Predictiva absorbe
# su rol de proyección. Las funciones proyeccion()/ranking_proyeccion() se eliminaron.
# `_dia_actual_ciclo` sobrevivió a ese retiro sin ningún llamador y se eliminó en
# ago-2026: además de ser código muerto, resolvía "hoy" con el reloj del servidor,
# justo la trampa que un servidor multipaís no puede dejar a mano de nadie.
