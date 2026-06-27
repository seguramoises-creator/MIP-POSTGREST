"""
SCGCPR — Router: Administración
Gestión de catálogos: Países, Líneas, Gerentes, RMs,
Indicadores, Tablas de puntuación, Ciclos, Reglas de Elegibilidad, Usuarios.
"""
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Usuario, Rol
from app.models.dimensiones import (
    Pais, Linea, Gerente, RepresentanteMedico,
    Indicador, IndicadorTabla, Ciclo, ReglaElegibilidad, Premio, CapacitacionDim
)
from app.schemas.schemas import (
    PaisCreate, PaisResponse,
    LineaCreate, LineaResponse,
    GerenteCreate, GerenteResponse,
    RMCreate, RMResponse,
    IndicadorCreate, IndicadorResponse,
    IndicadorTablaCreate, IndicadorTablaResponse,
    CicloCreate, CicloResponse,
    ReglaElegibilidadCreate, ReglaElegibilidadResponse,
    PremioCreate, PremioResponse,
    UsuarioCreate, UsuarioResponse, UsuarioUpdate,
)
from app.schemas.common import Msg, PagedResponse
from app.core.security import hash_password

router = APIRouter(prefix="/admin", tags=["Administración"])
AdminOnly = Depends(require_roles(Rol.ADMIN))
AdminOrGerProd = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))


# ── Países ────────────────────────────────────────────────────────────────────

@router.get("/paises", response_model=List[PaisResponse], summary="Listar países")
def list_paises(db: Session = Depends(get_db), _=AdminOrGerProd):
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
def list_lineas(pais_id: Optional[int] = None, db: Session = Depends(get_db), _=AdminOrGerProd):
    q = db.query(Linea).filter(Linea.activo == True)
    if pais_id:
        q = q.filter(Linea.pais_id == pais_id)
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
def list_gerentes(pais_id: Optional[int] = None, db: Session = Depends(get_db), _=AdminOrGerProd):
    q = db.query(Gerente).filter(Gerente.activo == True)
    if pais_id:
        q = q.filter(Gerente.pais_id == pais_id)
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
    pais_id: Optional[int] = None,
    gerente_id: Optional[int] = None,
    linea_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _=AdminOrGerProd
):
    q = db.query(RepresentanteMedico).filter(RepresentanteMedico.activo == True)
    if pais_id: q = q.filter(RepresentanteMedico.pais_id == pais_id)
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


# ── Indicadores ───────────────────────────────────────────────────────────────

@router.get("/indicadores", response_model=List[IndicadorResponse], summary="Listar indicadores")
def list_indicadores(modulo: Optional[str] = None, db: Session = Depends(get_db), _=AdminOrGerProd):
    q = db.query(Indicador).filter(Indicador.activo == True)
    if modulo: q = q.filter(Indicador.modulo == modulo)
    return q.order_by(Indicador.orden).all()

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


# ── Ciclos ────────────────────────────────────────────────────────────────────

@router.get("/ciclos", response_model=List[CicloResponse], summary="Listar ciclos")
def list_ciclos(pais_id: Optional[int] = None, anio: Optional[int] = None, db: Session = Depends(get_db), _=AdminOrGerProd):
    q = db.query(Ciclo).filter(Ciclo.activo == True)
    if pais_id: q = q.filter(Ciclo.pais_id == pais_id)
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


# ── Reglas de Elegibilidad ────────────────────────────────────────────────────

@router.get("/reglas-elegibilidad", response_model=List[ReglaElegibilidadResponse])
def list_reglas(pais_id: Optional[int] = None, db: Session = Depends(get_db), _=AdminOrGerProd):
    q = db.query(ReglaElegibilidad).filter(ReglaElegibilidad.activo == True)
    if pais_id: q = q.filter(ReglaElegibilidad.pais_id == pais_id)
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
