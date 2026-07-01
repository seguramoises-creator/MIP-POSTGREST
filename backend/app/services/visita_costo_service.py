"""Costo & ROI del Módulo de Visita (Parte 8 del spec).

Cruza el costo de operar las visitas (costo por contacto + costo por muestra +
costo fijo del ciclo) contra los ingresos (FACT_Ventas) para obtener costo por
visita, costo por médico y el ROI del ciclo.

Parámetros de costo en cascada: (ciclo, línea) específica → (ciclo, NULL) default.
El costo fijo del ciclo solo se imputa a nivel equipo (sin filtrar por VM); en la
vista de un VM individual solo cuentan los costos variables.
"""
from decimal import Decimal

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.visita import VisitaRegistro, MuestraEntregada, ParametroCosto
from app.models.dimensiones import RepresentanteMedico, Linea
from app.models.hechos import Ventas
from app.schemas.visita import ParametroCostoGuardar
from app.services.visita_cobertura_service import ciclo_por_defecto
from app.services.visita_parrilla_service import linea_de_vm


def obtener_parametros(db: Session, ciclo_id: int | None, linea_id: int | None) -> dict:
    """Resuelve los parámetros de costo: (ciclo,línea) → (ciclo,NULL) → ceros."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    fila = None
    if linea_id is not None:
        fila = db.query(ParametroCosto).filter(
            ParametroCosto.ciclo_id == ciclo_id, ParametroCosto.linea_id == linea_id,
            ParametroCosto.activo == True).first()  # noqa: E712
    if fila is None:
        fila = db.query(ParametroCosto).filter(
            ParametroCosto.ciclo_id == ciclo_id, ParametroCosto.linea_id.is_(None),
            ParametroCosto.activo == True).first()  # noqa: E712
    if fila is None:
        return {"ciclo_id": ciclo_id, "linea_id": linea_id, "costo_visita": 0.0,
                "costo_muestra": 0.0, "costo_fijo_ciclo": 0.0, "moneda": "RD$", "configurado": False}
    return {"ciclo_id": ciclo_id, "linea_id": fila.linea_id,
            "costo_visita": float(fila.costo_visita), "costo_muestra": float(fila.costo_muestra),
            "costo_fijo_ciclo": float(fila.costo_fijo_ciclo), "moneda": fila.moneda, "configurado": True}


def guardar_parametros(db: Session, datos: ParametroCostoGuardar, usuario_id: int | None) -> dict:
    """Upsert de parámetros por (ciclo, línea). linea_id NULL = default del ciclo."""
    from datetime import datetime, timezone
    ciclo_id = datos.ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    q = db.query(ParametroCosto).filter(ParametroCosto.ciclo_id == ciclo_id)
    q = q.filter(ParametroCosto.linea_id == datos.linea_id) if datos.linea_id is not None \
        else q.filter(ParametroCosto.linea_id.is_(None))
    fila = q.first()
    if fila is None:
        fila = ParametroCosto(ciclo_id=ciclo_id, linea_id=datos.linea_id)
        db.add(fila)
    fila.costo_visita = Decimal(str(datos.costo_visita))
    fila.costo_muestra = Decimal(str(datos.costo_muestra))
    fila.costo_fijo_ciclo = Decimal(str(datos.costo_fijo_ciclo))
    fila.moneda = datos.moneda
    fila.activo = True
    fila.fecha_actualizacion = datetime.now(timezone.utc)
    fila.modificado_por = usuario_id
    db.commit()
    logger.info(f"Parámetros de costo guardados ciclo={ciclo_id} linea={datos.linea_id}")
    return obtener_parametros(db, ciclo_id, datos.linea_id)


def _calcular_roi(contactos: int, medicos: int, muestras: int,
                  costo_visita: float, costo_muestra: float, costo_fijo: float,
                  ingresos: float) -> dict:
    """Fórmula pura de Costo & ROI (sin acceso a BD, testeable)."""
    costo_visitas = round(contactos * costo_visita, 2)
    costo_muestras = round(muestras * costo_muestra, 2)
    costo_total = round(costo_visitas + costo_muestras + costo_fijo, 2)
    utilidad = round(ingresos - costo_total, 2)
    return {
        "contactos": contactos, "medicos_visitados": medicos, "muestras": muestras,
        "costo_visitas": costo_visitas, "costo_muestras": costo_muestras,
        "costo_fijo": round(costo_fijo, 2), "costo_total": costo_total,
        "costo_por_contacto": round(costo_total / contactos, 2) if contactos else 0.0,
        "costo_por_medico": round(costo_total / medicos, 2) if medicos else 0.0,
        "ingresos": round(ingresos, 2), "utilidad": utilidad,
        "roi_pct": round(utilidad / costo_total * 100, 1) if costo_total > 0 else None,
        "ratio_ingreso_costo": round(ingresos / costo_total, 2) if costo_total > 0 else None,
        "rentable": (utilidad >= 0) if costo_total > 0 else None,
    }


def _metricas(db: Session, ciclo_id: int, vm_id: int | None) -> tuple[int, int, int, float]:
    """(contactos, médicos visitados, muestras, ingresos) del ciclo/scope."""
    vq = db.query(VisitaRegistro).filter(
        VisitaRegistro.ciclo_id == ciclo_id, VisitaRegistro.ejecutada == True)  # noqa: E712
    if vm_id:
        vq = vq.filter(VisitaRegistro.vm_id == vm_id)
    contactos = vq.count()
    medicos = vq.with_entities(VisitaRegistro.medico_id).distinct().count()

    mq = db.query(func.coalesce(func.sum(MuestraEntregada.cantidad), 0)).filter(
        MuestraEntregada.ciclo_id == ciclo_id)
    if vm_id:
        mq = mq.filter(MuestraEntregada.vm_id == vm_id)
    muestras = int(mq.scalar() or 0)

    iq = db.query(func.coalesce(func.sum(Ventas.ventas_reales), 0)).filter(Ventas.ciclo_id == ciclo_id)
    if vm_id:
        iq = iq.filter(Ventas.rm_id == vm_id)
    ingresos = float(iq.scalar() or 0)
    return contactos, medicos, muestras, ingresos


def roi(db: Session, ciclo_id: int | None, vm_id: int | None) -> dict:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        return {"ciclo_id": None, "configurado": False, "moneda": "RD$", "costo_total": 0.0}
    linea_id = linea_de_vm(db, vm_id) if vm_id else None
    params = obtener_parametros(db, ciclo_id, linea_id)
    contactos, medicos, muestras, ingresos = _metricas(db, ciclo_id, vm_id)
    # El costo fijo del ciclo solo se imputa a nivel equipo (vm_id None).
    costo_fijo = params["costo_fijo_ciclo"] if vm_id is None else 0.0
    r = _calcular_roi(contactos, medicos, muestras,
                      params["costo_visita"], params["costo_muestra"], costo_fijo, ingresos)
    r["ciclo_id"] = ciclo_id
    r["moneda"] = params["moneda"]
    r["configurado"] = params["configurado"]
    return r


def roi_ranking(db: Session, ciclo_id: int | None) -> dict:
    """Detalle desplegable: ROI por VM (peor primero). Objetivo: ser rentable (ROI ≥ 0)."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    vm_ids = [r[0] for r in db.query(MuestraEntregada.vm_id).filter(
        MuestraEntregada.ciclo_id == ciclo_id).distinct().all()]
    vm_ids += [r[0] for r in db.query(VisitaRegistro.vm_id).filter(
        VisitaRegistro.ciclo_id == ciclo_id, VisitaRegistro.ejecutada == True).distinct().all()]  # noqa: E712
    vm_ids = sorted(set(vm_ids))
    if not vm_ids:
        return {"metrica": "roi", "objetivo": 0, "items": [], "no_cumplen": 0, "total": 0}
    nombres = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.nombre)
                   .filter(RepresentanteMedico.id.in_(vm_ids)).all())
    zonas = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.zona)
                 .filter(RepresentanteMedico.id.in_(vm_ids)).all())
    filas = []
    for vm in vm_ids:
        r = roi(db, ciclo_id, vm)
        filas.append({"vm_id": vm, "nombre": nombres.get(vm, f"VM #{vm}"), "zona": zonas.get(vm),
                      "costo_total": r["costo_total"], "ingresos": r["ingresos"],
                      "valor": r["roi_pct"] if r["roi_pct"] is not None else 0.0,
                      "cumple": bool(r["rentable"])})
    filas.sort(key=lambda f: f["valor"])  # peor ROI primero
    return {"metrica": "roi", "objetivo": 0,
            "no_cumplen": sum(1 for f in filas if not f["cumple"]),
            "total": len(filas), "items": filas}
