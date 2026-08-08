"""Sincroniza las dimensiones que Mallén deja en `ext` con los catálogos de VISTA.

DOS REGLAS QUE NO SE NEGOCIAN
------------------------------
1. **Adoptar antes que crear.** VISTA lleva el piloto con su maestro cargado por
   Excel; sincronizar sin adoptar lo duplicaría entero. Lo resuelve
   `integracion_mapeo.resolver`.
2. **Nunca borrar.** Un registro que desaparece de `ext` conserva hechos
   históricos apuntándole. Se marca inactivo, no se elimina.

Una fila mala no detiene la sincronización: se anota un `Hallazgo` y se sigue,
mismo criterio que la validación de lotes (§7.1 del contrato).
"""
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Ciclo, Gerente, Linea, Pais, RepresentanteMedico
from app.models.integracion_ext import (
    ExtDimCiclo, ExtDimGerente, ExtDimLinea, ExtDimPais, ExtDimRepresentante,
)
from app.models.mapeo_externo import (
    ENT_CICLO, ENT_GERENTE, ENT_LINEA, ENT_PAIS, ENT_REPRESENTANTE,
)
from app.services import integracion_mapeo as mapeo

SEVERIDAD_ERROR = "error"
SEVERIDAD_AVISO = "aviso"


@dataclass
class Hallazgo:
    entidad: str
    codigo_externo: str
    problema: str
    severidad: str


@dataclass
class Conteo:
    entidad: str
    en_ext: int = 0
    creados: int = 0
    adoptados: int = 0
    actualizados: int = 0
    omitidos: int = 0

    def anotar(self, resultado: str) -> None:
        if resultado == mapeo.RESULTADO_CREADO:
            self.creados += 1
        elif resultado == mapeo.RESULTADO_ADOPTADO:
            self.adoptados += 1
        else:
            self.actualizados += 1


def _cabe(valor: str, largo: int) -> bool:
    return len(valor) <= largo


def _omitir_por_largo(conteo: Conteo, hallazgos: list, entidad: str,
                      codigo: str, columna: str, largo: int) -> None:
    """Un código que no cabe se omite, NO se trunca: dos códigos distintos que
    compartan los primeros N caracteres colapsarían en uno solo."""
    conteo.omitidos += 1
    hallazgos.append(Hallazgo(
        entidad, codigo,
        f"El código excede los {largo} caracteres de {columna}; la fila se omitió.",
        SEVERIDAD_ERROR))


def sincronizar_pais(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """El país es la raíz: sin él ninguna otra dimensión resuelve."""
    conteo = Conteo(ENT_PAIS)
    filas = (db.query(ExtDimPais)
             .filter(ExtDimPais.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        def _buscar(f=fila):
            return db.query(Pais).filter(Pais.codigo == f.pais_codigo).first()

        def _crear(f=fila):
            nuevo = Pais(codigo=f.pais_codigo, nombre=f.nombre,
                         moneda=f.moneda, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_PAIS, pais_codigo, fila.pais_codigo, Pais, _buscar, _crear)
        registro.nombre = fila.nombre
        registro.moneda = fila.moneda
        registro.activo = fila.activo
        conteo.anotar(resultado)
    return conteo


def sincronizar_linea(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    conteo = Conteo(ENT_LINEA)
    filas = (db.query(ExtDimLinea)
             .filter(ExtDimLinea.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not _cabe(fila.linea_codigo, 20):
            _omitir_por_largo(conteo, hallazgos, ENT_LINEA, fila.linea_codigo,
                              "DIM_Linea.codigo", 20)
            continue

        def _buscar(f=fila):
            return (db.query(Linea)
                    .filter(Linea.pais_codigo == f.pais_codigo,
                            Linea.codigo == f.linea_codigo).first())

        def _crear(f=fila):
            nuevo = Linea(pais_codigo=f.pais_codigo, codigo=f.linea_codigo,
                          nombre=f.nombre, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_LINEA, pais_codigo, fila.linea_codigo, Linea, _buscar, _crear)
        registro.nombre = fila.nombre
        registro.activo = fila.activo
        conteo.anotar(resultado)
    return conteo


def sincronizar_gerente(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """`DIM_Gerente.codigo` es único GLOBAL, mientras que en `ext` lo es por
    país: dos países con el mismo código colisionan y el segundo se omite."""
    conteo = Conteo(ENT_GERENTE)
    filas = (db.query(ExtDimGerente)
             .filter(ExtDimGerente.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not _cabe(fila.gerente_codigo, 20):
            _omitir_por_largo(conteo, hallazgos, ENT_GERENTE, fila.gerente_codigo,
                              "DIM_Gerente.codigo", 20)
            continue
        linea_id = (mapeo.id_mapeado(db, ENT_LINEA, pais_codigo, fila.linea_codigo)
                    if fila.linea_codigo else None)

        def _buscar(f=fila):
            return db.query(Gerente).filter(Gerente.codigo == f.gerente_codigo).first()

        def _crear(f=fila, lid=linea_id):
            nuevo = Gerente(pais_codigo=f.pais_codigo, codigo=f.gerente_codigo,
                            nombre=f.nombre, tipo=f.tipo, email=f.email,
                            linea_id=lid, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        existente = db.query(Gerente).filter(
            Gerente.codigo == fila.gerente_codigo).first()
        if existente is not None and existente.pais_codigo != pais_codigo:
            conteo.omitidos += 1
            hallazgos.append(Hallazgo(
                ENT_GERENTE, fila.gerente_codigo,
                f"El código ya existe en el país {existente.pais_codigo} y "
                f"DIM_Gerente.codigo es único global; la fila se omitió.",
                SEVERIDAD_ERROR))
            continue

        registro, resultado = mapeo.resolver(
            db, ENT_GERENTE, pais_codigo, fila.gerente_codigo, Gerente,
            _buscar, _crear)
        registro.nombre = fila.nombre
        registro.tipo = fila.tipo
        registro.email = fila.email
        registro.activo = fila.activo
        if linea_id is not None:
            registro.linea_id = linea_id
        conteo.anotar(resultado)
    return conteo


def sincronizar_representante(db: Session, pais_codigo: str,
                              hallazgos: list) -> Conteo:
    """`DIM_RM.linea_id` es NOT NULL: sin línea resuelta la fila se omite."""
    conteo = Conteo(ENT_REPRESENTANTE)
    filas = (db.query(ExtDimRepresentante)
             .filter(ExtDimRepresentante.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not _cabe(fila.rm_codigo, 20):
            _omitir_por_largo(conteo, hallazgos, ENT_REPRESENTANTE, fila.rm_codigo,
                              "DIM_RM.codigo", 20)
            continue
        linea_id = (mapeo.id_mapeado(db, ENT_LINEA, pais_codigo, fila.linea_codigo)
                    if fila.linea_codigo else None)
        if linea_id is None:
            conteo.omitidos += 1
            hallazgos.append(Hallazgo(
                ENT_REPRESENTANTE, fila.rm_codigo,
                f"No se pudo resolver la línea «{fila.linea_codigo}», que es "
                f"obligatoria en DIM_RM; la fila se omitió.", SEVERIDAD_ERROR))
            continue
        gerente_id = (mapeo.id_mapeado(db, ENT_GERENTE, pais_codigo,
                                       fila.gerente_codigo)
                      if fila.gerente_codigo else None)

        def _buscar(f=fila):
            return (db.query(RepresentanteMedico)
                    .filter(RepresentanteMedico.codigo == f.rm_codigo).first())

        def _crear(f=fila, lid=linea_id, gid=gerente_id):
            nuevo = RepresentanteMedico(
                pais_codigo=f.pais_codigo, codigo=f.rm_codigo, nombre=f.nombre,
                linea_id=lid, gerente_id=gid, cedula=f.cedula, email=f.email,
                zona=f.zona, fecha_ingreso=f.fecha_ingreso, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_REPRESENTANTE, pais_codigo, fila.rm_codigo,
            RepresentanteMedico, _buscar, _crear)
        registro.nombre = fila.nombre
        registro.linea_id = linea_id
        registro.cedula = fila.cedula
        registro.email = fila.email
        registro.zona = fila.zona
        registro.fecha_ingreso = fila.fecha_ingreso
        registro.activo = fila.activo
        if gerente_id is not None:
            registro.gerente_id = gerente_id
        conteo.anotar(resultado)
    return conteo


def sincronizar_ciclo(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """El ciclo se identifica por (país, año, número): `DIM_Ciclo` no tiene código.

    `cerrado` NO se sincroniza NUNCA (decisión del cliente): de él dependen los
    recálculos y los premios, y un envío externo no debe reabrir un ciclo cerrado
    ni cerrar el que está en curso. Si difiere, se avisa y manda VISTA.
    """
    conteo = Conteo(ENT_CICLO)
    filas = (db.query(ExtDimCiclo)
             .filter(ExtDimCiclo.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        def _buscar(f=fila):
            return (db.query(Ciclo)
                    .filter(Ciclo.pais_codigo == f.pais_codigo,
                            Ciclo.anio == f.anio, Ciclo.numero == f.numero)
                    .first())

        def _crear(f=fila):
            nuevo = Ciclo(pais_codigo=f.pais_codigo, anio=f.anio, numero=f.numero,
                          nombre=f.nombre or f.ciclo_codigo,
                          nombre_canonico=f.ciclo_codigo,
                          fecha_inicio=f.fecha_inicio, fecha_fin=f.fecha_fin,
                          dias_laborables=f.dias_laborables, cerrado=False)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_CICLO, pais_codigo, fila.ciclo_codigo, Ciclo, _buscar, _crear)
        registro.nombre = fila.nombre or fila.ciclo_codigo
        registro.fecha_inicio = fila.fecha_inicio
        registro.fecha_fin = fila.fecha_fin
        registro.dias_laborables = fila.dias_laborables
        if not registro.nombre_canonico:
            registro.nombre_canonico = fila.ciclo_codigo
        if fila.cerrado != registro.cerrado:
            hallazgos.append(Hallazgo(
                ENT_CICLO, fila.ciclo_codigo,
                f"El ciclo viene como cerrado={fila.cerrado} y en VISTA está "
                f"cerrado={registro.cerrado}. El estado del ciclo lo decide "
                f"VISTA: no se modificó.", SEVERIDAD_AVISO))
        conteo.anotar(resultado)
    return conteo
