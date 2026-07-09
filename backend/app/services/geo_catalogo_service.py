"""Catálogos geográficos y de especialidad para el maestro de médicos (Panel/Visita)
y la Categorización Médica: Provincia, Municipio, Centro Médico y Especialidad.

- Los formularios los consumen como listas desplegables (provincia → municipio en
  cascada; centro por país). El médico guarda el NOMBRE seleccionado.
- Se pueden mantener (alta / baja lógica) desde la Categorización Médica.
"""
from sqlalchemy.orm import Session

from app.models.dimensiones import Especialidad, Provincia, Municipio, CentroMedico


# ── Listado (para dropdowns) ─────────────────────────────────────────────────

def listar_provincias(db: Session, pais_codigo: str | None = None, incluir_inactivos: bool = False) -> list[dict]:
    q = db.query(Provincia)
    if not incluir_inactivos:
        q = q.filter(Provincia.activo == True)  # noqa: E712
    if pais_codigo:
        q = q.filter(Provincia.pais_codigo == pais_codigo)
    return [{"id": p.id, "nombre": p.nombre, "pais_codigo": p.pais_codigo, "activo": p.activo}
            for p in q.order_by(Provincia.nombre).all()]


def listar_municipios(db: Session, provincia_id: int | None = None, incluir_inactivos: bool = False) -> list[dict]:
    q = db.query(Municipio)
    if not incluir_inactivos:
        q = q.filter(Municipio.activo == True)  # noqa: E712
    if provincia_id:
        q = q.filter(Municipio.provincia_id == provincia_id)
    return [{"id": m.id, "nombre": m.nombre, "provincia_id": m.provincia_id, "activo": m.activo}
            for m in q.order_by(Municipio.nombre).all()]


def listar_centros(db: Session, pais_codigo: str | None = None, incluir_inactivos: bool = False) -> list[dict]:
    q = db.query(CentroMedico)
    if not incluir_inactivos:
        q = q.filter(CentroMedico.activo == True)  # noqa: E712
    if pais_codigo:
        q = q.filter(CentroMedico.pais_codigo == pais_codigo)
    return [{"id": c.id, "nombre": c.nombre, "pais_codigo": c.pais_codigo, "activo": c.activo}
            for c in q.order_by(CentroMedico.nombre).all()]


def listar_especialidades(db: Session, incluir_inactivos: bool = False) -> list[dict]:
    q = db.query(Especialidad)
    if not incluir_inactivos:
        q = q.filter(Especialidad.activo == True)  # noqa: E712
    return [{"id": e.id, "nombre": e.nombre, "activo": e.activo}
            for e in q.order_by(Especialidad.nombre).all()]


# ── Mantenimiento (alta / baja lógica) ───────────────────────────────────────

def _nombre_limpio(nombre: str) -> str:
    n = " ".join((nombre or "").strip().split())
    if len(n) < 2:
        raise ValueError("El nombre debe tener al menos 2 caracteres")
    return n


def crear_provincia(db: Session, pais_codigo: str, nombre: str) -> dict:
    nombre = _nombre_limpio(nombre)
    ex = db.query(Provincia).filter(Provincia.pais_codigo == pais_codigo, Provincia.nombre == nombre).first()
    if ex:
        if not ex.activo:
            ex.activo = True; db.commit()
        return {"id": ex.id, "nombre": ex.nombre, "pais_codigo": ex.pais_codigo}
    p = Provincia(pais_codigo=pais_codigo, nombre=nombre, activo=True)
    db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id, "nombre": p.nombre, "pais_codigo": p.pais_codigo}


def crear_municipio(db: Session, provincia_id: int, nombre: str) -> dict:
    nombre = _nombre_limpio(nombre)
    if not db.query(Provincia).filter(Provincia.id == provincia_id).first():
        raise ValueError("La provincia no existe")
    ex = db.query(Municipio).filter(Municipio.provincia_id == provincia_id, Municipio.nombre == nombre).first()
    if ex:
        if not ex.activo:
            ex.activo = True; db.commit()
        return {"id": ex.id, "nombre": ex.nombre, "provincia_id": ex.provincia_id}
    m = Municipio(provincia_id=provincia_id, nombre=nombre, activo=True)
    db.add(m); db.commit(); db.refresh(m)
    return {"id": m.id, "nombre": m.nombre, "provincia_id": m.provincia_id}


def crear_centro(db: Session, pais_codigo: str, nombre: str) -> dict:
    nombre = _nombre_limpio(nombre)
    ex = db.query(CentroMedico).filter(CentroMedico.pais_codigo == pais_codigo, CentroMedico.nombre == nombre).first()
    if ex:
        if not ex.activo:
            ex.activo = True; db.commit()
        return {"id": ex.id, "nombre": ex.nombre, "pais_codigo": ex.pais_codigo}
    c = CentroMedico(pais_codigo=pais_codigo, nombre=nombre, activo=True)
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "nombre": c.nombre, "pais_codigo": c.pais_codigo}


def crear_especialidad(db: Session, nombre: str) -> dict:
    nombre = _nombre_limpio(nombre)
    ex = db.query(Especialidad).filter(Especialidad.nombre == nombre).first()
    if ex:
        if not ex.activo:
            ex.activo = True; db.commit()
        return {"id": ex.id, "nombre": ex.nombre}
    e = Especialidad(nombre=nombre, activo=True)
    db.add(e); db.commit(); db.refresh(e)
    return {"id": e.id, "nombre": e.nombre}


_MODELOS = {"provincia": Provincia, "municipio": Municipio, "centro": CentroMedico, "especialidad": Especialidad}


def desactivar(db: Session, tipo: str, id_: int) -> None:
    """Baja lógica (activo=False) de un elemento del catálogo."""
    modelo = _MODELOS.get(tipo)
    if modelo is None:
        raise ValueError("Tipo de catálogo inválido")
    obj = db.query(modelo).filter(modelo.id == id_).first()
    if obj is None:
        raise ValueError("Elemento no encontrado")
    obj.activo = False
    db.commit()


def set_activo(db: Session, tipo: str, id_: int, activo: bool) -> dict:
    """Activa o desactiva (baja lógica) un elemento del catálogo."""
    modelo = _MODELOS.get(tipo)
    if modelo is None:
        raise ValueError("Tipo de catálogo inválido")
    obj = db.query(modelo).filter(modelo.id == id_).first()
    if obj is None:
        raise ValueError("Elemento no encontrado")
    obj.activo = bool(activo)
    db.commit()
    return {"id": obj.id, "activo": obj.activo}


def eliminar_permanente(db: Session, tipo: str, id_: int) -> None:
    """Borrado FÍSICO. Si el elemento está referenciado (FK), lo impide con un mensaje
    claro para que el usuario lo desactive en vez de borrarlo."""
    modelo = _MODELOS.get(tipo)
    if modelo is None:
        raise ValueError("Tipo de catálogo inválido")
    obj = db.query(modelo).filter(modelo.id == id_).first()
    if obj is None:
        raise ValueError("Elemento no encontrado")
    db.delete(obj)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ValueError("No se puede borrar: está en uso (referenciado por médicos u otros registros). Desactívalo en su lugar.")


def renombrar(db: Session, tipo: str, id_: int, nombre: str) -> dict:
    """Corrige el nombre de un elemento del catálogo (edición). Como el nombre se
    almacena por texto en los médicos, este cambio impacta el sistema completo."""
    modelo = _MODELOS.get(tipo)
    if modelo is None:
        raise ValueError("Tipo de catálogo inválido")
    nombre = _nombre_limpio(nombre)
    obj = db.query(modelo).filter(modelo.id == id_).first()
    if obj is None:
        raise ValueError("Elemento no encontrado")
    obj.nombre = nombre
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ValueError("Ya existe otro elemento con ese nombre")
    return {"id": obj.id, "nombre": obj.nombre}
