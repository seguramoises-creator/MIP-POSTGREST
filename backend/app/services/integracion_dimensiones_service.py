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
from app.models.dimensiones import (
    CentroMedico, Especialidad, Farmacia, Medico, Municipio, Producto, Provincia,
)
from app.models.integracion_ext import (
    ExtDimCiclo, ExtDimGerente, ExtDimLinea, ExtDimPais, ExtDimRepresentante,
)
from app.models.integracion_ext import (
    ExtDimEspecialidad, ExtDimFarmacia, ExtDimMedico, ExtDimProducto,
)
from app.models.mapeo_externo import (
    ENT_CICLO, ENT_GERENTE, ENT_LINEA, ENT_PAIS, ENT_REPRESENTANTE,
)
from app.models.mapeo_externo import (
    ENT_ESPECIALIDAD, ENT_FARMACIA, ENT_MEDICO, ENT_PRODUCTO,
)
from app.models.mapeo_externo import ENTIDADES, MapeoExterno
from app.services import integracion_mapeo as mapeo
from app.services import maestro_farmacia_service, maestro_medico_service

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
    """Un valor que no cabe se omite, NO se trunca: truncar podría colapsar dos
    filas distintas en una sola clave, o cortar un nombre a la mitad. Cubre
    tanto códigos (identidad) como nombres/textos largos (I4): `codigo` siempre
    es el identificador externo de la fila, para que el hallazgo sea rastreable
    aunque el campo que desbordó sea otro."""
    conteo.omitidos += 1
    hallazgos.append(Hallazgo(
        entidad, codigo,
        f"El valor excede los {largo} caracteres de {columna}; la fila se omitió.",
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
    """`DIM_RM.linea_id` es NOT NULL: sin línea resuelta la fila se omite.

    `DIM_RM.codigo` es único GLOBAL, igual que `DIM_Gerente.codigo` (I3): sin
    este guard, un `VM01` de otro país secuestraría al `VM01` dominicano —le
    pisaría nombre y `linea_id` con los de la línea del otro país— porque
    `_buscar` encuentra por código sin filtrar por país. Mismo criterio que
    `sincronizar_gerente`.
    """
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

        existente = db.query(RepresentanteMedico).filter(
            RepresentanteMedico.codigo == fila.rm_codigo).first()
        if existente is not None and existente.pais_codigo != pais_codigo:
            conteo.omitidos += 1
            hallazgos.append(Hallazgo(
                ENT_REPRESENTANTE, fila.rm_codigo,
                f"El código ya existe en el país {existente.pais_codigo} y "
                f"DIM_RM.codigo es único global; la fila se omitió.",
                SEVERIDAD_ERROR))
            continue

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
        # `DIM_Ciclo.nombre` es String(50) y `ext.dimciclo.nombre` permite 100;
        # el valor que realmente se escribe es `fila.nombre or fila.ciclo_codigo`
        # (I4) — hay que medir ESE valor, no `fila.nombre` a secas.
        nombre_valor = fila.nombre or fila.ciclo_codigo
        if not _cabe(nombre_valor, 50):
            _omitir_por_largo(conteo, hallazgos, ENT_CICLO, fila.ciclo_codigo,
                              "DIM_Ciclo.nombre", 50)
            continue

        def _buscar(f=fila):
            return (db.query(Ciclo)
                    .filter(Ciclo.pais_codigo == f.pais_codigo,
                            Ciclo.anio == f.anio, Ciclo.numero == f.numero)
                    .first())

        def _crear(f=fila, nv=nombre_valor):
            nuevo = Ciclo(pais_codigo=f.pais_codigo, anio=f.anio, numero=f.numero,
                          nombre=nv, nombre_canonico=f.ciclo_codigo,
                          fecha_inicio=f.fecha_inicio, fecha_fin=f.fecha_fin,
                          dias_laborables=f.dias_laborables, cerrado=False)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_CICLO, pais_codigo, fila.ciclo_codigo, Ciclo, _buscar, _crear)
        registro.nombre = nombre_valor
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


def _norm(texto: str | None) -> str:
    """Nombre normalizado para emparejar catálogos que se identifican por texto."""
    return (texto or "").strip().casefold()


def sincronizar_especialidad(db: Session, pais_codigo: str,
                             hallazgos: list) -> Conteo:
    """`DIM_Especialidad` no tiene código ni país: su identidad es el nombre.

    Por eso el mapeo se guarda con `pais_codigo=""` — es el único catálogo
    compartido entre países, igual que en el contrato.
    """
    conteo = Conteo(ENT_ESPECIALIDAD)
    filas = db.query(ExtDimEspecialidad).all()
    conteo.en_ext = len(filas)
    for fila in filas:
        def _buscar(f=fila):
            objetivo = _norm(f.nombre)
            for e in db.query(Especialidad).all():
                if _norm(e.nombre) == objetivo:
                    return e
            return None

        def _crear(f=fila):
            nuevo = Especialidad(nombre=f.nombre.strip(), activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_ESPECIALIDAD, "", fila.especialidad_codigo, Especialidad,
            _buscar, _crear)
        registro.activo = fila.activo
        conteo.anotar(resultado)
    return conteo


def _provincia_id(db: Session, pais_codigo: str, nombre: str | None) -> int | None:
    if not _norm(nombre):
        return None
    objetivo = _norm(nombre)
    for p in db.query(Provincia).filter(Provincia.pais_codigo == pais_codigo).all():
        if _norm(p.nombre) == objetivo:
            return p.id
    nueva = Provincia(pais_codigo=pais_codigo, nombre=nombre.strip())
    db.add(nueva)
    db.flush()
    return nueva.id


def _municipio_id(db: Session, provincia_id: int | None,
                  nombre: str | None) -> int | None:
    """`DIM_Municipio` cuelga de la provincia, no del país: sin provincia
    resuelta no se puede crear el municipio."""
    if provincia_id is None or not _norm(nombre):
        return None
    objetivo = _norm(nombre)
    for m in db.query(Municipio).filter(Municipio.provincia_id == provincia_id).all():
        if _norm(m.nombre) == objetivo:
            return m.id
    nuevo = Municipio(provincia_id=provincia_id, nombre=nombre.strip())
    db.add(nuevo)
    db.flush()
    return nuevo.id


def _centro_medico_id(db: Session, pais_codigo: str, nombre: str | None,
                      provincia_id: int | None,
                      municipio_id: int | None) -> int | None:
    if not _norm(nombre):
        return None
    objetivo = _norm(nombre)
    for c in db.query(CentroMedico).filter(
            CentroMedico.pais_codigo == pais_codigo).all():
        if _norm(c.nombre) == objetivo:
            return c.id
    nuevo = CentroMedico(pais_codigo=pais_codigo, nombre=nombre.strip(),
                         provincia_id=provincia_id, municipio_id=municipio_id)
    db.add(nuevo)
    db.flush()
    return nuevo.id


def sincronizar_medico(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """`ext` trae centro, provincia y municipio como texto; `DIM_Medico` los
    referencia por clave foránea. Se resuelven por nombre y se crean si faltan:
    son catálogos auxiliares sin identidad propia en el contrato, y descartar el
    dato sería peor que crearlos.

    La adopción por exequátur va después de la del código porque el exequátur es
    el identificador profesional: si el código de Mallén no coincide pero el
    exequátur sí, es la misma persona.

    TERCER intento (C1): `DIM_Medico` tiene DOS identidades (ver docstring de
    `Medico` en `app/models/dimensiones.py`) — universo Cobertura, por
    (pais_codigo, codigo); y universo Categorización/Panel del VM, por
    (pais_codigo, nombre, centro_medico_id), con `codigo` NULL. Sin este tercer
    intento, un médico ya cargado por Excel para Categorización nunca se
    encuentra por código ni por exequátur (no los tiene) y se duplica — y si el
    centro coincide, la creación viola `UQ_Medico_Pais_Nombre_Centro` y revienta
    la sincronización de las nueve dimensiones. Compara por nombre normalizado
    (`maestro_medico_service.normalizar_nombre`, que además de mayúsculas quita
    acentos y colapsa espacios — el `_norm` de este módulo no) restringido al
    mismo `centro_medico_id` ya resuelto (o a `centro_medico_id IS NULL` si no
    hay centro).
    """
    conteo = Conteo(ENT_MEDICO)
    filas = (db.query(ExtDimMedico)
             .filter(ExtDimMedico.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        provincia_id = _provincia_id(db, pais_codigo, fila.provincia)
        municipio_id = _municipio_id(db, provincia_id, fila.municipio)
        if fila.municipio and provincia_id is None:
            # M7: `_municipio_id` devuelve None en silencio cuando falta la
            # provincia; contra la filosofía del módulo ("anotar y seguir"),
            # se deja constancia en vez de perder el dato sin avisar.
            hallazgos.append(Hallazgo(
                ENT_MEDICO, fila.medico_codigo,
                f"El municipio «{fila.municipio}» no se pudo resolver porque no "
                f"llegó provincia; el médico se sincronizó sin municipio.",
                SEVERIDAD_AVISO))
        centro_id = _centro_medico_id(db, pais_codigo, fila.centro_trabajo,
                                      provincia_id, municipio_id)
        especialidad_id = (
            mapeo.id_mapeado(db, ENT_ESPECIALIDAD, "", fila.especialidad_codigo)
            if fila.especialidad_codigo else None)

        def _buscar(f=fila, cid=centro_id):
            por_codigo = (db.query(Medico)
                          .filter(Medico.pais_codigo == f.pais_codigo,
                                  Medico.codigo == f.medico_codigo).first())
            if por_codigo is not None:
                return por_codigo
            if f.exequatur:
                por_exequatur = (db.query(Medico)
                                  .filter(Medico.pais_codigo == f.pais_codigo,
                                          Medico.exequatur == f.exequatur).first())
                if por_exequatur is not None:
                    return por_exequatur
            objetivo = maestro_medico_service.normalizar_nombre(f.nombre)
            candidatos = db.query(Medico).filter(Medico.pais_codigo == f.pais_codigo)
            candidatos = (candidatos.filter(Medico.centro_medico_id == cid)
                          if cid is not None
                          else candidatos.filter(Medico.centro_medico_id.is_(None)))
            for candidato in candidatos.all():
                if maestro_medico_service.normalizar_nombre(candidato.nombre) == objetivo:
                    return candidato
            return None

        def _crear(f=fila, eid=especialidad_id, cid=centro_id,
                   pid=provincia_id, mid=municipio_id):
            nuevo = Medico(pais_codigo=f.pais_codigo, codigo=f.medico_codigo,
                           nombre=f.nombre, especialidad_id=eid,
                           centro_medico_id=cid, provincia_id=pid,
                           municipio_id=mid, exequatur=f.exequatur,
                           activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_MEDICO, pais_codigo, fila.medico_codigo, Medico,
            _buscar, _crear)
        registro.nombre = fila.nombre
        registro.activo = fila.activo
        if fila.exequatur:
            registro.exequatur = fila.exequatur
        # El código de Mallén se adopta también en el registro interno cuando
        # este no tenía ninguno: así los dos universos de médicos convergen.
        if not registro.codigo:
            registro.codigo = fila.medico_codigo
        if especialidad_id is not None:
            registro.especialidad_id = especialidad_id
        if centro_id is not None:
            registro.centro_medico_id = centro_id
        if provincia_id is not None:
            registro.provincia_id = provincia_id
        if municipio_id is not None:
            registro.municipio_id = municipio_id
        conteo.anotar(resultado)
    return conteo


def sincronizar_farmacia(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """`DIM_Farmacia` exige `direccion` y `encargado` (NOT NULL) que `ext` no
    envía: se crean vacíos para completarse en VISTA, y al re-sincronizar NO se
    pisan — son datos que VISTA enriqueció y Mallén no conoce.

    Entra con `origen='CONFIG'` y `estado='APROBADA'`: viene del maestro oficial,
    no de un representante solicitando un alta que un gerente deba aprobar.

    La adopción compara `nombre_completo` normalizado con
    `maestro_farmacia_service.normalizar` en AMBOS lados (C2): ese normalizador
    —a diferencia del `_norm` de este módulo— también quita acentos, y en
    República Dominicana un nombre con tilde (`'Farmacia San José'`) es la
    norma, no el caso de borde; compararlo tal cual contra el
    `'FARMACIA SAN JOSE'` que guarda el maestro nunca empataría y duplicaría la
    farmacia en cada corrida.
    """
    conteo = Conteo(ENT_FARMACIA)
    filas = (db.query(ExtDimFarmacia)
             .filter(ExtDimFarmacia.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if fila.provincia and not _cabe(fila.provincia, 100):
            _omitir_por_largo(conteo, hallazgos, ENT_FARMACIA, fila.farmacia_codigo,
                              "DIM_Farmacia.provincia", 100)
            continue
        if fila.municipio and not _cabe(fila.municipio, 100):
            _omitir_por_largo(conteo, hallazgos, ENT_FARMACIA, fila.farmacia_codigo,
                              "DIM_Farmacia.municipio", 100)
            continue

        def _buscar(f=fila):
            objetivo = maestro_farmacia_service.normalizar(f.nombre)
            for far in db.query(Farmacia).filter(
                    Farmacia.pais_codigo == f.pais_codigo).all():
                if maestro_farmacia_service.normalizar(far.nombre_completo) == objetivo:
                    return far
            return None

        def _crear(f=fila):
            nueva = Farmacia(
                pais_codigo=f.pais_codigo, es_cadena=False, nombre=f.nombre,
                nombre_completo=f.nombre, direccion="", encargado="",
                provincia=f.provincia, municipio=f.municipio,
                estado="APROBADA", origen="CONFIG")
            db.add(nueva)
            db.flush()
            return nueva

        registro, resultado = mapeo.resolver(
            db, ENT_FARMACIA, pais_codigo, fila.farmacia_codigo, Farmacia,
            _buscar, _crear)
        # `nombre`/`nombre_completo` SOLO se fijan arriba, en `_crear` (I5). El
        # maestro los guarda normalizados, y si `es_cadena=True` se DERIVAN de
        # `cadena`+`sucursal` — no del nombre libre de `ext`. Pisarlos en cada
        # sincronización (incluidas las filas adoptadas/actualizadas) degradaría
        # la propia detección de duplicados de C2 y la presentación en el panel
        # del VM.
        if fila.provincia:
            registro.provincia = fila.provincia
        if fila.municipio:
            registro.municipio = fila.municipio
        registro.activo = fila.activo  # M6: única de las nueve que no lo propagaba
        conteo.anotar(resultado)
    return conteo


def sincronizar_producto(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """Los campos propios de VISTA (`area_terapeutica`, `segmento_target`,
    `meta_muestras_visita`, `gerente_producto`) NO se tocan: `ext` no los conoce
    y pisarlos borraría configuración hecha en VISTA.

    `DIM_Producto.codigo` es único GLOBAL y, a diferencia de RM/Gerente, la
    tabla no tiene columna de país para detectar la colisión directamente (I3).
    En su lugar se mira el mapeo: si el producto ya está mapeado a OTRO país,
    es la misma colisión —un país repisando el `linea_id` de otro— y se omite
    igual que en `sincronizar_representante`/`sincronizar_gerente`.
    """
    conteo = Conteo(ENT_PRODUCTO)
    filas = (db.query(ExtDimProducto)
             .filter(ExtDimProducto.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not _cabe(fila.producto_codigo, 40):
            _omitir_por_largo(conteo, hallazgos, ENT_PRODUCTO,
                              fila.producto_codigo, "DIM_Producto.codigo", 40)
            continue
        if not _cabe(fila.nombre, 120):
            _omitir_por_largo(conteo, hallazgos, ENT_PRODUCTO,
                              fila.producto_codigo, "DIM_Producto.nombre", 120)
            continue
        linea_id = (mapeo.id_mapeado(db, ENT_LINEA, pais_codigo, fila.linea_codigo)
                    if fila.linea_codigo else None)

        existente = db.query(Producto).filter(
            Producto.codigo == fila.producto_codigo).first()
        if existente is not None:
            mapeo_otro_pais = (db.query(MapeoExterno)
                               .filter(MapeoExterno.entidad == ENT_PRODUCTO,
                                       MapeoExterno.id_interno == existente.id,
                                       MapeoExterno.pais_codigo != pais_codigo)
                               .first())
            if mapeo_otro_pais is not None:
                conteo.omitidos += 1
                hallazgos.append(Hallazgo(
                    ENT_PRODUCTO, fila.producto_codigo,
                    f"El código ya está mapeado al país {mapeo_otro_pais.pais_codigo} "
                    f"y DIM_Producto.codigo es único global; la fila se omitió.",
                    SEVERIDAD_ERROR))
                continue

        def _buscar(f=fila):
            return (db.query(Producto)
                    .filter(Producto.codigo == f.producto_codigo).first())

        def _crear(f=fila, lid=linea_id):
            nuevo = Producto(codigo=f.producto_codigo, nombre=f.nombre,
                             linea_id=lid, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_PRODUCTO, pais_codigo, fila.producto_codigo, Producto,
            _buscar, _crear)
        registro.nombre = fila.nombre
        registro.activo = fila.activo
        if linea_id is not None:
            registro.linea_id = linea_id
        conteo.anotar(resultado)
    return conteo


#: Cada dimensión en el orden en que debe correr: las posteriores resuelven sus
#: claves foráneas contra el mapeo que dejan las anteriores.
_SINCRONIZADORES = {
    ENT_PAIS: sincronizar_pais,
    ENT_LINEA: sincronizar_linea,
    ENT_GERENTE: sincronizar_gerente,
    ENT_REPRESENTANTE: sincronizar_representante,
    ENT_CICLO: sincronizar_ciclo,
    ENT_ESPECIALIDAD: sincronizar_especialidad,
    ENT_MEDICO: sincronizar_medico,
    ENT_FARMACIA: sincronizar_farmacia,
    ENT_PRODUCTO: sincronizar_producto,
}


def sincronizar_todo(db: Session, pais_codigo: str) -> dict:
    """Corre las nueve dimensiones en orden de dependencia.

    Un solo commit al final: o entra el maestro coherente o no entra nada. Las
    filas problemáticas no abortan —se omiten con su hallazgo—, así que el commit
    solo confirma lo que sí se pudo resolver.
    """
    hallazgos: list[Hallazgo] = []
    conteos: list[Conteo] = []
    for entidad in ENTIDADES:
        conteos.append(_SINCRONIZADORES[entidad](db, pais_codigo, hallazgos))
    db.commit()

    errores = sum(1 for h in hallazgos if h.severidad == SEVERIDAD_ERROR)
    logger.info(f"Dimensiones sincronizadas para {pais_codigo}: "
                f"{sum(c.creados for c in conteos)} creadas, "
                f"{sum(c.adoptados for c in conteos)} adoptadas, "
                f"{errores} con error")
    return {
        "pais_codigo": pais_codigo,
        "dimensiones": [{
            "entidad": c.entidad, "en_ext": c.en_ext, "creados": c.creados,
            "adoptados": c.adoptados, "actualizados": c.actualizados,
            "omitidos": c.omitidos,
        } for c in conteos],
        "hallazgos": [{
            "entidad": h.entidad, "codigo_externo": h.codigo_externo,
            "problema": h.problema, "severidad": h.severidad,
        } for h in hallazgos],
    }


#: Cuántas filas hay en `ext` por dimensión, para el tablero. La especialidad no
#: lleva país en el contrato, así que se cuenta entera.
_ORIGEN_CONTEO = {
    ENT_PAIS: (ExtDimPais, True),
    ENT_LINEA: (ExtDimLinea, True),
    ENT_GERENTE: (ExtDimGerente, True),
    ENT_REPRESENTANTE: (ExtDimRepresentante, True),
    ENT_CICLO: (ExtDimCiclo, True),
    ENT_ESPECIALIDAD: (ExtDimEspecialidad, False),
    ENT_MEDICO: (ExtDimMedico, True),
    ENT_FARMACIA: (ExtDimFarmacia, True),
    ENT_PRODUCTO: (ExtDimProducto, True),
}


def resumen_dimensiones(db: Session, pais_codigo: str) -> list[dict]:
    """Filas en `ext` frente a filas ya mapeadas, por dimensión."""
    salida = []
    for entidad in ENTIDADES:
        modelo, por_pais = _ORIGEN_CONTEO[entidad]
        q = db.query(modelo)
        if por_pais:
            q = q.filter(modelo.pais_codigo == pais_codigo)
        clave_pais = pais_codigo if entidad != ENT_ESPECIALIDAD else ""
        mapeadas = (db.query(MapeoExterno)
                    .filter(MapeoExterno.entidad == entidad,
                            MapeoExterno.pais_codigo == clave_pais).count())
        salida.append({"entidad": entidad, "en_ext": q.count(),
                       "mapeadas": mapeadas})
    return salida
