"""
SCGCPR — Router: Ranking
GET /api/v1/ranking  — Ranking acumulado ciclo 1..N, score = AVG (igual al dashboard)
Tendencia: compara score del ciclo N vs ciclo N-1 para cada RM.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer

from app.core.deps import get_db, get_current_active_user
from app.core.authz.deps import require
from app.core.authz.constantes import Accion, Recurso
from app.models.usuario import Rol
from app.models.hechos import RankingRM
from app.models.dimensiones import RepresentanteMedico, Linea, Gerente, Pais, Ciclo
from app.core.pagination import PaginationParams

router = APIRouter(prefix="/ranking", tags=["Ranking"])
AnyAuth = Depends(get_current_active_user)
# RBAC Fase 2: ranking.rkt DENIEGA a GERENTE_MEDICO (firewall). RM=propia fila (fail-closed en
# el cuerpo); managers ven el ranking con scope_gd. /generar (ops) queda en ADMIN+GERPROD.
ReadRanking = Depends(require(Accion.READ, Recurso.RANKING_RKT))


@router.get("/mi-posicion", response_model=dict, summary="Mi posición en el ranking (sin ver a nadie más)")
def get_mi_posicion(ciclo_id: Optional[int] = Query(None), db: Session = Depends(get_db),
                    current_user=ReadRanking):
    """Dónde está el representante y contra cuántos compite — nunca QUIÉN es quién.

    Decisión del cliente (jul-2026): el representante ve su posición ("estás 12 de 45"), no el
    ranking completo. Un ranking con nombres y puntajes es el dato individual de cada colega
    expuesto a los otros 44, y contradiría la regla que él mismo fijó para Productividad
    ("no puede ver ningún dato de ningún otro visitador"). Aquí solo salen su fila y CONTEOS
    del universo: nunca una fila ajena.
    """
    if current_user.rol != Rol.REPRESENTANTE_MEDICO:
        raise HTTPException(403, "Esta vista es la de un representante médico.")
    if not current_user.rm_id:
        raise HTTPException(403, "Tu usuario no está vinculado a un representante médico.")

    q = db.query(RankingRM).filter(RankingRM.rm_id == current_user.rm_id,
                                   RankingRM.tipo_ranking == "MENSUAL")
    if ciclo_id:
        q = q.filter(RankingRM.ciclo_id == ciclo_id)
    fila = q.order_by(RankingRM.ciclo_id.desc()).first()
    if not fila:
        return {"sin_datos": True, "posicion": None, "total": None,
                "motivo": "Todavía no tienes resultados en el ranking de este ciclo."}

    # Universo con el que compite: mismo ciclo, país y tipo. Solo se cuenta — no se lee
    # ninguna fila ajena.
    base = db.query(RankingRM).filter(RankingRM.ciclo_id == fila.ciclo_id,
                                      RankingRM.pais_codigo == fila.pais_codigo,
                                      RankingRM.tipo_ranking == "MENSUAL")
    total = base.count()
    total_linea = base.filter(RankingRM.linea_id == fila.linea_id).count() if fila.linea_id else None

    ciclo = db.query(Ciclo.nombre).filter(Ciclo.id == fila.ciclo_id).scalar()
    linea = db.query(Linea.nombre).filter(Linea.id == fila.linea_id).scalar() if fila.linea_id else None
    # Percentil: a cuántos supera, en %. Con 1 solo participante no significa nada.
    percentil = round((total - fila.posicion_global) / (total - 1) * 100) if total > 1 else None
    delta = (fila.posicion_anterior - fila.posicion_global) if fila.posicion_anterior else None

    return {
        "sin_datos": False,
        "ciclo": ciclo, "ciclo_id": fila.ciclo_id,
        "posicion": fila.posicion_global, "total": total,
        "posicion_linea": fila.posicion_linea, "total_linea": total_linea, "linea": linea,
        "score_total": float(fila.score_total or 0),
        "percentil": percentil,
        "posicion_anterior": fila.posicion_anterior,
        "variacion": delta,           # + = subió puestos, − = bajó
        "elegible": bool(fila.elegible),
    }


def _ciclos_acumulados(db: Session, ciclo_id: int):
    """Ids de ciclos 1..N del mismo pais+anio que el ciclo seleccionado."""
    sel = db.query(Ciclo).filter(Ciclo.id == ciclo_id).first()
    if not sel:
        return [ciclo_id], sel
    ids = [
        r.id for r in db.query(Ciclo.id).filter(
            Ciclo.pais_codigo == sel.pais_codigo,
            Ciclo.anio    == sel.anio,
            Ciclo.numero  <= sel.numero,
            Ciclo.activo  == True,
        ).all()
    ]
    return (ids or [ciclo_id]), sel


def _ultimo_ciclo(db: Session, pais_codigo: Optional[str], tipo: str) -> Optional[int]:
    q = (
        db.query(RankingRM.ciclo_id)
        .join(Ciclo, Ciclo.id == RankingRM.ciclo_id)
        .filter(RankingRM.tipo_ranking == tipo.upper())
    )
    if pais_codigo:
        q = q.filter(RankingRM.pais_codigo == pais_codigo)
    row = q.order_by(Ciclo.anio.desc(), Ciclo.numero.desc()).limit(1).first()
    return row.ciclo_id if row else None


def _score_por_rm_ciclo(db: Session, ciclo_id: int, tipo: str, pais_codigo: Optional[str]) -> dict:
    """Devuelve {rm_id: score_avg} para UN ciclo. rm_id ausente = sin datos (None implícito)."""
    q = (
        db.query(RankingRM.rm_id, func.avg(RankingRM.score_total).label("sc"))
        .filter(RankingRM.ciclo_id == ciclo_id, RankingRM.tipo_ranking == tipo.upper())
    )
    if pais_codigo:
        q = q.filter(RankingRM.pais_codigo == pais_codigo)
    return {r.rm_id: float(r.sc) for r in q.group_by(RankingRM.rm_id).all() if r.sc is not None}


@router.get("", response_model=dict, summary="Ranking acumulado (paginado)")
def get_ranking(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    tipo: str = "MENSUAL",
    top: Optional[int] = None,
    params: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=ReadRanking,
):
    # FIX (jul-2026, bug latente hoy inalcanzable desde la UI): `_ultimo_ciclo`
    # sin `pais_codigo` elegía el ciclo más reciente de CUALQUIER país (cada
    # ciclo_id pertenece a uno solo), y el resultado terminaba siendo el de un
    # país arbitrario disfrazado de "todos los países". Con ciclo_id explícito
    # no hay bug (el país se resuelve del propio ciclo en `_ciclos_acumulados`);
    # sin país NI ciclo_id, mejor dejarlo sin resolver — cae en el "sin datos"
    # de abajo en vez de un resultado silenciosamente incorrecto.
    ciclo_efectivo = ciclo_id or (_ultimo_ciclo(db, pais_codigo, tipo) if pais_codigo else None)
    if not ciclo_efectivo:
        return {"items": [], "total": 0, "page": 1, "size": params.size,
                "pages": 1, "ciclo_efectivo": None}

    ciclo_ids, ciclo_sel = _ciclos_acumulados(db, ciclo_efectivo)
    num_ciclos_total = len(ciclo_ids)

    # Todos los ciclos del año desde DIM_Ciclo (las 12 columnas)
    todos_ciclos = (
        db.query(Ciclo)
        .filter(
            Ciclo.pais_codigo == (ciclo_sel.pais_codigo if ciclo_sel else pais_codigo),
            Ciclo.anio    == (ciclo_sel.anio    if ciclo_sel else None),
            Ciclo.activo  == True,
        )
        .order_by(Ciclo.numero.asc())
        .all()
    ) if ciclo_sel else []

    ciclo_num_a_id = {c.numero: c.id for c in todos_ciclos}

    # Score por cada ciclo del año (0 si no hay datos cargados aún)
    scores_por_ciclo: dict[int, dict] = {}
    for c in todos_ciclos:
        scores_por_ciclo[c.numero] = _score_por_rm_ciclo(db, c.id, tipo, pais_codigo)

    # Score del ciclo anterior para calcular tendencia
    score_prev: dict = {}
    if ciclo_sel and ciclo_sel.numero > 1:
        prev_id = ciclo_num_a_id.get(ciclo_sel.numero - 1)
        if not prev_id:
            prev_id = db.query(Ciclo.id).filter(
                Ciclo.pais_codigo == ciclo_sel.pais_codigo,
                Ciclo.anio    == ciclo_sel.anio,
                Ciclo.numero  == ciclo_sel.numero - 1,
                Ciclo.activo  == True,
            ).scalar()
        if prev_id:
            score_prev = scores_por_ciclo.get(ciclo_sel.numero - 1,
                         _score_por_rm_ciclo(db, prev_id, tipo, pais_codigo))

    # Score del ciclo actual (ultimo de los acumulados) para comparar
    score_actual = scores_por_ciclo.get(ciclo_sel.numero if ciclo_sel else 0,
                   _score_por_rm_ciclo(db, ciclo_efectivo, tipo, pais_codigo))

    # Subquery: promedio acumulado por RM (AVG de ciclos 1..N)
    sub = (
        db.query(
            RankingRM.rm_id,
            func.avg(RankingRM.score_total).label("score_acumulado"),
            func.count(RankingRM.ciclo_id).label("num_ciclos"),
            func.max(RankingRM.elegible.cast(__import__('sqlalchemy').Integer)).label("elegible_max"),
        )
        .filter(
            RankingRM.tipo_ranking == tipo.upper(),
            RankingRM.ciclo_id.in_(ciclo_ids),
        )
    )
    if pais_codigo:
        sub = sub.filter(RankingRM.pais_codigo == pais_codigo)
    # FAIL-CLOSED: era `if rol == RM and current_user.rm_id`. Con rm_id nulo la condición era
    # falsa, el filtro NO se aplicaba y el representante veía el ranking COMPLETO de todos sus
    # compañeros. El representante usa /ranking/mi-posicion; aquí solo puede ver su fila.
    if current_user.rol == Rol.REPRESENTANTE_MEDICO:
        if not current_user.rm_id:
            raise HTTPException(403, "Tu usuario no está vinculado a un representante médico.")
        sub = sub.filter(RankingRM.rm_id == current_user.rm_id)
    sub = sub.group_by(RankingRM.rm_id).subquery()

    q = (
        db.query(
            sub,
            RepresentanteMedico.nombre.label("rm_nombre"),
            RepresentanteMedico.codigo.label("rm_codigo"),
            Linea.nombre.label("linea_nombre"),
            Gerente.nombre.label("gerente_nombre"),
        )
        .join(RepresentanteMedico, RepresentanteMedico.id == sub.c.rm_id)
        .outerjoin(Linea,   Linea.id   == RepresentanteMedico.linea_id)
        .outerjoin(Gerente, Gerente.id == RepresentanteMedico.gerente_id)
        .order_by(sub.c.score_acumulado.desc())
    )
    if top:
        q = q.limit(top)

    total = q.count()
    rows  = q.offset(params.offset).limit(params.size).all()

    items = []
    for i, r in enumerate(rows):
        pos        = params.offset + i + 1
        sc_actual  = score_actual.get(r.rm_id, float(r.score_acumulado or 0))
        sc_prev    = score_prev.get(r.rm_id)
        # variacion: diferencia de score ciclo_actual vs ciclo_anterior
        variacion  = round(sc_actual - sc_prev, 2) if sc_prev is not None else None

        # Scores por ciclo individual: None si el RM no tiene datos en ese ciclo
        ciclo_scores = {
            f"score_c{num}": round(sc_map[r.rm_id], 2) if r.rm_id in sc_map else None
            for num, sc_map in scores_por_ciclo.items()
        }

        items.append({
            "posicion":        pos,
            "posicion_linea":  None,
            "posicion_anterior": None,
            "variacion":       variacion,
            "rm_id":           r.rm_id,
            "rm_codigo":       r.rm_codigo,
            "rm_nombre":       r.rm_nombre,
            "linea_nombre":    r.linea_nombre  or "—",
            "gerente_nombre":  r.gerente_nombre or "—",
            "pais_codigo":         pais_codigo,
            # MIP = promedio acumulado (mismo escala que el dashboard)
            "score_total":     round(float(r.score_acumulado or 0), 2),
            "score_ciclo_actual": round(sc_actual, 2),
            "num_ciclos":      r.num_ciclos,
            "elegible":        bool(r.elegible_max),
            "tipo_ranking":    tipo.upper(),
            "ciclo_efectivo":  ciclo_efectivo,
            **ciclo_scores,
        })

    # GERENTE_DISTRITO: ve el ranking completo (posiciones globales de empresa) pero solo
    # identifica por nombre a su equipo; el resto queda como "Otro distrito".
    from app.core.scope_gd import anonimizar_para_gd
    anonimizar_para_gd(items, current_user, db)

    return {
        "items":           items,
        "total":           total,
        "page":            params.page,
        "size":            params.size,
        "pages":           max(1, -(-total // params.size)),
        "ciclo_efectivo":  ciclo_efectivo,
        "ciclos_numeros":  [c.numero for c in todos_ciclos],
    }


def _acumulado_por_pais(db: Session, pais_codigo: str, tipo: str = "MENSUAL") -> dict:
    """rm_id -> (score_acumulado, elegible) para un país, con la MISMA lógica de
    acumulado que usa GET /ranking (ciclo más reciente del país + promedio de los
    ciclos 1..N del mismo año, ver `_ultimo_ciclo`/`_ciclos_acumulados`)."""
    ciclo_efectivo = _ultimo_ciclo(db, pais_codigo, tipo)
    if not ciclo_efectivo:
        return {}
    ciclo_ids, _ = _ciclos_acumulados(db, ciclo_efectivo)
    rows = (
        db.query(
            RankingRM.rm_id,
            func.avg(RankingRM.score_total).label("score_acumulado"),
            func.max(RankingRM.elegible.cast(Integer)).label("elegible_max"),
        )
        .filter(
            RankingRM.tipo_ranking == tipo.upper(),
            RankingRM.ciclo_id.in_(ciclo_ids),
            RankingRM.pais_codigo == pais_codigo,
        )
        .group_by(RankingRM.rm_id)
        .all()
    )
    return {r.rm_id: (float(r.score_acumulado or 0), bool(r.elegible_max)) for r in rows}


@router.get("/regional", response_model=List[dict])
def get_ranking_regional(
    top: int = 10,
    db: Session = Depends(get_db),
    current_user=ReadRanking,
):
    """
    Ranking Regional: NO recalcula ningún score. Toma el resultado acumulado
    (YTD) que ya calcula correctamente GET /ranking para cada representante
    en su propio país (misma fórmula, mismos datos) y solo ordena/posiciona a
    todos los representantes elegibles de todos los países juntos por ese
    mismo número — es una vista en vivo, no requiere "generar" nada.
    """
    paises = [p for (p,) in db.query(Pais.codigo).filter(Pais.activo == True).all()]  # noqa: E712
    combinado: list = []
    for pais_codigo in paises:
        for rm_id, (score, elegible) in _acumulado_por_pais(db, pais_codigo).items():
            if elegible:
                combinado.append((rm_id, pais_codigo, score))

    combinado.sort(key=lambda x: x[2], reverse=True)
    combinado = combinado[:top]

    rm_ids = [c[0] for c in combinado]
    rms = (
        {r.id: r for r in db.query(RepresentanteMedico).filter(RepresentanteMedico.id.in_(rm_ids)).all()}
        if rm_ids else {}
    )
    lineas = {l.id: l.nombre for l in db.query(Linea).all()}
    gerentes = {g.id: g.nombre for g in db.query(Gerente).all()}
    nombres_pais = dict(db.query(Pais.codigo, Pais.nombre).all())

    resultado = []
    for pos, (rm_id, pais_codigo, score) in enumerate(combinado, start=1):
        rm = rms.get(rm_id)
        resultado.append({
            "posicion":       pos,
            "rm_id":          rm_id,
            "rm_codigo":      rm.codigo if rm else None,
            "rm_nombre":      rm.nombre if rm else f"RM #{rm_id}",
            "pais_nombre":    nombres_pais.get(pais_codigo, pais_codigo),
            "linea_nombre":   lineas.get(rm.linea_id, "—") if rm and rm.linea_id else "—",
            "gerente_nombre": gerentes.get(rm.gerente_id, "—") if rm and rm.gerente_id else "—",
            "score_total":    round(score, 2),
            "elegible":       True,
        })
    return resultado
