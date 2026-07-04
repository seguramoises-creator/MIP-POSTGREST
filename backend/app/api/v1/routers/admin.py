"""
SCGCPR — Router: Administración
Gestión de catálogos: Países, Líneas, Gerentes, RMs,
Indicadores, Tablas de puntuación, Ciclos, Reglas de Elegibilidad, Usuarios.
"""
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Usuario, Rol
from app.models.dimensiones import (
    Pais, Linea, Gerente, RepresentanteMedico, Producto,
    Indicador, IndicadorTabla, Ciclo, ReglaElegibilidad, Premio, CapacitacionDim,
    CategoriaMedica, CriterioCategoria, CriterioCategoriaTabla,
)
from app.schemas.schemas import (
    PaisCreate, PaisResponse,
    LineaCreate, LineaResponse,
    GerenteCreate, GerenteResponse,
    RMCreate, RMResponse,
    ProductoCreate, ProductoResponse,
    IndicadorCreate, IndicadorResponse,
    IndicadorTablaCreate, IndicadorTablaResponse,
    CicloCreate, CicloResponse,
    ReglaElegibilidadCreate, ReglaElegibilidadResponse,
    PremioCreate, PremioResponse,
    UsuarioCreate, UsuarioResponse, UsuarioUpdate,
    CategoriaMedicaCreate, CategoriaMedicaResponse,
    CriterioCategoriaCreate, CriterioCategoriaResponse,
    CriterioCategoriaTablaCreate, CriterioCategoriaTablaResponse,
)
from app.schemas.common import Msg, PagedResponse
from app.core.security import hash_password

router = APIRouter(prefix="/admin", tags=["Administración"])
AdminOnly = Depends(require_roles(Rol.ADMIN))
AdminOrGerProd = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))
AnyAuth = Depends(get_current_active_user)
# Lectura de catálogos (países/líneas/gerentes/RMs/ciclos) para poblar
# selects de formularios — incluye a GD y Gerente de Marca, que no
# administran catálogos pero sí necesitan listarlos (ej: formulario de
# evaluación LSII, filtros de Coaching). Los POST/PUT/DELETE de este
# router siguen restringidos a AdminOnly/AdminOrGerProd.
LecturaCatalogos = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA
))


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
                             db: Session = Depends(get_db), _=AdminOnly):
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
def create_categoria_medica(data: CategoriaMedicaCreate, db: Session = Depends(get_db), _=AdminOnly):
    if db.query(CategoriaMedica).filter(CategoriaMedica.codigo == data.codigo).first():
        raise HTTPException(400, "Código de categoría ya existe")
    obj = CategoriaMedica(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/categorias-medicas/{id}", response_model=CategoriaMedicaResponse, summary="Actualizar categoría médica")
def update_categoria_medica(id: int, data: CategoriaMedicaCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(CategoriaMedica).filter(CategoriaMedica.id == id).first()
    if not obj: raise HTTPException(404, "Categoría no encontrada")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/categorias-medicas/{id}", response_model=Msg, summary="Desactivar categoría médica")
def delete_categoria_medica(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(CategoriaMedica).filter(CategoriaMedica.id == id).first()
    if not obj: raise HTTPException(404, "Categoría no encontrada")
    obj.activo = False
    db.commit()
    return Msg(message="Categoría desactivada")


@router.get("/criterios-categoria", response_model=List[CriterioCategoriaResponse], summary="Listar criterios del Motor de Cálculo")
def list_criterios_categoria(db: Session = Depends(get_db), _=AnyAuth):
    return db.query(CriterioCategoria).filter(CriterioCategoria.activo == True).order_by(CriterioCategoria.orden).all()

@router.post("/criterios-categoria", response_model=CriterioCategoriaResponse, status_code=201, summary="Crear criterio")
def create_criterio_categoria(data: CriterioCategoriaCreate, db: Session = Depends(get_db), _=AdminOnly):
    if db.query(CriterioCategoria).filter(CriterioCategoria.codigo == data.codigo).first():
        raise HTTPException(400, "Código de criterio ya existe")
    obj = CriterioCategoria(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/criterios-categoria/{id}", response_model=CriterioCategoriaResponse, summary="Actualizar criterio")
def update_criterio_categoria(id: int, data: CriterioCategoriaCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(CriterioCategoria).filter(CriterioCategoria.id == id).first()
    if not obj: raise HTTPException(404, "Criterio no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/criterios-categoria/{id}", response_model=Msg, summary="Desactivar criterio")
def delete_criterio_categoria(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(CriterioCategoria).filter(CriterioCategoria.id == id).first()
    if not obj: raise HTTPException(404, "Criterio no encontrado")
    obj.activo = False
    db.commit()
    return Msg(message="Criterio desactivado")

@router.post("/criterios-categoria/{id}/tabla", response_model=CriterioCategoriaTablaResponse, status_code=201, summary="Agregar nivel a la tabla del criterio")
def add_tabla_criterio(id: int, data: CriterioCategoriaTablaCreate, db: Session = Depends(get_db), _=AdminOnly):
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
def delete_tabla_criterio(id: int, tabla_id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(CriterioCategoriaTabla).filter(
        CriterioCategoriaTabla.id == tabla_id, CriterioCategoriaTabla.criterio_id == id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Nivel no encontrado")
    obj.activo = False
    db.commit()
    return Msg(message="Nivel eliminado")


# ── Ciclos ────────────────────────────────────────────────────────────────────

@router.get("/ciclos", response_model=List[CicloResponse], summary="Listar ciclos")
def list_ciclos(pais_codigo: Optional[str] = None, anio: Optional[int] = None, db: Session = Depends(get_db), _=LecturaCatalogos):
    q = db.query(Ciclo).filter(Ciclo.activo == True)
    if pais_codigo: q = q.filter(Ciclo.pais_codigo == pais_codigo)
    if anio: q = q.filter(Ciclo.anio == anio)
    return q.order_by(Ciclo.anio, Ciclo.numero).all()

@router.post("/ciclos", response_model=CicloResponse, status_code=201, summary="Crear ciclo")
def create_ciclo(data: CicloCreate, db: Session = Depends(get_db), _=AdminOnly):
    obj = Ciclo(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
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
    obj.cerrado = False
    db.commit()
    return Msg(message=f"Ciclo '{obj.nombre}' abierto correctamente")


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

    from app.core.config import settings

    # PostgreSQL (edición clientes grandes): reset portable con TRUNCATE CASCADE.
    if settings.DB_ENGINE == "postgres":
        return _reset_datos_postgres(tipo)

    import pymssql

    try:
        conn = pymssql.connect(
            server=settings.DB_SERVER,
            port=int(settings.DB_PORT),
            database=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            as_dict=True,
        )
        cur = conn.cursor()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo conectar a la BD: {e}")

    resultados = []
    total = 0

    try:
        if tipo == "facts":
            # ── Fase 1: borrar DW / ETL / Audit ─────────────────────────────
            # Las FACT tables apuntan HACIA los DIMs, nunca al revés.
            # Borrarlas no viola ninguna FK → no se necesita NOCHECK.
            cur.execute("""
                SELECT TABLE_SCHEMA AS s, TABLE_NAME AS t
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                  AND TABLE_SCHEMA IN ('DW','ETL','Audit')
            """)
            tablas = cur.fetchall()
            for row in tablas:
                cur.execute(f"DELETE FROM [{row['s']}].[{row['t']}]")
                filas = cur.rowcount if cur.rowcount >= 0 else 0
                total += filas
                resultados.append({"tabla": f"{row['s']}.{row['t']}", "filas": filas, "estado": "ok"})

        else:
            # ── Fase 2: borrar Config (catálogos DIM) ────────────────────────
            # Requisito: FACTs ya están vacíos (fase 1 ejecutada).
            # Pasos:
            #   a) Nulificar pais_codigo en usuarios (FK Security→Config)
            #   b) NOCHECK todas las FKs dentro de Config
            #   c) Borrar todas las tablas Config
            #   d) Re-habilitar FKs (WITH NOCHECK = sin re-validar)

            # a) Nulificar pais_codigo en usuarios
            cur.execute(
                "UPDATE [Security].[DIM_Usuario] SET pais_codigo = NULL WHERE pais_codigo IS NOT NULL"
            )

            # b) Deshabilitar FKs dentro del esquema Config
            cur.execute("""
                SELECT
                    OBJECT_SCHEMA_NAME(fk.parent_object_id) AS s,
                    OBJECT_NAME(fk.parent_object_id)        AS t,
                    fk.name                                  AS n
                FROM sys.foreign_keys fk
                WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = 'Config'
            """)
            fks = cur.fetchall()
            for fk in fks:
                cur.execute(
                    f"ALTER TABLE [{fk['s']}].[{fk['t']}] NOCHECK CONSTRAINT [{fk['n']}]"
                )

            # c) Borrar todas las tablas Config
            cur.execute("""
                SELECT TABLE_SCHEMA AS s, TABLE_NAME AS t
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = 'Config'
            """)
            tablas = cur.fetchall()
            for row in tablas:
                cur.execute(f"DELETE FROM [{row['s']}].[{row['t']}]")
                filas = cur.rowcount if cur.rowcount >= 0 else 0
                total += filas
                resultados.append({"tabla": f"{row['s']}.{row['t']}", "filas": filas, "estado": "ok"})

            # d) Re-habilitar FKs sin validar datos actuales
            for fk in fks:
                cur.execute(
                    f"ALTER TABLE [{fk['s']}].[{fk['t']}] WITH NOCHECK CHECK CONSTRAINT [{fk['n']}]"
                )

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error en reset {tipo}: {e}")
    finally:
        cur.close()
        conn.close()

    return {"tipo": tipo, "total_filas_borradas": total, "tablas": resultados}


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

@router.post("/usuarios", response_model=UsuarioResponse, status_code=201, summary="Crear usuario")
def create_usuario(data: UsuarioCreate, db: Session = Depends(get_db), _=AdminOnly):
    if db.query(Usuario).filter(Usuario.username == data.username).first():
        raise HTTPException(400, "Username ya existe")
    payload = data.model_dump()
    payload["hashed_password"] = hash_password(payload.pop("password"))
    obj = Usuario(**payload)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.put("/usuarios/{id}", response_model=UsuarioResponse, summary="Actualizar usuario")
def update_usuario(id: int, data: UsuarioUpdate, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Usuario).filter(Usuario.id == id).first()
    if not obj: raise HTTPException(404, "Usuario no encontrado")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/usuarios/{id}", response_model=Msg, summary="Desactivar usuario")
def delete_usuario(id: int, db: Session = Depends(get_db), _=AdminOnly):
    obj = db.query(Usuario).filter(Usuario.id == id).first()
    if not obj: raise HTTPException(404, "Usuario no encontrado")
    obj.activo = False
    db.commit()
    return Msg(message="Usuario desactivado")


# ── Parámetros de sistema en runtime (solo ADMIN) ─────────────────────────────
from app.core.config import settings as _settings   # noqa: E402
from app.services import config_service as _cfg      # noqa: E402


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
