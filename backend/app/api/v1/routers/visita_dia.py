"""
Monitor del día — endpoint de solo lectura.

Una sola ruta: la pantalla necesita las tarjetas, la tabla y el avance de la
semana a la vez, y partirlo en varias obligaría al frontend a recomponer un
mismo instante desde respuestas tomadas en momentos distintos. En un monitor
que se mira mientras la jornada avanza, eso se ve: las tarjetas dirían 24
visitas y la tabla sumaría 25.

El cálculo vive entero en `visita_dia_service`; aquí solo se resuelve el país,
el alcance por rol y los filtros.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user
from app.db.database import get_db
from app.models.dimensiones import RepresentanteMedico
from app.models.usuario import Usuario
from app.services import visita_dia_service

router = APIRouter(prefix="/visita", tags=["Visita — Monitor del día"])

RequireAnyAuth = Depends(get_current_active_user)


def _rol(u) -> str:
    return getattr(u.rol, "value", str(u.rol)).replace("Rol.", "")


def _alcance(db: Session, u: Usuario) -> list[int] | None:
    """`None` = sin restricción; una lista = los únicos VM que puede ver.

    Mismo criterio que el resto del módulo (§17): el representante se acota a sí
    mismo y el gerente de distrito a su equipo. Se devuelve una LISTA VACÍA, no
    `None`, cuando el usuario debería tener alcance pero no lo tiene resuelto —
    un `None` ahí abriría la vista entera por un dato de configuración faltante.
    """
    rol = _rol(u)
    if rol == "REPRESENTANTE_MEDICO":
        return [u.rm_id] if getattr(u, "rm_id", None) else []
    if rol == "GERENTE_DISTRITO":
        gid = getattr(u, "gerente_id", None)
        if not gid:
            return []
        return [r.id for r in db.query(RepresentanteMedico.id)
                .filter(RepresentanteMedico.gerente_id == gid).all()]
    return None


@router.get("/dia", summary="Actividad del día por representante + avance de la semana")
def resumen_dia(
    fecha: date | None = Query(None, description="Día a consultar; por omisión, hoy"),
    pais_codigo: str | None = Query(None, description="País; por omisión, el del usuario"),
    gerente_id: int | None = Query(None, description="Filtrar por gerente de distrito"),
    linea_id: int | None = Query(None, description="Filtrar por línea"),
    db: Session = Depends(get_db),
    current_user: Usuario = RequireAnyAuth,
):
    """Qué ha registrado hoy la fuerza de ventas y cómo va contra su agenda.

    El avance se mide contra la SEMANA del ciclo, no contra un objetivo diario
    repartido a mano — ver la nota de módulo del servicio. Cuando la planeación
    trae día, se añade además el objetivo del día.
    """
    pc = pais_codigo or getattr(current_user, "pais_codigo", None)
    if not pc:
        raise HTTPException(400, "No se pudo determinar el país: indícalo en la consulta "
                                 "o asigna un país al usuario.")
    return visita_dia_service.resumen_dia(
        db, pais_codigo=pc, f=fecha or date.today(),
        gerente_id=gerente_id, linea_id=linea_id,
        rm_ids=_alcance(db, current_user))
