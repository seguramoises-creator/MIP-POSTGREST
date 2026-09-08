"""Biblioteca de material con lectura obligatoria (§5).

Antes de este módulo VISTA solo generaba exámenes. El cliente pidió poder subir
MATERIAL de estudio y **obligar al representante a confirmar que lo leyó antes
de habilitar el examen correspondiente**. Ese bloqueo es la razón de ser del
módulo: sin él, la Biblioteca sería un repositorio de archivos más.

Un mismo archivo se sube UNA vez y sirve en tres lugares (§4.3): alimenta la
generación del examen, la Biblioteca del representante y la Ayuda Visual que ya
usa Coaching. Duplicarlo por cada uso los desincronizaría en cuanto alguien
actualice una versión.
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.formacion import (
    BibliotecaConfirmacion, BibliotecaMaterial, ProductoLinea,
)

TIPOS_MATERIAL = ("manual", "ayuda_visual", "estudio_clinico", "ficha_tecnica", "video")


class MaterialNoAprobado(RuntimeError):
    """Firewall PhRMA (§2): el contenido científico no llega al representante
    hasta que Gerente Médico lo aprueba."""


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Gestión (Capacitación / Gerente Médico)
# ---------------------------------------------------------------------------

def subir_material(db: Session, datos: dict, actor=None) -> BibliotecaMaterial:
    """Registra un material. `obligatorio` viene activado por defecto (§5.3):
    el cliente pidió que la lectura obligatoria sea la norma, no la excepción."""
    if datos.get("tipo") not in TIPOS_MATERIAL:
        raise ValueError(
            f"Tipo de material inválido. Use uno de: {', '.join(TIPOS_MATERIAL)}.")
    m = BibliotecaMaterial(
        pais_codigo=datos["pais_codigo"],
        producto_id=datos.get("producto_id"),
        titulo=datos["titulo"],
        tipo=datos["tipo"],
        archivo_url=datos["archivo_url"],
        obligatorio=datos.get("obligatorio", True),
        usado_en_examen_id=datos.get("usado_en_examen_id"),
        usado_en_coaching_av=datos.get("usado_en_coaching_av", False),
        subido_por=getattr(actor, "id", None))
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def aprobar_material(db: Session, material_id: int, actor=None) -> BibliotecaMaterial:
    """Aprobación de Gerente Médico. Es lo que libera el material a los RM."""
    m = db.get(BibliotecaMaterial, material_id)
    if m is None:
        raise ValueError("Material no encontrado")
    m.aprobado_por_gm = True
    m.aprobado_por = getattr(actor, "id", None)
    db.commit()
    db.refresh(m)
    return m


def listar_materiales(db: Session, pais_codigo: str, producto_id: int | None = None,
                      solo_aprobados: bool = False) -> list[BibliotecaMaterial]:
    q = (db.query(BibliotecaMaterial)
         .filter(BibliotecaMaterial.pais_codigo == pais_codigo,
                 BibliotecaMaterial.activo.is_(True)))
    if producto_id is not None:
        q = q.filter(BibliotecaMaterial.producto_id == producto_id)
    if solo_aprobados:
        q = q.filter(BibliotecaMaterial.aprobado_por_gm.is_(True))
    return q.order_by(BibliotecaMaterial.titulo).all()


# ---------------------------------------------------------------------------
# Lectura obligatoria (Representante)
# ---------------------------------------------------------------------------

def materiales_obligatorios(db: Session, producto_ids: list[int]) -> list[BibliotecaMaterial]:
    """Los que bloquean un examen.

    Solo cuentan los APROBADOS por Gerente Médico: exigirle a un representante
    confirmar un material que todavía no pasó el firewall sería bloquearlo por
    algo que no puede resolver.
    """
    if not producto_ids:
        return []
    return (db.query(BibliotecaMaterial)
            .filter(BibliotecaMaterial.producto_id.in_(producto_ids),
                    BibliotecaMaterial.obligatorio.is_(True),
                    BibliotecaMaterial.activo.is_(True),
                    BibliotecaMaterial.aprobado_por_gm.is_(True))
            .all())


def confirmar_lectura(db: Session, material_id: int, rm_id: int) -> BibliotecaConfirmacion:
    """El representante declara haber leído un material.

    Es idempotente: volver a confirmar devuelve la confirmación original con su
    fecha, sin crear otra. El único de la tabla ya lo impide a nivel de base,
    pero resolverlo aquí evita que un doble clic acabe en un error 500.

    La marca de tiempo la pone el SERVIDOR (§5.5), como `fecha_coaching`: es
    prueba de cumplimiento y no puede depender del reloj del cliente.
    """
    m = db.get(BibliotecaMaterial, material_id)
    if m is None:
        raise ValueError("Material no encontrado")
    if m.obligatorio and not m.aprobado_por_gm:
        raise MaterialNoAprobado(
            f"«{m.titulo}» todavía no fue aprobado por Gerencia Médica y no "
            "está disponible para lectura.")
    existente = (db.query(BibliotecaConfirmacion)
                 .filter(BibliotecaConfirmacion.material_id == material_id,
                         BibliotecaConfirmacion.rm_id == rm_id)
                 .first())
    if existente is not None:
        return existente
    c = BibliotecaConfirmacion(material_id=material_id, rm_id=rm_id,
                               timestamp_confirmacion=_ahora())
    db.add(c)
    db.commit()
    db.refresh(c)
    # §5.4: Capacitación se entera al instante. La vista de "quién ya confirmó"
    # (`confirmaciones_de_material`) es en vivo, así que el registro basta para
    # que el dato esté disponible sin recargar nada.
    logger.info(f"Biblioteca: RM {rm_id} confirmó lectura del material "
                f"{material_id} ({m.titulo})")
    return c


def progreso_lectura(db: Session, rm_id: int, producto_ids: list[int]) -> dict:
    """Lo que el representante ve: "2 de 4 confirmados" y QUÉ le falta (§5.3).

    Devuelve los pendientes por nombre, no solo el conteo: decirle a alguien que
    le faltan dos sin decirle cuáles lo obliga a adivinar.
    """
    obligatorios = materiales_obligatorios(db, producto_ids)
    if not obligatorios:
        return {"total": 0, "confirmados": 0, "completo": True, "pendientes": []}
    ids = [m.id for m in obligatorios]
    confirmados = {c.material_id for c in
                   db.query(BibliotecaConfirmacion)
                   .filter(BibliotecaConfirmacion.rm_id == rm_id,
                           BibliotecaConfirmacion.material_id.in_(ids))
                   .all()}
    pendientes = [{"id": m.id, "titulo": m.titulo, "tipo": m.tipo}
                  for m in obligatorios if m.id not in confirmados]
    return {
        "total": len(obligatorios),
        "confirmados": len(obligatorios) - len(pendientes),
        "completo": not pendientes,
        "pendientes": pendientes,
    }


def confirmaciones_de_material(db: Session, material_id: int) -> list[dict]:
    """Quién ya confirmó un material (§5.4). Es la vista en vivo que consulta
    Capacitación."""
    filas = (db.query(BibliotecaConfirmacion)
             .filter(BibliotecaConfirmacion.material_id == material_id)
             .order_by(BibliotecaConfirmacion.timestamp_confirmacion.desc())
             .all())
    return [{"rm_id": f.rm_id, "confirmado_en": f.timestamp_confirmacion} for f in filas]


# ---------------------------------------------------------------------------
# Productos de la línea (§4.3)
# ---------------------------------------------------------------------------

def productos_de_linea(db: Session, pais_codigo: str, linea_id: int,
                       solo_principales: bool = False) -> list[ProductoLinea]:
    q = (db.query(ProductoLinea)
         .filter(ProductoLinea.pais_codigo == pais_codigo,
                 ProductoLinea.linea_id == linea_id,
                 ProductoLinea.activo.is_(True)))
    if solo_principales:
        q = q.filter(ProductoLinea.rol_en_ruta == "principal")
    return q.order_by(ProductoLinea.nombre_producto).all()
