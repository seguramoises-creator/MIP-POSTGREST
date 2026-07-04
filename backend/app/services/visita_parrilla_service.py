"""Parrilla Promocional y Muestras (Parte 6 del spec).

La *parrilla* define, por (ciclo, línea), qué productos promover, con qué mensaje
clave, prioridad y meta de muestras del ciclo. Las *muestras* registran lo que el
VM entrega a cada médico; el resumen las cruza contra la meta de la parrilla.

Parrilla: patrón delete-then-insert por (ciclo, línea). Producto es texto libre y se
normaliza (case-insensitive) para que el cruce parrilla↔muestras sea estable.
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.models.visita import ParrillaPromocional, MuestraEntregada, MedicoVisita, VisitaRegistro
from app.models.dimensiones import RepresentanteMedico, Linea, Producto
from app.schemas.visita import ParrillaItem, MuestraItem
from app.services.visita_cobertura_service import ciclo_por_defecto
from app.services import recalculo_service


def _guard_ciclo_abierto(db, ciclo_id):
    """Bloquea escrituras sobre ciclos cerrados (inmutables)."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        raise ValueError("El ciclo está cerrado — solo lectura")


def linea_de_vm(db: Session, vm_id: int) -> int | None:
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
    return rm.linea_id if rm else None


def listar_lineas(db: Session) -> list[dict]:
    return [{"id": l.id, "nombre": l.nombre}
            for l in db.query(Linea).filter(Linea.activo == True)  # noqa: E712
            .order_by(Linea.nombre).all()]


def listar_productos(db: Session, linea_id: int | None = None) -> list[dict]:
    """Catálogo DIM_Producto (para llenar la parrilla). Filtra por línea si se indica."""
    q = db.query(Producto).filter(Producto.activo == True)  # noqa: E712
    if linea_id:
        q = q.filter((Producto.linea_id == linea_id) | (Producto.linea_id.is_(None)))
    return [{
        "id": p.id, "codigo": p.codigo, "nombre": p.nombre,
        "area_terapeutica": p.area_terapeutica, "descripcion": p.descripcion,
        "segmento_target": p.segmento_target, "meta_muestras_visita": p.meta_muestras_visita,
        "gerente_producto": p.gerente_producto, "linea_id": p.linea_id,
    } for p in q.order_by(Producto.codigo).all()]


def listar_parrilla(db: Session, ciclo_id: int | None, linea_id: int, solo_publicada: bool = False) -> list[dict]:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    q = db.query(ParrillaPromocional).filter(
        ParrillaPromocional.ciclo_id == ciclo_id,
        ParrillaPromocional.linea_id == linea_id,
        ParrillaPromocional.activo == True)  # noqa: E712
    if solo_publicada:
        q = q.filter(ParrillaPromocional.publicada == True)  # noqa: E712
    filas = q.order_by(ParrillaPromocional.prioridad, ParrillaPromocional.producto).all()
    prod_ids = {f.producto_id for f in filas if f.producto_id}
    prods = {p.id: p for p in db.query(Producto).filter(Producto.id.in_(prod_ids)).all()} if prod_ids else {}
    out = []
    for f in filas:
        p = prods.get(f.producto_id)
        out.append({
            "id": f.id, "producto_id": f.producto_id, "producto": f.producto,
            "nombre": p.nombre if p else f.producto,
            "area_terapeutica": p.area_terapeutica if p else None,
            "descripcion": p.descripcion if p else f.mensaje_clave,
            "gerente_producto": p.gerente_producto if p else None,
            "mensaje_clave": f.mensaje_clave,
            "segmento_target": f.segmento_target or (p.segmento_target if p else None),
            "prioridad": f.prioridad, "meta_muestras": f.meta_muestras,
            "publicada": f.publicada,
            "fecha_publicacion": f.fecha_publicacion.isoformat() if f.fecha_publicacion else None,
        })
    return out


def parrilla_publicada(db: Session, ciclo_id: int, linea_id: int) -> bool:
    return db.query(ParrillaPromocional).filter(
        ParrillaPromocional.ciclo_id == ciclo_id, ParrillaPromocional.linea_id == linea_id,
        ParrillaPromocional.publicada == True).first() is not None  # noqa: E712


def guardar_parrilla(db: Session, ciclo_id: int | None, linea_id: int,
                     items: list[ParrillaItem], usuario_id: int | None) -> int:
    """Guarda (reemplaza) la parrilla. Queda en BORRADOR (publicada=False): el VM no la
    ve hasta que el Gerente de Producto la publique."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    vistos = set()
    for it in items:
        clave = it.producto.lower()
        if clave in vistos:
            raise ValueError(f"Producto duplicado en la parrilla: {it.producto}")
        vistos.add(clave)
    db.query(ParrillaPromocional).filter(
        ParrillaPromocional.ciclo_id == ciclo_id,
        ParrillaPromocional.linea_id == linea_id).delete(synchronize_session=False)
    for it in items:
        db.add(ParrillaPromocional(
            ciclo_id=ciclo_id, linea_id=linea_id, producto_id=it.producto_id, producto=it.producto,
            mensaje_clave=it.mensaje_clave, segmento_target=it.segmento_target, prioridad=it.prioridad,
            meta_muestras=it.meta_muestras, activo=True, publicada=False,
            fecha_creacion=datetime.now(timezone.utc), modificado_por=usuario_id))
    db.commit()
    logger.info(f"Parrilla guardada (borrador) ciclo={ciclo_id} linea={linea_id}: {len(items)} productos")
    return len(items)


def publicar_parrilla(db: Session, ciclo_id: int | None, linea_id: int, usuario_id: int | None) -> int:
    """Publica la parrilla al equipo: a partir de aquí el VM la recibe (solo lectura)."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    filas = db.query(ParrillaPromocional).filter(
        ParrillaPromocional.ciclo_id == ciclo_id, ParrillaPromocional.linea_id == linea_id).all()
    if not filas:
        raise ValueError("No hay parrilla que publicar para esta línea.")
    ahora = datetime.now(timezone.utc)
    for f in filas:
        f.publicada = True
        f.fecha_publicacion = ahora
        f.publicada_por = usuario_id
    db.commit()
    logger.info(f"Parrilla PUBLICADA ciclo={ciclo_id} linea={linea_id}: {len(filas)} productos")
    return len(filas)


def penetracion_ciclo(db: Session, ciclo_id: int | None, linea_id: int) -> dict:
    """Penetración por producto en el ciclo: % de médicos alcanzados (sobre el panel de
    la línea), muestras totales y promedio por visita ejecutada."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    # VMs de la línea
    vm_ids = [r.id for r in db.query(RepresentanteMedico).filter(RepresentanteMedico.linea_id == linea_id).all()]
    panel = db.query(MedicoVisita).filter(
        MedicoVisita.vm_id.in_(vm_ids), MedicoVisita.activo == True).count() if vm_ids else 0  # noqa: E712
    visitas = db.query(VisitaRegistro).filter(
        VisitaRegistro.ciclo_id == ciclo_id, VisitaRegistro.vm_id.in_(vm_ids),
        VisitaRegistro.ejecutada == True).count() if vm_ids else 0  # noqa: E712
    muestras = db.query(MuestraEntregada).filter(
        MuestraEntregada.ciclo_id == ciclo_id, MuestraEntregada.vm_id.in_(vm_ids)).all() if vm_ids else []

    agg: dict[str, dict] = {}
    for m in muestras:
        k = m.producto.lower()
        d = agg.setdefault(k, {"producto": m.producto, "unidades": 0, "medicos": set()})
        d["unidades"] += m.cantidad
        d["medicos"].add(m.medico_id)

    productos = []
    for f in listar_parrilla(db, ciclo_id, linea_id):
        k = f["producto"].lower()
        d = agg.get(k, {"unidades": 0, "medicos": set()})
        med = len(d["medicos"])
        productos.append({
            "producto": f["producto"], "nombre": f.get("nombre"),
            "segmento_target": f.get("segmento_target"),
            "medicos": med,
            "penetracion_pct": round(med / panel * 100, 1) if panel else 0.0,
            "muestras_total": d["unidades"],
            "promedio_visita": round(d["unidades"] / visitas, 1) if visitas else 0.0,
        })
    return {"ciclo_id": ciclo_id, "panel": panel, "visitas": visitas, "productos": productos}


def registrar_muestras(db: Session, vm_id: int, ciclo_id: int | None, medico_id: int,
                       entregas: list[MuestraItem], usuario_id: int | None) -> int:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    medico = db.query(MedicoVisita).filter(MedicoVisita.id == medico_id).first()
    if not medico:
        raise ValueError("El médico no existe")
    if medico.vm_id != vm_id:
        raise ValueError("El médico no pertenece a tu panel")
    for e in entregas:
        db.add(MuestraEntregada(
            vm_id=vm_id, ciclo_id=ciclo_id, medico_id=medico_id,
            producto=e.producto, cantidad=e.cantidad,
            fecha_entrega=datetime.now(timezone.utc), registrado_por=usuario_id))
    db.commit()
    logger.info(f"Muestras registradas VM={vm_id} medico={medico_id} ciclo={ciclo_id}: {len(entregas)} producto(s)")
    return len(entregas)


def resumen_muestras(db: Session, ciclo_id: int | None, vm_id: int | None) -> dict:
    """Por producto: unidades entregadas, médicos alcanzados, meta y cobertura vs meta.
    La meta se toma de la parrilla de la(s) línea(s) del alcance."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    mq = db.query(MuestraEntregada).filter(MuestraEntregada.ciclo_id == ciclo_id)
    if vm_id:
        mq = mq.filter(MuestraEntregada.vm_id == vm_id)
    muestras = mq.all()

    # Metas de parrilla: si hay VM, su línea; si no, todas las líneas del ciclo.
    pq = db.query(ParrillaPromocional).filter(
        ParrillaPromocional.ciclo_id == ciclo_id, ParrillaPromocional.activo == True)  # noqa: E712
    if vm_id:
        linea = linea_de_vm(db, vm_id)
        if linea:
            pq = pq.filter(ParrillaPromocional.linea_id == linea)
    metas: dict[str, int] = {}
    mensajes: dict[str, str | None] = {}
    for p in pq.all():
        k = p.producto.lower()
        metas[k] = metas.get(k, 0) + (p.meta_muestras or 0)
        mensajes.setdefault(k, p.mensaje_clave)

    # Agregado de muestras por producto (normalizado).
    agg: dict[str, dict] = {}
    for m in muestras:
        k = m.producto.lower()
        d = agg.setdefault(k, {"producto": m.producto, "entregadas": 0, "medicos": set()})
        d["entregadas"] += m.cantidad
        d["medicos"].add(m.medico_id)

    # Unir productos de parrilla aunque no tengan muestras aún.
    for k in metas:
        agg.setdefault(k, {"producto": k, "entregadas": 0, "medicos": set()})

    productos = []
    total_entregadas = 0
    for k, d in agg.items():
        meta = metas.get(k, 0)
        entregadas = d["entregadas"]
        total_entregadas += entregadas
        productos.append({
            "producto": d["producto"],
            "mensaje_clave": mensajes.get(k),
            "entregadas": entregadas,
            "medicos_alcanzados": len(d["medicos"]),
            "meta": meta,
            "cobertura_meta_pct": round(min(100.0, entregadas / meta * 100), 1) if meta else None,
            "en_parrilla": k in metas,
        })
    productos.sort(key=lambda p: (-p["entregadas"], p["producto"]))
    return {
        "ciclo_id": ciclo_id,
        "total_entregadas": total_entregadas,
        "productos_con_muestras": sum(1 for p in productos if p["entregadas"] > 0),
        "productos": productos,
    }
