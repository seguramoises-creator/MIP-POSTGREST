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

from app.models.visita import ParrillaPromocional, MuestraEntregada, MedicoVisita
from app.models.dimensiones import RepresentanteMedico, Linea
from app.schemas.visita import ParrillaItem, MuestraItem
from app.services.visita_cobertura_service import ciclo_por_defecto


def linea_de_vm(db: Session, vm_id: int) -> int | None:
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
    return rm.linea_id if rm else None


def listar_lineas(db: Session) -> list[dict]:
    return [{"id": l.id, "nombre": l.nombre}
            for l in db.query(Linea).filter(Linea.activo == True)  # noqa: E712
            .order_by(Linea.nombre).all()]


def listar_parrilla(db: Session, ciclo_id: int | None, linea_id: int) -> list[dict]:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    filas = (db.query(ParrillaPromocional)
             .filter(ParrillaPromocional.ciclo_id == ciclo_id,
                     ParrillaPromocional.linea_id == linea_id,
                     ParrillaPromocional.activo == True)  # noqa: E712
             .order_by(ParrillaPromocional.prioridad, ParrillaPromocional.producto).all())
    return [{"id": f.id, "producto": f.producto, "mensaje_clave": f.mensaje_clave,
             "prioridad": f.prioridad, "meta_muestras": f.meta_muestras} for f in filas]


def guardar_parrilla(db: Session, ciclo_id: int | None, linea_id: int,
                     items: list[ParrillaItem], usuario_id: int | None) -> int:
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    # Un mismo producto no puede repetirse en la parrilla de la línea (case-insensitive).
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
            ciclo_id=ciclo_id, linea_id=linea_id, producto=it.producto,
            mensaje_clave=it.mensaje_clave, prioridad=it.prioridad,
            meta_muestras=it.meta_muestras, activo=True,
            fecha_creacion=datetime.now(timezone.utc), modificado_por=usuario_id))
    db.commit()
    logger.info(f"Parrilla guardada ciclo={ciclo_id} linea={linea_id}: {len(items)} productos")
    return len(items)


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
