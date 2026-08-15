"""
SCGCPR — Router: Productividad
FIX W-03: Todos los endpoints de lista usan PaginationParams.
GET /api/v1/productividad              — KPIs generales
GET /api/v1/productividad/rm/{rm_id}  — KPIs de un RM
GET /api/v1/productividad/pais/{id}   — KPIs por país
GET /api/v1/productividad/resumen     — Resumen consolidado

REDISEÑO (jun-2026): la fuente pasó de FACT_RendimientoComercial
(valor_real/porcentaje_cumplimiento/puntaje) a FACT_ResultadoIndicador
(resultado_real/resultado_porcentaje/puntos_obtenidos). Las claves de las
respuestas JSON se conservan (valor_real, cumplimiento_pct, puntaje, etc.)
para no romper al frontend — solo cambia el origen ORM de los datos.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_active_user, require_roles
from app.core.authz.deps import require
from app.core.authz.constantes import Accion, Recurso
from app.core.authz.paises import PaisPermitido, exigir_pais
from app.core.authz import scope
from app.core.pagination import PaginationParams, paginate_list
from app.models.usuario import Rol
from app.models.hechos import ResultadoIndicador
from app.models.dimensiones import RepresentanteMedico, Indicador, Ciclo, Linea, Gerente
from app.schemas.schemas import KPIProductividadResponse

router = APIRouter(prefix="/productividad", tags=["Productividad"])
AnyAuth = Depends(get_current_active_user)
# RBAC Fase 2: guard por matriz. productividad.comercial DENIEGA a GERENTE_MEDICO (firewall
# Médico-Comercial) y a cualquiera sin lectura. El detalle por rol (RM=propio, GD=agregado de
# empresa con nombres solo de su equipo vía scope_gd — regla del cliente) se mantiene en el cuerpo.
ReadProductividad = Depends(require(Accion.READ, Recurso.PRODUCTIVIDAD_COMERCIAL))


@router.get("", response_model=dict, summary="KPIs generales de productividad (paginado)")
def get_productividad(
    pais_codigo: Optional[str] = Depends(PaisPermitido),
    ciclo_id: Optional[int] = Query(None),
    linea_id: Optional[int] = Query(None),
    params: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=ReadProductividad,
):
    """
    Retorna KPIs de productividad agregados.
    Filtra por rol automáticamente (RM solo ve su propia data).
    """
    q = db.query(
        RepresentanteMedico.id.label("rm_id"),
        RepresentanteMedico.codigo.label("rm_codigo"),
        RepresentanteMedico.nombre.label("rm_nombre"),
        RepresentanteMedico.pais_codigo.label("pais_codigo"),
        Linea.nombre.label("linea_nombre"),
        Gerente.nombre.label("gerente_nombre"),
        Indicador.codigo.label("indicador_codigo"),
        ResultadoIndicador.ciclo_id.label("ciclo_id"),
        func.sum(ResultadoIndicador.resultado_real).label("valor_real"),
        func.avg(ResultadoIndicador.resultado_porcentaje).label("cumplimiento_pct"),
        func.sum(ResultadoIndicador.puntos_obtenidos).label("puntaje"),
    ).join(
        RepresentanteMedico, RepresentanteMedico.id == ResultadoIndicador.rm_id
    ).join(
        Indicador, Indicador.id == ResultadoIndicador.indicador_id
    ).outerjoin(
        Linea, Linea.id == ResultadoIndicador.linea_id
    ).outerjoin(
        Gerente, Gerente.id == RepresentanteMedico.gerente_id
    ).filter(
        ResultadoIndicador.activo == True,
    )

    if pais_codigo:
        q = q.filter(ResultadoIndicador.pais_codigo == pais_codigo)
    # Hallazgo Critical de revisión (ago-2026): `pais_codigo` es opcional y el filtro de
    # arriba solo actúa si el cliente lo manda. Sin él, esta consulta no tenía NINGÚN otro
    # límite de país (a diferencia de `ranking.py`, aquí no hay `ciclo_id` de por medio: el
    # hueco es más simple — basta con omitir el parámetro). `permitidos` es el piso real:
    # se aplica SIEMPRE que el usuario tenga países asignados, lo haya pedido o no.
    permitidos = scope.paises_visibles(db, current_user)
    if permitidos is not None:
        q = q.filter(ResultadoIndicador.pais_codigo.in_(permitidos))
    if ciclo_id:
        q = q.filter(ResultadoIndicador.ciclo_id == ciclo_id)
    if linea_id:
        q = q.filter(ResultadoIndicador.linea_id == linea_id)

    # Filtro por rol: RM solo ve su propia información
    # FAIL-CLOSED: antes era `if rol == RM and current_user.rm_id`, así que un representante
    # SIN rm_id (usuario mal creado) se saltaba el filtro y veía a TODOS los RMs. Ahora sin
    # rm_id se deniega — mismo criterio que Cobertura Predictiva y Categorización.
    if current_user.rol == Rol.REPRESENTANTE_MEDICO:
        if not current_user.rm_id:
            raise HTTPException(403, "Tu usuario no está vinculado a un representante médico.")
        q = q.filter(ResultadoIndicador.rm_id == current_user.rm_id)

    results = q.group_by(
        RepresentanteMedico.id,
        RepresentanteMedico.codigo,
        RepresentanteMedico.nombre,
        RepresentanteMedico.pais_codigo,
        Linea.nombre,
        Gerente.nombre,
        Indicador.codigo,
        ResultadoIndicador.ciclo_id,
    ).all()

    all_items = [
        {
            "rm_id": r.rm_id,
            "rm_codigo": r.rm_codigo,
            "rm_nombre": r.rm_nombre,
            "pais_codigo": r.pais_codigo,
            "linea_nombre": r.linea_nombre or "—",
            "gerente_nombre": r.gerente_nombre or "—",
            "indicador_codigo": r.indicador_codigo,
            "ciclo_id": r.ciclo_id,
            "valor_real": float(r.valor_real or 0),
            "cumplimiento_pct": float(r.cumplimiento_pct or 0),
            "puntaje": float(r.puntaje or 0),
        }
        for r in results
    ]
    # GERENTE_DISTRITO: agregado de empresa, pero solo identifica por nombre a su equipo.
    from app.core.scope_gd import anonimizar_para_gd
    anonimizar_para_gd(all_items, current_user, db)
    return paginate_list(all_items, params)  # FIX W-03


@router.get("/rm/{rm_id}", response_model=dict, summary="KPIs de un RM específico")
def get_productividad_rm(
    rm_id: int,
    ciclo_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user=ReadProductividad,
):
    """KPIs completos de productividad para un RM: F1, F2, Farmacias, Promedio Diario."""
    # RMs solo pueden ver su propia data
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id != rm_id:
        from fastapi import HTTPException
        raise HTTPException(403, "No tiene permiso para ver datos de otro RM")

    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == rm_id).first()
    if not rm:
        from fastapi import HTTPException
        raise HTTPException(404, "RM no encontrado")

    q = db.query(
        Indicador.codigo,
        Indicador.nombre,
        func.sum(ResultadoIndicador.resultado_real).label("valor"),
        func.avg(ResultadoIndicador.resultado_porcentaje).label("cumplimiento"),
        func.sum(ResultadoIndicador.puntos_obtenidos).label("puntaje"),
    ).join(
        Indicador, Indicador.id == ResultadoIndicador.indicador_id
    ).filter(
        ResultadoIndicador.rm_id == rm_id,
        Indicador.modulo == "GESTION",
        ResultadoIndicador.activo == True,
    )

    if ciclo_id:
        q = q.filter(ResultadoIndicador.ciclo_id == ciclo_id)

    rows = q.group_by(Indicador.codigo, Indicador.nombre).all()

    kpis = {r.codigo: {"nombre": r.nombre, "valor": float(r.valor or 0),
                       "cumplimiento_pct": float(r.cumplimiento or 0),
                       "puntaje": float(r.puntaje or 0)} for r in rows}

    return {
        "rm_id": rm_id,
        "rm_codigo": rm.codigo,
        "rm_nombre": rm.nombre,
        "ciclo_id": ciclo_id,
        "kpis": kpis,
        "puntaje_total_productividad": sum(v["puntaje"] for v in kpis.values()),
    }


# Mínimo de RMs con datos para poder mostrar el promedio de la línea. Con 2, el promedio
# revelaría al otro exactamente (promedio×2 − el mío); con 3+ solo se obtiene la suma de los
# demás, nunca un dato individual. Con 1, el "promedio de la línea" sería él mismo.
MIN_RMS_LINEA = 3


@router.get("/mi-linea", response_model=dict, summary="Mi productividad vs. el promedio de mi línea")
def get_mi_linea(ciclo_id: Optional[int] = Query(None), db: Session = Depends(get_db),
                 current_user=AnyAuth):
    """Lo del representante + el PROMEDIO de su línea, para que sepa si va bien o mal.

    Nunca expone a un colega: de la línea solo salen agregados (promedio y nº de RMs), jamás
    filas individuales. Y el promedio se oculta si la línea tiene menos de `MIN_RMS_LINEA`
    representantes con datos, porque con 2 el promedio permite despejar al otro.
    """
    if current_user.rol != Rol.REPRESENTANTE_MEDICO:
        raise HTTPException(403, "Esta vista es la de un representante médico.")
    if not current_user.rm_id:
        raise HTTPException(403, "Tu usuario no está vinculado a un representante médico.")

    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == current_user.rm_id).first()
    if not rm:
        raise HTTPException(404, "Representante no encontrado.")
    linea_nombre = (db.query(Linea.nombre).filter(Linea.id == rm.linea_id).scalar()
                    if rm.linea_id else None)

    base = (db.query(ResultadoIndicador)
            .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
            .filter(Indicador.modulo == "GESTION", ResultadoIndicador.activo == True))  # noqa: E712
    if ciclo_id:
        base = base.filter(ResultadoIndicador.ciclo_id == ciclo_id)

    def _agg(q):
        r = q.with_entities(
            func.avg(ResultadoIndicador.resultado_porcentaje),
            func.sum(ResultadoIndicador.puntos_obtenidos),
            func.count(func.distinct(ResultadoIndicador.rm_id)),
        ).first()
        return (float(r[0] or 0), float(r[1] or 0), int(r[2] or 0))

    mi_pct, mis_puntos, _ = _agg(base.filter(ResultadoIndicador.rm_id == current_user.rm_id))

    linea = None
    motivo = None
    if not rm.linea_id:
        motivo = "Tu representante no tiene una línea asignada."
    else:
        q_linea = base.join(RepresentanteMedico, RepresentanteMedico.id == ResultadoIndicador.rm_id) \
                      .filter(RepresentanteMedico.linea_id == rm.linea_id)
        l_pct, l_puntos, l_rms = _agg(q_linea)
        if l_rms < MIN_RMS_LINEA:
            motivo = (f"Tu línea tiene {l_rms} representante(s) con datos: no se muestra el "
                      f"promedio porque permitiría deducir resultados individuales.")
        else:
            linea = {"nombre": linea_nombre, "rms": l_rms,
                     "cumplimiento_pct": round(l_pct, 1),
                     "puntos_promedio": round(l_puntos / l_rms, 1)}

    # Sus indicadores, en la misma respuesta: la vista los necesita siempre y así no hay que
    # exponer su rm_id al frontend solo para pedir el detalle por separado.
    filas = (base.filter(ResultadoIndicador.rm_id == current_user.rm_id)
             .with_entities(
                 Indicador.codigo, Indicador.nombre,
                 func.sum(ResultadoIndicador.resultado_real).label("valor"),
                 func.avg(ResultadoIndicador.resultado_porcentaje).label("cumplimiento"),
                 func.sum(ResultadoIndicador.puntos_obtenidos).label("puntaje"))
             .group_by(Indicador.codigo, Indicador.nombre)
             .order_by(Indicador.codigo).all())

    return {
        "rm": {"nombre": rm.nombre, "codigo": rm.codigo, "linea": linea_nombre,
               "cumplimiento_pct": round(mi_pct, 1), "puntos": round(mis_puntos, 1),
               "sin_datos": not filas},
        "linea": linea,
        "linea_oculta_motivo": motivo,
        "indicadores": [{"codigo": f.codigo, "nombre": f.nombre,
                         "valor": float(f.valor or 0),
                         "cumplimiento_pct": round(float(f.cumplimiento or 0), 1),
                         "puntaje": round(float(f.puntaje or 0), 1)} for f in filas],
        "ciclo_id": ciclo_id,
    }


@router.get("/pais/{pais_codigo}", response_model=List[dict], summary="Productividad por país")
def get_productividad_pais(
    pais_codigo: str,
    ciclo_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user=ReadProductividad,
):
    """KPIs de productividad consolidados por país — todos los RMs."""
    # `pais_codigo` viene por la URL (path param), no por querystring: no puede usar la
    # dependency `PaisPermitido` (lee de `Query`), así que se valida a mano con el mismo guard.
    exigir_pais(db, current_user, pais_codigo)
    q = db.query(
        RepresentanteMedico.id.label("rm_id"),
        RepresentanteMedico.nombre.label("rm_nombre"),
        func.avg(ResultadoIndicador.resultado_porcentaje).label("cumplimiento_promedio"),
        func.sum(ResultadoIndicador.puntos_obtenidos).label("puntaje_total"),
    ).join(
        RepresentanteMedico, RepresentanteMedico.id == ResultadoIndicador.rm_id
    ).join(
        Indicador, Indicador.id == ResultadoIndicador.indicador_id
    ).filter(
        ResultadoIndicador.pais_codigo == pais_codigo,
        Indicador.modulo == "GESTION",
        ResultadoIndicador.activo == True,
    )
    if ciclo_id:
        q = q.filter(ResultadoIndicador.ciclo_id == ciclo_id)

    rows = q.group_by(RepresentanteMedico.id, RepresentanteMedico.nombre).all()

    items = [
        {
            "rm_id": r.rm_id,
            "rm_nombre": r.rm_nombre,
            "cumplimiento_promedio_pct": float(r.cumplimiento_promedio or 0),
            "puntaje_total": float(r.puntaje_total or 0),
        }
        for r in rows
    ]
    # GD: agregado de empresa, nombres solo de su equipo (ver scope_gd).
    from app.core.scope_gd import anonimizar_para_gd
    return anonimizar_para_gd(items, current_user, db)


@router.get("/resumen", response_model=dict, summary="Resumen ejecutivo de productividad")
def get_resumen_productividad(
    pais_codigo: Optional[str] = Depends(PaisPermitido),
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=ReadProductividad,
):
    """Resumen estadístico de productividad para dashboards ejecutivos."""
    q = db.query(
        func.count(func.distinct(ResultadoIndicador.rm_id)).label("total_rms"),
        func.avg(ResultadoIndicador.resultado_porcentaje).label("cumplimiento_promedio"),
        func.avg(ResultadoIndicador.puntos_obtenidos).label("puntaje_promedio"),
        func.max(ResultadoIndicador.puntos_obtenidos).label("puntaje_max"),
        func.min(ResultadoIndicador.puntos_obtenidos).label("puntaje_min"),
    ).join(
        Indicador, Indicador.id == ResultadoIndicador.indicador_id
    ).filter(
        Indicador.modulo == "GESTION",
        ResultadoIndicador.activo == True,
    )

    if pais_codigo:
        q = q.filter(ResultadoIndicador.pais_codigo == pais_codigo)
    # Mismo hallazgo Critical que `get_productividad`: floor de país siempre aplicado.
    permitidos = scope.paises_visibles(db, current_user)
    if permitidos is not None:
        q = q.filter(ResultadoIndicador.pais_codigo.in_(permitidos))
    if ciclo_id:
        q = q.filter(ResultadoIndicador.ciclo_id == ciclo_id)

    r = q.first()
    return {
        "total_rms": r.total_rms or 0,
        "cumplimiento_promedio_pct": float(r.cumplimiento_promedio or 0),
        "puntaje_promedio": float(r.puntaje_promedio or 0),
        "puntaje_max": float(r.puntaje_max or 0),
        "puntaje_min": float(r.puntaje_min or 0),
    }
