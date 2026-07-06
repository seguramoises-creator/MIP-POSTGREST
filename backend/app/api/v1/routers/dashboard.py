"""
SCGCPR — Router: Dashboards
GET /api/v1/dashboard/catalogos    — Catálogos para filtros (cualquier usuario autenticado)
GET /api/v1/dashboard/ejecutivo    — KPIs MIP completos (Presidencia)
GET /api/v1/dashboard/productividad — Operativo
GET /api/v1/dashboard/reconocimiento — Premios
GET /api/v1/dashboard/capacitacion  — Formación

REDISEÑO (jun-2026): las fuentes de cálculo cambiaron:
  - FACT_RendimientoComercial → FACT_ResultadoIndicador
  - FACT_Ranking → FACT_RankingRM  (score_total en escala 0-100)
  - FACT_Reconocimiento → FACT_ReconocimientoRM
  Los componentes IUP se calculan aquí desde FACT_ResultadoIndicador.

RETIRADO (jun-2026): GET /dashboard/comercial fue sustituido por
GET /cobertura-predictiva/resumen (app/api/v1/routers/cobertura_predictiva.py).
Las métricas de lag (ventas, EVO IR, cumplimiento de cuota) se reemplazaron
en el dashboard de GD por las métricas predictivas de cobertura médica y
ritmo de visitas (metodología 4DX).
"""
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Rol
from app.models.hechos import (
    RankingRM, ReconocimientoRM, CapacitacionFact,
    ResultadoIndicador
)
from app.models.dimensiones import (
    Indicador, RepresentanteMedico, Gerente, Ciclo, Linea, Pais
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# ── Catálogos para filtros del dashboard ─────────────────────────────────────

@router.get("/catalogos", response_model=dict, summary="Catálogos para filtros del dashboard")
def dashboard_catalogos(
    pais_codigo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Retorna listas de países, ciclos, líneas terapéuticas y gerentes
    para poblar los selectores del dashboard ejecutivo.
    Filtrar por pais_codigo reduce ciclos/líneas/gerentes al país seleccionado.
    """
    paises = db.query(Pais).filter(Pais.activo == True).order_by(Pais.nombre).all()

    # Los ciclos son por país — solo mostrar si se seleccionó un país
    ciclos = []
    if pais_codigo:
        ciclos = (
            db.query(Ciclo)
            .filter(Ciclo.activo == True, Ciclo.pais_codigo == pais_codigo)
            .order_by(Ciclo.anio.asc(), Ciclo.numero.asc())
            .all()
        )

    lineas_q = db.query(Linea).filter(Linea.activo == True)
    if pais_codigo:
        lineas_q = lineas_q.filter(Linea.pais_codigo == pais_codigo)
    lineas = lineas_q.order_by(Linea.nombre).all()

    gerentes_q = db.query(Gerente).filter(Gerente.activo == True)
    if pais_codigo:
        gerentes_q = gerentes_q.filter(Gerente.pais_codigo == pais_codigo)
    gerentes = gerentes_q.order_by(Gerente.nombre).all()

    return {
        "paises": [
            {"id": p.id, "codigo": p.codigo, "nombre": p.nombre}
            for p in paises
        ],
        "ciclos": [
            {
                "id": c.id,
                "nombre": c.nombre,
                "nombre_canonico": c.nombre_canonico,
                "anio": c.anio,
                "numero": c.numero,
            }
            for c in ciclos
        ],
        "lineas": [
            {"id": l.id, "codigo": l.codigo, "nombre": l.nombre}
            for l in lineas
        ],
        "gerentes": [
            {"id": g.id, "codigo": g.codigo, "nombre": g.nombre, "tipo": g.tipo}
            for g in gerentes
        ],
    }


# ── Dashboard Ejecutivo ───────────────────────────────────────────────────────

@router.get("/ejecutivo", response_model=dict, summary="Dashboard Ejecutivo — KPIs MIP completos")
def dashboard_ejecutivo(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    linea_id: Optional[int] = None,
    gerente_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(
        Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL, Rol.GERENTE_PRODUCTIVIDAD
    )),
):
    """
    Dashboard Ejecutivo completo:
    - Filtros: pais_codigo, ciclo_id, linea_id, gerente_id
    - KPIs de resumen del ciclo seleccionado (o el último con datos)
    - Indicadores MIP con cumplimiento, puntaje y delta vs ciclo anterior
    - Top 5 y Bottom 5 representantes
    - Top gerentes de distrito
    - Tendencia histórica por ciclo (todos los ciclos, sin filtro de ciclo_id)
    - Distribución del equipo (Excelente/Bueno/En Desarrollo/Crítico)
    - Componentes del score integral para gráfico radar
    """
    # ── Ciclo efectivo: usa el más reciente si no se especifica ─────────────
    ciclo_efectivo = ciclo_id
    if not ciclo_efectivo:
        ultimo = (
            db.query(func.max(RankingRM.ciclo_id))
            .filter(RankingRM.tipo_ranking == "MENSUAL")
            .filter(*([ RankingRM.pais_codigo == pais_codigo ] if pais_codigo else []))
            .scalar()
        )
        ciclo_efectivo = ultimo

    # ── Subconjunto de rm_ids si hay filtro de línea o gerente ───────────────
    rm_ids_filtro = None
    if linea_id or gerente_id:
        rm_q = db.query(RepresentanteMedico.id)
        if linea_id:
            rm_q = rm_q.filter(RepresentanteMedico.linea_id == linea_id)
        if gerente_id:
            rm_q = rm_q.filter(RepresentanteMedico.gerente_id == gerente_id)
        rm_ids_filtro = rm_q.subquery()

    def _filt_rank(q):
        q = q.filter(RankingRM.tipo_ranking == "MENSUAL")
        if pais_codigo:
            q = q.filter(RankingRM.pais_codigo == pais_codigo)
        if ciclo_efectivo:
            q = q.filter(RankingRM.ciclo_id == ciclo_efectivo)
        if linea_id:
            q = q.filter(RankingRM.linea_id == linea_id)
        if gerente_id:
            q = q.filter(RankingRM.gerente_id == gerente_id)
        return q

    def _filt_ri(q):
        if pais_codigo:
            q = q.filter(ResultadoIndicador.pais_codigo == pais_codigo)
        if ciclo_efectivo:
            q = q.filter(ResultadoIndicador.ciclo_id == ciclo_efectivo)
        if rm_ids_filtro is not None:
            q = q.filter(ResultadoIndicador.rm_id.in_(
                db.query(rm_ids_filtro.c.id)
            ))
        return q

    # ── Nombre del ciclo efectivo ────────────────────────────────────────────
    ciclo_nombre_actual = None
    if ciclo_efectivo:
        c_row = db.query(Ciclo.nombre).filter(Ciclo.id == ciclo_efectivo).first()
        if c_row:
            ciclo_nombre_actual = c_row.nombre

    # ── Ciclo anterior (para delta de KPIs) ─────────────────────────────────
    prev_ciclo_id = None
    prev_data: dict = {}
    if ciclo_efectivo:
        prev_row = (
            db.query(Ciclo.id)
            .join(RankingRM, RankingRM.ciclo_id == Ciclo.id)
            .filter(RankingRM.tipo_ranking == "MENSUAL")
            .filter(Ciclo.id < ciclo_efectivo)
            .filter(*([ RankingRM.pais_codigo == pais_codigo ] if pais_codigo else []))
            .group_by(Ciclo.id, Ciclo.anio, Ciclo.numero)
            .order_by(Ciclo.anio.desc(), Ciclo.numero.desc())
            .limit(1)
            .first()
        )
        if prev_row:
            prev_ciclo_id = prev_row.id
            prev_q = (
                db.query(
                    Indicador.codigo,
                    func.avg(ResultadoIndicador.resultado_porcentaje).label("prev_cumpl"),
                )
                .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
                .filter(ResultadoIndicador.activo == True)
                .filter(ResultadoIndicador.ciclo_id == prev_ciclo_id)
            )
            if pais_codigo:
                prev_q = prev_q.filter(ResultadoIndicador.pais_codigo == pais_codigo)
            prev_data = {
                r.codigo: float(r.prev_cumpl or 0)
                for r in prev_q.group_by(Indicador.codigo).all()
            }

    # ── 1. KPIs de resumen ───────────────────────────────────────────────────
    s = _filt_rank(db.query(
        func.avg(RankingRM.score_total).label("score_prom"),
        func.max(RankingRM.score_total).label("score_max"),
        func.min(RankingRM.score_total).label("score_min"),
        func.count(func.distinct(RankingRM.rm_id)).label("total_rms"),
        func.sum(case((RankingRM.score_total >= 90, 1), else_=0)).label("elegibles"),
    )).first()

    total_rms  = s.total_rms or 0
    elegibles  = int(s.elegibles or 0)
    score_prom = round(float(s.score_prom or 0), 2)
    score_max  = round(float(s.score_max or 0), 2)
    score_min  = round(float(s.score_min or 0), 2)

    # ── 2. Indicadores MIP con delta vs ciclo anterior ───────────────────────
    kpi_q = (
        _filt_ri(
            db.query(
                Indicador.codigo,
                Indicador.nombre,
                Indicador.modulo,
                Indicador.ponderacion_pct,
                func.avg(ResultadoIndicador.resultado_porcentaje).label("cumpl_prom"),
                func.avg(ResultadoIndicador.puntos_obtenidos).label("puntaje_prom"),
                func.count(func.distinct(ResultadoIndicador.rm_id)).label("total_rms_kpi"),
            )
            .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
            .filter(ResultadoIndicador.activo == True)
        )
        .group_by(
            Indicador.codigo, Indicador.nombre, Indicador.modulo,
            Indicador.ponderacion_pct,
        )
        .order_by(Indicador.codigo.asc())
    )
    kpis_indicadores = [
        {
            "codigo": r.codigo,
            "nombre": r.nombre,
            "modulo": r.modulo,
            "ponderacion_pct": r.ponderacion_pct,
            "cumplimiento_promedio_pct": round(float(r.cumpl_prom or 0), 2),
            "puntaje_promedio": round(float(r.puntaje_prom or 0), 2),
            "total_rms": r.total_rms_kpi,
            "delta_vs_anterior": round(
                float(r.cumpl_prom or 0) - prev_data.get(r.codigo, float(r.cumpl_prom or 0)),
                2
            ) if prev_ciclo_id else None,
        }
        for r in kpi_q.all()
    ]

    # ── 3. Top 5 y Bottom 5 RMs ──────────────────────────────────────────────
    def _query_rm_rank():
        return (
            _filt_rank(
                db.query(
                    RankingRM,
                    RepresentanteMedico.nombre.label("rm_nombre"),
                    Gerente.nombre.label("gerente_nombre"),
                    Linea.nombre.label("linea_nombre"),
                )
            )
            .join(RepresentanteMedico, RepresentanteMedico.id == RankingRM.rm_id)
            .outerjoin(Gerente, Gerente.id == RepresentanteMedico.gerente_id)
            .outerjoin(Linea, Linea.id == RepresentanteMedico.linea_id)
        )

    def _fmt_rm(r):
        return {
            "posicion": r.RankingRM.posicion_global,
            "rm_id": r.RankingRM.rm_id,
            "rm_nombre": r.rm_nombre,
            "linea_nombre": r.linea_nombre or "—",
            "gerente_nombre": r.gerente_nombre or "—",
            "score_total": round(float(r.RankingRM.score_total or 0), 2),
        }

    # Top y Bottom disjuntos por UMBRAL de desempeño (score 80):
    #   >=80 (verde >=90 / azul 80-90) -> solo Top, los mejores primero.
    #   <80  (naranja 60-80 / rojo <60) -> solo Bottom, los peores primero.
    # Al partir por 80 las listas son disjuntas por construcción: un RM está por
    # encima o por debajo del umbral, nunca en ambas. Cada lista se limita a 5.
    _ranked = _query_rm_rank().order_by(RankingRM.posicion_global.asc()).all()  # mejor→peor
    def _score(r):
        return float(r.RankingRM.score_total or 0)
    top_rows    = [r for r in _ranked if _score(r) >= 80][:5]            # buenos: mejores primero
    bottom_rows = [r for r in reversed(_ranked) if _score(r) < 80][:5]   # a mejorar: peores primero
    top5    = [_fmt_rm(r) for r in top_rows]
    bottom5 = [_fmt_rm(r) for r in reversed(bottom_rows)]

    # ── 4. Top Gerentes de Distrito ──────────────────────────────────────────
    top_gerentes = [
        {
            "gerente_id": r.gerente_id,
            "gerente_nombre": r.gerente_nombre,
            "score_promedio": round(float(r.score_prom_ger or 0), 2),
            "total_rms": r.total_rms_ger,
        }
        for r in (
            _filt_rank(
                db.query(
                    Gerente.id.label("gerente_id"),
                    Gerente.nombre.label("gerente_nombre"),
                    func.avg(RankingRM.score_total).label("score_prom_ger"),
                    func.count(func.distinct(RankingRM.rm_id)).label("total_rms_ger"),
                )
            )
            .join(RepresentanteMedico, RepresentanteMedico.id == RankingRM.rm_id)
            .join(Gerente, Gerente.id == RepresentanteMedico.gerente_id)
            .group_by(Gerente.id, Gerente.nombre)
            .order_by(func.avg(RankingRM.score_total).desc())
            .all()
        )
    ]

    # ── 5. Tendencia histórica (todos los ciclos, sin filtro ciclo_efectivo) ──
    # Nota: la tendencia siempre muestra todos los ciclos para el país/línea/gerente
    # seleccionado, independientemente del ciclo_efectivo.
    tend_filt = [RankingRM.tipo_ranking == "MENSUAL"]
    if pais_codigo:
        tend_filt.append(RankingRM.pais_codigo == pais_codigo)
    if linea_id:
        tend_filt.append(RankingRM.linea_id == linea_id)
    if gerente_id:
        tend_filt.append(RankingRM.gerente_id == gerente_id)

    tendencia = [
        {
            "ciclo_id":       r.ciclo_id,
            "ciclo_nombre":   r.ciclo_nombre,
            "ciclo_numero":   r.ciclo_numero,
            "ciclo_anio":     r.ciclo_anio,
            "score_promedio": round(float(r.score_prom_ciclo or 0), 2),
            "score_maximo":   round(float(r.score_max_ciclo  or 0), 2),
            "score_minimo":   round(float(r.score_min_ciclo  or 0), 2),
            "total_rms":      r.total_rms_ciclo or 0,
        }
        for r in (
            db.query(
                Ciclo.id.label("ciclo_id"),
                Ciclo.nombre.label("ciclo_nombre"),
                Ciclo.numero.label("ciclo_numero"),
                Ciclo.anio.label("ciclo_anio"),
                func.avg(RankingRM.score_total).label("score_prom_ciclo"),
                func.max(RankingRM.score_total).label("score_max_ciclo"),
                func.min(RankingRM.score_total).label("score_min_ciclo"),
                func.count(func.distinct(RankingRM.rm_id)).label("total_rms_ciclo"),
            )
            .join(Ciclo, Ciclo.id == RankingRM.ciclo_id)
            .filter(*tend_filt)
            .group_by(Ciclo.id, Ciclo.nombre, Ciclo.numero, Ciclo.anio)
            .order_by(Ciclo.anio.asc(), Ciclo.numero.asc())
            .all()
        )
    ]

    # ── 6. Distribución del equipo por categoría ─────────────────────────────
    dist = _filt_rank(db.query(
        func.sum(case((RankingRM.score_total >= 90, 1), else_=0)).label("excelente"),
        func.sum(case(((RankingRM.score_total >= 80) & (RankingRM.score_total < 90), 1), else_=0)).label("bueno"),
        func.sum(case(((RankingRM.score_total >= 60) & (RankingRM.score_total < 80), 1), else_=0)).label("en_desarrollo"),
        func.sum(case((RankingRM.score_total < 60, 1), else_=0)).label("critico"),
    )).first()

    distribucion = {
        "excelente":     int(dist.excelente or 0),
        "bueno":         int(dist.bueno or 0),
        "en_desarrollo": int(dist.en_desarrollo or 0),
        "critico":       int(dist.critico or 0),
    }

    # ── 7. Componentes del score integral promedio (radar) ───────────────────
    comp_rows = (
        _filt_ri(
            db.query(
                Indicador.modulo,
                func.avg(ResultadoIndicador.puntos_obtenidos).label("prom"),
            )
            .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
            .filter(ResultadoIndicador.activo == True, ResultadoIndicador.puntos_obtenidos.isnot(None))
        )
        .group_by(Indicador.modulo)
        .all()
    )
    comp_por_modulo = {r.modulo: float(r.prom or 0) for r in comp_rows}

    return {
        # Resumen ejecutivo del ciclo seleccionado
        "total_rms":       total_rms,
        "score_promedio":  score_prom,
        "score_maximo":    score_max,
        "score_minimo":    score_min,
        # Alias retrocompatibles
        "iup_promedio":    score_prom,
        "iup_maximo":      score_max,
        "iup_minimo":      score_min,
        "total_elegibles": elegibles,
        "pct_elegibles":   round(elegibles / total_rms * 100, 2) if total_rms else 0,

        # Ciclo efectivo usado
        "ciclo_efectivo":  ciclo_efectivo,
        "ciclo_nombre":    ciclo_nombre_actual,

        # KPIs de indicadores MIP con delta vs anterior
        "kpis_indicadores": kpis_indicadores,

        # Top / Bottom 5 RMs
        "top5":    top5,
        "bottom5": bottom5,

        # Gerentes
        "top_gerentes": top_gerentes,

        # Tendencia histórica (todos los ciclos)
        "tendencia": tendencia,

        # Distribución categorías
        "distribucion": distribucion,

        # Componentes del score integral (radar)
        "componentes_iup": {
            "productividad": round(comp_por_modulo.get("PRODUCTIVIDAD", comp_por_modulo.get("GESTION", 0)), 2),
            "comercial":     round(comp_por_modulo.get("COMERCIAL", comp_por_modulo.get("RESULTADOS", 0)), 2),
            "coaching":      round(comp_por_modulo.get("COACHING", 0), 2),
            "capacitacion":  round(comp_por_modulo.get("CAPACITACION", 0), 2),
            "consistencia":  0,
        },

        # Retrocompatibilidad
        "top_rms": [
            {"posicion": r["posicion"], "rm_id": r["rm_id"], "score_total": r["score_total"]}
            for r in top5
        ],

        "filtros": {
            "pais_codigo":   pais_codigo,
            "ciclo_id":  ciclo_efectivo,
            "linea_id":  linea_id,
            "gerente_id": gerente_id,
        },
    }


# ── Dashboard Productividad ──────────────────────────────────────────────────

@router.get("/productividad", response_model=dict, summary="Dashboard de Productividad")
def dashboard_productividad(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """KPIs de productividad: Cobertura F1, F2, Farmacias, Promedio Diario."""
    q = db.query(
        Indicador.codigo,
        Indicador.nombre,
        func.avg(ResultadoIndicador.resultado_porcentaje).label("cumplimiento_promedio"),
        func.avg(ResultadoIndicador.puntos_obtenidos).label("puntaje_promedio"),
        func.count(func.distinct(ResultadoIndicador.rm_id)).label("total_rms"),
    ).join(
        Indicador, Indicador.id == ResultadoIndicador.indicador_id
    ).filter(
        Indicador.modulo == "GESTION",
        ResultadoIndicador.activo == True,
    )

    if pais_codigo: q = q.filter(ResultadoIndicador.pais_codigo == pais_codigo)
    if ciclo_id: q = q.filter(ResultadoIndicador.ciclo_id == ciclo_id)

    rows = q.group_by(Indicador.codigo, Indicador.nombre).all()

    return {
        "kpis": [
            {
                "codigo": r.codigo, "nombre": r.nombre,
                "cumplimiento_promedio_pct": float(r.cumplimiento_promedio or 0),
                "puntaje_promedio": float(r.puntaje_promedio or 0),
                "total_rms": r.total_rms,
            }
            for r in rows
        ],
        "filtros": {"pais_codigo": pais_codigo, "ciclo_id": ciclo_id},
    }


# ── Dashboard Comercial: RETIRADO (jun-2026) ─────────────────────────────────
# GET /dashboard/comercial fue sustituido por GET /cobertura-predictiva/resumen
# (router app/api/v1/routers/cobertura_predictiva.py). Las métricas de lag
# (ventas, EVO IR, cumplimiento de cuota) se reemplazaron por las métricas
# predictivas de cobertura médica y ritmo de visitas (4DX).


# ── Dashboard Reconocimiento ─────────────────────────────────────────────────

@router.get("/reconocimiento", response_model=dict, summary="Dashboard de Reconocimiento")
def dashboard_reconocimiento(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Elegibles, premiados, certificados generados."""
    q_rank = db.query(
        func.count(func.distinct(RankingRM.rm_id)).label("total_rms"),
        func.sum(case((RankingRM.score_total >= 90, 1), else_=0)).label("elegibles"),
    ).filter(RankingRM.tipo_ranking == "MENSUAL")
    if pais_codigo: q_rank = q_rank.filter(RankingRM.pais_codigo == pais_codigo)
    if ciclo_id: q_rank = q_rank.filter(RankingRM.ciclo_id == ciclo_id)
    rank_data = q_rank.first()

    q_rec = db.query(
        func.count(ReconocimientoRM.id).label("total_reconocimientos"),
        func.sum(case((ReconocimientoRM.certificado_generado == True, 1), else_=0)).label("certificados"),
    )
    if pais_codigo: q_rec = q_rec.filter(ReconocimientoRM.pais_codigo == pais_codigo)
    if ciclo_id: q_rec = q_rec.filter(ReconocimientoRM.ciclo_id == ciclo_id)
    rec_data = q_rec.first()

    total = rank_data.total_rms or 1
    elegibles = int(rank_data.elegibles or 0)

    return {
        "total_rms": rank_data.total_rms or 0,
        "rms_elegibles": elegibles,
        "total_elegibles": elegibles,
        "pct_elegibles": round(elegibles / total * 100, 2),
        "total_reconocimientos": rec_data.total_reconocimientos or 0,
        "certificados_generados": int(rec_data.certificados or 0),
        "filtros": {"pais_codigo": pais_codigo, "ciclo_id": ciclo_id},
    }


# ── Dashboard Capacitación ───────────────────────────────────────────────────

@router.get("/capacitacion", response_model=dict, summary="Dashboard de Capacitación")
def dashboard_capacitacion(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    q = db.query(
        func.count(CapacitacionFact.id).label("total"),
        func.sum(CapacitacionFact.horas_completadas).label("horas_total"),
        func.avg(CapacitacionFact.calificacion).label("calificacion_promedio"),
        func.sum(case((CapacitacionFact.aprobado == True, 1), else_=0)).label("aprobados"),
        func.sum(case((CapacitacionFact.asistio == True, 1), else_=0)).label("con_asistencia"),
    )
    if pais_codigo: q = q.filter(CapacitacionFact.pais_codigo == pais_codigo)
    if ciclo_id: q = q.filter(CapacitacionFact.ciclo_id == ciclo_id)
    r = q.first()

    total = r.total or 1
    return {
        "total_registros": r.total or 0,
        "horas_formacion_total": float(r.horas_total or 0),
        "calificacion_promedio": float(r.calificacion_promedio or 0),
        "total_aprobados": r.aprobados or 0,
        "tasa_aprobacion_pct": round((r.aprobados or 0) / total * 100, 2),
        "tasa_asistencia_pct": round((r.con_asistencia or 0) / total * 100, 2),
        "filtros": {"pais_codigo": pais_codigo, "ciclo_id": ciclo_id},
    }
