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
from app.services import recalculo_service


def _guard_ciclo_abierto(db, ciclo_id):
    """Bloquea escrituras sobre ciclos cerrados (inmutables)."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        raise ValueError("El ciclo está cerrado — solo lectura")


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
    _guard_ciclo_abierto(db, ciclo_id)
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


# ── Modelo financiero completo: Estructura de costo + Pool + Plan anual + Impacto ──
from datetime import datetime as _dt, timezone as _tz
from app.models.visita import CostoEstructura, CostoProducto, ParrillaPromocional
from app.models.dimensiones import Producto as _Producto, RepresentanteMedico as _RM

_DEFAULTS = dict(
    salario_mensual=0, cargas_pct=0, viaticos_dia=0, materiales_ciclo=0, dias_campo=19,
    total_visitas=190, dias_mes=21, visitadores=1, visitas_ciclo_vm=190, ciclos_anio=11,
    coef_conservador=0.40, coef_optimista=0.70, psp_a=0, psp_b=0, psp_c=0,
    med_sin_visitar_a=None, med_sin_visitar_b=None, med_sin_visitar_c=None, moneda="RD$",
)


def obtener_estructura(db: Session, ciclo_id, linea_id) -> dict:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    e = db.query(CostoEstructura).filter(
        CostoEstructura.ciclo_id == ciclo_id, CostoEstructura.linea_id == linea_id).first()
    if not e:
        return {"ciclo_id": ciclo_id, "linea_id": linea_id, "configurado": False, **_DEFAULTS}
    return {
        "ciclo_id": ciclo_id, "linea_id": linea_id, "configurado": True, "moneda": e.moneda,
        "salario_mensual": float(e.salario_mensual), "cargas_pct": float(e.cargas_pct),
        "viaticos_dia": float(e.viaticos_dia), "materiales_ciclo": float(e.materiales_ciclo),
        "dias_campo": e.dias_campo, "total_visitas": e.total_visitas, "dias_mes": e.dias_mes,
        "visitadores": e.visitadores, "visitas_ciclo_vm": e.visitas_ciclo_vm, "ciclos_anio": e.ciclos_anio,
        "coef_conservador": float(e.coef_conservador), "coef_optimista": float(e.coef_optimista),
        "psp_a": float(e.psp_a), "psp_b": float(e.psp_b), "psp_c": float(e.psp_c),
        "med_sin_visitar_a": e.med_sin_visitar_a, "med_sin_visitar_b": e.med_sin_visitar_b,
        "med_sin_visitar_c": e.med_sin_visitar_c,
    }


def _productos(db: Session, ciclo_id, linea_id):
    rows = (db.query(CostoProducto)
            .filter(CostoProducto.ciclo_id == ciclo_id, CostoProducto.linea_id == linea_id)
            .order_by(CostoProducto.orden, CostoProducto.producto).all())
    if rows:
        return rows
    # Aún no hay costo configurado para esta (ciclo, línea): sembrar la lista con los
    # productos de la PARRILLA de la línea (los que el equipo promueve), en ceros, para
    # que las muestras de la línea aparezcan listas para llenar. Son objetos transitorios
    # (no se agregan a la sesión): solo se persisten si el usuario pulsa "Guardar".
    return _semilla_desde_parrilla(db, ciclo_id, linea_id)


def _semilla_desde_parrilla(db: Session, ciclo_id, linea_id):
    """Placeholders de CostoProducto (en ceros) a partir de la parrilla de la línea.

    Si el ciclo pedido aún no tiene parrilla propia, cae a la parrilla MÁS RECIENTE de
    esa línea en cualquier ciclo, para que las muestras de la línea aparezcan de forma
    estable sin importar qué ciclo esté seleccionado (evita el 'salen y desaparecen').
    """
    if not linea_id:
        return []
    from app.services.visita_parrilla_service import listar_parrilla
    from app.models.dimensiones import Ciclo
    try:
        parrilla = listar_parrilla(db, ciclo_id, linea_id)
        if not parrilla:
            cid = (db.query(ParrillaPromocional.ciclo_id)
                   .join(Ciclo, Ciclo.id == ParrillaPromocional.ciclo_id)
                   .filter(ParrillaPromocional.linea_id == linea_id,
                           ParrillaPromocional.activo == True)  # noqa: E712
                   .order_by(Ciclo.anio.desc(), Ciclo.numero.desc()).first())
            if cid:
                parrilla = listar_parrilla(db, cid[0], linea_id)
    except Exception:
        return []
    seed = []
    for i, f in enumerate(parrilla, 1):
        seed.append(CostoProducto(
            ciclo_id=ciclo_id, linea_id=linea_id,
            producto_id=f.get("producto_id"), producto=f["producto"], orden=i,
            # Cantidad = meta de muestras de la parrilla (lo que se promete entregar).
            costo_unitario_muestra=0, cantidad_muestras=int(f.get("meta_muestras") or 0),
            pool_ventas=0, visitas_detalladas=0, presupuesto_anual=0, precio_prom=0))
    return seed


def guardar_estructura(db: Session, datos, usuario_id) -> dict:
    ciclo_id = datos.ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    e = db.query(CostoEstructura).filter(
        CostoEstructura.ciclo_id == ciclo_id, CostoEstructura.linea_id == datos.linea_id).first()
    if not e:
        e = CostoEstructura(ciclo_id=ciclo_id, linea_id=datos.linea_id); db.add(e)
    for f in ("moneda", "salario_mensual", "cargas_pct", "viaticos_dia", "materiales_ciclo",
              "dias_campo", "total_visitas", "dias_mes", "visitadores", "visitas_ciclo_vm",
              "ciclos_anio", "coef_conservador", "coef_optimista", "psp_a", "psp_b", "psp_c",
              "med_sin_visitar_a", "med_sin_visitar_b", "med_sin_visitar_c"):
        setattr(e, f, getattr(datos, f))
    e.fecha_actualizacion = _dt.now(_tz.utc)
    e.modificado_por = usuario_id
    db.query(CostoProducto).filter(
        CostoProducto.ciclo_id == ciclo_id, CostoProducto.linea_id == datos.linea_id).delete(synchronize_session=False)
    for i, p in enumerate(datos.productos, 1):
        db.add(CostoProducto(
            ciclo_id=ciclo_id, linea_id=datos.linea_id, producto_id=p.producto_id, producto=p.producto,
            orden=p.orden or i, costo_unitario_muestra=p.costo_unitario_muestra, cantidad_muestras=p.cantidad_muestras,
            pool_ventas=p.pool_ventas, visitas_detalladas=p.visitas_detalladas,
            presupuesto_anual=p.presupuesto_anual, precio_prom=p.precio_prom))
    db.commit()
    logger.info(f"Costo & ROI: estructura guardada ciclo={ciclo_id} linea={datos.linea_id} ({len(datos.productos)} prod)")
    return calcular_full(db, ciclo_id, datos.linea_id)


def _med_sin_visitar_por_cat(db: Session, ciclo_id, linea_id) -> dict:
    from app.services.visita_cobertura_service import _cobertura_base
    q = db.query(_RM.id)
    if linea_id:
        q = q.filter(_RM.linea_id == linea_id)
    vm_ids = [r[0] for r in q.all()]
    cat = {"A": 0, "B": 0, "C": 0}
    for vm in vm_ids:
        base = _cobertura_base(db, ciclo_id, vm)
        for m in base.get("sin_visita", []):
            c = m.get("categoria")
            if c in cat:
                cat[c] += 1
    return cat


def vista_representante(db: Session, ciclo_id, linea_id) -> dict:
    """Recorte de `calcular_full` para el REPRESENTANTE — solo las dos piezas que el cliente
    autorizó (jul-2026): las UNIDADES a producir por contacto/producto para llegar al 100% de
    su presupuesto, y el IMPACTO económico de la cobertura en el presupuesto de su línea.

    NO devuelve nada gerencial: ni salarios, ni costos fijos/variables, ni ROI de la fuerza de
    venta, ni presupuesto total, ni headcount. Se deriva de `calcular_full` (no se recalcula)
    para que nunca se desincronice del número que ve gerencia, y luego se PODA — la fuente
    financiera se lee una sola vez y solo se expone el subconjunto permitido.
    """
    full = calcular_full(db, ciclo_id, linea_id)
    # Meta por producto: cuántas unidades por contacto para el 100%. De `plan_anual.productos`
    # se conservan producto, unidades objetivo y cumplimiento; se OMITEN presupuesto_anual,
    # precio_prom y retorno_real (cifras de negocio de la línea, no del representante).
    metas = [{"producto": p["producto"],
              "unidades_obj_contacto": p["unidades_obj_contacto"],
              "cumplimiento_pct": p["cumplimiento_pct"]}
             for p in full["plan_anual"]["productos"]]
    # Impacto de la cobertura en el presupuesto de la línea: médicos sin visitar y venta en
    # riesgo por categoría. Se PODA `headcount_equivalente` (cuántos visitadores harían falta)
    # porque es una lectura de gestión sobre la fuerza de venta, no del representante.
    imp = full["impacto"]
    impacto = {"categorias": imp["categorias"],
               "venta_riesgo_bajo": imp["venta_riesgo_bajo"],
               "venta_riesgo_alto": imp["venta_riesgo_alto"],
               "total_medicos_sin_visitar": imp["total_medicos_sin_visitar"]}
    return {
        "ciclo_id": full["ciclo_id"], "linea_id": full["linea_id"], "moneda": full["moneda"],
        "configurado": full["configurado"],
        "unidades_por_contacto": metas,
        "impacto_cobertura": impacto,
    }


def calcular_full(db: Session, ciclo_id, linea_id) -> dict:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    e = obtener_estructura(db, ciclo_id, linea_id)
    prods = _productos(db, ciclo_id, linea_id)
    mon = e["moneda"]
    tv = max(1, e["total_visitas"]); dias = max(1, e["dias_campo"]); dias_mes = max(1, e["dias_mes"])

    salario_ciclo = e["salario_mensual"] * (dias / dias_mes) * (1 + e["cargas_pct"] / 100)
    viaticos_total = e["viaticos_dia"] * dias
    costo_fijo_total = round(salario_ciclo + viaticos_total + e["materiales_ciclo"], 2)
    costo_fijo_dia = round(costo_fijo_total / dias, 2)
    costo_fijo_visita = round(costo_fijo_total / tv, 2)

    muestras_rows, total_muestras, costo_total_muestras = [], 0, 0.0
    for p in prods:
        total_ciclo = round(float(p.costo_unitario_muestra) * p.cantidad_muestras, 2)
        total_muestras += p.cantidad_muestras; costo_total_muestras += total_ciclo
        muestras_rows.append({"producto": p.producto, "costo_unitario": float(p.costo_unitario_muestra),
                              "cantidad": p.cantidad_muestras, "total_ciclo": total_ciclo})
    costo_variable_visita = round(costo_total_muestras / tv, 2)

    pool_rows, pool_total = [], 0.0
    for p in prods:
        vd = p.visitas_detalladas or 0
        rv = round(float(p.pool_ventas) / vd, 2) if vd else 0.0
        pool_total += float(p.pool_ventas)
        pool_rows.append({"producto": p.producto, "pool_ventas": float(p.pool_ventas),
                          "visitas_detalladas": p.visitas_detalladas, "retorno_x_visita": rv})

    costo_total_visita = round(costo_fijo_visita + costo_variable_visita, 2)
    retorno_prom_visita = round(pool_total / tv, 2)
    roi_promedio = round(retorno_prom_visita / costo_total_visita, 2) if costo_total_visita else None

    contactos_anio = e["visitadores"] * e["visitas_ciclo_vm"] * e["ciclos_anio"]
    contactos_anio_vm = e["visitas_ciclo_vm"] * e["ciclos_anio"]
    presupuesto_total = sum(float(p.presupuesto_anual) for p in prods)
    presupuesto_por_vm = round(presupuesto_total / e["visitadores"], 2) if e["visitadores"] else 0.0
    prod_obj_contacto = round(presupuesto_total / contactos_anio, 2) if contactos_anio else 0.0
    ret_by_prod = {r["producto"]: r["retorno_x_visita"] for r in pool_rows}
    plan_rows = []
    for p in prods:
        po = round(float(p.presupuesto_anual) / contactos_anio, 2) if contactos_anio else 0.0
        unid = round(po / float(p.precio_prom), 2) if p.precio_prom else 0.0
        ret_real = ret_by_prod.get(p.producto, 0.0)
        cumpl = round(ret_real / po * 100, 0) if po else 0.0
        plan_rows.append({"producto": p.producto, "presupuesto_anual": float(p.presupuesto_anual),
                          "precio_prom": float(p.precio_prom), "productiv_obj_contacto": po,
                          "unidades_obj_contacto": unid, "cumplimiento_pct": cumpl, "retorno_real": ret_real})

    muestras_by_prod = {r["producto"]: r["total_ciclo"] for r in muestras_rows}
    roi_rows = []
    for p in prods:
        vd = p.visitas_detalladas or 0
        var_prod = round(muestras_by_prod.get(p.producto, 0.0) / vd, 2) if vd else 0.0
        cvis = round(costo_fijo_visita + var_prod, 2)
        rvis = ret_by_prod.get(p.producto, 0.0)
        roi = round(rvis / cvis, 2) if cvis else 0.0
        estado = "Excelente" if roi >= 2 else ("Aceptable" if roi >= 1 else "En riesgo")
        roi_rows.append({"producto": p.producto, "costo_visita": cvis, "retorno_visita": rvis,
                        "roi": roi, "estado": estado})

    # Requerimiento Mallén (Item 10): los médicos sin visitar del impacto financiero salen
    # SIEMPRE de la Cobertura (Panel/Registro), no son editables a mano — se ignora cualquier
    # override manual guardado en la estructura.
    derivado = _med_sin_visitar_por_cat(db, ciclo_id, linea_id)
    msv = {"A": derivado["A"], "B": derivado["B"], "C": derivado["C"]}
    psp = {"A": e["psp_a"], "B": e["psp_b"], "C": e["psp_c"]}
    impacto_cat, riesgo_bajo, riesgo_alto = [], 0.0, 0.0
    for c in ("A", "B", "C"):
        bajo = round(msv[c] * psp[c] * e["coef_conservador"], 2)
        alto = round(msv[c] * psp[c] * e["coef_optimista"], 2)
        riesgo_bajo += bajo; riesgo_alto += alto
        impacto_cat.append({"categoria": c, "medicos_sin_visitar": msv[c], "psp": psp[c],
                            "venta_riesgo_bajo": bajo, "venta_riesgo_alto": alto})
    total_msv = msv["A"] + msv["B"] + msv["C"]
    headcount_equiv = round(total_msv / e["visitas_ciclo_vm"], 2) if e["visitas_ciclo_vm"] else 0.0

    return {
        "ciclo_id": ciclo_id, "linea_id": linea_id, "moneda": mon, "configurado": e["configurado"],
        "estructura": e,
        "fijo": {"costo_fijo_total": costo_fijo_total, "costo_fijo_dia": costo_fijo_dia,
                 "costo_fijo_visita": costo_fijo_visita, "salario_ciclo": round(salario_ciclo, 2),
                 "viaticos_total": round(viaticos_total, 2)},
        "muestras": {"productos": muestras_rows, "total_muestras": total_muestras,
                     "costo_total_muestras": round(costo_total_muestras, 2),
                     "costo_variable_visita": costo_variable_visita},
        "pool": {"productos": pool_rows, "pool_total": round(pool_total, 2)},
        "plan_anual": {"contactos_anio": contactos_anio, "contactos_anio_vm": contactos_anio_vm,
                       "presupuesto_total": round(presupuesto_total, 2), "presupuesto_por_vm": presupuesto_por_vm,
                       "productiv_obj_contacto": prod_obj_contacto, "productos": plan_rows},
        "resumen": {"costo_total_visita": costo_total_visita, "retorno_prom_visita": retorno_prom_visita,
                    "roi_promedio": roi_promedio, "productos": roi_rows},
        "impacto": {"categorias": impacto_cat, "venta_riesgo_bajo": round(riesgo_bajo, 2),
                    "venta_riesgo_alto": round(riesgo_alto, 2), "total_medicos_sin_visitar": total_msv,
                    "headcount_equivalente": headcount_equiv},
    }


def importar_excel(db: Session, contenido: bytes, ciclo_id, linea_id, usuario_id) -> dict:
    import io
    import pandas as pd
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    xls = pd.ExcelFile(io.BytesIO(contenido))
    df = None
    for hoja in xls.sheet_names:
        tmp = xls.parse(hoja)
        cols = [str(c).strip().lower() for c in tmp.columns]
        if "producto" in cols:
            tmp.columns = cols
            df = tmp
            break
    if df is None:
        raise ValueError("El Excel no tiene una hoja con columna producto.")

    def num(row, key, default=0):
        v = row.get(key, default)
        try:
            return float(v) if v is not None and str(v) != "nan" else default
        except (ValueError, TypeError):
            return default

    prod_by_cod = {p.codigo.lower(): p for p in db.query(_Producto).all()}
    db.query(CostoProducto).filter(
        CostoProducto.ciclo_id == ciclo_id, CostoProducto.linea_id == linea_id).delete(synchronize_session=False)
    n = 0
    for i, (_, row) in enumerate(df.iterrows(), 1):
        cod = str(row.get("producto", "")).strip()
        if not cod or cod.lower() == "nan":
            continue
        p = prod_by_cod.get(cod.lower())
        db.add(CostoProducto(
            ciclo_id=ciclo_id, linea_id=linea_id, producto_id=(p.id if p else None), producto=cod, orden=i,
            costo_unitario_muestra=num(row, "costo_unitario_muestra"), cantidad_muestras=int(num(row, "cantidad_muestras")),
            pool_ventas=num(row, "pool_ventas"), visitas_detalladas=int(num(row, "visitas_detalladas")),
            presupuesto_anual=num(row, "presupuesto_anual"), precio_prom=num(row, "precio_prom")))
        n += 1
    db.commit()
    logger.info(f"Costo & ROI: importados {n} productos desde Excel (ciclo={ciclo_id} linea={linea_id})")
    return {"importados": n, **calcular_full(db, ciclo_id, linea_id)}
