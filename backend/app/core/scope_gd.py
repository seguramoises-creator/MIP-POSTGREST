"""Alcance del GERENTE_DISTRITO en las vistas de desempeño (jul-2026).

Regla del cliente: un Gerente de Distrito ve el AGREGADO de toda la empresa (promedios,
distribución, conteos) pero solo IDENTIFICA por nombre a los RMs de SU equipo. No puede ver
el nombre/dato individual de un RM de otro distrito.

La forma de lograr "agregado global + detalle local" en un mismo listado es ANONIMIZAR (no
filtrar): las filas de RMs ajenos conservan su puntaje (para que los agregados sigan siendo de
empresa) pero pierden nombre/código/gerente. Filtrar reduciría el agregado a su equipo, que no
es lo pedido.

Solo aplica a GERENTE_DISTRITO. ADMIN y gerentes de nivel superior (Productividad, Marca,
Dirección, Presidencia) ven todos los nombres.
"""
from sqlalchemy.orm import Session

from app.models.dimensiones import RepresentanteMedico
from app.models.usuario import Rol

ANONIMO = "Otro distrito"


def rm_ids_de_gd(db: Session, gerente_id) -> set[int]:
    """IDs de los RMs del equipo de un GD (mismo gerente_id). Vacío si no tiene gerente_id."""
    if not gerente_id:
        return set()
    return {r[0] for r in db.query(RepresentanteMedico.id)
            .filter(RepresentanteMedico.gerente_id == gerente_id).all()}


def anonimizar_para_gd(items: list[dict], current_user, db: Session) -> list[dict]:
    """Si el usuario es GERENTE_DISTRITO, anonimiza el nombre/código/gerente de las filas cuyo
    RM no es de su equipo. Conserva `rm_id` (opaco, necesario como key) y todos los puntajes.
    Devuelve la MISMA lista (mutada in-place). Para otros roles no cambia nada."""
    if getattr(current_user, "rol", None) != Rol.GERENTE_DISTRITO:
        return items
    mios = rm_ids_de_gd(db, getattr(current_user, "gerente_id", None))
    for it in items:
        if it.get("rm_id") not in mios:
            it["rm_nombre"] = ANONIMO
            it["rm_codigo"] = None
            if "gerente_nombre" in it:
                it["gerente_nombre"] = "—"
    return items
