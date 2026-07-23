"""Cobertura interna de Farmacias — Task 7 (plan `2026-07-22-modulo-farmacias.md`).

Dashboard operativo interno, **AD-HOC y SIN F1/F2** (Global Constraint del plan):

    cobertura = (farmacias del panel del VM en estado_aprobacion="APROBADO", activas,
                 con >=1 visita ejecutada en el ciclo)
                / (farmacias del panel del VM en estado_aprobacion="APROBADO", activas)

- F22: una farmacia PENDIENTE_APROBACION/PENDIENTE_ALTA no cuenta ni en el numerador ni
  en el denominador — el universo se filtra directamente por `estado_aprobacion="APROBADO"`.
- Una visita con `ejecutada=False` no cuenta como visitada.
- **COEXISTE con el SFA**: esto NO se cablea al Score/Ranking. `COB_FARMACIAS` del score
  sigue viniendo del SFA (fuente externa) — este servicio es puramente informativo/operativo,
  no toca `motor_calculo_service` ni `iup_service`.
"""
from sqlalchemy.orm import Session

from app.models.dimensiones import Farmacia, RepresentanteMedico
from app.models.visita import FarmaciaVisita, FactVisitaFarmacia


def _universo_ids(db: Session, vm_id: int) -> list[int]:
    """IDs de panel (`Visita.DIM_FarmaciaVisita.id`) que cuentan para cobertura: panel
    APROBADO+activo Y maestro `ACTIVA`. PENDIENTE_APROBACION/PENDIENTE_ALTA quedan
    fuera (F22).

    Hallazgo menor 6: antes solo se filtraba por `estado_aprobacion` del panel; una
    farmacia cuyo MAESTRO pasó a INACTIVA (p.ej. cerró, fue dada de baja por el
    ADMIN/GERENTE_PRODUCTIVIDAD) seguía contando en universo y visitas aunque ya no
    exista como tal — se agrega el join con `Farmacia` y el filtro `estado == "ACTIVA"`.
    """
    filas = (
        db.query(FarmaciaVisita.id)
        .join(Farmacia, Farmacia.id == FarmaciaVisita.maestro_farmacia_id)
        .filter(
            FarmaciaVisita.vm_id == vm_id,
            FarmaciaVisita.estado_aprobacion == "APROBADO",
            FarmaciaVisita.activo == True,  # noqa: E712
            Farmacia.estado == "ACTIVA",
        )
        .all()
    )
    return [f[0] for f in filas]


def cobertura_rm(db: Session, vm_id: int, ciclo_id: int) -> dict:
    """Cobertura simple de farmacias de UN VM en un ciclo.

    Retorna `{visitadas, universo, cobertura_pct}`. Panel vacío (o sin farmacias
    APROBADAS) → cobertura 0 sin dividir por cero.
    """
    universo_ids = _universo_ids(db, vm_id)
    universo = len(universo_ids)

    if universo == 0:
        return {"visitadas": 0, "universo": 0, "cobertura_pct": 0.0}

    visitadas = (
        db.query(FactVisitaFarmacia.farmacia_id)
        .filter(
            FactVisitaFarmacia.vm_id == vm_id,
            FactVisitaFarmacia.ciclo_id == ciclo_id,
            FactVisitaFarmacia.ejecutada == True,  # noqa: E712
            FactVisitaFarmacia.farmacia_id.in_(universo_ids),
        )
        .distinct()
        .count()
    )

    cobertura_pct = round((visitadas / universo) * 100, 2)
    return {"visitadas": visitadas, "universo": universo, "cobertura_pct": cobertura_pct}


def cobertura_equipo(db: Session, gerente_id: int, ciclo_id: int) -> list[dict]:
    """Cobertura de farmacias por cada VM del distrito (`gerente_id`).

    Retorna una lista con un dict por VM: `{vm_id, vm_nombre, visitadas, universo,
    cobertura_pct}`. VMs sin panel APROBADO aparecen con cobertura 0 (no se omiten,
    para que el gerente vea el equipo completo)."""
    vms = (
        db.query(RepresentanteMedico)
        .filter(
            RepresentanteMedico.gerente_id == gerente_id,
            RepresentanteMedico.activo == True,  # noqa: E712
        )
        .all()
    )

    resultado = []
    for vm in vms:
        detalle = cobertura_rm(db, vm.id, ciclo_id)
        resultado.append({
            "vm_id": vm.id,
            "vm_nombre": vm.nombre,
            **detalle,
        })
    return resultado
