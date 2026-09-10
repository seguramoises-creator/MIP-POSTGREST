"""
Monitor del día — qué está haciendo la fuerza de ventas hoy.

Responde a una pregunta operativa, no analítica: *a esta hora, ¿quién ha
registrado actividad y cómo va contra lo que tenía agendado?* Por eso mira el
DÍA y la SEMANA en curso, no el ciclo cerrado.

EL AVANCE SE MIDE CONTRA LA SEMANA, NO CONTRA UN OBJETIVO DIARIO INVENTADO.
`Visita.PlaneacionCiclo` guarda `semana` (1-4) y un `dia_semana` OPCIONAL. Si se
repartiera la semana entre sus días hábiles saldría un objetivo diario que nadie
fijó, y el lunes y el viernes pesarían igual aunque el trabajo no se reparta así.
El acumulado semanal compara contra algo que el sistema sí sabe: lo planeado
para esta semana frente a lo ejecutado en ella hasta hoy.

Cuando la planeación SÍ trae `dia_semana`, se añade además el objetivo del día
—ahí el dato existe y no hay que derivar nada—. Es información extra, nunca el
sustento del avance: si faltara en la mitad de las filas, el porcentaje del día
mediría la calidad de la captura y no el trabajo del representante.

SIN PLANEACIÓN NO SE INVENTA UN CERO. `avance_calculable=False` distingue «no hay
agenda contra la que medir» de «la agenda se cumplió al 0%». Un 0% en rojo sobre
un equipo que no tenía nada planeado es una acusación falsa.

EL DÍA ES EL DEL PAÍS. Las columnas `fecha_hora` guardan UTC; el día contra el que
se pregunta es el del calendario del representante. Componer la ventana con
`datetime.combine(f, time.min)` mezclaba las dos escalas: recortaba el día por las
8 de la noche —medianoche UTC en RD— y ademas enseñaba `ultima_actividad` cuatro
horas corrida. Todo lo que aquí acota un día pasa por `ventana_dia_local`.
"""
from __future__ import annotations

from datetime import date, timedelta, timezone

from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from app.core.tiempo import ventana_dia_local, zona_horaria

from app.models.coaching_more_models import CoachingSesion
from app.models.dimensiones import Ciclo, Gerente, Linea, RepresentanteMedico
from app.models.visita import FactVisitaFarmacia, PlaneacionCiclo, VisitaRegistro
from app.services.visita_top_service import fecha_planeada

DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


def _ciclo_de(db: Session, pais_codigo: str, f: date) -> Ciclo | None:
    """El ciclo que CONTIENE la fecha; si ninguno la contiene, el abierto.

    El respaldo importa: un ciclo vencido —el caso real más frecuente— deja
    fechas recientes fuera de todo rango, y sin él la pantalla saldría vacía
    justo cuando hace falta mirarla.
    """
    q = db.query(Ciclo).filter(Ciclo.pais_codigo == pais_codigo)
    dentro = q.filter(Ciclo.fecha_inicio <= f, Ciclo.fecha_fin >= f).first()
    if dentro:
        return dentro
    return (q.filter(Ciclo.cerrado.is_(False))
             .order_by(Ciclo.anio.desc(), Ciclo.numero.desc()).first())


def _semana_de(ciclo: Ciclo, f: date) -> int:
    """Número de semana (1-4) del ciclo en el que cae `f`.

    Se cuenta por semanas de calendario desde el lunes que contiene el inicio,
    igual que `fecha_planeada` — usar otro criterio aquí haría que el avance
    comparara contra la semana equivocada.
    """
    lunes_1 = ciclo.fecha_inicio - timedelta(days=ciclo.fecha_inicio.weekday())
    return max(1, ((f - lunes_1).days // 7) + 1)


def _rango_semana(ciclo: Ciclo, semana: int) -> tuple[date, date]:
    lunes_1 = ciclo.fecha_inicio - timedelta(days=ciclo.fecha_inicio.weekday())
    ini = lunes_1 + timedelta(weeks=semana - 1)
    return ini, ini + timedelta(days=6)


def _pct(hecho: int, meta: int) -> float | None:
    """None cuando no hay meta: ver la nota de módulo sobre el cero falso."""
    if meta <= 0:
        return None
    return round(hecho * 100.0 / meta, 1)


def resumen_dia(db: Session, pais_codigo: str, f: date,
                gerente_id: int | None = None,
                linea_id: int | None = None,
                rm_ids: list[int] | None = None) -> dict:
    """Actividad del día por representante, más el avance de la semana.

    `rm_ids` lo impone el llamador cuando el rol obliga a un alcance (un VM ve
    solo lo suyo, un GD su equipo): se aplica ADEMÁS de los filtros que elija el
    usuario, nunca en su lugar.
    """
    ciclo = _ciclo_de(db, pais_codigo, f)
    # Rango semiabierto en la escala en que están guardadas las columnas (UTC), pero
    # recortando el día LOCAL del país.
    _, desde, fin = ventana_dia_local(db, pais_codigo, f)

    rms_q = (db.query(RepresentanteMedico)
             .filter(RepresentanteMedico.pais_codigo == pais_codigo,
                     RepresentanteMedico.activo.is_(True)))
    if gerente_id:
        rms_q = rms_q.filter(RepresentanteMedico.gerente_id == gerente_id)
    if linea_id:
        rms_q = rms_q.filter(RepresentanteMedico.linea_id == linea_id)
    if rm_ids is not None:
        rms_q = rms_q.filter(RepresentanteMedico.id.in_(rm_ids or [-1]))
    rms = rms_q.order_by(RepresentanteMedico.codigo).all()
    ids = [r.id for r in rms]
    if not ids:
        return {"fecha": f.isoformat(), "ciclo": None, "totales": _totales_vacios(),
                "semana": {"calculable": False}, "representantes": []}

    nombres_ger = {g.id: g.nombre for g in db.query(Gerente).filter(
        Gerente.id.in_([r.gerente_id for r in rms if r.gerente_id])).all()}
    nombres_lin = {l.id: l.nombre for l in db.query(Linea).filter(
        Linea.id.in_([r.linea_id for r in rms if r.linea_id])).all()}

    # ── Actividad del día ──────────────────────────────────────────────────
    # `ejecutada` filtra las que se registraron como NO realizadas (con causa):
    # cuentan para la bitácora, no para «lo hecho hoy».
    med = (db.query(VisitaRegistro.vm_id, VisitaRegistro.tipo_visita,
                    func.count().label("n"),
                    func.sum(func.cast(VisitaRegistro.acompanado, Integer)).label("gd"),
                    func.max(VisitaRegistro.fecha_hora).label("ult"))
           .filter(VisitaRegistro.vm_id.in_(ids),
                   VisitaRegistro.ejecutada.is_(True),
                   VisitaRegistro.fecha_hora >= desde, VisitaRegistro.fecha_hora < fin)
           .group_by(VisitaRegistro.vm_id, VisitaRegistro.tipo_visita).all())

    far = (db.query(FactVisitaFarmacia.vm_id, func.count().label("n"),
                    func.max(FactVisitaFarmacia.fecha_hora).label("ult"))
           .filter(FactVisitaFarmacia.vm_id.in_(ids),
                   FactVisitaFarmacia.ejecutada.is_(True),
                   FactVisitaFarmacia.fecha_hora >= desde, FactVisitaFarmacia.fecha_hora < fin)
           .group_by(FactVisitaFarmacia.vm_id).all())

    more = dict(db.query(CoachingSesion.rm_id, func.count())
                .filter(CoachingSesion.rm_id.in_(ids),
                        CoachingSesion.fecha_coaching == f)
                .group_by(CoachingSesion.rm_id).all())

    por_rm: dict[int, dict] = {i: {"v": 0, "r": 0, "farmacias": 0, "con_gd": 0,
                                  "more": 0, "ultima": None} for i in ids}
    for vm_id, tipo, n, gd, ult in med:
        d = por_rm[vm_id]
        d["r" if (tipo or "V").upper() == "R" else "v"] += n
        d["con_gd"] += int(gd or 0)
        d["ultima"] = max(d["ultima"], ult) if d["ultima"] else ult
    for vm_id, n, ult in far:
        d = por_rm[vm_id]
        d["farmacias"] += n
        d["ultima"] = max(d["ultima"], ult) if d["ultima"] else ult
    for vm_id, n in more.items():
        por_rm[vm_id]["more"] = n

    # ── Avance de la semana (y del día, si la planeación trae día) ─────────
    plan_sem: dict[int, int] = {}
    plan_dia: dict[int, int] = {}
    hecho_sem: dict[int, int] = {}
    semana = None
    if ciclo:
        semana = _semana_de(ciclo, f)
        ini_sem, _fin_sem = _rango_semana(ciclo, semana)
        # También el arranque de la semana es medianoche LOCAL, no medianoche UTC.
        _, _ini_utc, _ = ventana_dia_local(db, pais_codigo, ini_sem)
        for p in (db.query(PlaneacionCiclo)
                  .filter(PlaneacionCiclo.vm_id.in_(ids),
                          PlaneacionCiclo.ciclo_id == ciclo.id,
                          PlaneacionCiclo.semana == semana).all()):
            plan_sem[p.vm_id] = plan_sem.get(p.vm_id, 0) + 1
            if fecha_planeada(ciclo, p.semana, p.dia_semana) == f:
                plan_dia[p.vm_id] = plan_dia.get(p.vm_id, 0) + 1
        # Ejecutado en la semana HASTA HOY, no la semana entera: comparar contra
        # el futuro haría que el lunes todo el equipo pareciera atrasado.
        hecho_sem = dict(db.query(VisitaRegistro.vm_id, func.count())
                         .filter(VisitaRegistro.vm_id.in_(ids),
                                 VisitaRegistro.ejecutada.is_(True),
                                 VisitaRegistro.fecha_hora >= _ini_utc,
                                 VisitaRegistro.fecha_hora < fin)
                         .group_by(VisitaRegistro.vm_id).all())

    _UTC, _tz = timezone.utc, zona_horaria(db, pais_codigo)
    filas = []
    for r in rms:
        d = por_rm[r.id]
        ps, pd = plan_sem.get(r.id, 0), plan_dia.get(r.id, 0)
        hs = hecho_sem.get(r.id, 0)
        filas.append({
            "rm_id": r.id, "codigo": r.codigo, "nombre": r.nombre,
            "linea": nombres_lin.get(r.linea_id), "gerente": nombres_ger.get(r.gerente_id),
            "v": d["v"], "r": d["r"], "farmacias": d["farmacias"],
            "con_gd": d["con_gd"], "more": d["more"],
            # La hora que el gerente reconoce es la del reloj de su representante:
            # `fecha_hora` viene en UTC y sin traducir salía 4 horas adelantada.
            "ultima_actividad": (d["ultima"].replace(tzinfo=_UTC).astimezone(_tz).strftime("%H:%M")
                                 if d["ultima"] else None),
            "semana": {"planeadas": ps, "ejecutadas": hs, "avance_pct": _pct(hs, ps)},
            "dia": {"planeadas": pd, "ejecutadas": d["v"] + d["r"],
                    "avance_pct": _pct(d["v"] + d["r"], pd)},
        })

    total_ps, total_hs = sum(plan_sem.values()), sum(hecho_sem.values())
    return {
        "fecha": f.isoformat(),
        "ciclo": ({"id": ciclo.id, "nombre": ciclo.nombre,
                   "vencido": bool(ciclo.fecha_fin and ciclo.fecha_fin < f),
                   "cerrado": ciclo.cerrado, "semana": semana} if ciclo else None),
        "totales": {
            "medicas": sum(x["v"] + x["r"] for x in por_rm.values()),
            "farmacias": sum(x["farmacias"] for x in por_rm.values()),
            "visitas": sum(x["v"] + x["r"] + x["farmacias"] for x in por_rm.values()),
            "rms_con_actividad": sum(1 for x in por_rm.values()
                                     if x["v"] + x["r"] + x["farmacias"] > 0),
            "rms_total": len(ids),
            "acompanadas_gd": sum(x["con_gd"] for x in por_rm.values()),
            "hojas_more": sum(x["more"] for x in por_rm.values()),
        },
        "semana": {"numero": semana, "planeadas": total_ps, "ejecutadas": total_hs,
                   "avance_pct": _pct(total_hs, total_ps),
                   "calculable": total_ps > 0},
        "representantes": filas,
    }


def _totales_vacios() -> dict:
    return {"medicas": 0, "farmacias": 0, "visitas": 0, "rms_con_actividad": 0,
            "rms_total": 0, "acompanadas_gd": 0, "hojas_more": 0}
