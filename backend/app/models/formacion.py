"""VISTA — Ampliación del Módulo de Formación (esquema `formacion`).

Implementa el modelo de datos de "Ampliación del Módulo de Formación" v1.0
(jul-2026, Laboratorio Mallén), secciones 4 a 12 y 20.

QUÉ NO ESTÁ AQUÍ, PORQUE YA EXISTE
-----------------------------------
El prompt describe piezas que VISTA ya tiene, y que se REFERENCIAN en vez de
recrearse — verificado leyendo el código, no supuesto:
  - Exámenes y su generación con IA → esquema `exam`.
  - Coaching MORE y su escala D/P/A/E → esquema `coaching`.
  - Matriz LSII → `DW.FACT_EvaluacionReceptividad`, que YA tiene sus dos ejes
    (`score_receptividad` y `score_desempeno`). El §6 no crea un eje nuevo:
    cambia cómo se calcula el eje Y. Ver punto abierto 8 del plan.
  - Certificaciones con vigencia de 12 meses.
  - Visibilidad por rol (§6.4, §11.5) → matriz RBAC/ABAC con alcances
    own/team/all; no se programa con condicionales por rol.

DOS DECISIONES DE MODELADO QUE EL PROMPT NO FIJA
-------------------------------------------------
1. **`OnboardingPasoProgreso` no está en el prompt y hace falta.** El §4.4 solo
   guarda `paso_actual` en la asignación, con lo que se sabe dónde va el
   representante pero no QUIÉN marcó cada paso ni CUÁNDO — y el §4.6 reparte esa
   responsabilidad entre cuatro roles distintos (el RM avanza, el GD marca el
   hito de campo, Capacitación aprueba el checkpoint). Sin esta tabla no hay
   trazabilidad de una ruta ya completada.
2. **`RefuerzoCapsula` tampoco está y es imprescindible.** El §11.4 exige la
   "pregunta más y menos acertada" en los cuatro desgloses, y el §11.6 la
   referencia como `pregunta_mas_acertada_id`: sin una entidad pregunta con
   identidad propia, ese KPI no se puede calcular.

Los dominios acotados van como `String` y se validan en el servicio, igual que
en el resto del proyecto (`estado_aprobacion` de Farmacias, por ejemplo).
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

ESQUEMA = "formacion"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ===========================================================================
# §4.3 — Productos de la línea: Principal vs. Relacionado
# ===========================================================================

class ProductoLinea(Base):
    """Producto de una línea terapéutica, con su papel en la ruta de aprendizaje.

    `rol_en_ruta` es lo que decide la forma de la ruta: cada producto
    **principal** agrega automáticamente un paso DAVID (§4.2 paso 7+), mientras
    que un **relacionado** solo aporta material de consulta a Biblioteca y entra
    en el examen general del paso 6.
    """
    __tablename__ = "ProductoLinea"
    __table_args__ = (
        UniqueConstraint("pais_codigo", "linea_id", "nombre_producto",
                         name="UQ_ProductoLinea_nombre"),
        Index("IX_ProductoLinea_linea", "linea_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(
        String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    linea_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False)
    nombre_producto: Mapped[str] = mapped_column(String(200), nullable=False)
    rol_en_ruta: Mapped[str] = mapped_column(String(20), nullable=False)  # principal | relacionado
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=_ahora, nullable=False)


# ===========================================================================
# §4 — Onboarding: constructor de ruta de aprendizaje
# ===========================================================================

class OnboardingPlantilla(Base):
    """Ruta de onboarding de una línea. Los 10 pasos del §4.2 llevan un orden
    pedagógico que el cliente confirmó explícitamente y que no debe reordenarse:
    base científica primero, visión general de todos los productos después, y
    solo al final el detalle DAVID de cada producto principal."""
    __tablename__ = "OnboardingPlantilla"
    __table_args__ = (
        Index("IX_OnbPlantilla_linea", "pais_codigo", "linea_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(
        String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    linea_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False)
    nombre_plantilla: Mapped[str] = mapped_column(String(200), nullable=False)
    duracion_dias: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=_ahora, nullable=False)


class OnboardingPaso(Base):
    """Un paso de la ruta.

    `bloqueante` existe desde el modelo porque el §4.5 deja ABIERTO si la
    secuencia es estricta o admite pasos en paralelo (punto abierto 1): el campo
    permite ambos comportamientos sin migración cuando el cliente decida.

    `quien_lo_marca` reparte la responsabilidad según el §4.6 — el hito de campo
    lo marca el GD, el checkpoint final lo aprueba Capacitación, y ningún otro
    rol puede hacerlo por ellos.
    """
    __tablename__ = "OnboardingPaso"
    __table_args__ = (
        UniqueConstraint("plantilla_id", "orden", name="UQ_OnbPaso_orden"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plantilla_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.OnboardingPlantilla.id", ondelete="CASCADE"),
        nullable=False, index=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    # contenido | documento | examen | material_examen | hito_campo | checkpoint
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    titulo: Mapped[str] = mapped_column(String(250), nullable=False)
    plazo_sugerido: Mapped[str | None] = mapped_column(String(60))
    bloqueante: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # representante | sistema | gd | capacitacion
    quien_lo_marca: Mapped[str] = mapped_column(String(20), nullable=False, default="representante")
    # Referencia polimórfica: a qué apunta el paso según su tipo (examen, material,
    # producto). Se guarda el tipo junto al id para no crear seis columnas nulas.
    referencia_tipo: Mapped[str | None] = mapped_column(String(30))
    referencia_id: Mapped[int | None] = mapped_column(Integer)


class OnboardingAsignacion(Base):
    """Una ruta asignada a un representante concreto."""
    __tablename__ = "OnboardingAsignacion"
    __table_args__ = (
        UniqueConstraint("plantilla_id", "rm_id", name="UQ_OnbAsignacion_rm"),
        Index("IX_OnbAsignacion_rm", "rm_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plantilla_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.OnboardingPlantilla.id"), nullable=False)
    rm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    paso_actual_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.OnboardingPaso.id"), nullable=True)
    progreso_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    completada_en: Mapped[datetime | None] = mapped_column(DateTime)
    asignada_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=_ahora, nullable=False)


class OnboardingPasoProgreso(Base):
    """Quién completó cada paso y cuándo. NO viene en el prompt (ver docstring
    del módulo): sin ella la asignación sabe dónde va el RM pero no deja rastro
    de quién marcó el hito de campo ni quién aprobó el checkpoint, que el §4.6
    asigna a roles distintos."""
    __tablename__ = "OnboardingPasoProgreso"
    __table_args__ = (
        UniqueConstraint("asignacion_id", "paso_id", name="UQ_OnbProgreso_paso"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asignacion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.OnboardingAsignacion.id", ondelete="CASCADE"),
        nullable=False, index=True)
    paso_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.OnboardingPaso.id"), nullable=False)
    completado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Hora del servidor, no editable — mismo criterio de integridad que
    # `fecha_coaching` en Coaching y que `timestamp_confirmacion` del §5.5.
    completado_en: Mapped[datetime | None] = mapped_column(DateTime)
    completado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text)


# ===========================================================================
# §5 — Biblioteca de material con lectura obligatoria
# ===========================================================================

class BibliotecaMaterial(Base):
    """Material de estudio. Se sube UNA vez y se reutiliza en tres lugares
    (§4.3): alimenta la generación del examen, la Biblioteca del representante y
    la Ayuda Visual que ya usa Coaching.

    `aprobado_por_gm` implementa el firewall PhRMA del §2: todo contenido
    científico que suba Capacitación debe quedar visible y aprobable por Gerente
    Médico antes de publicarse a los RM.
    """
    __tablename__ = "BibliotecaMaterial"
    __table_args__ = (
        Index("IX_BibMaterial_producto", "producto_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(
        String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    producto_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.ProductoLinea.id"), nullable=True)
    titulo: Mapped[str] = mapped_column(String(250), nullable=False)
    # manual | ayuda_visual | estudio_clinico | ficha_tecnica | video
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    archivo_url: Mapped[str] = mapped_column(Text, nullable=False)
    # Por defecto TRUE (§5.3): el cliente pidió que la lectura obligatoria sea
    # la norma, no la excepción.
    obligatorio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    usado_en_examen_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("exam.DimExamen.id"), nullable=True)
    usado_en_coaching_av: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subido_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    aprobado_por_gm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    aprobado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=_ahora, nullable=False)


class BibliotecaConfirmacion(Base):
    """Confirmación de lectura de un material obligatorio.

    El único por (material, RM) es lo que impide inflar el progreso confirmando
    dos veces el mismo material."""
    __tablename__ = "BibliotecaConfirmacion"
    __table_args__ = (
        UniqueConstraint("material_id", "rm_id", name="UQ_BibConfirmacion"),
        Index("IX_BibConfirmacion_rm", "rm_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.BibliotecaMaterial.id", ondelete="CASCADE"),
        nullable=False)
    rm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    # Hora del servidor, no editable (§5.5).
    timestamp_confirmacion: Mapped[datetime] = mapped_column(
        DateTime, default=_ahora, nullable=False)


# ===========================================================================
# §7 — Generador de calendario de coaching
# ===========================================================================

class ParametroFrecuenciaLSII(Base):
    """Cuántas veces por ciclo debe acompañarse a un RM según su cuadrante.

    Vive en tabla y no en el código porque el §7.2 marca esa tabla como SUPUESTO
    NO CONFIRMADO por el cliente, y el §17.5 exige explícitamente dejarla
    configurable hasta que se valide."""
    __tablename__ = "ParametroFrecuenciaLSII"
    __table_args__ = (
        UniqueConstraint("pais_codigo", "cuadrante", name="UQ_FrecLSII_cuadrante"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(
        String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    cuadrante: Mapped[str] = mapped_column(String(5), nullable=False)  # D1..D4
    visitas_por_ciclo: Mapped[int] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(120))


class CalendarioCoachingSugerido(Base):
    """Celda del calendario sugerido: un RM, una semana, un día.

    `cuadrante_al_generar` es un SNAPSHOT a propósito: el cuadrante del RM puede
    cambiar después, y sin esta foto no se podría auditar por qué el sistema
    sugirió esa frecuencia en su momento."""
    __tablename__ = "CalendarioCoachingSugerido"
    __table_args__ = (
        Index("IX_CalCoach_gd_ciclo", "gd_id", "ciclo_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gd_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    rm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    semana: Mapped[int] = mapped_column(Integer, nullable=False)
    dia_semana: Mapped[str] = mapped_column(String(10), nullable=False)  # lunes..viernes
    cuadrante_al_generar: Mapped[str | None] = mapped_column(String(5))
    editado_manualmente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    publicado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=_ahora, nullable=False)


# ===========================================================================
# §8 — Ranking gamificado de Formación
# ===========================================================================

class RankingFormacionPuntos(Base):
    """Puntos de Formación de un RM en un ciclo.

    Los cuatro componentes se guardan por separado (§8.2) para que el RM pueda
    ver de dónde sale su posición, no solo el total."""
    __tablename__ = "RankingFormacionPuntos"
    __table_args__ = (
        UniqueConstraint("rm_id", "ciclo_id", name="UQ_RankingForm_rm_ciclo"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    puntos_certificacion: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    puntos_examenes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    puntos_refuerzo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    puntos_onboarding: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    puntos_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    racha_ciclos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=_ahora, nullable=False)


# ===========================================================================
# §10 — Refuerzo de Memoria (curva de Ebbinghaus)
# ===========================================================================

class RefuerzoCampana(Base):
    """Campaña de refuerzo sobre un tema/producto.

    Capacitación define solo cinco cosas (§10.2) y VISTA arma el resto: el
    calendario de rondas y la redacción de las cápsulas."""
    __tablename__ = "RefuerzoCampana"
    __table_args__ = (
        Index("IX_RefCampana_ciclo", "pais_codigo", "ciclo_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(
        String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    ciclo_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    producto_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.ProductoLinea.id"), nullable=True)
    duracion_dias: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # 'creciente' es el default recomendado por la literatura del §10.1.3
    # (Landauer y Bjork 1978, Cull 1996); 'fijo_48h' fue lo que pidió el cliente
    # originalmente. Punto abierto 5: cuál queda como default en producción.
    modo_espaciado: Mapped[str] = mapped_column(String(20), nullable=False, default="creciente")
    material_fuente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.BibliotecaMaterial.id"), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="BORRADOR")
    aprobado_por_gm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=_ahora, nullable=False)


class RefuerzoRondaProgramada(Base):
    """Una ronda de la campaña.

    Dos marcas de tiempo distintas a propósito (§10.3): VISTA SUGIERE la fecha
    según la teoría, y Capacitación CONFIRMA la definitiva. Ninguna cápsula se
    envía sin que `fecha_hora_programada` esté confirmada, aunque solo se acepte
    la sugerencia sin cambiarla."""
    __tablename__ = "RefuerzoRondaProgramada"
    __table_args__ = (
        UniqueConstraint("campana_id", "numero_ronda", name="UQ_RefRonda_numero"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campana_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.RefuerzoCampana.id", ondelete="CASCADE"),
        nullable=False, index=True)
    numero_ronda: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_hora_sugerida: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_hora_programada: Mapped[datetime | None] = mapped_column(DateTime)
    # microlectura | reto | caso_breve | reflexion_abierta (combinables, §10.5)
    formato: Mapped[dict | None] = mapped_column(JSON)
    publicada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notificada_en: Mapped[datetime | None] = mapped_column(DateTime)


class RefuerzoCapsula(Base):
    """El contenido concreto de una ronda. NO viene en el prompt (ver docstring
    del módulo): el §11.4 pide la "pregunta más y menos acertada" en los cuatro
    desgloses, y eso exige que la pregunta sea una entidad con identidad propia.

    El §10.7 obliga a que el reto sea SIEMPRE opción múltiple con una única
    correcta, para poder corregir en el acto sin esperar a un proceso posterior.
    `explicacion` es la razón por la que la correcta lo es, que se muestra al
    fallar."""
    __tablename__ = "RefuerzoCapsula"
    __table_args__ = ({"schema": ESQUEMA},)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ronda_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.RefuerzoRondaProgramada.id", ondelete="CASCADE"),
        nullable=False, index=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    formato: Mapped[str] = mapped_column(String(30), nullable=False)
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    # Opciones A-D y la correcta: solo aplican al formato 'reto'.
    opciones: Mapped[dict | None] = mapped_column(JSON)
    opcion_correcta: Mapped[str | None] = mapped_column(String(1))
    explicacion: Mapped[str | None] = mapped_column(Text)
    generada_por_ia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RefuerzoRespuesta(Base):
    """Respuesta de un RM a una cápsula.

    Guarda por separado la PARTICIPACIÓN (qué tan rápido reaccionó, §10.6) y el
    ACIERTO (si eligió bien, §10.7). El §10.8 lo marca como requisito de diseño:
    las dos métricas nunca se combinan en un solo número, porque una respuesta
    rápida y equivocada tiene que verse como lo que es — alta participación y
    bajo acierto a la vez."""
    __tablename__ = "RefuerzoRespuesta"
    __table_args__ = (
        UniqueConstraint("capsula_id", "rm_id", name="UQ_RefRespuesta"),
        Index("IX_RefRespuesta_rm", "rm_id"),
        Index("IX_RefRespuesta_ronda", "ronda_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ronda_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{ESQUEMA}.RefuerzoRondaProgramada.id"), nullable=False)
    capsula_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{ESQUEMA}.RefuerzoCapsula.id", ondelete="CASCADE"),
        nullable=False)
    rm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    # Cuándo se disparó la notificación (§10.4) — es el punto de partida del
    # cronómetro de participación.
    timestamp_recibido: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Hora del servidor, no editable.
    timestamp_respondido: Mapped[datetime | None] = mapped_column(DateTime)
    tiempo_respuesta_seg: Mapped[int | None] = mapped_column(Integer)
    pct_puntaje_participacion: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    opcion_seleccionada: Mapped[str | None] = mapped_column(String(1))
    es_acierto: Mapped[bool | None] = mapped_column(Boolean)
    texto_libre: Mapped[str | None] = mapped_column(Text)  # solo 'reflexion_abierta'
    puntos_obtenidos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ===========================================================================
# §9 — Simulacro de venta con IA (modelo MORE) · Fase 3
# ===========================================================================

class SimulacroSesion(Base):
    """Sesión de práctica contra un médico simulado.

    El estilo social sale de la Matriz de Estilos Sociales de la Guía MORE
    (§9.2.1.b). "Amistoso" y "Afable" son EL MISMO cuadrante, no dos distintos:
    se guarda un único valor canónico."""
    __tablename__ = "SimulacroSesion"
    __table_args__ = (
        Index("IX_SimSesion_rm", "rm_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    # Directivo | Analitico | Amistoso | Expresivo
    estilo_social_asignado: Mapped[str] = mapped_column(String(20), nullable=False)
    medico_simulado: Mapped[str] = mapped_column(String(150), nullable=False)
    genero_simulado: Mapped[str | None] = mapped_column(String(10))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=_ahora, nullable=False)
    finalizada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SimulacroRonda(Base):
    """Una objeción y la respuesta del RM. `fase_more` ancla cada ronda a una de
    las cuatro fases del modelo (§9.2.5); la acción correcta sale del contenido
    transcrito en el §9.2, no se inventa contenido nuevo del modelo MORE."""
    __tablename__ = "SimulacroRonda"
    __table_args__ = ({"schema": ESQUEMA},)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sesion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{ESQUEMA}.SimulacroSesion.id", ondelete="CASCADE"),
        nullable=False, index=True)
    # Planificacion | Apertura | Desarrollo | Cierre
    fase_more: Mapped[str] = mapped_column(String(20), nullable=False)
    # Una de las 6 técnicas nombradas del §9.2.3.c, solo en Desarrollo.
    tecnica_objecion: Mapped[str | None] = mapped_column(String(40))
    objecion_texto: Mapped[str] = mapped_column(Text, nullable=False)
    opciones: Mapped[dict | None] = mapped_column(JSON)
    opcion_seleccionada: Mapped[str | None] = mapped_column(String(1))
    opcion_correcta: Mapped[str] = mapped_column(String(1), nullable=False)
    es_correcta: Mapped[bool | None] = mapped_column(Boolean)
    retroalimentacion: Mapped[str | None] = mapped_column(Text)


class SimulacroResultado(Base):
    """Calificación final en la MISMA escala D/P/A/E (1-4) que Coaching, para que
    los dos módulos sean comparables (§9.3 paso 5)."""
    __tablename__ = "SimulacroResultado"
    __table_args__ = ({"schema": ESQUEMA},)

    sesion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{ESQUEMA}.SimulacroSesion.id", ondelete="CASCADE"),
        primary_key=True)
    calificacion_apertura: Mapped[int | None] = mapped_column(Integer)
    calificacion_desarrollo: Mapped[int | None] = mapped_column(Integer)
    calificacion_cierre: Mapped[int | None] = mapped_column(Integer)
    calificacion_general: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))


# ===========================================================================
# §12 — Plan de Cierre de Brechas
# ===========================================================================

class ParametroFormacion(Base):
    """Umbrales de las 5 reglas del §12.2, configurables y no incrustados en el
    código: el §12.3 los marca como valores ilustrativos del mockup que hay que
    confirmar con Capacitación (punto abierto 6)."""
    __tablename__ = "ParametroFormacion"
    __table_args__ = (
        UniqueConstraint("pais_codigo", "clave", name="UQ_ParamFormacion_clave"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(
        String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    clave: Mapped[str] = mapped_column(String(60), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(250))


class PlanCierreBrecha(Base):
    """Alerta generada por el motor de reglas. No se captura a mano.

    El valor está en que cruza los CUATRO desgloses del §11 a la vez: una misma
    pregunta fallada en muchos segmentos es un vacío de contenido (Regla 1),
    mientras que fallada solo en un equipo es un problema de ese equipo (Regla
    2). Ninguna vista aislada distingue esas dos cosas."""
    __tablename__ = "PlanCierreBrecha"
    __table_args__ = (
        Index("IX_PlanBrecha_ciclo", "pais_codigo", "ciclo_id"),
        {"schema": ESQUEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(
        String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    ciclo_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)
    # contenido_generalizado | concentrada_equipo_pais | material_no_personas |
    # escalamiento_individual | operativa_gestion
    regla_aplicada: Mapped[str] = mapped_column(String(40), nullable=False)
    prioridad: Mapped[str] = mapped_column(String(15), nullable=False)  # alta|media|informativa
    alcance: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    accion_sugerida: Mapped[str] = mapped_column(Text, nullable=False)
    link_accion: Mapped[str | None] = mapped_column(String(250))
    atendida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generado_en: Mapped[datetime] = mapped_column(DateTime, default=_ahora, nullable=False)
