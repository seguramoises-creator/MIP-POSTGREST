"""Asignación de países a usuarios y de líneas a gerentes.

`fijar_*` REEMPLAZA el conjunto completo, no añade. Con un endpoint que solo
agrega, revocar un acceso exigiría un DELETE aparte — y un permiso de más nunca
se manifiesta como error: simplemente funciona, hasta que alguien ve lo que no
debía.

Ambos `fijar_*` VALIDAN el conjunto contra su catálogo ANTES de tocar la tabla
(antes del `delete`, no solo antes del `insert`): un típo debe rechazarse al
guardarlo, no dejar al usuario con el conjunto anterior borrado y nada válido en
su lugar. La garantía vive aquí, en el servicio, no solo en el router — así la
hereda cualquier otro llamador (una carga masiva, un script).
"""
from sqlalchemy.orm import Session

from app.models.alcance import GerenteLinea, UsuarioPais
from app.models.dimensiones import Linea, Pais


class AlcanceInvalidoError(ValueError):
    """Se intentó fijar un código de país o un id de línea que no existe en su catálogo."""


def paises_de(db: Session, usuario_id: int) -> set[str]:
    return {r[0] for r in db.query(UsuarioPais.pais_codigo)
            .filter(UsuarioPais.usuario_id == usuario_id).all()}


def fijar_paises(db: Session, usuario_id: int, codigos: list[str]) -> set[str]:
    """`Security.FACT_UsuarioPais.pais_codigo` es un `String(10)` SIN clave foránea hacia
    `Config.DIM_Pais` (se guarda el código suelto). Sin esta validación, un típo como "D0"
    en vez de "DO" se guardaría sin queja: `paises_visibles` devolvería un conjunto NO
    vacío que nunca coincide con ningún país real, y el usuario dejaría de ver
    absolutamente todo — sin ninguna excepción que avise que algo salió mal."""
    deseados = set(codigos)
    if deseados:
        existentes = {r[0] for r in db.query(Pais.codigo).filter(Pais.codigo.in_(deseados)).all()}
        faltantes = deseados - existentes
        if faltantes:
            raise AlcanceInvalidoError(
                f"País(es) inexistente(s) en el catálogo: {', '.join(sorted(faltantes))}")
    # La validación va ANTES del delete: un conjunto inválido no debe borrar el
    # vigente. Si el `raise` de arriba no detuvo la ejecución, no llegamos aquí.
    db.query(UsuarioPais).filter(UsuarioPais.usuario_id == usuario_id).delete()
    for c in sorted(deseados):
        db.add(UsuarioPais(usuario_id=usuario_id, pais_codigo=c))
    db.flush()
    return set(codigos)


def lineas_de(db: Session, gerente_id: int) -> set[int]:
    return {r[0] for r in db.query(GerenteLinea.linea_id)
            .filter(GerenteLinea.gerente_id == gerente_id).all()}


def fijar_lineas(db: Session, gerente_id: int, linea_ids: list[int]) -> set[int]:
    """`Config.DIM_GerenteLinea.linea_id` SÍ tiene clave foránea hacia `DIM_Linea`, pero sin
    validar antes, un id inexistente llegaría hasta el `commit` como `IntegrityError` sin
    manejar (500 genérico, sin decir qué id falló). Validar aquí, antes del `delete`, deja
    que el router responda 422 con el detalle — y protege el conjunto vigente del mismo
    modo que `fijar_paises`."""
    deseados = set(linea_ids)
    if deseados:
        existentes = {r[0] for r in db.query(Linea.id).filter(Linea.id.in_(deseados)).all()}
        faltantes = deseados - existentes
        if faltantes:
            raise AlcanceInvalidoError(
                f"Línea(s) inexistente(s) en el catálogo: "
                f"{', '.join(str(x) for x in sorted(faltantes))}")
    db.query(GerenteLinea).filter(GerenteLinea.gerente_id == gerente_id).delete()
    for lid in sorted(deseados):
        db.add(GerenteLinea(gerente_id=gerente_id, linea_id=lid))
    db.flush()
    return set(linea_ids)
