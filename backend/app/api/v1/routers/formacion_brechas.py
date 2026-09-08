"""Plan de Cierre de Brechas (§12).

Router del motor de REGLAS que cruza los cuatro desgloses del KPI de Refuerzo
(§11) para distinguir tres causas que ninguna vista aislada separa: contenido
mal enseñado (a todos), problema de un equipo (a uno), o material mal escrito
(falla incluso a quien domina el resto). No hay generación por IA aquí —el
§20.7 lo excluye a propósito—, solo condiciones que evaluar.

LO QUE NO SALE POR AQUÍ
-----------------------
Las alertas que devuelve el servicio traen una clave interna `_capsula_id` que
la orquestación usa para excluir de la regla 2 lo ya marcado como generalizado.
Es un detalle de cálculo, no del contrato: se filtra antes de responder.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, require_roles  # noqa: F401
from app.db.database import get_db
from app.models.formacion import PlanCierreBrecha
from app.models.usuario import Rol, Usuario
from app.services import formacion_brechas_service as brechas

router = APIRouter(prefix="/formacion/brechas",
                   tags=["Formación — Plan de Cierre de Brechas"])

#: Quién opera el plan: lo genera, lo atiende y ajusta sus umbrales (§12).
RequireCapacitacion = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION))
#: Quién solo lo consulta: el mismo consolidado que ve el KPI de Refuerzo
#: (_VEN_TODO en el router de Refuerzo), sumando Presidencia y Gerencia Médica.
RequireLectura = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION,
    Rol.PRESIDENCIA, Rol.GERENTE_MEDICO))


# ===========================================================================
# Serialización
# ===========================================================================

def _publica(alerta: dict) -> dict:
    """Las claves con guion bajo son internas del cálculo, no del contrato."""
    return {k: v for k, v in alerta.items() if not k.startswith("_")}


def _serializar(a: PlanCierreBrecha) -> dict:
    return {
        "id": a.id,
        "pais_codigo": a.pais_codigo,
        "ciclo_id": a.ciclo_id,
        "regla_aplicada": a.regla_aplicada,
        "prioridad": a.prioridad,
        "alcance": a.alcance,
        "descripcion": a.descripcion,
        "accion_sugerida": a.accion_sugerida,
        "link_accion": a.link_accion,
        "atendida": a.atendida,
        "generado_en": a.generado_en,
    }


# ===========================================================================
# Generar y consultar el plan
# ===========================================================================

class GenerarEntrada(BaseModel):
    pais_codigo: str
    campana_id: int | None = None
    ciclo_id: int | None = None
    persistir: bool = True


@router.post("/generar", summary="Evaluar las 5 reglas y devolver el plan priorizado")
def generar(datos: GenerarEntrada, db: Session = Depends(get_db),
            _: Usuario = RequireCapacitacion):
    """Corre el motor sobre el KPI vigente. Persistir BORRA lo anterior del mismo
    país y ciclo antes de insertar: el plan es una foto del estado actual, no un
    historial —acumular corridas dejaría a Capacitación mirando brechas ya
    cerradas—."""
    alertas = brechas.generar(
        db, pais_codigo=datos.pais_codigo, campana_id=datos.campana_id,
        ciclo_id=datos.ciclo_id, persistir=datos.persistir)
    return {"total": len(alertas), "alertas": [_publica(a) for a in alertas]}


@router.get("", summary="Alertas persistidas del país")
def listar(pais_codigo: str, ciclo_id: int | None = None,
           incluir_atendidas: bool = False, db: Session = Depends(get_db),
           _: Usuario = RequireLectura):
    filas = brechas.listar(db, pais_codigo=pais_codigo, ciclo_id=ciclo_id,
                           incluir_atendidas=incluir_atendidas)
    return [_serializar(a) for a in filas]


@router.patch("/{alerta_id}/atender", summary="Marcar una alerta como atendida")
def atender(alerta_id: int, db: Session = Depends(get_db),
            _: Usuario = RequireCapacitacion):
    """No se borra: marcarla atendida la saca del listado por defecto pero
    conserva la traza de que se detectó y se actuó."""
    try:
        a = brechas.marcar_atendida(db, alerta_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _serializar(a)


# ===========================================================================
# Umbrales configurables (§12.3 — punto abierto 6)
# ===========================================================================

class UmbralEntrada(BaseModel):
    pais_codigo: str
    clave: str = Field(min_length=1, max_length=60)
    valor: float
    descripcion: str | None = None


@router.get("/umbrales", summary="Umbrales vigentes del país (arranque + overrides)")
def umbrales(pais_codigo: str, db: Session = Depends(get_db),
             _: Usuario = RequireLectura):
    """Devuelve los valores efectivos y cuáles de ellos se pueden sobrescribir,
    para que la UI no tenga que conocer la lista de claves válidas."""
    return {
        "pais_codigo": pais_codigo,
        "valores": brechas.umbrales(db, pais_codigo),
        "claves_validas": sorted(brechas.UMBRALES_DEFECTO),
    }


@router.put("/umbrales", summary="Fijar el override de un umbral para el país")
def fijar_umbral(datos: UmbralEntrada, db: Session = Depends(get_db),
                 _: Usuario = RequireCapacitacion):
    try:
        p = brechas.fijar_umbral(
            db, pais_codigo=datos.pais_codigo, clave=datos.clave,
            valor=datos.valor, descripcion=datos.descripcion)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"id": p.id, "pais_codigo": p.pais_codigo, "clave": p.clave,
            "valor": float(p.valor), "descripcion": p.descripcion}
