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


def estado_ruptura(db: Session, vm_id: int | None = None,
                   gerente_id: int | None = None, linea_id: int | None = None,
                   pais_codigo: str | None = None,
                   permitidos: set[str] | None = None) -> dict:
    """Médicos en ruptura agrupados por severidad (1 / 2 / ≥3 ciclos sin visita).
    Filtros (gestión): `vm_id` (un visitador), `gerente_id`/`linea_id` (distrito/línea),
    `pais_codigo` (aislamiento multipaís, jul-2026: cuando ADMIN/gerencias consultan
    "todos los visitadores" sin distrito/línea, sin este filtro se mezclaban médicos de
    TODOS los países del sistema). `permitidos` (hallazgo Critical de revisión, ago-2026)
    = `scope.paises_visibles(db, user)`, piso que se aplica SIEMPRE, aunque el cliente no
    haya mandado `pais_codigo` — antes, omitir `pais_codigo` sin distrito/línea devolvía
    médicos en ruptura de TODOS los países sin que el guard del endpoint lo detectara."""
    from app.services.visita_cobertura_service import _rm_ids_por
    q = db.query(MedicoVisita).filter(
        MedicoVisita.activo == True, MedicoVisita.ciclos_sin_visita >= SEV_ALERTA)  # noqa: E712
    if vm_id:
        q = q.filter(MedicoVisita.vm_id == vm_id)
    # None solo si no hay NINGÚN filtro (ni distrito/línea/país/permitidos) — ver `_rm_ids_por`.
    rm_ids = _rm_ids_por(db, gerente_id, linea_id, pais_codigo, permitidos)
    if rm_ids is not None:
        q = q.filter(MedicoVisita.vm_id.in_(rm_ids or [-1]))
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
    """Núcleo compartido por previsualizar (aplicar=False) y cerrar (aplicar=True).

    FIX AISLAMIENTO POR PAÍS (jul-2026, hallazgo crítico): un ciclo pertenece a UN país
    (`Ciclo.pais_codigo`). Antes esta función traía TODOS los médicos del sistema sin
    filtrar por país. Como ningún médico de OTRO país tiene visitas registradas bajo
    ESTE `ciclo_id` (los ciclos son país-específicos), cada cierre de ciclo de un país
    incrementaba por error el contador de ruptura de secuencia (`ciclos_sin_visita`) de
    los médicos de TODOS los demás países — corrupción de datos activa en cada cierre.
    Ahora se acota primero a los VM del país del ciclo."""
    from app.services.visita_aprobacion_service import ordenes_ciclo, cuenta_en_ciclo
    ordenes = ordenes_ciclo(db)
    ciclo_orden = ordenes.get(ciclo_id)
    mapa = _mapa_visitas(db, ciclo_id, None)  # todos los VM del país (ver filtro abajo)

    ciclo = db.query(Ciclo).filter(Ciclo.id == ciclo_id).first()
    mq = db.query(MedicoVisita)
    if ciclo and ciclo.pais_codigo:
        rm_ids_pais = [r[0] for r in db.query(RepresentanteMedico.id)
                       .filter(RepresentanteMedico.pais_codigo == ciclo.pais_codigo).all()]
        mq = mq.filter(MedicoVisita.vm_id.in_(rm_ids_pais or [-1]))
    # Solo los médicos vigentes para el ciclo (excluye altas pendientes, respeta alta/baja).
    medicos = [m for m in mq.all() if cuenta_en_ciclo(m, ciclo_orden, ordenes)]
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


def historial_cierres(db: Session, limite: int = 24,
                      permitidos: set[str] | None = None) -> list[dict]:
    """Cierres registrados, del más reciente al más antiguo, con el nombre del ciclo.
    `permitidos` (piso de país, ronda 3): `None` = todos (usuario sin país asignado);
    conjunto = solo cierres de ciclos de esos países."""
    q = db.query(CierreCicloVisita)
    if permitidos is not None:
        q = q.join(Ciclo, Ciclo.id == CierreCicloVisita.ciclo_id).filter(
            Ciclo.pais_codigo.in_(permitidos or {"__ninguno__"}))
    filas = q.order_by(CierreCicloVisita.fecha_cierre.desc()).limit(limite).all()
    ciclo_ids = {f.ciclo_id for f in filas}
    ciclos = dict(db.query(Ciclo.id, Ciclo.nombre).filter(Ciclo.id.in_(ciclo_ids)).all()) if ciclo_ids else {}
    return [{
        "id": f.id, "ciclo_id": f.ciclo_id, "ciclo_nombre": ciclos.get(f.ciclo_id, f"Ciclo #{f.ciclo_id}"),
        "fecha_cierre": f.fecha_cierre.isoformat() if f.fecha_cierre else None,
        "panel": f.panel, "visitados": f.visitados, "sin_visitar": f.sin_visitar,
        "ruptura_nueva": f.ruptura_nueva, "ruptura_critica": f.ruptura_critica,
    } for f in filas]
