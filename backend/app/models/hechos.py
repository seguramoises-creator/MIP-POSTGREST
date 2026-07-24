"""
SCGCPR — Modelos: Todas las Tablas de Hechos (DW schema)
========================================================
REDISEÑO (jun-2026): se reemplazan FACT_RendimientoComercial, FACT_Ranking
y FACT_Reconocimiento por una nueva familia de tablas modelada según la
estructura real de cálculo observada en FACT_MIP_FINAL.xlsx (hojas
FACT_RESULTADO_INDICADOR, FACT_SCORE_INTEGRAL_RM, FACT_RANKING_RM,
FACT_RANKING_GERENTE, FACT_RECONOCIMIENTO_RM, FACT_SCORECARD_INDICADOR,
FACT_DISTRIBUCION_EQUIPO, FACT_DASHBOARD_EJECUTIVO, FACT_TENDENCIA_CICLO).

Mapeo de diseño (tabla vieja → nueva, con justificación):
  FACT_RendimientoComercial → FACT_ResultadoIndicador
      Es la tabla de ENTRADA (alimentada por ETL/sistemas externos): un
      registro por RM+indicador+ciclo con el resultado bruto. Se adopta el
      nombre y estructura de la hoja FACT_RESULTADO_INDICADOR del Excel
      (más rica: factor_aplicado, puntos_máximos, porcentaje_logro) porque
      es la única hoja del archivo con la granularidad por-indicador
      necesaria para servir como entrada real del motor de cálculo.
      (Nota de diseño: FACT_SCORE_INTEGRAL_RM, aunque el usuario la
      describió como "alimentada por sistemas externos", solo contiene un
      SCORE_TOTAL agregado por RM — estructuralmente no puede ser la
      entrada granular; es, por construcción, una salida calculada.)
  FACT_Ranking → FACT_RankingRM + FACT_RankingGerente
      Se separan en dos tablas calculadas, una por RM y otra por Gerente,
      replicando las hojas FACT_RANKING_RM y FACT_RANKING_GERENTE.
  FACT_Reconocimiento → FACT_ReconocimientoRM
      Salida calculada, replica FACT_RECONOCIMIENTO_RM (conserva los campos
      de certificado PDF que ya existían — funcionalidad vigente).

Tablas NUEVAS 100% calculadas (no existían antes, pobladas por el motor):
  FACT_ScoreIntegralRM, FACT_ScorecardIndicador, FACT_DistribucionEquipo,
  FACT_DashboardEjecutivo, FACT_TendenciaCiclo

Tablas que se CONSERVAN sin cambios (decisión del usuario: seguir
funcionando como entradas detalladas que alimentan los indicadores):
  FACT_Ventas, FACT_EVOIR, FACT_Coaching, FACT_Capacitacion

Tablas de soporte que se conservan: FACT_Auditoria, FACT_CargaExcel
"""
from datetime import datetime, date, timezone
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, Integer, Date, DateTime,
    Numeric, ForeignKey, Text, BigInteger, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


# ═════════════════════════════════════════════════════════════════════════
# ENTRADA — alimentada por ETL / sistemas externos
# ═════════════════════════════════════════════════════════════════════════

class ResultadoIndicador(Base):
    """Tabla de hechos principal de ENTRADA — un resultado por RM/indicador/ciclo.

    Reemplaza a FACT_RendimientoComercial. Es la tabla que alimenta el motor
    de cálculo (ETL / sistemas externos cargan aquí los resultados brutos);
    todas las demás FACT_* de este módulo son su resultado calculado.
    Estructura adoptada de la hoja FACT_RESULTADO_INDICADOR de
    FACT_MIP_FINAL.xlsx (más completa que el RendimientoComercial anterior:
    incorpora factor_aplicado, puntos_maximos y porcentaje_logro, que vienen
    de DIM_MetaIndicador en el momento del cálculo).
    """
    __tablename__ = "FACT_ResultadoIndicador"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    linea_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False)
    gerente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)  # FK agregada (Fase 1, F4)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    indicador_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Indicador.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)
    mes_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Resultado bruto cargado (origen externo)
    resultado_real: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    # Calculados por el motor de recálculo a partir de DIM_MetaIndicador / DIM_IndicadorTabla
    resultado_porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    factor_aplicado: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    puntos_obtenidos: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    puntos_maximos: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    porcentaje_logro: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)

    # Auditoría
    carga_excel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    fecha_calculo: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


# ═════════════════════════════════════════════════════════════════════════
# Tablas que se CONSERVAN sin cambios — entradas detalladas existentes
# ═════════════════════════════════════════════════════════════════════════

class Ventas(Base):
    __tablename__ = "FACT_Ventas"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    linea_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    ventas_reales: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    cuota: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=True)
    cumplimiento_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    crecimiento_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    puntaje: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class EvoIR(Base):
    __tablename__ = "FACT_EVOIR"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    producto_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    producto_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    prescripciones_actuales: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    prescripciones_anteriores: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    evolucion_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    puntaje: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Coaching(Base):
    __tablename__ = "FACT_Coaching"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    gerente_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=False)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    tipo: Mapped[str] = mapped_column(String(30), nullable=False)  # INDIVIDUAL | CAMPO
    coaching_programado: Mapped[int] = mapped_column(Integer, default=0)
    coaching_ejecutado: Mapped[int] = mapped_column(Integer, default=0)
    cumplimiento_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    calificacion_calidad: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    peso_cantidad: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0.7)
    peso_calidad: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0.3)
    resultado_coaching: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    puntaje: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    fecha_coaching: Mapped[date | None] = mapped_column(Date, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class CapacitacionFact(Base):
    __tablename__ = "FACT_Capacitacion"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    capacitacion_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Capacitacion.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    asistio: Mapped[bool] = mapped_column(Boolean, default=False)
    calificacion: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    aprobado: Mapped[bool] = mapped_column(Boolean, default=False)
    horas_completadas: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    fecha_actividad: Mapped[date | None] = mapped_column(Date, nullable=True)
    puntaje: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


# ═════════════════════════════════════════════════════════════════════════
# NUEVO — Módulo de Cobertura Predictiva y Ritmo de Ejecución (4DX)
# Reemplaza la entrada de datos que antes alimentaba Comercial/Ventas+EVO_IR
# en el dashboard del GD. Origen: hoja Fact_Visitas de
# Modulo_Cobertura_Predictiva_Ejemplo_VM_v3.xlsx — registro crudo de cada
# visita médica realizada/no realizada, usado por
# cobertura_predictiva_service.py para derivar L (médicos únicos
# visitados) y M (contactos realizados) del Motor_Formulas.
# ═════════════════════════════════════════════════════════════════════════

class Visita(Base):
    """Registro de visitas médicas (planeadas/realizadas) — DW.FACT_Visita.

    Una fila por contacto (visita) de un RM a un médico de su territorio.
    No existe una dimensión DIM_Medico separada: el médico se identifica por
    `medico_codigo`, que se cruza contra Config.DIM_TargetMedico para saber
    si pertenece al universo programado del RM en ese ciclo (igual que en el
    Excel de referencia, donde Target_Medicos y Fact_Visitas comparten la
    columna `medico_id`).

    Motor_Formulas (verificado contra el Excel de referencia):
      L = COUNT(DISTINCT medico_codigo) WHERE estado_visita='Realizada'
          AND fecha_visita <= fecha_corte AND rm_id=X AND ciclo_id=Y
      M = COUNT(*) bajo el mismo filtro (cuenta repeticiones, a diferencia de L)
    """
    __tablename__ = "FACT_Visita"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    medico_codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    fecha_visita: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    tipo_contacto: Mapped[str | None] = mapped_column(String(50), nullable=True)
    estado_visita: Mapped[str] = mapped_column(String(20), nullable=False, default="Realizada")  # Realizada | Programada | Cancelada
    producto_foco: Mapped[str | None] = mapped_column(String(100), nullable=True)
    carga_excel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


# ═════════════════════════════════════════════════════════════════════════
# NUEVO — Módulo de Categorización Médica (sustituye a Capacitación)
# ═════════════════════════════════════════════════════════════════════════

# NO es código muerto (verificado jul-2026): aunque el listado/lectura de Categorización
# Médica corre exclusivamente sobre cat.* (cat_models.py), esta tabla SÍ se sigue
# escribiendo en cada aprobación de médico vía
# categorizacion_service.registrar_en_maestro_categorizacion (patrón write-only).
class CategorizacionMedica(Base):
    """Categorización A/B/C/D de cada médico, por ciclo — DW.FACT_CategorizacionMedica.

    A diferencia de Cobertura Predictiva (cálculo en vivo, sin tabla
    materializada), aquí SÍ se persiste un resultado por
    (medico_id, rm_id, ciclo_id) porque el negocio requiere Historial
    (categoría actual vs. anterior) y Reportes de evolución — igual que
    FACT_RankingRM, que guarda `posicion_anterior` para el mismo propósito.
    `categoria_anterior_id` se completa automáticamente al recalcular: es
    la categoría que tenía el médico (para ese mismo RM) en su fila del
    ciclo previo (ver categorizacion_service).

    Grano (REVISADO): la llave es (medico_id, rm_id, ciclo_id), no solo
    (medico_id, ciclo_id) — un mismo médico real puede ser visitado por
    más de un RM/línea en el mismo ciclo (territorios/líneas
    superpuestos), y cada combinación necesita su propio resultado. Con la
    llave anterior, datos de producción mostraban ~36% de colisiones
    (filas que se sobrescribían entre sí); con rm_id en la llave, las
    colisiones residuales caen a médicos con nombre genérico que
    DIM_Medico.UQ_Medico_Pais_Nombre_Centro ya resuelve por separado.

    Motor de Cálculo (Excel "Bases y Criterios" / hoja Calculos):
      score_total = score_pacientes + score_poder_adquisitivo +
                    score_prescripcion + score_ubicacion + score_kol
      score_<criterio> = (nivel_1_a_5 / 5) × peso_criterio
    La categoría se determina por el rango [score_min, score_max] de
    Config.DIM_CategoriaMedica que contiene a score_total. Si los 5
    insumos crudos vienen vacíos, la categoría es 'PENDIENTE' (catálogo,
    sin rango numérico) en vez de caer en score_total=0 → categoría D.

    pais_codigo/linea_id/gerente_id/rm_id se denormalizan en la fila (capturados
    al momento del cálculo) para filtrar sin joins, igual que en
    FACT_ResultadoIndicador / FACT_RankingRM.
    """
    __tablename__ = "FACT_CategorizacionMedica"
    __table_args__ = (
        UniqueConstraint("medico_id", "rm_id", "ciclo_id", name="UQ_CategorizacionMedica_Medico_RM_Ciclo"),
        {"schema": "DW"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    gerente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)  # FK agregada (Fase 1, F4)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    medico_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Medico.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    # Valores capturados (entrada cruda, antes de convertir a nivel/score)
    pacientes_semana: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    costo_consulta: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    potencial_prescripcion: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)  # recetas/semana
    ubicacion_territorial: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Mala..Alta
    kol: Mapped[str | None] = mapped_column(String(100), nullable=True)  # etiqueta KOL

    # Niveles 1-5 resueltos por DIM_CriterioCategoriaTabla
    nivel_pacientes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nivel_poder_adquisitivo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nivel_prescripcion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nivel_ubicacion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nivel_kol: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Score ponderado por criterio (nivel/5 × peso) y total
    score_pacientes: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    score_poder_adquisitivo: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    score_prescripcion: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    score_ubicacion: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    score_kol: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    score_total: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)

    categoria_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_CategoriaMedica.id"), nullable=True)
    categoria_anterior_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_CategoriaMedica.id"), nullable=True)

    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    carga_excel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_calculo: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    usuario_calculo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


# ═════════════════════════════════════════════════════════════════════════
# SALIDAS CALCULADAS — pobladas 100% por el motor de recálculo
# (recalculo_service / iup_service / ranking_service / reconocimiento_service)
# ═════════════════════════════════════════════════════════════════════════

class ScoreIntegralRM(Base):
    """Score integral consolidado por RM/ciclo — salida calculada.

    Reemplaza conceptualmente al IUP consolidado que antes vivía solo dentro
    de FACT_Ranking; ahora es su propia tabla (replica FACT_SCORE_INTEGRAL_RM
    del Excel), de forma que el ranking pueda referenciarla y que otros
    procesos (reconocimiento, scorecard) lean un único score consolidado.
    """
    __tablename__ = "FACT_ScoreIntegralRM"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    gerente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)  # FK agregada (Fase 1, F4)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    score_total: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    categoria_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_CategoriaDesempeno.id"), nullable=True)
    elegible_reconocimiento: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_calculo: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class RankingRM(Base):
    """Ranking de Representantes Médicos — salida calculada (reemplaza FACT_Ranking).

    Conserva tipo_ranking / elegible / posicion_anterior del modelo anterior
    porque routers y dashboards existentes dependen de esa semántica
    operativa (múltiples tipos de ranking, variación de posición, filtro de
    elegibles). Los componentes IUP por módulo (antes columnas iup_* aquí)
    ahora se calculan dinámicamente desde FACT_ResultadoIndicador agrupado
    por DIM_Indicador.modulo — evita duplicar datos y sigue el espíritu de
    la nueva estructura (esta tabla solo guarda el score consolidado).
    """
    __tablename__ = "FACT_RankingRM"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    gerente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)  # FK agregada (Fase 1, F4)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    ciclo_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)

    tipo_ranking: Mapped[str] = mapped_column(String(30), nullable=False)  # MENSUAL | TRIMESTRAL | ANUAL | REGIONAL
    score_total: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    categoria_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_CategoriaDesempeno.id"), nullable=True)
    posicion_global: Mapped[int] = mapped_column(Integer, nullable=False)
    posicion_linea: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posicion_anterior: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elegible: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class RankingGerente(Base):
    """Ranking de Gerentes de Distrito — salida calculada (NUEVA, replica FACT_RANKING_GERENTE).

    Consolida el score promedio del equipo de RMs de cada gerente.
    Cubre el pendiente "Ranking Gerentes de Distrito" listado en CLAUDE.md §18.
    """
    __tablename__ = "FACT_RankingGerente"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    gerente_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=False, index=True)
    ciclo_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)

    score_total: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    posicion: Mapped[int] = mapped_column(Integer, nullable=False)
    metodo_calculo: Mapped[str | None] = mapped_column(String(50), nullable=True)  # ej: PROMEDIO_EQUIPO
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class ReconocimientoRM(Base):
    """Reconocimientos otorgados — salida calculada (reemplaza FACT_Reconocimiento).

    Conserva los campos de certificado PDF (certificado_generado,
    certificado_url, aprobado_por, observaciones) porque
    reconocimiento_service.generar_certificado_pdf() ya los usa — es
    funcionalidad vigente que no debe perderse en el rediseño.
    """
    __tablename__ = "FACT_ReconocimientoRM"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    gerente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)  # FK agregada (Fase 1, F4)
    rm_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=True)
    premio_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Premio.id"), nullable=False)
    ciclo_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)

    score_total: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    posicion_linea: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posicion_ranking: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elegible: Mapped[bool] = mapped_column(Boolean, default=True)
    certificado_generado: Mapped[bool] = mapped_column(Boolean, default=False)
    certificado_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    aprobado_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_calculo: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class ScorecardIndicador(Base):
    """Scorecard agregado por indicador/ciclo — salida calculada (NUEVA, replica FACT_SCORECARD_INDICADOR).

    Resume, por país+ciclo+indicador: peso, resultado promedio, score
    promedio, categoría de desempeño y variación contra el ciclo anterior.
    Alimenta vistas tipo "scorecard de indicadores" del dashboard ejecutivo.
    """
    __tablename__ = "FACT_ScorecardIndicador"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)
    indicador_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Indicador.id"), nullable=False, index=True)

    peso_indicador: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    resultado_promedio: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    score_promedio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    categoria_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_CategoriaDesempeno.id"), nullable=True)
    variacion_vs_ciclo_anterior: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    fecha_calculo: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class DistribucionEquipo(Base):
    """Distribución del equipo por categoría de desempeño — salida calculada
    (NUEVA, replica FACT_DISTRIBUCION_EQUIPO). Alimenta el gráfico de
    distribución (Excelente/Bueno/En Desarrollo/Crítico/Sin Datos) del
    dashboard ejecutivo, ahora basado en DIM_CategoriaDesempeno configurable
    en lugar de umbrales fijos en código.
    """
    __tablename__ = "FACT_DistribucionEquipo"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)
    categoria_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_CategoriaDesempeno.id"), nullable=False)

    cantidad_rm: Mapped[int] = mapped_column(Integer, default=0)
    porcentaje_rm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    fecha_calculo: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class DashboardEjecutivoFact(Base):
    """KPIs consolidados del Dashboard Ejecutivo — salida calculada
    (NUEVA, replica FACT_DASHBOARD_EJECUTIVO). Cada fila es el valor de un
    DIM_KpiDashboard para un país/ciclo, con su valor anterior y variación
    — permite alimentar el dashboard ejecutivo desde datos pre-calculados
    en vez de recalcular agregaciones pesadas en cada request.
    """
    __tablename__ = "FACT_DashboardEjecutivo"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)
    kpi_dashboard_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_KpiDashboard.id"), nullable=False, index=True)

    valor: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    valor_anterior: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    variacion: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    unidad: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fuente_calculo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fecha_calculo: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class TendenciaCiclo(Base):
    """Tendencia del score integral por ciclo — salida calculada
    (NUEVA, replica FACT_TENDENCIA_CICLO). Resume score promedio/mín/máx y
    total de RMs evaluados por ciclo — alimenta el gráfico de tendencia
    histórica del dashboard ejecutivo.
    """
    __tablename__ = "FACT_TendenciaCiclo"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    score_promedio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    score_minimo: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    score_maximo: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    total_rm: Mapped[int] = mapped_column(Integer, default=0)
    fecha_calculo: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


# ═════════════════════════════════════════════════════════════════════════
# Soporte — sin cambios
# ═════════════════════════════════════════════════════════════════════════

class Auditoria(Base):
    __tablename__ = "FACT_Auditoria"
    __table_args__ = {"schema": "Audit"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    accion: Mapped[str] = mapped_column(String(50), nullable=False)  # LOGIN | LOGOUT | CREATE | UPDATE | DELETE | ETL | RANKING
    modulo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tabla: Mapped[str | None] = mapped_column(String(100), nullable=True)
    campo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registro_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    exitoso: Mapped[bool] = mapped_column(Boolean, default=True)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)


class CargaExcel(Base):
    __tablename__ = "FACT_CargaExcel"
    __table_args__ = {"schema": "ETL"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String(300), nullable=False)
    tipo_archivo: Mapped[str] = mapped_column(String(50), nullable=False)  # PRODUCTIVIDAD | COMERCIAL | COACHING | CAPACITACION
    ciclo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modo: Mapped[str] = mapped_column(String(20), nullable=False)  # SIMULACION | PRODUCCION
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE")  # PENDIENTE | PROCESANDO | EXITOSO | ERROR
    total_filas: Mapped[int] = mapped_column(Integer, default=0)
    filas_exitosas: Mapped[int] = mapped_column(Integer, default=0)
    filas_error: Mapped[int] = mapped_column(Integer, default=0)
    filas_advertencia: Mapped[int] = mapped_column(Integer, default=0)
    log_errores: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_advertencias: Mapped[str | None] = mapped_column(Text, nullable=True)
    duracion_segundos: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EvaluacionReceptividad(Base):
    """Cabecera de evaluación de Receptividad/Compromiso — Matriz de Desarrollo LSII (NUEVA).

    Una fila por evaluación de un RM en un ciclo. Cruza:
      - score_receptividad (eje X, 0-100): calculado de forma oculta a partir de
        las 5 dimensiones conductuales seleccionadas por el GD (ver detalle).
      - score_desempeno (eje Y, 0-100): snapshot del score de FACT_RankingRM /
        FACT_ScoreIntegralRM al momento de evaluar (se congela para que la
        evaluación histórica no cambie si el ranking se recalcula después).
    Con ambos ejes se clasifica el nivel D1-D4 y el estilo de liderazgo
    sugerido (Dirigir/Entrenar/Apoyar/Delegar) — ver lsii_service.py.
    """
    __tablename__ = "FACT_EvaluacionReceptividad"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    gerente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)
    evaluador_usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    score_receptividad: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)  # eje X
    score_desempeno: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)            # eje Y (snapshot)
    nivel_lsii: Mapped[str] = mapped_column(String(5), nullable=False)            # D1 | D2 | D3 | D4
    estilo_liderazgo: Mapped[str] = mapped_column(String(50), nullable=False)     # Dirigir | Entrenar | Apoyar | Delegar
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_evaluacion: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class EvaluacionReceptividadDetalle(Base):
    """Detalle de evaluación de Receptividad — una fila por cada una de las 5
    dimensiones conductuales evaluadas (NUEVA). Guarda snapshot de score_oculto
    y peso_dimension al momento de la evaluación (auditoría: si el catálogo
    DIM_ReceptividadOpcion cambia después, la evaluación histórica no se altera).
    """
    __tablename__ = "FACT_EvaluacionReceptividadDetalle"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evaluacion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("DW.FACT_EvaluacionReceptividad.id"), nullable=False, index=True
    )
    dimension_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    opcion_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_ReceptividadOpcion.id"), nullable=False)
    score_oculto: Mapped[int] = mapped_column(Integer, nullable=False)              # snapshot
    peso_dimension: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)  # snapshot


class KpiRaw(Base):
    """Tabla de staging: almacena el Excel FACT_KPI_RM tal como viene del source,
    sin transformar. Permite validar los datos originales antes del cálculo.
    Columnas = estructura exacta de FACT_KPI_RM_VF.xlsx.
    """
    __tablename__ = "FACT_KPI_RAW"
    __table_args__ = {"schema": "ETL"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    carga_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ETL.FACT_CargaExcel.id"), nullable=False, index=True
    )
    # Columnas tal como vienen del Excel fuente
    fact_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pais_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pais_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nombre_rm: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rm_codigo: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    gerente_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gerente_codigo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linea_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    linea_codigo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    indicador_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indicador_codigo: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    tipo_periodo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ciclo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ciclo_nombre: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mes_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ciclo_mes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valor_real: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    # Metadato de carga
    fecha_carga: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
