"""Ruptura de Secuencia y Cierre de Ciclo (Parte 5 del spec).

Un médico está en *ruptura de secuencia* cuando acumula ciclos sin ser visitado.
El contador `MedicoVisita.ciclos_sin_visita` no se toca en el día a día: solo lo
hace *rodar* el **cierre de ciclo**, una operación gerencial que, para el ciclo dado:
  - resetea a 0 el contador de los médicos con ≥1 visita ejecutada, y
  - incrementa en 1 el de los que no tuvieron ninguna.

El cierre es idempotente por diseño: se registra en `Visita.CierreCicloVisita` y no
puede repetirse sobre el mismo ciclo (evitaría un doble incremento del contador).
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.visita import MedicoVisita, CierreCicloVisita
from app.models.dimensiones import RepresentanteMedico, Ciclo
from app.services.visita_cobertura_service import ciclo_por_defecto, _mapa_visitas

# Umbrales de severidad por ciclos consecutivos sin visita.
SEV_ALERTA = 1   # 1 ciclo — atención
SEV_GRAVE = 2    # 2 ciclos — grave
SEV_CRITICA = 3  # ≥3 ciclos — ruptura crítica


class CicloVisitaYaCerradoError(Exception):
    """El ciclo ya tiene un cierre de visita registrado (evita doble incremento)."""
    def __init__(self, cierre: CierreCicloVisita):
        self.cierre = cierre
        super().__init__("El ciclo de visita ya fue cerrado")


def _severidad(n: int) -> str:
    if n >= SEV_CRITICA:
        return "critica"
    if n == SEV_GRAVE:
        return "grave"
    if n == SEV_ALERTA:
        return "alerta"
    return "ninguna"


def estado_ruptura(db: Session, vm_id: int | None = None) -> dict:
    """Médicos en ruptura agrupados por severidad (1 / 2 / ≥3 ciclos sin visita)."""
    q = db.query(MedicoVisita).filter(
        MedicoVisita.activo == True, MedicoVisita.ciclos_sin_visita >= SEV_ALERTA)  # noqa: E712
    if vm_id:
        q = q.filter(MedicoVisita.vm_id == vm_id)
    medicos = q.order_by(MedicoVisita.ciclos_sin_visita.desc()).all()

    vm_ids = {m.vm_id for m in medicos}
    nombres = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.nombre)
                   .filter(RepresentanteMedico.id.in_(vm_ids)).all()) if vm_ids else {}

    buckets = {"alerta": [], "grave": [], "critica": []}
    for m in medicos:
        sev = _severidad(m.ciclos_sin_visita)
        buckets[sev].append({
            "id": m.id, "nombre": m.nombre_completo, "categoria": m.categoria,
            "vm_id": m.vm_id, "vm_nombre": nombres.get(m.vm_id, f"VM #{m.vm_id}"),
            "ciclos_sin_visita": m.ciclos_sin_visita,
        })
    return {
        "total": len(medicos),
        "alerta": len(buckets["alerta"]),
        "grave": len(buckets["grave"]),
        "critica": len(buckets["critica"]),
        "medicos": buckets,
    }


def _resumen_cierre(db: Session, ciclo_id: int, aplicar: bool, usuario_id: int | None) -> dict:
    """Núcleo compartido por previsualizar (aplicar=False) y cerrar (aplicar=True)."""
    mapa = _mapa_visitas(db, ciclo_id, None)  # todos los VM
    medicos = db.query(MedicoVisita).filter(MedicoVisita.activo == True).all()  # noqa: E712
    panel = len(medicos)
    visitados = sin_visitar = ruptura_nueva = ruptura_critica = 0
    for m in medicos:
        tuvo = m.id in mapa
        if tuvo:
            visitados += 1
            nuevo = 0
        else:
            sin_visitar += 1
            ruptura_nueva += 1
            nuevo = m.ciclos_sin_visita + 1
        if not tuvo and nuevo >= SEV_CRITICA:
            ruptura_critica += 1
        if aplicar:
            m.ciclos_sin_visita = nuevo
    resumen = {
        "ciclo_id": ciclo_id, "panel": panel, "visitados": visitados,
        "sin_visitar": sin_visitar, "ruptura_nueva": ruptura_nueva,
        "ruptura_critica": ruptura_critica,
    }
    if aplicar:
        db.add(CierreCicloVisita(
            ciclo_id=ciclo_id, fecha_cierre=datetime.now(timezone.utc),
            panel=panel, visitados=visitados, sin_visitar=sin_visitar,
            ruptura_nueva=ruptura_nueva, ruptura_critica=ruptura_critica,
            cerrado_por=usuario_id))
        db.commit()
        logger.info(f"Cierre de ciclo de visita ciclo={ciclo_id}: panel={panel} "
                    f"visitados={visitados} sin_visita={sin_visitar} criticos={ruptura_critica}")
    return resumen


def previsualizar_cierre(db: Session, ciclo_id: int | None = None) -> dict:
    """Simula el cierre sin escribir: cuántos se resetearían/incrementarían."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    ya = db.query(CierreCicloVisita).filter(CierreCicloVisita.ciclo_id == ciclo_id).first()
    r = _resumen_cierre(db, ciclo_id, aplicar=False, usuario_id=None)
    r["ya_cerrado"] = ya is not None
    r["fecha_cierre"] = ya.fecha_cierre.isoformat() if ya and ya.fecha_cierre else None
    return r


def cerrar_ciclo(db: Session, ciclo_id: int | None, usuario_id: int | None) -> dict:
    """Aplica el cierre: hace rodar el contador y registra el resumen. Idempotente."""
    ciclo_id = ciclo_id or ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    ya = db.query(CierreCicloVisita).filter(CierreCicloVisita.ciclo_id == ciclo_id).first()
    if ya:
        raise CicloVisitaYaCerradoError(ya)
    return _resumen_cierre(db, ciclo_id, aplicar=True, usuario_id=usuario_id)


def historial_cierres(db: Session, limite: int = 24) -> list[dict]:
    """Cierres registrados, del más reciente al más antiguo, con el nombre del ciclo."""
    filas = (db.query(CierreCicloVisita)
             .order_by(CierreCicloVisita.fecha_cierre.desc()).limit(limite).all())
    ciclo_ids = {f.ciclo_id for f in filas}
    ciclos = dict(db.query(Ciclo.id, Ciclo.nombre).filter(Ciclo.id.in_(ciclo_ids)).all()) if ciclo_ids else {}
    return [{
        "id": f.id, "ciclo_id": f.ciclo_id, "ciclo_nombre": ciclos.get(f.ciclo_id, f"Ciclo #{f.ciclo_id}"),
        "fecha_cierre": f.fecha_cierre.isoformat() if f.fecha_cierre else None,
        "panel": f.panel, "visitados": f.visitados, "sin_visitar": f.sin_visitar,
        "ruptura_nueva": f.ruptura_nueva, "ruptura_critica": f.ruptura_critica,
    } for f in filas]
