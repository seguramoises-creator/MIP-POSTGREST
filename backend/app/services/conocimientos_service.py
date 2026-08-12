"""Captura manual de notas de conocimiento y su integración al ciclo.

Sustituye al Excel para EVAL_CONOCIMIENTOS. La captura pasa por una tabla propia
—`DW.FACT_NotaConocimiento`— y se integra en un paso explícito, igual que los
otros dos caminos: el examen tiene intentos → consolidación, Mallén tiene `ext` →
integración. De ahí salen tres propiedades que escribir directo no da: la nota se
corrige antes de entrar, queda auditada con autor y fecha, y el reproceso es
idempotente.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Indicador, RepresentanteMedico
from app.models.hechos import NotaConocimiento, ResultadoIndicador
from app.models.integracion_ext import ExtControlCarga, ExtFactEvaluacionConocimiento
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE
from app.services import fuente_indicador_service as fuentes
from app.services import integracion_mapeo as mapeo
from app.services import recalculo_service
from app.services.integracion_dimensiones_service import SEVERIDAD_ERROR, Hallazgo

NOTA_MIN = Decimal("0")
NOTA_MAX = Decimal("100")


def _validar_nota(nota: Decimal) -> Decimal:
    """En el servicio y no solo en el formulario: la API la llama cualquiera."""
    valor = Decimal(str(nota))
    if valor < NOTA_MIN or valor > NOTA_MAX:
        raise ValueError(
            f"La nota debe estar entre {NOTA_MIN} y {NOTA_MAX}; llegó {valor}.")
    return valor


def capturar_nota(db: Session, pais_codigo: str, ciclo_id: int, rm_id: int,
                  nota: Decimal, fecha_evaluacion: date, tema: str | None,
                  usuario_id: int | None) -> NotaConocimiento:
    """Añade una nota. Para CORREGIR una existente se usa `corregir_nota`.

    La distinción importa: la tabla no lleva UNIQUE porque un RM puede tener
    varias notas en un ciclo, así que corregir insertando dejaría la nota vieja
    entrando al promedio.
    """
    fila = NotaConocimiento(
        pais_codigo=pais_codigo, ciclo_id=ciclo_id, rm_id=rm_id,
        nota=_validar_nota(nota), fecha_evaluacion=fecha_evaluacion, tema=tema,
        capturado_por_usuario_id=usuario_id,
        capturado_en=datetime.now(timezone.utc))
    db.add(fila)
    db.flush()
    return fila


def corregir_nota(db: Session, nota_id: int, nota: Decimal, tema: str | None,
                  usuario_id: int | None) -> NotaConocimiento:
    """Corrige una nota ya capturada EDITANDO su fila."""
    fila = db.get(NotaConocimiento, nota_id)
    if fila is None:
        raise ValueError(f"No existe la nota {nota_id}.")
    fila.nota = _validar_nota(nota)
    fila.tema = tema
    fila.capturado_por_usuario_id = usuario_id
    fila.capturado_en = datetime.now(timezone.utc)
    db.flush()
    return fila


def notas_del_ciclo(db: Session, pais_codigo: str, ciclo_id: int) -> list[dict]:
    """Los RM del país con sus notas del ciclo — incluidos los que no tienen
    ninguna, que es lo que le dice al responsable cuánto le falta."""
    rms = (db.query(RepresentanteMedico)
           .filter(RepresentanteMedico.pais_codigo == pais_codigo)
           .order_by(RepresentanteMedico.codigo).all())
    por_rm: dict[int, list] = {}
    for n in (db.query(NotaConocimiento)
              .filter(NotaConocimiento.ciclo_id == ciclo_id,
                      NotaConocimiento.pais_codigo == pais_codigo)
              .order_by(NotaConocimiento.fecha_evaluacion).all()):
        por_rm.setdefault(n.rm_id, []).append(n)
    salida = []
    for rm in rms:
        notas = por_rm.get(rm.id, [])
        salida.append({
            "rm_id": rm.id, "rm_codigo": rm.codigo, "rm_nombre": rm.nombre,
            "notas": [{"id": n.id, "nota": n.nota, "tema": n.tema,
                       "fecha_evaluacion": n.fecha_evaluacion,
                       "capturado_en": n.capturado_en} for n in notas],
            "promedio": (sum((n.nota for n in notas), Decimal(0)) / len(notas)
                         if notas else None),
        })
    return salida


def _upsert_resultado(db: Session, rm, ciclo_id: int, nota: Decimal) -> bool:
    """Escribe la nota del RM en `FACT_ResultadoIndicador`, reemplazando la
    anterior. `pais_codigo`/`linea_id`/`gerente_id` salen del RM: son NOT NULL y
    no vienen en la nota. Devuelve False si el país no tiene el indicador.
    """
    indicador = (db.query(Indicador)
                 .filter(Indicador.codigo == fuentes.INDICADOR_CONOCIMIENTOS,
                         Indicador.pais_codigo == rm.pais_codigo).first())
    if indicador is None:
        logger.warning(f"Conocimientos: {rm.pais_codigo} no tiene el indicador "
                       f"{fuentes.INDICADOR_CONOCIMIENTOS}")
        return False
    (db.query(ResultadoIndicador)
     .filter(ResultadoIndicador.rm_id == rm.id,
             ResultadoIndicador.indicador_id == indicador.id,
             ResultadoIndicador.ciclo_id == ciclo_id)
     .delete(synchronize_session=False))
    db.add(ResultadoIndicador(
        rm_id=rm.id, indicador_id=indicador.id, ciclo_id=ciclo_id,
        pais_codigo=rm.pais_codigo, linea_id=rm.linea_id,
        gerente_id=rm.gerente_id, resultado_real=nota, activo=True))
    return True


def integrar_captura(db: Session, pais_codigo: str, ciclo_id: int) -> dict:
    """Promedia las notas capturadas de cada RM y las escribe al indicador.

    `integrar_captura` exige que el país sea de CAPTURA_MANUAL — esa comprobación
    va ANTES del guard de ciclo cerrado y antes de tocar nada. El guard de ciclo
    cerrado, a su vez, va ANTES de cualquier borrado: un delete-then-insert que
    luego aborta borra `puntos_obtenidos` para siempre.
    """
    fuentes.asegurar_duenio(db, pais_codigo, fuentes.FUENTE_CAPTURA_MANUAL)
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        logger.info(f"Conocimientos: ciclo {ciclo_id} cerrado — no se integra")
        return {"abortado": True, "motivo": "ciclo_cerrado", "rms_integrados": 0}

    filas = (db.query(NotaConocimiento)
             .filter(NotaConocimiento.ciclo_id == ciclo_id,
                     NotaConocimiento.pais_codigo == pais_codigo).all())
    por_rm: dict[int, list] = {}
    for n in filas:
        por_rm.setdefault(n.rm_id, []).append(n.nota)

    integrados = 0
    for rm_id, notas in por_rm.items():
        rm = db.get(RepresentanteMedico, rm_id)
        if rm is None:
            continue
        promedio = sum(notas, Decimal(0)) / len(notas)
        if _upsert_resultado(db, rm, ciclo_id, promedio):
            integrados += 1

    logger.info(f"Conocimientos: {integrados} RM integrados en el ciclo {ciclo_id} "
                f"de {pais_codigo}")
    return {"abortado": False, "rms_integrados": integrados,
            "ciclo_id": ciclo_id, "pais_codigo": pais_codigo}


#: Un lote ya INTEGRADO se vuelve a leer sin problema: la escritura es
#: idempotente y reprocesar debe poder repetirse.
_ESTADOS_INTEGRABLES = ("VALIDADO", "INTEGRADO")


def integrar_conocimientos(db: Session, pais_codigo: str, ciclo_codigo: str,
                           hallazgos: list) -> dict:
    """`ext.factevaluacionconocimiento` → `EVAL_CONOCIMIENTOS`, promediando por RM.

    Un RM puede traer varias notas (temas o fechas distintas): se promedian,
    igual que en los otros dos caminos.
    """
    fuente = fuentes.fuente_de(db, pais_codigo)
    if fuente != fuentes.FUENTE_NOTA_EXTERNA:
        hallazgos.append(Hallazgo(
            "factevaluacionconocimiento", ciclo_codigo,
            f"En {pais_codigo}, {fuentes.INDICADOR_CONOCIMIENTOS} lo alimenta "
            f"«{fuente}»; las notas de Mallén no se integraron. Cambia la fuente "
            f"en Conocimientos si esa es la decisión.", SEVERIDAD_ERROR))
        return {"abortado": True, "motivo": "fuente_ajena", "rms_integrados": 0}

    ciclo_id = mapeo.id_mapeado(db, ENT_CICLO, pais_codigo, ciclo_codigo)
    if ciclo_id is None:
        hallazgos.append(Hallazgo(
            "factevaluacionconocimiento", ciclo_codigo,
            f"No se pudo resolver el ciclo «{ciclo_codigo}»; sincroniza "
            f"dimensiones primero.", SEVERIDAD_ERROR))
        return {"abortado": True, "motivo": "ciclo_no_mapeado", "rms_integrados": 0}

    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        logger.info(f"Conocimientos: ciclo {ciclo_id} cerrado — no se integra")
        return {"abortado": True, "motivo": "ciclo_cerrado", "rms_integrados": 0}

    filas = (db.query(ExtFactEvaluacionConocimiento)
             .filter(ExtFactEvaluacionConocimiento.pais_codigo == pais_codigo,
                     ExtFactEvaluacionConocimiento.ciclo_codigo == ciclo_codigo).all())
    estados = {l.lote_id: l.estado for l in db.query(ExtControlCarga).filter(
        ExtControlCarga.lote_id.in_({f.lote_id for f in filas} or {0})).all()}

    por_rm: dict[str, list] = {}
    for fila in filas:
        if estados.get(fila.lote_id) not in _ESTADOS_INTEGRABLES:
            continue
        por_rm.setdefault(fila.rm_codigo, []).append(fila.nota)

    integrados = 0
    for rm_codigo, notas in sorted(por_rm.items()):
        rm_id = mapeo.id_mapeado(db, ENT_REPRESENTANTE, pais_codigo, rm_codigo)
        rm = db.get(RepresentanteMedico, rm_id) if rm_id else None
        if rm is None:
            hallazgos.append(Hallazgo(
                "factevaluacionconocimiento", rm_codigo,
                f"El representante «{rm_codigo}» no está sincronizado; su nota "
                f"no se integró.", SEVERIDAD_ERROR))
            continue
        promedio = sum(notas, Decimal(0)) / len(notas)
        if _upsert_resultado(db, rm, ciclo_id, promedio):
            integrados += 1

    logger.info(f"Conocimientos (Mallén): {integrados} RM integrados en "
                f"{pais_codigo}/{ciclo_codigo}")
    return {"abortado": False, "rms_integrados": integrados,
            "ciclo_id": ciclo_id, "pais_codigo": pais_codigo}
