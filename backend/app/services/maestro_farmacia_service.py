"""Maestro de Farmacias — nombre_completo + anti-dup + alta/edición central.

Espejo de `maestro_medico_service.py`. Reglas (spec `2026-07-22-modulo-farmacias-*`):
  - Nombre visible (F20): `cadena + " " + sucursal` si `es_cadena`, si no `nombre`.
  - Bloqueantes (F23/F24): `direccion` y `encargado` NOT NULL — validación dura.
  - Anti-dup (F25/F09): DURA (bloquea) si ya existe una farmacia del mismo país con
    la misma `(cadena, sucursal)` normalizadas. Sin blando por ahora — la clave
    cadena+sucursal es exacta.
"""
import unicodedata
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Farmacia


class DuplicadoDuroError(Exception):
    def __init__(self, coincidencias):
        self.coincidencias = coincidencias
        super().__init__("Farmacia duplicada (misma cadena y sucursal en el país)")


def normalizar(txt: str | None) -> str:
    if not txt:
        return ""
    s = unicodedata.normalize("NFKD", txt)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split())


def nombre_completo(datos: dict) -> str:
    if datos.get("es_cadena"):
        cadena = datos.get("cadena") or ""
        sucursal = datos.get("sucursal") or ""
        return normalizar(f"{cadena} {sucursal}".strip())
    return normalizar(datos.get("nombre") or "")


def validar_bloqueantes(datos: dict) -> None:
    """F23/F24: dirección y encargado son obligatorios, sin importar el origen."""
    direccion = (datos.get("direccion") or "").strip()
    if not direccion:
        raise ValueError("Debe completar la dirección de la farmacia para poder grabarla.")
    encargado = (datos.get("encargado") or "").strip()
    if not encargado:
        raise ValueError("Debe indicar el nombre del encargado para poder grabar la farmacia.")


def _dto(f: Farmacia) -> dict:
    return {"id": f.id, "cadena": f.cadena, "sucursal": f.sucursal, "nombre": f.nombre,
            "nombre_completo": f.nombre_completo, "estado": f.estado}


def _base(db: Session, pais_codigo: str, excluir_id=None):
    q = db.query(Farmacia).filter(
        Farmacia.pais_codigo == pais_codigo,
        Farmacia.activo == True,  # noqa: E712
        Farmacia.estado != "RECHAZADA",
    )
    if excluir_id:
        q = q.filter(Farmacia.id != excluir_id)
    return q


def detectar_duplicados(db: Session, pais_codigo: str, *, cadena=None, sucursal=None,
                        excluir_id=None) -> dict:
    """DURA (bloquea) = misma `(pais_codigo, cadena, sucursal)` normalizada, sobre
    farmacias activas y no rechazadas. Comparación normalizada en Python (acentos,
    mayúsculas y espacios no distinguen), igual que el patrón de Médicos."""
    norm_cadena = normalizar(cadena)
    norm_sucursal = normalizar(sucursal)
    duros = []
    for f in _base(db, pais_codigo, excluir_id).all():
        if normalizar(f.cadena) == norm_cadena and normalizar(f.sucursal) == norm_sucursal:
            duros.append(_dto(f))
    return {"duros": duros}


def detectar_posibles_duplicados(db: Session, pais_codigo: str, *, nombre_completo: str,
                                 excluir_id=None) -> list[dict]:
    """BLANDA (informativa, NO bloquea): farmacias ACTIVAS del maestro cuyo `nombre_completo`
    normalizado coincide por PREFIJO con el de `nombre_completo` (en cualquier dirección) —
    p.ej. "GBC PANTOJA" vs "GBC PANTOJA 2". Usada en la bandeja del GD (§3.2 del txt) como
    alerta visible junto a la solicitud; no bloquea aprobar/rechazar (a diferencia de
    `detectar_duplicados`, que es DURA y solo corre en el alta)."""
    objetivo = normalizar(nombre_completo)
    if not objetivo:
        return []
    q = db.query(Farmacia).filter(
        Farmacia.pais_codigo == pais_codigo,
        Farmacia.activo == True,  # noqa: E712
        Farmacia.estado == "ACTIVA",
    )
    if excluir_id:
        q = q.filter(Farmacia.id != excluir_id)
    posibles = []
    for f in q.all():
        candidato = normalizar(f.nombre_completo)
        if candidato and (candidato.startswith(objetivo) or objetivo.startswith(candidato)):
            posibles.append(_dto(f))
    return posibles


def _auditar(db: Session, usuario_id, farmacia_id, accion: str, detalle: str) -> None:
    """Deja rastro estructurado en Audit.FACT_Auditoria (fuente del historial de la farmacia)."""
    from app.models.hechos import Auditoria
    db.add(Auditoria(usuario_id=usuario_id, accion=accion, modulo="MAESTRO_FARMACIAS",
                     tabla="DIM_Farmacia", registro_id=str(farmacia_id), detalle=detalle))


def crear_maestro(db: Session, pais_codigo: str, datos: dict, *, origen="VM",
                  estado="PENDIENTE_APROBACION", usuario_id=None) -> Farmacia:
    validar_bloqueantes(datos)

    dups = detectar_duplicados(db, pais_codigo, cadena=datos.get("cadena"),
                               sucursal=datos.get("sucursal"))
    if dups["duros"]:
        raise DuplicadoDuroError(dups["duros"])

    campos = {k: v for k, v in datos.items() if hasattr(Farmacia, k)}
    campos["nombre_completo"] = nombre_completo(datos)
    campos.setdefault("activo", True)
    f = Farmacia(pais_codigo=pais_codigo, origen=origen, estado=estado, **campos)
    db.add(f); db.flush()
    _auditar(db, usuario_id, f.id, "CREATE", f"Alta (origen={origen}, estado={estado})")
    db.commit(); db.refresh(f)
    logger.info(f"Maestro farmacia creado id={f.id} '{f.nombre_completo}' pais={pais_codigo} origen={origen}")
    return f


def actualizar_maestro(db: Session, farmacia: Farmacia, cambios: dict, usuario_id=None) -> Farmacia:
    # Revalida bloqueantes si la edición toca dirección/encargado.
    if "direccion" in cambios or "encargado" in cambios:
        validar_bloqueantes({
            "direccion": cambios.get("direccion", farmacia.direccion),
            "encargado": cambios.get("encargado", farmacia.encargado),
        })

    aplicados = []
    for k, v in cambios.items():
        if hasattr(Farmacia, k) and k not in ("id", "pais_codigo", "created_at"):
            setattr(farmacia, k, v); aplicados.append(k)

    if {"cadena", "sucursal", "nombre", "es_cadena"} & set(cambios):
        farmacia.nombre_completo = nombre_completo({
            "es_cadena": farmacia.es_cadena, "cadena": farmacia.cadena,
            "sucursal": farmacia.sucursal, "nombre": farmacia.nombre,
        })

    farmacia.updated_at = datetime.now(timezone.utc)
    _auditar(db, usuario_id, farmacia.id, "UPDATE", f"Campos: {', '.join(aplicados) or 'ninguno'}")
    db.commit(); db.refresh(farmacia)
    logger.info(f"Maestro farmacia actualizado id={farmacia.id} campos={list(cambios)} por={usuario_id}")
    return farmacia
