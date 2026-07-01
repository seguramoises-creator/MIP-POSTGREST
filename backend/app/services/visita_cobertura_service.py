"""Cobertura del Módulo de Visita Médica (Partes 5-6 del spec) + patrón de
"detalle desplegable por visitador" (ranking de quién cumple/no cumple un indicador).

Todo se calcula en tiempo real a partir de Visita.DIM_MedicoVisita y Visita.FactVisita
(no hay tablas de agregado). Objetivos por defecto: cobertura ≥80%, V+R ≥60%.
"""
from loguru import logger
from sqlalchemy.orm import Session

from app.models.visita import MedicoVisita, VisitaRegistro
from app.models.dimensiones import RepresentanteMedico, Ciclo

OBJ_COBERTURA = 80.0
OBJ_COMPLETA = 60.0


def ciclo_por_defecto(db: Session) -> int | None:
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


def _cobertura_base(db: Session, ciclo_id: int, vm_id: int | None) -> dict:
    """Calcula panel, visitados, completos, sin visitar y desglose por categoría."""
    mq = db.query(MedicoVisita).filter(MedicoVisita.activo == True)  # noqa: E712
    if vm_id:
        mq = mq.filter(MedicoVisita.vm_id == vm_id)
    medicos = mq.all()
    mapa = _mapa_visitas(db, ciclo_id, vm_id)

    total = len(medicos)
    visitados = con_revisita = 0
    cat = {c: {"total": 0, "visitados": 0, "completos": 0} for c in ("A", "B", "C")}
    sin_visita, falta_revisita = [], []
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
            sin_visita.append({"id": m.id, "nombre": m.nombre_completo, "categoria": m.categoria,
                               "especialidad_id": m.especialidad_id})
        if vis and not comp:  # solo Vista, falta Revisita
            falta_revisita.append({"id": m.id, "nombre": m.nombre_completo, "categoria": m.categoria})
    return {
        "panel": total, "visitados": visitados, "con_revisita": con_revisita,
        "sin_visitar": total - visitados,
        "pct_cobertura": _pct(visitados, total),
        "pct_completa": _pct(con_revisita, total),
        "pct_gap": round(100 - _pct(visitados, total), 1),
        "categorias": cat, "sin_visita": sin_visita, "falta_revisita": falta_revisita,
    }


def resumen_cobertura(db: Session, ciclo_id: int | None = None, vm_id: int | None = None) -> dict:
    """Datos del Dashboard de Cobertura: gauges, desglose A/B/C, listas y ruptura."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        return {"ciclo_id": None, "panel": 0, "visitados": 0, "con_revisita": 0,
                "sin_visitar": 0, "pct_cobertura": 0, "pct_completa": 0, "pct_gap": 0,
                "categorias": {}, "sin_visita": [], "falta_revisita": [], "ruptura": []}
    base = _cobertura_base(db, ciclo_id, vm_id)
    # Ruptura de secuencia (≥3 ciclos sin visita)
    rq = db.query(MedicoVisita).filter(
        MedicoVisita.activo == True, MedicoVisita.ciclos_sin_visita >= 3)  # noqa: E712
    if vm_id:
        rq = rq.filter(MedicoVisita.vm_id == vm_id)
    base["ruptura"] = [{"id": m.id, "nombre": m.nombre_completo, "categoria": m.categoria,
                        "ciclos_sin_visita": m.ciclos_sin_visita}
                       for m in rq.order_by(MedicoVisita.ciclos_sin_visita.desc()).all()]
    base["ciclo_id"] = ciclo_id
    base["objetivo_cobertura"] = OBJ_COBERTURA
    base["objetivo_completa"] = OBJ_COMPLETA
    return base


def ranking_visitadores(db: Session, ciclo_id: int | None, metrica: str) -> dict:
    """Detalle desplegable: por cada VM con médicos en su panel, el valor de la
    métrica y si cumple el objetivo. metrica: 'cobertura' | 'completa' | 'sin_visitar'."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    vm_ids = [r[0] for r in db.query(MedicoVisita.vm_id)
              .filter(MedicoVisita.activo == True).distinct().all()]  # noqa: E712
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
