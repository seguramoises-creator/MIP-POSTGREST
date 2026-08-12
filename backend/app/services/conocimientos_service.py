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
from app.models.integracion_ext import ExtFactEvaluacionConocimiento
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE
from app.services import fuente_indicador_service as fuentes
from app.services import integracion_mapeo as mapeo
from app.services import recalculo_service
# Ronda de correcciones 1 (Tarea 4): el `Hallazgo` correcto es el de
# `integracion_visitas_service`, NO el de `integracion_dimensiones_service` (esos
# tienen campos distintos: `hecho`/`origen_id` vs `entidad`/`codigo_externo`).
# `integrar_conocimientos` corre dentro del MISMO proceso por lotes que
# `integracion_indicadores_service` (que ya hace este mismo import) — comparte su
# lista de hallazgos, así que un objeto con campos ajenos revienta con
# `AttributeError` al serializar, al FINAL del lote, después de haber escrito.
# También se reutilizan `_lote_habilitado`/`_resolver_estados_lotes`: dos
# definiciones de «lote integrable» sobre el mismo dato es justo lo que hay que
# evitar (mismo criterio que documenta `integracion_indicadores_service`).
from app.services.integracion_visitas_service import (
    SEVERIDAD_AVISO, SEVERIDAD_ERROR, Hallazgo, _lote_habilitado, _resolver_estados_lotes,
)

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


def integrar_conocimientos(db: Session, pais_codigo: str, ciclo_codigo: str,
                           hallazgos: list,
                           estados_lote: dict[int, str] | None = None) -> dict:
    """`ext.factevaluacionconocimiento` → `EVAL_CONOCIMIENTOS`, promediando por RM.

    Un RM puede traer varias notas (temas o fechas distintas): se promedian,
    igual que en los otros dos caminos.

    ASIMETRÍA DELIBERADA con `integrar_captura`: ese camino LEVANTA
    `FuenteAjenaError` si el país no es suyo (lo llama un humano desde la
    pantalla de Conocimientos, y una excepción interrumpe justo ahí). Este
    camino, en cambio, anota un `Hallazgo` de severidad error y devuelve sin
    escribir — corre dentro del mismo proceso POR LOTES que
    `integracion_indicadores_service`/`integracion_visitas_service`, donde una
    excepción abortaría el resto de los hechos del lote (ventas, visitas,
    farmacias...) que no tienen nada que ver con esta fuente. `Hallazgo` es el
    contrato de ese proceso; `FuenteAjenaError` es el de la pantalla manual.

    `estados_lote` sigue el mismo patrón que
    `integracion_visitas_service.integrar_ventas`/etc: si el llamador ya lo
    resolvió para toda la corrida (un futuro `integrar_todo` que también cubra
    Conocimientos), se reutiliza tal cual; si no, se resuelve aquí con
    `_resolver_estados_lotes` (una sola consulta).
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
    if estados_lote is None:
        estados_lote = _resolver_estados_lotes(db, {f.lote_id for f in filas})

    por_rm: dict[str, list] = {}
    omitidas_por_estado: dict[str | None, int] = {}
    for fila in filas:
        if not _lote_habilitado(estados_lote, fila.lote_id):
            estado = estados_lote.get(fila.lote_id)
            omitidas_por_estado[estado] = omitidas_por_estado.get(estado, 0) + 1
            continue
        # Nota fuera de rango: se omite ESA fila con un hallazgo de error, en
        # vez de escribirla tal cual (el motor la acotaría para los puntos,
        # pero el número que se reporta —`resultado_real`— quedaría mal) o de
        # recortarla en silencio (inventaría un valor que Mallén no mandó).
        if fila.nota < NOTA_MIN or fila.nota > NOTA_MAX:
            hallazgos.append(Hallazgo(
                "factevaluacionconocimiento", fila.origen_id,
                f"La nota {fila.nota} del representante «{fila.rm_codigo}» está "
                f"fuera de [{NOTA_MIN}, {NOTA_MAX}]; la fila se omitió.",
                SEVERIDAD_ERROR))
            continue
        por_rm.setdefault(fila.rm_codigo, []).append(fila.nota)

    # Un hallazgo de aviso por estado (no por fila): sin esto, un lote entero
    # descartado por estar RECHAZADO/RECIBIDO se traduce en `rms_integrados: 0`
    # y una lista de hallazgos vacía — el operador no tiene ninguna pista de
    # que había datos y por qué no entraron.
    for estado, n in sorted(omitidas_por_estado.items(), key=lambda kv: kv[0] or ""):
        hallazgos.append(Hallazgo(
            "factevaluacionconocimiento", ciclo_codigo,
            f"{n} fila(s) se omitieron por estar en un lote «"
            f"{estado or 'sin control de carga'}», no VALIDADO/INTEGRADO.",
            SEVERIDAD_AVISO))

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
