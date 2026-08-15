"""Asignación de países a usuarios y de líneas a gerentes.

`fijar_*` REEMPLAZA el conjunto completo, no añade. Con un endpoint que solo
agrega, revocar un acceso exigiría un DELETE aparte — y un permiso de más nunca
se manifiesta como error: simplemente funciona, hasta que alguien ve lo que no
debía.
"""
from sqlalchemy.orm import Session

from app.models.alcance import GerenteLinea, UsuarioPais


def paises_de(db: Session, usuario_id: int) -> set[str]:
    return {r[0] for r in db.query(UsuarioPais.pais_codigo)
            .filter(UsuarioPais.usuario_id == usuario_id).all()}


def fijar_paises(db: Session, usuario_id: int, codigos: list[str]) -> set[str]:
    db.query(UsuarioPais).filter(UsuarioPais.usuario_id == usuario_id).delete()
    for c in sorted(set(codigos)):
        db.add(UsuarioPais(usuario_id=usuario_id, pais_codigo=c))
    db.flush()
    return set(codigos)


def lineas_de(db: Session, gerente_id: int) -> set[int]:
    return {r[0] for r in db.query(GerenteLinea.linea_id)
            .filter(GerenteLinea.gerente_id == gerente_id).all()}


def fijar_lineas(db: Session, gerente_id: int, linea_ids: list[int]) -> set[int]:
    db.query(GerenteLinea).filter(GerenteLinea.gerente_id == gerente_id).delete()
    for lid in sorted(set(linea_ids)):
        db.add(GerenteLinea(gerente_id=gerente_id, linea_id=lid))
    db.flush()
    return set(linea_ids)
