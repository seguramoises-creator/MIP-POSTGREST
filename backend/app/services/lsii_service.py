"""
SCGCPR — Motor de cálculo: Matriz de Desarrollo LSII (Liderazgo Situacional II)

Cruza dos ejes para ubicar a cada RM en un nivel de desarrollo D1-D4 y
sugerir el estilo de liderazgo que su Gerente de Distrito debe aplicar:

  - Eje Y = Desempeño/Competencia (0-100): se toma de FACT_RankingRM
    (motor de score ya existente — ver ranking.py/ranking_service.py).
  - Eje X = Receptividad/Compromiso (0-100): se calcula aquí con un
    modelo de comportamiento OCULTO al evaluador. El GD jamás ve un
    score_oculto ni un peso_dimension — solo selecciona el texto de
    comportamiento observado (DIM_ReceptividadOpcion.texto_comportamiento),
    para evitar sesgo del evaluador.

Fórmula de receptividad (5 dimensiones, peso 0.20 cada una):
    receptividad = Σ (score_oculto / 5 × 100 × peso_dimension)
    → todo-5 = 100 pts | todo-1 = 20 pts | acotado a [0, 100]

Cuadrantes (corte en 80 para ambos ejes):
    D1 Dirigir  → desempeño BAJO + receptividad BAJA
    D2 Entrenar → desempeño BAJO + receptividad ALTA
    D3 Apoyar   → desempeño ALTO + receptividad BAJA
    D4 Delegar  → desempeño ALTO + receptividad ALTA
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.orm import Session
from loguru import logger

from app.models.dimensiones import ReceptividadOpcion, ConfiguracionLsii
from app.models.hechos import RankingRM, EvaluacionReceptividad, EvaluacionReceptividadDetalle
from app.services import recalculo_service


def _guard_ciclo_abierto(db, ciclo_id):
    """Bloquea escrituras sobre ciclos cerrados (inmutables)."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        raise ValueError("El ciclo está cerrado — solo lectura")

# Valores de respaldo: solo se usan si Config.DIM_ConfiguracionLSII no tiene
# ninguna fila todavía (instalación sin la migración aplicada). El valor
# vigente en producción se lee siempre de BD vía obtener_configuracion() —
# ver sección "Configuración editable (umbral D1-D4)" más abajo — para que
# un ADMIN/GERENTE_PRODUCTIVIDAD pueda ajustarlo desde la aplicación.
CORTE_DESEMPENO = Decimal("80")
CORTE_RECEPTIVIDAD = Decimal("80")

# (banda_desempeño, banda_receptividad) -> (nivel_lsii, estilo_liderazgo)
# D1 = bajo desempeño + ALTA receptividad (actitud positiva, necesita dirección)
# D2 = bajo desempeño + BAJA receptividad (requiere entrenamiento + motivación)
# FIX jul-2026: D1/D2 estaban invertidos (bajo+baja clasificaba D1), lo que
# contradecía la definición del módulo y la matriz del frontend.
NIVELES_LSII = {
    ("BAJO", "BAJO"): ("D2", "Entrenar"),
    ("BAJO", "ALTO"): ("D1", "Dirigir"),
    ("ALTO", "BAJO"): ("D3", "Apoyar"),
    ("ALTO", "ALTO"): ("D4", "Delegar"),
}


def _clamp(value: Decimal, min_val: Decimal, max_val: Decimal) -> Decimal:
    """Restringe value al intervalo [min_val, max_val]."""
    return max(min_val, min(value, max_val))


def _dimensiones_activas(db: Session) -> set[str]:
    """Códigos de dimensión distintos que tienen al menos una opción activa."""
    filas = (
        db.query(ReceptividadOpcion.dimension_codigo)
        .filter(ReceptividadOpcion.activo == True)
        .distinct()
        .all()
    )
    return {f[0] for f in filas}


def obtener_dimensiones_catalogo(db: Session) -> list[dict]:
    """
    Devuelve las 5 dimensiones de receptividad con sus opciones de
    comportamiento, EXPONIENDO solo texto_comportamiento — esto es
    exactamente lo que el GD ve en el formulario de evaluación. Nunca
    incluye score_oculto ni peso_dimension.
    """
    opciones = (
        db.query(ReceptividadOpcion)
        .filter(ReceptividadOpcion.activo == True)
        .order_by(ReceptividadOpcion.orden_dimension.asc(), ReceptividadOpcion.orden_opcion.asc())
        .all()
    )
    dimensiones: dict[str, dict] = {}
    for op in opciones:
        dim = dimensiones.setdefault(op.dimension_codigo, {
            "dimension_codigo": op.dimension_codigo,
            "dimension_nombre": op.dimension_nombre,
            "dimension_descripcion": op.dimension_descripcion,
            "orden_dimension": op.orden_dimension,
            "opciones": [],
        })
        dim["opciones"].append({
            "id": op.id,
            "orden_opcion": op.orden_opcion,
            "texto_comportamiento": op.texto_comportamiento,
        })
    return sorted(dimensiones.values(), key=lambda d: d["orden_dimension"])


def calcular_receptividad(
    db: Session,
    opcion_ids: Sequence[int],
) -> tuple[Decimal, list[ReceptividadOpcion]]:
    """
    Resuelve las opciones elegidas (una por dimensión) a su score_oculto +
    peso_dimension y calcula la receptividad agregada.

    Valida que: (a) todas las opciones existan y estén activas, (b) no
    haya dos opciones de la misma dimensión (una selección por dimensión),
    y (c) venga exactamente una selección por cada dimensión ACTIVA del
    catálogo vigente — el número de dimensiones ya no está fijo en 5: un
    ADMIN puede agregar/quitar dimensiones desde la pantalla de
    administración (ver upsert_dimension_admin / desactivar_dimension_admin
    más abajo) y esta validación se ajusta automáticamente.
    """
    opciones = (
        db.query(ReceptividadOpcion)
        .filter(ReceptividadOpcion.id.in_(opcion_ids), ReceptividadOpcion.activo == True)
        .all()
    )
    if len(opciones) != len(set(opcion_ids)):
        encontrados = {o.id for o in opciones}
        faltantes = set(opcion_ids) - encontrados
        raise ValueError(f"Opción(es) de comportamiento no encontrada(s) o inactiva(s): {faltantes}")

    dims_vistas = [o.dimension_codigo for o in opciones]
    if len(set(dims_vistas)) != len(opciones):
        raise ValueError("No puede seleccionar más de una opción para la misma dimensión")

    dims_activas = _dimensiones_activas(db)
    dims_faltantes = dims_activas - set(dims_vistas)
    if dims_faltantes:
        raise ValueError(f"Falta seleccionar un comportamiento para las dimensiones: {sorted(dims_faltantes)}")

    total = Decimal("0")
    for op in opciones:
        aporte = (Decimal(op.score_oculto) / Decimal("5")) * Decimal("100") * op.peso_dimension
        total += aporte
        logger.debug(
            f"Receptividad: dim={op.dimension_codigo} score_oculto={op.score_oculto} "
            f"peso={op.peso_dimension} aporte={aporte}"
        )

    score = _clamp(total, Decimal("0"), Decimal("100"))
    logger.debug(f"Receptividad total calculada: {score}")
    return score, opciones


def resolver_score_desempeno(
    db: Session,
    rm_id: int,
    ciclo_id: int,
    pais_codigo: Optional[str] = None,
    tipo_ranking: str = "MENSUAL",
) -> Optional[Decimal]:
    """
    Toma el score de desempeño (eje Y) desde FACT_RankingRM — la misma
    fuente que /ranking. Si el ciclo aún no tiene ranking generado para
    ese RM, retorna None (la evaluación de receptividad puede registrarse
    igual; el cruce LSII se completa cuando exista score de desempeño).
    """
    q = db.query(RankingRM).filter(
        RankingRM.rm_id == rm_id,
        RankingRM.ciclo_id == ciclo_id,
        RankingRM.tipo_ranking == tipo_ranking.upper(),
    )
    if pais_codigo is not None:
        q = q.filter(RankingRM.pais_codigo == pais_codigo)
    row = q.first()
    return row.score_total if row else None


def _clasificar_eje(valor: Decimal, corte: Decimal) -> str:
    return "ALTO" if valor >= corte else "BAJO"


def clasificar_desempeno(score_desempeno: Decimal, corte: Decimal = CORTE_DESEMPENO) -> str:
    """ALTO si score_desempeno >= corte (80 por defecto), si no BAJO."""
    return _clasificar_eje(score_desempeno, corte)


def clasificar_lsii(
    score_desempeno: Decimal,
    score_receptividad: Decimal,
    corte_desempeno: Decimal = CORTE_DESEMPENO,
    corte_receptividad: Decimal = CORTE_RECEPTIVIDAD,
) -> tuple[str, str]:
    """
    Cruza desempeño (eje Y) y receptividad (eje X) y retorna
    (nivel_lsii, estilo_liderazgo) según el cuadrante D1-D4.
    """
    banda_y = _clasificar_eje(score_desempeno, corte_desempeno)
    banda_x = _clasificar_eje(score_receptividad, corte_receptividad)
    nivel, estilo = NIVELES_LSII[(banda_y, banda_x)]
    logger.debug(
        f"Clasificación LSII: desempeño={score_desempeno} ({banda_y}) "
        f"receptividad={score_receptividad} ({banda_x}) → {nivel} {estilo}"
    )
    return nivel, estilo


def registrar_evaluacion(
    db: Session,
    pais_codigo: str,
    rm_id: int,
    ciclo_id: int,
    selecciones: Sequence[dict],
    gerente_id: Optional[int] = None,
    evaluador_usuario_id: Optional[int] = None,
    observaciones: Optional[str] = None,
    tipo_ranking: str = "MENSUAL",
) -> EvaluacionReceptividad:
    """
    Registra una evaluación completa de Receptividad/Compromiso:
      1) Calcula score_receptividad a partir de las opciones elegidas.
      2) Resuelve score_desempeno (snapshot del ranking vigente).
      3) Clasifica el nivel LSII y el estilo de liderazgo sugerido.
      4) Persiste 1 fila de cabecera (FACT_EvaluacionReceptividad) +
         5 filas de detalle (FACT_EvaluacionReceptividadDetalle).

    `selecciones` es una lista de dicts {"dimension_codigo": str, "opcion_id": int}.
    El score_oculto y peso_dimension SOLO se guardan en BD (detalle) —
    nunca se devuelven al evaluador en la respuesta del endpoint.
    """
    _guard_ciclo_abierto(db, ciclo_id)
    opcion_ids = [s["opcion_id"] for s in selecciones]
    score_receptividad, opciones_resueltas = calcular_receptividad(db, opcion_ids)
    opciones_por_id = {o.id: o for o in opciones_resueltas}

    score_desempeno = resolver_score_desempeno(db, rm_id, ciclo_id, pais_codigo, tipo_ranking)
    desempeno_para_clasificar = score_desempeno if score_desempeno is not None else Decimal("0")

    config = obtener_configuracion(db)
    nivel_lsii, estilo_liderazgo = clasificar_lsii(
        desempeno_para_clasificar,
        score_receptividad,
        corte_desempeno=config.corte_desempeno,
        corte_receptividad=config.corte_receptividad,
    )

    cabecera = EvaluacionReceptividad(
        pais_codigo=pais_codigo,
        rm_id=rm_id,
        gerente_id=gerente_id,
        ciclo_id=ciclo_id,
        evaluador_usuario_id=evaluador_usuario_id,
        score_receptividad=score_receptividad,
        score_desempeno=score_desempeno,
        nivel_lsii=nivel_lsii,
        estilo_liderazgo=estilo_liderazgo,
        observaciones=observaciones,
        fecha_evaluacion=datetime.now(timezone.utc),
    )
    db.add(cabecera)
    db.flush()  # obtener cabecera.id para los detalles

    for s in selecciones:
        opcion = opciones_por_id[s["opcion_id"]]
        detalle = EvaluacionReceptividadDetalle(
            evaluacion_id=cabecera.id,
            dimension_codigo=opcion.dimension_codigo,
            opcion_id=opcion.id,
            score_oculto=opcion.score_oculto,
            peso_dimension=opcion.peso_dimension,
        )
        db.add(detalle)

    db.commit()
    db.refresh(cabecera)
    logger.info(
        f"Evaluación LSII registrada: rm_id={rm_id} ciclo_id={ciclo_id} "
        f"receptividad={score_receptividad} desempeño={score_desempeno} → {nivel_lsii} ({estilo_liderazgo})"
    )
    return cabecera


# ════════════════════════════════════════════════════════════════════════
# Configuración editable (umbral D1-D4) — Config.DIM_ConfiguracionLSII
# ════════════════════════════════════════════════════════════════════════
# Permite que un ADMIN/GERENTE_PRODUCTIVIDAD ajuste el corte que separa
# ALTO/BAJO en cada eje desde la pantalla de Administración, sin tocar
# código ni la base de datos directamente.

def obtener_configuracion(db: Session) -> ConfiguracionLsii:
    """
    Devuelve la fila única de configuración vigente. Si la tabla está
    vacía (instalación donde la migración no sembró la fila por algún
    motivo) crea una con los valores históricos por defecto (80/80) para
    no romper el cálculo de evaluaciones existentes.
    """
    config = db.query(ConfiguracionLsii).order_by(ConfiguracionLsii.id.asc()).first()
    if config is None:
        config = ConfiguracionLsii(
            corte_desempeno=CORTE_DESEMPENO,
            corte_receptividad=CORTE_RECEPTIVIDAD,
            actualizado_en=datetime.now(timezone.utc),
            actualizado_por="sistema (auto-creada)",
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        logger.warning(
            "Config.DIM_ConfiguracionLSII estaba vacía — se creó una fila "
            "con los valores por defecto 80/80."
        )
    return config


def actualizar_configuracion(
    db: Session,
    corte_desempeno: Decimal,
    corte_receptividad: Decimal,
    actualizado_por: Optional[str] = None,
) -> ConfiguracionLsii:
    """Actualiza el umbral de corte D1-D4 (afecta solo evaluaciones futuras;
    las ya registradas conservan el nivel_lsii con el que se calcularon)."""
    config = obtener_configuracion(db)
    config.corte_desempeno = corte_desempeno
    config.corte_receptividad = corte_receptividad
    config.actualizado_en = datetime.now(timezone.utc)
    config.actualizado_por = actualizado_por
    db.commit()
    db.refresh(config)
    logger.info(
        f"Configuración LSII actualizada por {actualizado_por}: "
        f"corte_desempeno={corte_desempeno} corte_receptividad={corte_receptividad}"
    )
    return config


# ════════════════════════════════════════════════════════════════════════
# Administración del catálogo (matriz: dimensiones + opciones)
# Config.DIM_ReceptividadOpcion
# ════════════════════════════════════════════════════════════════════════
# A diferencia de obtener_dimensiones_catalogo() (vista del GD), estas
# funciones SÍ devuelven score_oculto y peso_dimension — solo deben
# llamarse desde endpoints /lsii/admin/* protegidos con rol
# ADMIN/GERENTE_PRODUCTIVIDAD.

def listar_dimensiones_admin(db: Session, incluir_inactivas: bool = False) -> list[dict]:
    """Catálogo completo (dimensiones + opciones) para la pantalla de administración."""
    q = db.query(ReceptividadOpcion)
    if not incluir_inactivas:
        q = q.filter(ReceptividadOpcion.activo == True)
    opciones = (
        q.order_by(ReceptividadOpcion.orden_dimension.asc(), ReceptividadOpcion.orden_opcion.asc())
        .all()
    )

    dimensiones: dict[str, dict] = {}
    for op in opciones:
        dim = dimensiones.setdefault(op.dimension_codigo, {
            "dimension_codigo": op.dimension_codigo,
            "dimension_nombre": op.dimension_nombre,
            "dimension_descripcion": op.dimension_descripcion,
            "orden_dimension": op.orden_dimension,
            "peso_dimension": op.peso_dimension,
            "activo": False,
            "opciones": [],
        })
        if op.activo:
            dim["activo"] = True
        dim["opciones"].append({
            "id": op.id,
            "orden_opcion": op.orden_opcion,
            "texto_comportamiento": op.texto_comportamiento,
            "score_oculto": op.score_oculto,
            "activo": op.activo,
        })
    return sorted(dimensiones.values(), key=lambda d: d["orden_dimension"])


def upsert_dimension_admin(db: Session, payload: dict, actualizado_por: Optional[str] = None) -> dict:
    """
    Crea o actualiza una dimensión completa con sus opciones.

    Si `dimension_codigo` ya existe:
      - Sincroniza dimension_nombre/descripcion/orden/peso en TODAS sus
        filas (son denormalizadas: 1 fila por opción de comportamiento).
      - Actualiza las opciones cuyo `id` viene en el payload.
      - Crea las opciones del payload que no traen `id`.
      - Desactiva (activo=False) las opciones existentes que NO vienen en
        el payload — nunca se borran físicamente, para no romper la FK
        `opcion_id` de evaluaciones ya registradas
        (DW.FACT_EvaluacionReceptividadDetalle).
    Si `dimension_codigo` no existe, crea la dimensión y todas sus opciones.

    `payload` es el resultado de DimensionLsiiUpsert.model_dump().
    """
    dimension_codigo = payload["dimension_codigo"]
    existentes = (
        db.query(ReceptividadOpcion)
        .filter(ReceptividadOpcion.dimension_codigo == dimension_codigo)
        .all()
    )
    existentes_por_id = {o.id: o for o in existentes}
    ids_en_payload: set[int] = set()

    for op_payload in payload["opciones"]:
        op_id = op_payload.get("id")
        if op_id is not None and op_id in existentes_por_id:
            fila = existentes_por_id[op_id]
            fila.orden_opcion = op_payload["orden_opcion"]
            fila.texto_comportamiento = op_payload["texto_comportamiento"]
            fila.score_oculto = op_payload["score_oculto"]
            fila.activo = op_payload.get("activo", True)
            ids_en_payload.add(op_id)
        else:
            fila = ReceptividadOpcion(
                dimension_codigo=dimension_codigo,
                dimension_nombre=payload["dimension_nombre"],
                dimension_descripcion=payload.get("dimension_descripcion"),
                orden_dimension=payload["orden_dimension"],
                orden_opcion=op_payload["orden_opcion"],
                texto_comportamiento=op_payload["texto_comportamiento"],
                score_oculto=op_payload["score_oculto"],
                peso_dimension=payload["peso_dimension"],
                activo=op_payload.get("activo", True),
            )
            db.add(fila)
            db.flush()  # obtener fila.id
            ids_en_payload.add(fila.id)

    desactivadas = 0
    for op_id, fila in existentes_por_id.items():
        if op_id not in ids_en_payload:
            fila.activo = False
            desactivadas += 1

    # Sincronizar los campos denormalizados de la dimensión en TODAS sus filas
    todas = (
        db.query(ReceptividadOpcion)
        .filter(ReceptividadOpcion.dimension_codigo == dimension_codigo)
        .all()
    )
    for fila in todas:
        fila.dimension_nombre = payload["dimension_nombre"]
        fila.dimension_descripcion = payload.get("dimension_descripcion")
        fila.orden_dimension = payload["orden_dimension"]
        fila.peso_dimension = payload["peso_dimension"]

    db.commit()
    logger.info(
        f"Dimensión LSII '{dimension_codigo}' guardada por {actualizado_por}: "
        f"{len(payload['opciones'])} opciones vigentes, {desactivadas} desactivadas."
    )

    dimensiones_admin = listar_dimensiones_admin(db, incluir_inactivas=True)
    return next(d for d in dimensiones_admin if d["dimension_codigo"] == dimension_codigo)


def actualizar_opcion_admin(db: Session, opcion_id: int, payload: dict) -> ReceptividadOpcion:
    """Edición puntual de una opción existente (texto, score oculto y/o estado).

    `payload` es el resultado de OpcionLsiiUpdate.model_dump(exclude_unset=True).
    """
    opcion = db.query(ReceptividadOpcion).filter(ReceptividadOpcion.id == opcion_id).first()
    if opcion is None:
        raise ValueError(f"Opción de comportamiento {opcion_id} no encontrada")

    if payload.get("texto_comportamiento") is not None:
        opcion.texto_comportamiento = payload["texto_comportamiento"]
    if payload.get("score_oculto") is not None:
        opcion.score_oculto = payload["score_oculto"]
    if payload.get("activo") is not None:
        opcion.activo = payload["activo"]

    db.commit()
    db.refresh(opcion)
    logger.info(f"Opción LSII {opcion_id} ({opcion.dimension_codigo}) actualizada.")
    return opcion


def desactivar_dimension_admin(db: Session, dimension_codigo: str) -> int:
    """
    Desactiva (soft-delete) TODAS las opciones de una dimensión. No se
    borran filas físicamente — así no se rompe la FK `opcion_id` de
    evaluaciones ya registradas. La dimensión deja de aparecer en
    /lsii/catalogo y, desde ese momento, ya no se exige una selección
    para ella (ver calcular_receptividad / _dimensiones_activas).

    Retorna la cantidad de opciones desactivadas. Lanza ValueError si la
    dimensión no existe o ya estaba inactiva.
    """
    filas = (
        db.query(ReceptividadOpcion)
        .filter(ReceptividadOpcion.dimension_codigo == dimension_codigo, ReceptividadOpcion.activo == True)
        .all()
    )
    if not filas:
        raise ValueError(f"La dimensión '{dimension_codigo}' no existe o ya está inactiva")
    for fila in filas:
        fila.activo = False
    db.commit()
    logger.info(f"Dimensión LSII '{dimension_codigo}' desactivada ({len(filas)} opciones).")
    return len(filas)
