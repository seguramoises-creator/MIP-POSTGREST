"""
SCGCPR — Router: Administración
Gestión de catálogos: Países, Líneas, Gerentes, RMs,
Indicadores, Tablas de puntuación, Ciclos, Reglas de Elegibilidad, Usuarios.
"""
import secrets
from datetime import date, datetime, timezone
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_active_user, require_roles
from app.core.authz.audit import registrar_evento_seguridad
from app.core.authz.deps import require as _require_authz
from app.core.authz.constantes import Accion as _Acc, Recurso as _Rec
from app.models.usuario import Usuario, Rol
from app.models.dimensiones import (
    Pais, Linea, Gerente, RepresentanteMedico, Producto,
    Indicador, IndicadorTabla, Ciclo, ReglaElegibilidad, Premio, CapacitacionDim,
    CategoriaMedica, CriterioCategoria, CriterioCategoriaTabla, Feriado, CatalogoError,
)
from app.schemas.schemas import (
    CatalogoErrorCrear, CatalogoErrorActualizar, CatalogoErrorResponse,
)
from app.schemas.schemas import (
    PaisCreate, PaisResponse,
    LineaCreate, LineaResponse,
    GerenteCreate, GerenteResponse,
    RMCreate, RMResponse,
    ProductoCreate, ProductoResponse,
    IndicadorCreate, IndicadorResponse,
    IndicadorTablaCreate, IndicadorTablaResponse,
    CicloCreate, CicloResponse, CicloUpdate, FeriadoIn, FeriadoResponse,
    ReglaElegibilidadCreate, ReglaElegibilidadResponse,
    PremioCreate, PremioResponse,
    UsuarioCreate, UsuarioResponse, UsuarioUpdate, AdminSetPassword, CorreoConfig, CorreoTest,
    CategoriaMedicaCreate, CategoriaMedicaResponse,
    CriterioCategoriaCreate, CriterioCategoriaResponse,
    CriterioCategoriaTablaCreate, CriterioCategoriaTablaResponse,
)
from app.schemas.common import Msg, PagedResponse
from app.core.security import hash_password

router = APIRouter(prefix="/admin", tags=["Administración"])
AdminOnly = Depends(require_roles(Rol.ADMIN))
# RBAC Fase 2 (deuda #2): la configuración del motor de categorización (criterios + pesos +
# categorías A/B/C/D) = categorizacion.detalle → Gerente de Producto (GERENTE_MARCA) + ADMIN.
# Las LECTURAS quedan amplias (datos de referencia que consumen las pantallas de categorización).
ConfigCategorizacion = Depends(_require_authz(_Acc.CONFIGURE, _Rec.CATEGORIZACION_DETALLE))
AdminOrGerProd = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))
AnyAuth = Depends(get_current_active_user)
# Lectura de catálogos (países/líneas/gerentes/RMs/ciclos) para poblar
# selects de formularios — incluye a GD y Gerente de Marca, que no
# administran catálogos pero sí necesitan listarlos (ej: formulario de
# evaluación LSII, filtros de Coaching). Los POST/PUT/DELETE de este
# router siguen restringidos a AdminOnly/AdminOrGerProd.
# Catálogos de REFERENCIA (países, líneas, gerentes, RMs, productos): son datos no sensibles
# que necesita el selector/contexto de prácticamente TODA pantalla, incluidos los roles de solo
# lectura (CONSULTA, PRESIDENCIA, DIR_COMERCIAL, ANALISTA_DATOS, GERENTE_MARKETING/MEDICO,
# FINANZAS, REPRESENTANTE_MEDICO). Restringirlos a 4 roles rompía el contexto global País+Ciclo
# para todos los demás (init del store daba 403 → país nulo → pantallas en blanco). La LECTURA
# se abre a cualquier autenticado; la ESCRITURA de catálogos sigue restringida (AdminOnly).
LecturaCatalogos = AnyAuth


# ── Países ────────────────────────────────────────────────────────────────────

@router.get("/paises", response_model=List[PaisResponse], summary="Listar países")
def list_paises(db: Session = Depends(get_db), _=LecturaCatalogos):
    return db.query(Pais).filter(Pais.activo == True).all()

@router.post("/paises", response_model=PaisResponse, status_code=201, summary="Crear país")
def create_pais(data: PaisCreate, db: Session = Depends(get_db), _=AdminOnly):
    if db.query(Pais).filter(Pais.codigo == data.codigo).first():
        raise HTTPException(400, "Código de país ya existe")
    obj = Pais(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/paises/{id}", response_model=PaisResponse, summary="Actualizar país")
def update_pais(id: int, data: PaisCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Pais).filter(Pais.id == id).first()
    if not obj:
        raise HTTPException(404, "País no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/paises/{id}", response_model=Msg, summary="Desactivar país")
def delete_pais(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Pais).filter(Pais.id == id).first()
    if not obj:
        raise HTTPException(404, "País no encontrado")
    obj.activo = False
    db.commit()
    return Msg(message="País desactivado")


# ── Líneas ────────────────────────────────────────────────────────────────────

@router.get("/lineas", response_model=List[LineaResponse], summary="Listar líneas")
def list_lineas(pais_codigo: Optional[str] = None, db: Session = Depends(get_db), _=LecturaCatalogos):
    q = db.query(Linea).filter(Linea.activo == True)
    if pais_codigo:
        q = q.filter(Linea.pais_codigo == pais_codigo)
    return q.all()

@router.post("/lineas", response_model=LineaResponse, status_code=201, summary="Crear línea")
def create_linea(data: LineaCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = Linea(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/lineas/{id}", response_model=LineaResponse, summary="Actualizar línea")
def update_linea(id: int, data: LineaCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Linea).filter(Linea.id == id).first()
    if not obj: raise HTTPException(404, "Línea no encontrada")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj


# ── Gerentes ─────────────────────────────────────────────────────────────────

@router.get("/gerentes", response_model=List[GerenteResponse], summary="Listar gerentes")
def list_gerentes(pais_codigo: Optional[str] = None, db: Session = Depends(get_db), _=LecturaCatalogos):
    q = db.query(Gerente).filter(Gerente.activo == True)
    if pais_codigo:
        q = q.filter(Gerente.pais_codigo == pais_codigo)
    return q.all()

@router.post("/gerentes", response_model=GerenteResponse, status_code=201, summary="Crear gerente")
def create_gerente(data: GerenteCreate, db: Session = Depends(get_db), _=AdminOnly):
    if db.query(Gerente).filter(Gerente.codigo == data.codigo).first():
        raise HTTPException(400, "Código de gerente ya existe")
    obj = Gerente(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/gerentes/{id}", response_model=GerenteResponse, summary="Actualizar gerente")
def update_gerente(id: int, data: GerenteCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Gerente).filter(Gerente.id == id).first()
    if not obj: raise HTTPException(404, "Gerente no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj


# ── Representantes Médicos ────────────────────────────────────────────────────

@router.get("/rms", response_model=List[RMResponse], summary="Listar RMs")
def list_rms(
    pais_codigo: Optional[str] = None,
    gerente_id: Optional[int] = None,
    linea_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _=LecturaCatalogos
):
    q = db.query(RepresentanteMedico).filter(RepresentanteMedico.activo == True)
    if pais_codigo: q = q.filter(RepresentanteMedico.pais_codigo == pais_codigo)
    if gerente_id: q = q.filter(RepresentanteMedico.gerente_id == gerente_id)
    if linea_id: q = q.filter(RepresentanteMedico.linea_id == linea_id)
    return q.all()

@router.post("/rms", response_model=RMResponse, status_code=201, summary="Crear RM")
def create_rm(data: RMCreate, db: Session = Depends(get_db), _=AdminOnly):
    if db.query(RepresentanteMedico).filter(RepresentanteMedico.codigo == data.codigo).first():
        raise HTTPException(400, "Código de RM ya existe")
    obj = RepresentanteMedico(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/rms/{id}", response_model=RMResponse, summary="Actualizar RM")
def update_rm(id: int, data: RMCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == id).first()
    if not obj: raise HTTPException(404, "RM no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj


# ── Productos (DIM_Producto) — catálogo para la Parrilla Promocional ──────────

def _producto_dict(db: Session, p: Producto) -> dict:
    """Producto + pais_codigo derivado de su línea (para prellenar el país en el form)."""
    pais = None
    if p.linea_id:
        linea = db.query(Linea).filter(Linea.id == p.linea_id).first()
        pais = linea.pais_codigo if linea else None
    return {
        "id": p.id, "codigo": p.codigo, "nombre": p.nombre,
        "area_terapeutica": p.area_terapeutica, "descripcion": p.descripcion,
        "segmento_target": p.segmento_target, "meta_muestras_visita": p.meta_muestras_visita,
        "gerente_producto": p.gerente_producto, "linea_id": p.linea_id,
        "pais_codigo": pais, "activo": p.activo,
    }

@router.get("/productos", response_model=List[ProductoResponse], summary="Listar productos")
def list_productos(linea_id: Optional[int] = None, db: Session = Depends(get_db), _=LecturaCatalogos):
    q = db.query(Producto).filter(Producto.activo == True)
    if linea_id:
        q = q.filter(Producto.linea_id == linea_id)
    return [_producto_dict(db, p) for p in q.order_by(Producto.codigo).all()]

@router.post("/productos", response_model=ProductoResponse, status_code=201, summary="Crear producto")
def create_producto(data: ProductoCreate, db: Session = Depends(get_db), _=AdminOnly):
    if db.query(Producto).filter(Producto.codigo == data.codigo).first():
        raise HTTPException(400, "Código de producto ya existe")
    obj = Producto(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return _producto_dict(db, obj)

@router.put("/productos/{id}", response_model=ProductoResponse, summary="Actualizar producto")
def update_producto(id: int, data: ProductoCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Producto).filter(Producto.id == id).first()
    if not obj: raise HTTPException(404, "Producto no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return _producto_dict(db, obj)

@router.delete("/productos/{id}", response_model=Msg, summary="Desactivar producto")
def delete_producto(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Producto).filter(Producto.id == id).first()
    if not obj: raise HTTPException(404, "Producto no encontrado")
    obj.activo = False
    db.commit()
    return Msg(mensaje="Producto desactivado")


# ── Indicadores ───────────────────────────────────────────────────────────────

@router.get("/indicadores", response_model=dict, summary="Listar indicadores")
def list_indicadores(
    pais_codigo: Optional[str] = None,
    modulo: Optional[str] = None,
    size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _=AnyAuth,
):
    q = db.query(Indicador).filter(Indicador.activo == True)
    if pais_codigo: q = q.filter(Indicador.pais_codigo == pais_codigo)
    if modulo:  q = q.filter(Indicador.modulo == modulo)
    indicadores = q.order_by(Indicador.orden).limit(size).all()

    # Derivar valor_min / valor_max desde DIM_IndicadorTabla cuando no están en DIM_Indicador
    ind_ids = [i.id for i in indicadores]
    rangos_q = (
        db.query(
            IndicadorTabla.indicador_id,
            func.min(IndicadorTabla.rango_desde).label("r_min"),
            func.max(IndicadorTabla.rango_hasta).label("r_max"),
        )
        .filter(
            IndicadorTabla.indicador_id.in_(ind_ids),
            IndicadorTabla.activo == True,
            IndicadorTabla.rango_hasta < 9999,   # excluir centinela 999999
        )
        .group_by(IndicadorTabla.indicador_id)
        .all()
    ) if ind_ids else []
    rangos_map = {r.indicador_id: (r.r_min, r.r_max) for r in rangos_q}

    items = []
    for ind in indicadores:
        rango = rangos_map.get(ind.id, (None, None))
        v_min = ind.valor_min if ind.valor_min is not None else rango[0]
        v_max = ind.valor_max if ind.valor_max is not None else rango[1]
        items.append({
            "id": ind.id,
            "pais_codigo": ind.pais_codigo,
            "codigo": ind.codigo,
            "nombre": ind.nombre,
            "modulo": ind.modulo,
            "tipo_periodo": ind.tipo_periodo,
            "ponderacion_pct": ind.ponderacion_pct,
            "escala": ind.escala,
            "peso_iup": float(ind.peso_iup or 0),
            "valor_min": float(v_min) if v_min is not None else None,
            "valor_max": float(v_max) if v_max is not None else None,
            "activo": ind.activo,
            "orden": ind.orden,
        })
    return {"items": items, "total": len(items)}

@router.post("/indicadores", response_model=IndicadorResponse, status_code=201, summary="Crear indicador")
def create_indicador(data: IndicadorCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = Indicador(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/indicadores/{id}", response_model=IndicadorResponse, summary="Actualizar indicador")
def update_indicador(id: int, data: IndicadorCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Indicador).filter(Indicador.id == id).first()
    if not obj: raise HTTPException(404, "Indicador no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/indicadores/{id}", response_model=Msg, summary="Desactivar indicador")
def delete_indicador(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Indicador).filter(Indicador.id == id).first()
    if not obj: raise HTTPException(404, "Indicador no encontrado")
    obj.activo = False
    db.commit()
    return Msg(message="Indicador desactivado")

@router.post("/indicadores/{id}/tabla", response_model=IndicadorTablaResponse, status_code=201)
def add_tabla_puntuacion(id: int, data: IndicadorTablaCreate, db: Session = Depends(get_db), _=AdminOnly):
    data.indicador_id = id
    obj = IndicadorTabla(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.get("/indicadores/{id}/tabla", response_model=List[IndicadorTablaResponse])
def get_tabla_puntuacion(id: int, db: Session = Depends(get_db), _=AdminOrGerProd):
    return db.query(IndicadorTabla).filter(IndicadorTabla.indicador_id == id, IndicadorTabla.activo == True).all()

@router.put("/indicadores/{id}/tabla/{tabla_id}", response_model=IndicadorTablaResponse)
def update_tabla_puntuacion(id: int, tabla_id: int, data: IndicadorTablaCreate,
                             db: Session = Depends(get_db), _=ConfigCategorizacion):
    obj = db.query(IndicadorTabla).filter(IndicadorTabla.id == tabla_id, IndicadorTabla.indicador_id == id).first()
    if not obj:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Rango no encontrado")
    obj.rango_desde  = data.rango_desde
    obj.rango_hasta  = data.rango_hasta
    obj.puntos       = data.puntos
    obj.descripcion  = data.descripcion
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/indicadores/{id}/tabla/{tabla_id}", response_model=Msg)
def delete_tabla_puntuacion(id: int, tabla_id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(IndicadorTabla).filter(IndicadorTabla.id == tabla_id, IndicadorTabla.indicador_id == id).first()
    if not obj:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Rango no encontrado")
    obj.activo = False
    db.commit()
    return Msg(message="Rango eliminado")


# ── Categorización Médica (sustituye a Capacitación, ver categorizacion.py) ──
# Mantenimiento de Categorías (DIM_CategoriaMedica) y Mantenimiento de
# Parámetros (DIM_CriterioCategoria + DIM_CriterioCategoriaTabla), mismo
# patrón CRUD que Indicadores / Indicadores-Tabla más arriba.

@router.get("/categorias-medicas", response_model=List[CategoriaMedicaResponse], summary="Listar categorías médicas (A/B/C/D)")
def list_categorias_medicas(db: Session = Depends(get_db), _=AnyAuth):
    return db.query(CategoriaMedica).filter(CategoriaMedica.activo == True).order_by(CategoriaMedica.orden).all()

@router.post("/categorias-medicas", response_model=CategoriaMedicaResponse, status_code=201, summary="Crear categoría médica")
def create_categoria_medica(data: CategoriaMedicaCreate, db: Session = Depends(get_db), _=ConfigCategorizacion):
    if db.query(CategoriaMedica).filter(CategoriaMedica.codigo == data.codigo).first():
        raise HTTPException(400, "Código de categoría ya existe")
    obj = CategoriaMedica(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/categorias-medicas/{id}", response_model=CategoriaMedicaResponse, summary="Actualizar categoría médica")
def update_categoria_medica(id: int, data: CategoriaMedicaCreate, db: Session = Depends(get_db), _=ConfigCategorizacion):
    obj = db.query(CategoriaMedica).filter(CategoriaMedica.id == id).first()
    if not obj: raise HTTPException(404, "Categoría no encontrada")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/categorias-medicas/{id}", response_model=Msg, summary="Desactivar categoría médica")
def delete_categoria_medica(id: int, db: Session = Depends(get_db), _=ConfigCategorizacion):
    obj = db.query(CategoriaMedica).filter(CategoriaMedica.id == id).first()
    if not obj: raise HTTPException(404, "Categoría no encontrada")
    obj.activo = False
    db.commit()
    return Msg(message="Categoría desactivada")


@router.get("/criterios-categoria", response_model=List[CriterioCategoriaResponse], summary="Listar criterios del Motor de Cálculo")
def list_criterios_categoria(db: Session = Depends(get_db), _=AnyAuth):
    return db.query(CriterioCategoria).filter(CriterioCategoria.activo == True).order_by(CriterioCategoria.orden).all()

@router.post("/criterios-categoria", response_model=CriterioCategoriaResponse, status_code=201, summary="Crear criterio")
def create_criterio_categoria(data: CriterioCategoriaCreate, db: Session = Depends(get_db), _=ConfigCategorizacion):
    if db.query(CriterioCategoria).filter(CriterioCategoria.codigo == data.codigo).first():
        raise HTTPException(400, "Código de criterio ya existe")
    obj = CriterioCategoria(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/criterios-categoria/{id}", response_model=CriterioCategoriaResponse, summary="Actualizar criterio")
def update_criterio_categoria(id: int, data: CriterioCategoriaCreate, db: Session = Depends(get_db), _=ConfigCategorizacion):
    obj = db.query(CriterioCategoria).filter(CriterioCategoria.id == id).first()
    if not obj: raise HTTPException(404, "Criterio no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/criterios-categoria/{id}", response_model=Msg, summary="Desactivar criterio")
def delete_criterio_categoria(id: int, db: Session = Depends(get_db), _=ConfigCategorizacion):
    obj = db.query(CriterioCategoria).filter(CriterioCategoria.id == id).first()
    if not obj: raise HTTPException(404, "Criterio no encontrado")
    obj.activo = False
    db.commit()
    return Msg(message="Criterio desactivado")

@router.post("/criterios-categoria/{id}/tabla", response_model=CriterioCategoriaTablaResponse, status_code=201, summary="Agregar nivel a la tabla del criterio")
def add_tabla_criterio(id: int, data: CriterioCategoriaTablaCreate, db: Session = Depends(get_db), _=ConfigCategorizacion):
    data.criterio_id = id
    obj = CriterioCategoriaTabla(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.get("/criterios-categoria/{id}/tabla", response_model=List[CriterioCategoriaTablaResponse], summary="Tabla de niveles del criterio")
def get_tabla_criterio(id: int, db: Session = Depends(get_db), _=AdminOrGerProd):
    return db.query(CriterioCategoriaTabla).filter(
        CriterioCategoriaTabla.criterio_id == id, CriterioCategoriaTabla.activo == True
    ).all()

@router.put("/criterios-categoria/{id}/tabla/{tabla_id}", response_model=CriterioCategoriaTablaResponse)
def update_tabla_criterio(id: int, tabla_id: int, data: CriterioCategoriaTablaCreate,
                           db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(CriterioCategoriaTabla).filter(
        CriterioCategoriaTabla.id == tabla_id, CriterioCategoriaTabla.criterio_id == id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Nivel no encontrado")
    obj.pais_codigo     = data.pais_codigo
    obj.rango_desde = data.rango_desde
    obj.rango_hasta = data.rango_hasta
    obj.etiqueta    = data.etiqueta
    obj.nivel       = data.nivel
    obj.descripcion = data.descripcion
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/criterios-categoria/{id}/tabla/{tabla_id}", response_model=Msg)
def delete_tabla_criterio(id: int, tabla_id: int, db: Session = Depends(get_db), _=ConfigCategorizacion):
    obj = db.query(CriterioCategoriaTabla).filter(
        CriterioCategoriaTabla.id == tabla_id, CriterioCategoriaTabla.criterio_id == id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Nivel no encontrado")
    obj.activo = False
    db.commit()
    return Msg(message="Nivel eliminado")


# ── Ciclos ────────────────────────────────────────────────────────────────────

def _dias_habiles(db: Session, pais_codigo: str, inicio, fin) -> int:
    """Días laborables entre inicio y fin (ambos inclusive): cuenta solo lunes-viernes
    y excluye los feriados/días no laborables del país que caigan en día hábil.
    Weekday(): 0=lunes … 4=viernes, 5=sábado, 6=domingo."""
    from datetime import timedelta
    if inicio is None or fin is None or fin < inicio:
        return 0
    feriados = {
        f.fecha for f in db.query(Feriado).filter(
            Feriado.pais_codigo == pais_codigo, Feriado.activo == True,  # noqa: E712
            Feriado.fecha >= inicio, Feriado.fecha <= fin).all()
        if f.fecha.weekday() < 5  # sábado/domingo ya no cuentan; no restar dos veces
    }
    total, d = 0, inicio
    while d <= fin:
        if d.weekday() < 5 and d not in feriados:
            total += 1
        d += timedelta(days=1)
    return total


def _validar_fechas_ciclo(db: Session, pais_codigo: str, inicio, fin, excluir_id=None):
    """Control de calidad de fechas del ciclo: inicio anterior a fin y SIN solapamiento
    con otro ciclo activo del mismo país (garantiza un único ciclo por ventana de tiempo)."""
    if inicio is None or fin is None or fin <= inicio:
        raise HTTPException(400, "La fecha de inicio debe ser anterior a la fecha de fin.")
    q = (db.query(Ciclo).filter(
            Ciclo.activo == True, Ciclo.pais_codigo == pais_codigo,  # noqa: E712
            Ciclo.fecha_inicio <= fin, Ciclo.fecha_fin >= inicio))
    if excluir_id is not None:
        q = q.filter(Ciclo.id != excluir_id)
    solapado = q.first()
    if solapado:
        raise HTTPException(400,
            f"Las fechas se solapan con el ciclo '{solapado.nombre}' "
            f"({solapado.fecha_inicio} a {solapado.fecha_fin}). Ajusta el rango.")


def _ciclo_abierto_de(db: Session, pais_codigo: str, excluir_id=None):
    """El ciclo abierto del país, si lo hay. Soporte de la regla "un solo ciclo abierto"."""
    q = db.query(Ciclo).filter(Ciclo.pais_codigo == pais_codigo, Ciclo.cerrado == False)  # noqa: E712
    if excluir_id is not None:
        q = q.filter(Ciclo.id != excluir_id)
    return q.first()


def _validar_ciclo_unico_abierto(db: Session, pais_codigo: str, nombre_nuevo: str, excluir_id=None):
    """REGLA DE NEGOCIO: **un solo ciclo abierto por país** (decisión del cliente, jul-2026).

    Hasta ahora la regla solo vivía en la disciplina de cerrar a mano: `Ciclo.cerrado` tiene
    `default=False`, así que todo ciclo nacía ABIERTO por las tres vías (crear, importar,
    reabrir). Importar los 12 ciclos del Excel dejaba 12 abiertos, y el que elegía el motor
    era el de número más alto (C12), no el del mes en curso — de ahí salieron los médicos con
    alta en diciembre, la hoja de coaching archivada en C12 y el panel de cobertura en 0.
    """
    abierto = _ciclo_abierto_de(db, pais_codigo, excluir_id)
    if abierto:
        raise HTTPException(409,
            f"Ya hay un ciclo abierto en {pais_codigo}: '{abierto.nombre}' "
            f"({abierto.fecha_inicio} a {abierto.fecha_fin}). Solo puede haber un ciclo abierto "
            f"por país: ciérralo antes de abrir '{nombre_nuevo}'.")


def _ciclo_actual_de(ciclos):
    """Ciclo abierto (cerrado=False) más reciente: max por (anio, numero)."""
    abiertos = [c for c in ciclos if not c.cerrado]
    if not abiertos:
        return None
    return max(abiertos, key=lambda c: (c.anio, c.numero))


@router.get("/ciclos", response_model=List[CicloResponse], summary="Listar ciclos")
def list_ciclos(pais_codigo: Optional[str] = None, anio: Optional[int] = None,
                abierto: Optional[bool] = None,
                db: Session = Depends(get_db), _=AnyAuth):
    q = db.query(Ciclo).filter(Ciclo.activo == True)
    if pais_codigo:
        q = q.filter(Ciclo.pais_codigo == pais_codigo)
    if anio:
        q = q.filter(Ciclo.anio == anio)
    if abierto is not None:
        q = q.filter(Ciclo.cerrado == (not abierto))
    return q.order_by(Ciclo.anio, Ciclo.numero).all()


@router.get("/ciclos/actual", response_model=Optional[CicloResponse],
            summary="Ciclo abierto actual de un país")
def ciclo_actual(pais_codigo: str, db: Session = Depends(get_db), _=AnyAuth):
    ciclos = (db.query(Ciclo)
              .filter(Ciclo.activo == True, Ciclo.pais_codigo == pais_codigo)
              .all())
    return _ciclo_actual_de(ciclos)

@router.get("/ciclos/ultimo-con-datos", response_model=Optional[CicloResponse],
            summary="Último ciclo de un país que tiene datos operativos")
def ciclo_ultimo_con_datos(pais_codigo: str, db: Session = Depends(get_db), _=AnyAuth):
    """El ciclo MÁS RECIENTE (año/número desc) con datos operativos (visitas, planeación u hojas
    de Costo/ROI). Sirve para que los roles de consulta arranquen sobre información real y no en
    un ciclo abierto todavía vacío. None si ningún ciclo del país tiene datos."""
    from app.models.visita import VisitaRegistro, PlaneacionCiclo, CostoEstructura
    ciclos = (db.query(Ciclo).filter(Ciclo.pais_codigo == pais_codigo)
              .order_by(Ciclo.anio.desc(), Ciclo.numero.desc()).all())
    for c in ciclos:
        tiene = (db.query(VisitaRegistro.id).filter(VisitaRegistro.ciclo_id == c.id).first()
                 or db.query(PlaneacionCiclo.id).filter(PlaneacionCiclo.ciclo_id == c.id).first()
                 or db.query(CostoEstructura.id).filter(CostoEstructura.ciclo_id == c.id).first())
        if tiene:
            return c
    return None


@router.get("/pais-defecto", response_model=Optional[str],
            summary="País por defecto del contexto (el que tiene operación/datos)")
def pais_defecto(db: Session = Depends(get_db), _=AnyAuth):
    """País donde arranca el contexto para un usuario sin país propio (ADMIN): el que
    tiene más Representantes Médicos (donde está la operación). None si ninguno tiene RMs."""
    from sqlalchemy import func
    from app.models.dimensiones import RepresentanteMedico
    row = (db.query(RepresentanteMedico.pais_codigo)
           .group_by(RepresentanteMedico.pais_codigo)
           .order_by(func.count(RepresentanteMedico.id).desc())
           .first())
    return row[0] if row else None

@router.get("/ciclos/dias-habiles", response_model=int,
            summary="Días laborables entre dos fechas (para el formulario de ciclo)")
def ciclo_dias_habiles(pais_codigo: str, fecha_inicio: date, fecha_fin: date,
                       db: Session = Depends(get_db), _=AnyAuth):
    """Preview: lunes-viernes entre las fechas menos los feriados del país."""
    return _dias_habiles(db, pais_codigo, fecha_inicio, fecha_fin)


@router.post("/ciclos", response_model=CicloResponse, status_code=201, summary="Crear ciclo")
def create_ciclo(data: CicloCreate, db: Session = Depends(get_db), _=AdminOnly):
    _validar_fechas_ciclo(db, data.pais_codigo, data.fecha_inicio, data.fecha_fin)
    payload = data.model_dump()
    # dias_laborables SIEMPRE se calcula (lun-vie menos feriados), no se toma del cliente.
    payload["dias_laborables"] = _dias_habiles(db, data.pais_codigo, data.fecha_inicio, data.fecha_fin)
    # Un solo ciclo abierto por país: el PRIMER ciclo del país nace abierto (si no, el país
    # quedaría sin ciclo de trabajo); los demás nacen CERRADOS y se abren explícitamente
    # cuando les toque, cerrando el anterior. `cerrado` nunca se acepta del cliente.
    payload["cerrado"] = _ciclo_abierto_de(db, data.pais_codigo) is not None
    obj = Ciclo(**payload)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


@router.put("/ciclos/{id}", response_model=CicloResponse, summary="Editar ciclo")
def update_ciclo(id: int, data: CicloUpdate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Ciclo).filter(Ciclo.id == id).first()
    if not obj:
        raise HTTPException(404, "Ciclo no encontrado")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(obj, campo, valor)
    _validar_fechas_ciclo(db, obj.pais_codigo, obj.fecha_inicio, obj.fecha_fin, excluir_id=obj.id)
    # Recalcular días laborables con las fechas (nuevas o vigentes) y los feriados del país.
    obj.dias_laborables = _dias_habiles(db, obj.pais_codigo, obj.fecha_inicio, obj.fecha_fin)
    db.commit(); db.refresh(obj)
    return obj


@router.patch("/ciclos/{id}/cerrar", response_model=Msg, summary="Cerrar ciclo")
def close_ciclo(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Ciclo).filter(Ciclo.id == id).first()
    if not obj: raise HTTPException(404, "Ciclo no encontrado")
    obj.cerrado = True
    db.commit()
    return Msg(message=f"Ciclo '{obj.nombre}' cerrado correctamente")


@router.patch("/ciclos/{id}/abrir", response_model=Msg, summary="Reabrir ciclo cerrado")
def open_ciclo(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Ciclo).filter(Ciclo.id == id).first()
    if not obj: raise HTTPException(404, "Ciclo no encontrado")
    _validar_ciclo_unico_abierto(db, obj.pais_codigo, obj.nombre, excluir_id=obj.id)
    obj.cerrado = False
    db.commit()
    return Msg(message=f"Ciclo '{obj.nombre}' abierto correctamente")


@router.get("/ciclos/{id}/salud", summary="Panel de salud/completitud de un ciclo")
def ciclo_salud(id: int, db: Session = Depends(get_db), _=AnyAuth):
    """Indicadores de salud del ciclo: ventana temporal, estado, completitud de
    planeación, cobertura del panel, configuración (parrilla/costo) y ciclos vencidos
    sin cerrar del país. Alimenta el panel de salud del frontend."""
    from datetime import date
    from sqlalchemy import func, distinct
    from app.models.dimensiones import RepresentanteMedico
    from app.models.visita import (
        MedicoVisita, VisitaRegistro, PlaneacionCiclo, ParrillaPromocional, CostoEstructura,
    )
    c = db.query(Ciclo).filter(Ciclo.id == id).first()
    if not c:
        raise HTTPException(404, "Ciclo no encontrado")

    hoy = date.today()
    totales = c.dias_laborables or _dias_habiles(db, c.pais_codigo, c.fecha_inicio, c.fecha_fin)
    transcurridos = _dias_habiles(db, c.pais_codigo, c.fecha_inicio, min(hoy, c.fecha_fin)) if hoy >= c.fecha_inicio else 0
    restantes = _dias_habiles(db, c.pais_codigo, hoy, c.fecha_fin) if hoy <= c.fecha_fin else 0
    progreso = round(transcurridos / totales * 100) if totales else 0

    # VMs del país y cuántos tienen planeación cargada en el ciclo.
    vms_pais = [r.id for r in db.query(RepresentanteMedico.id).filter(
        RepresentanteMedico.pais_codigo == c.pais_codigo, RepresentanteMedico.activo == True).all()]  # noqa: E712
    vm_total = len(vms_pais)
    vm_con_plan = db.query(func.count(distinct(PlaneacionCiclo.vm_id))).filter(
        PlaneacionCiclo.ciclo_id == id).scalar() or 0

    # Panel de médicos. IMPORTANTE: se cuenta el panel EFECTIVO del ciclo aplicando el
    # mismo criterio que el Dashboard de Cobertura (`cuenta_en_ciclo`: activo, aprobado y
    # vigente según su ciclo de alta/baja). Así este panel refleja lo mismo que la
    # cobertura y delata desfases (p. ej. médicos con alta en un ciclo posterior, que
    # dejan el panel efectivo en 0 aunque haya médicos cargados).
    from app.services.visita_aprobacion_service import ordenes_ciclo, cuenta_en_ciclo
    ordenes = ordenes_ciclo(db)
    ciclo_orden = ordenes.get(id)
    _medicos = db.query(MedicoVisita).filter(MedicoVisita.vm_id.in_(vms_pais or [-1])).all()
    medicos_registrados = sum(1 for m in _medicos if m.activo)
    medicos_panel = sum(1 for m in _medicos if cuenta_en_ciclo(m, ciclo_orden, ordenes))
    medicos_fuera_de_ciclo = max(0, medicos_registrados - medicos_panel)
    medicos_visitados = db.query(func.count(distinct(VisitaRegistro.medico_id))).filter(
        VisitaRegistro.ciclo_id == id, VisitaRegistro.ejecutada == True).scalar() or 0  # noqa: E712
    visitas_registradas = db.query(func.count(VisitaRegistro.id)).filter(
        VisitaRegistro.ciclo_id == id).scalar() or 0

    parrilla_publicada = (db.query(func.count(ParrillaPromocional.id)).filter(
        ParrillaPromocional.ciclo_id == id, ParrillaPromocional.activo == True).scalar() or 0) > 0  # noqa: E712
    costo_configurado = (db.query(func.count(CostoEstructura.id)).filter(
        CostoEstructura.ciclo_id == id).scalar() or 0) > 0

    # Ciclos VENCIDOS sin cerrar del país (abiertos con fecha fin ya pasada).
    vencidos = db.query(func.count(Ciclo.id)).filter(
        Ciclo.pais_codigo == c.pais_codigo, Ciclo.activo == True,  # noqa: E712
        Ciclo.cerrado == False, Ciclo.fecha_fin < hoy).scalar() or 0

    return {
        "ciclo_id": c.id, "nombre": c.nombre, "estado": c.estado, "vencido": c.vencido,
        "fecha_inicio": c.fecha_inicio.isoformat(), "fecha_fin": c.fecha_fin.isoformat(),
        "dias_totales": totales, "dias_transcurridos": transcurridos,
        "dias_restantes": restantes, "progreso_pct": progreso,
        "vm_total": vm_total, "vm_con_planeacion": vm_con_plan,
        "vm_sin_planeacion": max(0, vm_total - vm_con_plan),
        "pct_planeacion": round(vm_con_plan / vm_total * 100) if vm_total else 0,
        "medicos_panel": medicos_panel,                       # vigentes para ESTE ciclo
        "medicos_registrados": medicos_registrados,           # activos en el panel (todos)
        "medicos_fuera_de_ciclo": medicos_fuera_de_ciclo,     # cargados pero no vigentes aquí
        "medicos_visitados": medicos_visitados,
        "medicos_sin_visitar": max(0, medicos_panel - medicos_visitados),
        "pct_cobertura": round(medicos_visitados / medicos_panel * 100) if medicos_panel else 0,
        "visitas_registradas": visitas_registradas,
        "parrilla_publicada": parrilla_publicada, "costo_configurado": costo_configurado,
        "ciclos_vencidos_sin_cerrar": vencidos,
    }


# ── Feriados / Días no laborables (DIM_Feriado) ───────────────────────────────
# Fechas entre semana (lun-vie) que NO se cuentan como días laborables del ciclo.

@router.get("/feriados", response_model=List[FeriadoResponse], summary="Listar feriados por país")
def list_feriados(pais_codigo: Optional[str] = None, db: Session = Depends(get_db), _=AnyAuth):
    q = db.query(Feriado).filter(Feriado.activo == True)  # noqa: E712
    if pais_codigo:
        q = q.filter(Feriado.pais_codigo == pais_codigo)
    return q.order_by(Feriado.fecha).all()


@router.post("/feriados", response_model=FeriadoResponse, status_code=201, summary="Crear feriado")
def create_feriado(data: FeriadoIn, db: Session = Depends(get_db), _=AdminOnly):
    ya = db.query(Feriado).filter(
        Feriado.pais_codigo == data.pais_codigo, Feriado.fecha == data.fecha).first()
    if ya:
        # Si estaba desactivado, reactívalo (idempotente); si no, error de duplicado.
        if not ya.activo:
            ya.activo = True
            if data.nombre:
                ya.nombre = data.nombre
            db.commit(); db.refresh(ya)
            return ya
        raise HTTPException(409, f"Ya existe un feriado en {data.fecha.isoformat()} para {data.pais_codigo}")
    obj = Feriado(pais_codigo=data.pais_codigo, fecha=data.fecha, nombre=data.nombre, activo=True)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


@router.delete("/feriados/{id}", response_model=Msg, summary="Eliminar feriado")
def delete_feriado(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Feriado).filter(Feriado.id == id).first()
    if not obj:
        raise HTTPException(404, "Feriado no encontrado")
    db.delete(obj); db.commit()
    return Msg(message="Feriado eliminado")


# ── Reset de datos ────────────────────────────────────────────────────────────

def _reset_datos_postgres(tipo: str) -> dict:
    """Reset portable para PostgreSQL (edición clientes grandes). Usa TRUNCATE con
    RESTART IDENTITY CASCADE (respeta FKs sin NOCHECK). Los identificadores mixtos
    (DW, Config, DIM_*) van entre comillas dobles."""
    from sqlalchemy import text
    from app.db.database import SessionLocal
    schemas = ("DW", "ETL", "Audit") if tipo == "facts" else ("Config",)
    db = SessionLocal()
    resultados, total = [], 0
    try:
        if tipo == "dims":
            db.execute(text('UPDATE "Security"."DIM_Usuario" SET pais_codigo = NULL WHERE pais_codigo IS NOT NULL'))
        tablas = db.execute(text(
            "SELECT table_schema AS s, table_name AS t FROM information_schema.tables "
            "WHERE table_type='BASE TABLE' AND table_schema = ANY(:schemas)"),
            {"schemas": list(schemas)}).mappings().all()
        for row in tablas:
            db.execute(text(f'TRUNCATE TABLE "{row["s"]}"."{row["t"]}" RESTART IDENTITY CASCADE'))
            resultados.append({"tabla": f'{row["s"]}.{row["t"]}', "filas": -1, "estado": "ok"})
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error en reset {tipo} (postgres): {e}")
    finally:
        db.close()
    return {"tipo": tipo, "total_filas": total, "tablas": resultados}


@router.post("/reset", response_model=dict, summary="Borrar datos por fase: facts o dims")
def reset_datos(tipo: str = "facts", _=AdminOnly):
    """
    Borrado en dos fases independientes:
      tipo=facts → borra DW + ETL + Audit (datos de desempeño).
                   No hay FK issues: las FACT referencian DIMs, no al revés.
      tipo=dims  → borra Config (catálogos maestros).
                   Seguro solo después de borrar FACTs.
                   Deshabilita FKs dentro de Config para respetar el orden
                   y nulifica pais_codigo en usuarios antes de borrar DIM_Pais.
    """
    if tipo not in ("facts", "dims"):
        raise HTTPException(status_code=400, detail="tipo debe ser 'facts' o 'dims'")

    # Reset portable con TRUNCATE ... RESTART IDENTITY CASCADE (PostgreSQL).
    return _reset_datos_postgres(tipo)


# ── Reglas de Elegibilidad ────────────────────────────────────────────────────

@router.get("/reglas-elegibilidad", response_model=List[ReglaElegibilidadResponse])
def list_reglas(pais_codigo: Optional[str] = None, db: Session = Depends(get_db), _=AdminOrGerProd):
    q = db.query(ReglaElegibilidad).filter(ReglaElegibilidad.activo == True)
    if pais_codigo: q = q.filter(ReglaElegibilidad.pais_codigo == pais_codigo)
    return q.all()

@router.post("/reglas-elegibilidad", response_model=ReglaElegibilidadResponse, status_code=201)
def create_regla(data: ReglaElegibilidadCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = ReglaElegibilidad(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/reglas-elegibilidad/{id}", response_model=ReglaElegibilidadResponse)
def update_regla(id: int, data: ReglaElegibilidadCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(ReglaElegibilidad).filter(ReglaElegibilidad.id == id).first()
    if not obj: raise HTTPException(404, "Regla no encontrada")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/reglas-elegibilidad/{id}", response_model=Msg)
def delete_regla(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(ReglaElegibilidad).filter(ReglaElegibilidad.id == id).first()
    if not obj: raise HTTPException(404, "Regla no encontrada")
    obj.activo = False
    db.commit()
    return Msg(message="Regla desactivada")


# ── Premios ───────────────────────────────────────────────────────────────────

@router.get("/premios", response_model=List[PremioResponse])
def list_premios(db: Session = Depends(get_db), _=AdminOrGerProd):
    return db.query(Premio).filter(Premio.activo == True).all()

@router.post("/premios", response_model=PremioResponse, status_code=201)
def create_premio(data: PremioCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = Premio(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


# ── Usuarios ──────────────────────────────────────────────────────────────────

@router.get("/usuarios", response_model=List[UsuarioResponse], summary="Listar usuarios")
def list_usuarios(db: Session = Depends(get_db), _=AdminOnly):
    return db.query(Usuario).all()

# Mismo listado que `ROLES_MULTIPAIS` en `frontend/src/store/ciclo.store.ts`: si cambia uno,
# tiene que cambiar el otro.
ROLES_MULTIPAIS = {"ADMIN", "PRESIDENCIA", "DIR_COMERCIAL", "GERENTE_PRODUCTIVIDAD"}


def _validar_pais_usuario(db: Session, rol, pais_codigo):
    """El país es OBLIGATORIO salvo para los roles multipaís.

    Sin país, `ciclo.store.init()` nunca llama a `setPais()` y **toda la tienda de
    País+Ciclo queda vacía** para ese usuario: sin badge, sin `cicloId`, sin lista de
    ciclos. Y falla en silencio — nada da error, cada módulo se las arregla con un
    fallback y el usuario simplemente ve menos de lo que debería. Se detectó con 7 de 9
    representantes en producción (jul-2026).

    Los 4 roles multipaís (mismo listado que `ROLES_MULTIPAIS` en `ciclo.store.ts`) ven
    todos los países y pueden cambiarlos: para ellos el país propio es opcional a propósito.
    """
    r = getattr(rol, "value", str(rol)).upper()
    if r in ROLES_MULTIPAIS:
        return
    if not (pais_codigo or "").strip():
        raise HTTPException(422, f"El país es obligatorio para el rol {r}: sin país el "
                                 f"usuario no puede resolver su ciclo de trabajo.")
    if not db.query(Pais.codigo).filter(Pais.codigo == pais_codigo).first():
        raise HTTPException(422, f"El país '{pais_codigo}' no existe.")


def _validar_rm_usuario(db: Session, rol, rm_id):
    """El REPRESENTANTE_MEDICO debe vincularse a un registro DIM_RM (rm_id). Sin ese vínculo
    el auto-scope por rm_id falla con 403 en TODAS sus pantallas (Cobertura, Registrar Visita,
    Productividad, LSII…): el usuario "no puede ver su cobertura". Se detectó con RMs nuevos
    creados sin vincular (jul-2026)."""
    r = getattr(rol, "value", str(rol)).upper()
    if r != "REPRESENTANTE_MEDICO":
        return
    if not rm_id:
        raise HTTPException(422, "El representante médico debe vincularse a un registro DIM_RM "
                                 "(campo 'Representante médico'): sin ese vínculo el usuario no "
                                 "puede ver su cobertura ni registrar visitas.")
    if not db.query(RepresentanteMedico.id).filter(RepresentanteMedico.id == rm_id).first():
        raise HTTPException(422, f"El representante (rm_id={rm_id}) no existe.")


@router.post("/usuarios", response_model=UsuarioResponse, status_code=201, summary="Crear usuario")
def create_usuario(data: UsuarioCreate, db: Session = Depends(get_db), _=AdminOnly):
    _validar_pais_usuario(db, data.rol, data.pais_codigo)
    _validar_rm_usuario(db, data.rol, data.rm_id)
    if db.query(Usuario).filter(Usuario.username == data.username).first():
        raise HTTPException(400, "El nombre de usuario ya existe. Elige otro.")
    if data.email and db.query(Usuario).filter(Usuario.email == data.email).first():
        raise HTTPException(400, f"El correo '{data.email}' ya está registrado con otro usuario.")
    from datetime import datetime, timezone
    from loguru import logger            # este router no importa logger a nivel de módulo
    from app.services import password_policy_service

    # Dos caminos para la contraseña inicial:
    #  (a) SIN contraseña + con correo  → se envía un ENLACE DE ACTIVACIÓN y el usuario crea
    #      la suya. Es el camino recomendado: ninguna contraseña viaja por correo, donde
    #      quedaría archivada para siempre en el buzón y en los servidores intermedios.
    #  (b) CON contraseña → el administrador la fija y la entrega por otra vía. Necesario
    #      para usuarios sin correo, donde no hay dónde mandar el enlace.
    password = (data.password or "").strip()
    por_activacion = not password
    if por_activacion and not data.email:
        raise HTTPException(422, "Sin correo no se puede enviar el enlace de activación: "
                                 "escribe una contraseña inicial o agrega un correo.")
    if not por_activacion:
        try:
            password_policy_service.validar_complejidad(db, password, data.rol)
        except ValueError as e:
            raise HTTPException(400, str(e))

    payload = data.model_dump()
    payload.pop("password", None)
    if por_activacion:
        # Contraseña aleatoria que nadie conoce (ni el administrador): la cuenta solo puede
        # abrirse con el enlace. El campo no admite NULL y dejarlo vacío haría que cualquier
        # cadena que hasheara igual sirviera; esto la vuelve inutilizable por diseño.
        payload["hashed_password"] = hash_password(secrets.token_urlsafe(32))
        payload["activado_en"] = None
        payload["password_actualizado_en"] = None
    else:
        payload["hashed_password"] = hash_password(password)
        # El administrador le entregó credenciales que ya funcionan: la cuenta está activada
        # aunque le exijamos cambiar la clave al primer ingreso.
        payload["activado_en"] = datetime.now(timezone.utc)
        payload["password_actualizado_en"] = datetime.now(timezone.utc)
    payload["debe_cambiar_password"] = True
    obj = Usuario(**payload)
    db.add(obj); db.commit(); db.refresh(obj)

    # Correo best-effort: si falla, el usuario ya quedó creado y el admin puede reenviarlo
    # desde Administración → Usuarios. Ninguno de los dos correos lleva la contraseña.
    if obj.email:
        try:
            from app.services import activacion_service, notification_service
            if por_activacion:
                activacion_service.enviar_activacion(db, obj)
            else:
                notification_service.notificar_bienvenida(
                    destinatario=obj.email,
                    nombre=obj.nombre_completo or obj.username,
                    username=obj.username)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Correo de alta falló (no bloquea) usuario={obj.id}: {e}")
    return obj

@router.put("/usuarios/{id}", response_model=UsuarioResponse, summary="Actualizar usuario")
def update_usuario(id: int, data: UsuarioUpdate, db: Session = Depends(get_db), current_user=AdminOnly):
    obj = db.query(Usuario).filter(Usuario.id == id).first()
    if not obj: raise HTTPException(404, "Usuario no encontrado")
    cambios = data.model_dump(exclude_none=True)
    rol_anterior = obj.rol
    # El país no puede perderse al editar: se valida el resultado FINAL (lo que llega o,
    # si no llega, lo que ya tiene), contra el rol final.
    _validar_pais_usuario(db,
                          cambios.get("rol", obj.rol),
                          cambios.get("pais_codigo", obj.pais_codigo))
    _validar_rm_usuario(db,
                        cambios.get("rol", obj.rol),
                        cambios.get("rm_id", obj.rm_id))
    if cambios.get("email") and db.query(Usuario).filter(
            Usuario.email == cambios["email"], Usuario.id != id).first():
        raise HTTPException(400, f"El correo '{cambios['email']}' ya está registrado con otro usuario.")
    for k, v in cambios.items():
        setattr(obj, k, v)
    # Reactivar un usuario también lo desbloquea (limpia intentos/bloqueo temporal).
    if cambios.get("activo") is True:
        obj.intentos_fallidos = 0
        obj.bloqueado_hasta = None
    # RBAC Fase 1 — si cambió el rol: marcar roles_actualizado_en (revoca los access tokens
    # emitidos antes; ver deps.get_current_user) y auditar la asignación de rol.
    rol_cambio = "rol" in cambios and obj.rol != rol_anterior
    if rol_cambio:
        obj.roles_actualizado_en = datetime.now(timezone.utc)
    db.commit(); db.refresh(obj)
    if rol_cambio:
        _ra = getattr(rol_anterior, "value", str(rol_anterior))
        _rn = getattr(obj.rol, "value", str(obj.rol))
        registrar_evento_seguridad(db, current_user, "ROL_ASIGNADO", objetivo=f"user:{obj.id}",
                                   detalle=f"rol_anterior={_ra} rol_nuevo={_rn}")
    return obj

@router.delete("/usuarios/{id}", response_model=Msg, summary="Desactivar usuario")
def delete_usuario(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Usuario).filter(Usuario.id == id).first()
    if not obj: raise HTTPException(404, "Usuario no encontrado")
    obj.activo = False
    db.commit()
    return Msg(message="Usuario desactivado")


@router.post("/usuarios/{id}/reenviar-activacion", response_model=Msg,
             summary="Reenviar el enlace de activación de un usuario (ADMIN)")
def reenviar_activacion_usuario(id: int, db: Session = Depends(get_db), _=AdminOnly):
    """Genera un enlace de activación NUEVO y lo envía por correo. El anterior queda
    inservible en el acto: sirve tanto para un enlace vencido como para uno que pudo
    quedar expuesto.

    A diferencia del endpoint público, aquí sí se dice qué pasó — quien lo llama es un
    administrador autenticado que necesita saber por qué no se envió."""
    from app.services import activacion_service
    obj = db.query(Usuario).filter(Usuario.id == id).first()
    if not obj:
        raise HTTPException(404, "Usuario no encontrado")
    if not obj.email:
        raise HTTPException(422, f"{obj.username} no tiene correo registrado: no hay a dónde "
                                 f"enviar el enlace. Agrégale un correo o fíjale una contraseña.")
    if obj.activado_en is not None:
        raise HTTPException(409, f"{obj.username} ya activó su cuenta. Si perdió la contraseña, "
                                 f"usa «Restablecer contraseña» o que use «¿Olvidó su contraseña?».")
    enviado = activacion_service.enviar_activacion(db, obj)
    if not enviado:
        # El token se generó igual; lo que falló fue el envío (SMTP mal configurado o caído).
        raise HTTPException(502, "No se pudo enviar el correo. Revisa la configuración de "
                                 "correo en Administración y vuelve a intentarlo.")
    return Msg(message=f"Enlace de activación reenviado a {obj.email}")


@router.post("/usuarios/{id}/reset-password", response_model=Msg, summary="Restablecer contraseña de un usuario (ADMIN)")
def reset_password_usuario(id: int, data: AdminSetPassword, db: Session = Depends(get_db), _=AdminOnly):
    """Un ADMIN fija una nueva contraseña para cualquier usuario desde la edición.
    Valida la política de complejidad, la guarda hasheada y fuerza el cambio en el
    próximo inicio de sesión del usuario (debe_cambiar_password=True)."""
    from datetime import datetime, timezone
    from app.core.security import hash_password
    from app.services import password_policy_service
    obj = db.query(Usuario).filter(Usuario.id == id).first()
    if not obj:
        raise HTTPException(404, "Usuario no encontrado")
    try:
        password_policy_service.validar_complejidad(db, data.password_nuevo, obj.rol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    obj.hashed_password = hash_password(data.password_nuevo)
    obj.password_actualizado_en = datetime.now(timezone.utc)
    obj.debe_cambiar_password = True
    # Al restablecer la clave, desbloquear la cuenta: limpia intentos fallidos y el
    # bloqueo temporal — así el ADMIN puede rescatar de inmediato a un usuario que
    # quedó bloqueado por intentos con la contraseña anterior.
    obj.intentos_fallidos = 0
    obj.bloqueado_hasta = None
    db.commit()
    return Msg(message=f"Contraseña de {obj.username} restablecida y cuenta desbloqueada")


@router.patch("/usuarios/{id}/bloqueo", response_model=UsuarioResponse, summary="Bloquear/desbloquear un usuario (ADMIN)")
def set_bloqueo_usuario(id: int, body: dict, db: Session = Depends(get_db), _=AdminOnly):
    """Casilla "Bloqueado" desde Administración de Usuarios.
    - `{"bloqueado": false}` → DESBLOQUEA (limpia intentos y bloqueo temporal).
    - `{"bloqueado": true}`  → bloquea manualmente (bloqueo indefinido).
    """
    from datetime import datetime, timezone, timedelta
    obj = db.query(Usuario).filter(Usuario.id == id).first()
    if not obj:
        raise HTTPException(404, "Usuario no encontrado")
    bloquear = bool(body.get("bloqueado"))
    if bloquear:
        # Bloqueo manual indefinido (fecha muy lejana). Se levanta al desmarcar.
        obj.bloqueado_hasta = datetime.now(timezone.utc) + timedelta(days=3650)
    else:
        obj.intentos_fallidos = 0
        obj.bloqueado_hasta = None
    db.commit(); db.refresh(obj)
    return obj


# ── Parámetros de sistema en runtime (solo ADMIN) ─────────────────────────────
from app.core.config import settings as _settings   # noqa: E402
from app.services import config_service as _cfg      # noqa: E402


# ── Configuración del servidor de correo (SMTP) — solo ADMIN ───────────────────
@router.get("/config/correo", summary="Configuración SMTP vigente (contraseña enmascarada)")
def get_config_correo(db: Session = Depends(get_db), _=AdminOnly):
    """Config SMTP efectiva (BD con fallback a .env). La contraseña NO se devuelve;
    solo `password_set` indica si hay una guardada."""
    from app.services import notification_service as _ns
    cfg = _ns.mail_config()
    return {
        "server": cfg["server"], "port": cfg["port"], "username": cfg["username"],
        "from_email": cfg["from"], "from_name": cfg["from_name"],
        "tls": cfg["tls"], "ssl": cfg["ssl"],
        "password_set": bool(cfg["password"]),
        "habilitado": bool(cfg["server"]),
    }


@router.put("/config/correo", response_model=Msg, summary="Guardar configuración SMTP")
def put_config_correo(data: CorreoConfig, db: Session = Depends(get_db), _=AdminOnly):
    """Guarda la config SMTP en BD (claves MAIL_*). Si `password` viene vacío/None,
    conserva la contraseña anterior (no la borra)."""
    _cfg.fijar(db, "MAIL_SERVER", data.server or "")
    _cfg.fijar(db, "MAIL_PORT", str(data.port or 587))
    _cfg.fijar(db, "MAIL_USERNAME", data.username or "")
    _cfg.fijar(db, "MAIL_FROM", data.from_email or "")
    _cfg.fijar(db, "MAIL_FROM_NAME", data.from_name or "")
    _cfg.fijar(db, "MAIL_TLS", "true" if data.tls else "false")
    _cfg.fijar(db, "MAIL_SSL", "true" if data.ssl else "false")
    if data.password:  # solo si el ADMIN escribió una nueva
        _cfg.fijar(db, "MAIL_PASSWORD", data.password)
    return Msg(message="Configuración de correo guardada")


@router.post("/config/correo/probar", response_model=Msg, summary="Enviar correo de prueba")
def probar_config_correo(data: CorreoTest, db: Session = Depends(get_db), _=AdminOnly):
    """Envía un correo de prueba a la dirección indicada con la config vigente."""
    from app.services import notification_service as _ns
    cfg = _ns.mail_config()
    if not cfg.get("server"):
        raise HTTPException(status_code=400, detail="No hay servidor SMTP configurado.")
    cuerpo = ("<html><body style='font-family:Arial,sans-serif;color:#333;'>"
              "<h2>Correo de prueba</h2><p>Si ves este mensaje, el servidor SMTP del "
              "Sistema MIP está configurado correctamente.</p>"
              "<hr><p style='color:#aaa;font-size:12px;'>Sistema MIP — SCGCPR</p></body></html>")
    ok = _ns._enviar(data.email, "Prueba de configuración de correo — Sistema MIP", cuerpo)
    if not ok:
        raise HTTPException(status_code=400, detail=(
            "No se pudo enviar. Revisa servidor/puerto/usuario/contraseña (Gmail requiere "
            "App Password) y que TLS/SSL sean correctos."))
    return Msg(message=f"Correo de prueba enviado a {data.email}")


@router.get("/config/examen-ia-demo", summary="Estado del modo de generación con IA (DEMO/real)")
def get_examen_ia_demo(db: Session = Depends(get_db), _=AdminOnly):
    """True = modo DEMO (genera local, sin gastar API). False = IA real (Claude)."""
    return {"demo": _cfg.obtener_bool(db, "EXAMEN_IA_DEMO", _settings.EXAMEN_IA_DEMO)}


@router.put("/config/examen-ia-demo", summary="Alternar modo DEMO / IA real de generación")
def set_examen_ia_demo(body: dict, db: Session = Depends(get_db), _=AdminOnly):
    """Cambia en vivo el modo de generación de exámenes con IA (sin reiniciar)."""
    demo = bool(body.get("demo"))
    _cfg.fijar(db, "EXAMEN_IA_DEMO", "true" if demo else "false")
    return {"demo": demo}


@router.get("/config/password-policy", summary="Política de contraseñas vigente")
def get_password_policy(db: Session = Depends(get_db), _=AdminOnly):
    return {
        "expiracion_activa":  _cfg.obtener_bool(db, "PASSWORD_EXPIRACION_ACTIVA", True),
        "expiracion_dias":    _cfg.obtener_int(db, "PASSWORD_EXPIRACION_DIAS", 90),
        "aviso_dias":         _cfg.obtener_int(db, "PASSWORD_AVISO_DIAS", 7),
        "historial_n":        _cfg.obtener_int(db, "PASSWORD_HISTORIAL_N", 5),
        "min_longitud":       _cfg.obtener_int(db, "PASSWORD_MIN_LONGITUD", 8),
        "min_longitud_admin": _cfg.obtener_int(db, "PASSWORD_MIN_LONGITUD_ADMIN", 12),
    }


@router.put("/config/password-policy", summary="Actualizar política de contraseñas")
def set_password_policy(body: dict, db: Session = Depends(get_db), _=AdminOnly):
    def _int(clave, k, minimo):
        if k in body:
            try:
                v = int(body[k])
            except (ValueError, TypeError):
                raise HTTPException(400, f"{k} debe ser un entero")
            if v < minimo:
                raise HTTPException(400, f"{k} debe ser >= {minimo}")
            _cfg.fijar(db, clave, str(v))
    if "expiracion_activa" in body:
        _cfg.fijar(db, "PASSWORD_EXPIRACION_ACTIVA", "true" if body["expiracion_activa"] else "false")
    _int("PASSWORD_EXPIRACION_DIAS", "expiracion_dias", 1)
    _int("PASSWORD_AVISO_DIAS", "aviso_dias", 0)
    _int("PASSWORD_HISTORIAL_N", "historial_n", 0)
    _int("PASSWORD_MIN_LONGITUD", "min_longitud", 8)
    _int("PASSWORD_MIN_LONGITUD_ADMIN", "min_longitud_admin", 8)
    return get_password_policy(db, _)


# ── Configuración de avisos de Médicos TOP (§7.3, cron de recordatorio/escalamiento) ──
@router.get("/config/medicos-top", summary="Configuración de avisos de Médicos TOP")
def get_config_medicos_top(db: Session = Depends(get_db), _=AdminOnly):
    """Los 3 parámetros que lee `visita_top_service.procesar_avisos` (cron diario:
    recordatorio al representante + escalamiento al Gerente de Distrito).

    Los defaults (`*_default` en la respuesta) NO son una decisión cerrada con el
    cliente: siguen abiertos con Mallén (pendiente nº 8 del requerimiento). Un campo
    vacío/omitido en el guardado deja vigente el default, no un error."""
    from app.services import visita_top_service as _top
    return {
        "dias_recordatorio": _cfg.obtener_int(db, _top.CFG_DIAS_RECORDATORIO,
                                              _top.DIAS_RECORDATORIO_DEFAULT),
        "pct_ciclo_escalamiento": _cfg.obtener_int(db, _top.CFG_PCT_ESCALAMIENTO,
                                                   _top.PCT_ESCALAMIENTO_DEFAULT),
        "avisos_activos": _cfg.obtener_bool(db, _top.CFG_AVISOS_ACTIVOS,
                                            _top.AVISOS_ACTIVOS_DEFAULT),
        "dias_recordatorio_default": _top.DIAS_RECORDATORIO_DEFAULT,
        "pct_ciclo_escalamiento_default": _top.PCT_ESCALAMIENTO_DEFAULT,
        "avisos_activos_default": _top.AVISOS_ACTIVOS_DEFAULT,
    }


@router.put("/config/medicos-top", summary="Guardar configuración de avisos de Médicos TOP")
def set_config_medicos_top(body: dict, db: Session = Depends(get_db), _=AdminOnly):
    """Guarda en BD los parámetros de `visita_top_service.procesar_avisos` — el
    próximo corte del cron los toma tal cual, sin redesplegar. Solo escribe las
    claves presentes en el body; omitir una la deja como estaba."""
    from app.services import visita_top_service as _top
    if "dias_recordatorio" in body:
        try:
            v = int(body["dias_recordatorio"])
        except (ValueError, TypeError):
            raise HTTPException(400, "Los días de gracia deben ser un número entero.")
        if v < 0:
            raise HTTPException(400, "Los días de gracia no pueden ser negativos.")
        _cfg.fijar(db, _top.CFG_DIAS_RECORDATORIO, str(v))
    if "pct_ciclo_escalamiento" in body:
        try:
            v = int(body["pct_ciclo_escalamiento"])
        except (ValueError, TypeError):
            raise HTTPException(400, "El % de escalamiento debe ser un número entero.")
        if v < 0 or v > 100:
            raise HTTPException(400, "El % de escalamiento debe estar entre 0 y 100.")
        _cfg.fijar(db, _top.CFG_PCT_ESCALAMIENTO, str(v))
    if "avisos_activos" in body:
        _cfg.fijar(db, _top.CFG_AVISOS_ACTIVOS, "true" if body["avisos_activos"] else "false")
    return get_config_medicos_top(db, _)


# ── Catálogo de Errores (matriz de errores mantenible) ──────────────────────────
_AdminOnly = Depends(require_roles(Rol.ADMIN))


@router.get("/catalogo-errores", response_model=List[CatalogoErrorResponse],
            summary="Listar la matriz de errores")
def list_catalogo_errores(db: Session = Depends(get_db), _=AnyAuth):
    return db.query(CatalogoError).order_by(CatalogoError.codigo).all()


@router.post("/catalogo-errores", response_model=CatalogoErrorResponse, status_code=201,
             summary="Crear un error del catálogo (ADMIN)")
def crear_catalogo_error(datos: CatalogoErrorCrear, db: Session = Depends(get_db), _=_AdminOnly):
    if db.query(CatalogoError).filter(CatalogoError.codigo == datos.codigo).first():
        raise HTTPException(400, f"Ya existe un error con el código '{datos.codigo}'.")
    obj = CatalogoError(**datos.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


@router.put("/catalogo-errores/{id}", response_model=CatalogoErrorResponse,
            summary="Actualizar un error del catálogo (ADMIN)")
def actualizar_catalogo_error(id: int, datos: CatalogoErrorActualizar,
                              db: Session = Depends(get_db), _=_AdminOnly):
    obj = db.query(CatalogoError).filter(CatalogoError.id == id).first()
    if not obj:
        raise HTTPException(404, "Error no encontrado")
    for k, v in datos.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj


@router.delete("/catalogo-errores/{id}", response_model=Msg,
               summary="Eliminar un error del catálogo (ADMIN)")
def eliminar_catalogo_error(id: int, db: Session = Depends(get_db), _=_AdminOnly):
    obj = db.query(CatalogoError).filter(CatalogoError.id == id).first()
    if not obj:
        raise HTTPException(404, "Error no encontrado")
    db.delete(obj); db.commit()
    return Msg(message="Error eliminado del catálogo")
