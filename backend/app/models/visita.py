"""SCGCPR — Modelos del Módulo de Visita Médica (esquema `Visita`).

Adapta la especificación "VISTA — Módulo de Visita Médica" al stack del proyecto
(PostgreSQL + SQLAlchemy 2.0). Reutiliza Config.DIM_RM (visitador médico / VM),
Config.DIM_Ciclo y Config.DIM_Especialidad en lugar de crear catálogos nuevos.

Fase 1: Panel Médico (catálogo de médicos del universo de visita).
"""
from datetime import datetime, timezone, date

from sqlalchemy import (
    String, Boolean, Integer, DateTime, Date, ForeignKey, CHAR, Index, Numeric, LargeBinary,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class MedicoVisita(Base):
    """Médico del panel de visita de un VM (Parte 2 del spec).

    `ciclos_sin_visita` lo mantiene el cierre de ciclo (Ruptura de Secuencia, Parte 5):
    se resetea a 0 si hubo ≥1 visita en el ciclo, o se incrementa si no hubo ninguna.
    """
    __tablename__ = "DIM_MedicoVisita"
    __table_args__ = (
        Index("IX_MedicoVisita_vm", "vm_id"),
        Index("IX_MedicoVisita_nombre", "nombre_completo"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)  # Representante asignado
    # Maestro de Médicos (jul-2026): el Panel referencia al médico central del
    # Maestro (Config.DIM_Medico) en vez de duplicar sus datos generales.
    maestro_medico_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Medico.id"), nullable=True, index=True)
    codigo: Mapped[str | None] = mapped_column(String(40), nullable=True)      # Código del médico (identificador)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)  # solo MAYÚSCULAS
    nombre: Mapped[str | None] = mapped_column(String(100), nullable=True)     # primer nombre
    apellidos: Mapped[str | None] = mapped_column(String(150), nullable=True)  # apellidos
    especialidad_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Especialidad.id"), nullable=True)
    subespecialidad: Mapped[str | None] = mapped_column(String(120), nullable=True)
    categoria: Mapped[str] = mapped_column(CHAR(1), nullable=False)            # A / B / C / D
    # Ubicación / zonificación
    centro_trabajo: Mapped[str | None] = mapped_column(String(200), nullable=True)   # clínica u hospital
    institucion_tipo: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Pública / Privada
    tipo_consultorio: Mapped[str | None] = mapped_column(String(60), nullable=True)
    provincia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    direccion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    latitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    # Contacto
    telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    exequatur: Mapped[str | None] = mapped_column(String(50), nullable=True)   # número de colegiación
    # Consulta / visita
    dias_consulta: Mapped[str | None] = mapped_column(String(100), nullable=True)
    horario_consulta: Mapped[str | None] = mapped_column(String(100), nullable=True)
    frecuencia_visita: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Semanal/Quincenal/Mensual...
    acepta_visita: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Comercial
    potencial_prescripcion: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Alto/Medio/Bajo
    kol: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # Influenciador
    segmento: Mapped[str | None] = mapped_column(String(60), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Estado / control
    ciclos_sin_visita: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # Estado Activo/Inactivo
    fecha_alta: Mapped[date | None] = mapped_column(Date, nullable=True)         # Fecha de alta (negocio)
    # Flujo de aprobación de alta/baja por el Gerente de Distrito. El ALTA, una vez
    # aprobada, cuenta desde el MISMO ciclo (v2 jul-2026); la BAJA surte efecto el ciclo siguiente.
    # estado_aprobacion: APROBADO | PENDIENTE_ALTA | PENDIENTE_BAJA | RECHAZADO
    estado_aprobacion: Mapped[str] = mapped_column(String(16), nullable=False, default="APROBADO")
    ciclo_alta_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)   # cuenta desde este ciclo
    ciclo_baja_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)   # deja de contar desde este ciclo
    solicitado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    aprobado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    fecha_solicitud: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)  # nota / motivo de rechazo
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    registrado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)


class VisitaRegistro(Base):
    """Registro de visita médica (Parte 4 del spec). Fuente de la Cobertura.

    Tabla en el esquema `Visita` (distinta del `DW.FACT_Visita` de Cobertura Predictiva).
    tipo_visita: 'V' (Vista) / 'R' (Revisita). `ejecutada=False` = no-visita con causa.
    """
    __tablename__ = "FactVisita"
    __table_args__ = (
        Index("IX_FactVisita_vm_ciclo", "vm_id", "ciclo_id"),
        Index("IX_FactVisita_medico", "medico_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    medico_id: Mapped[int] = mapped_column(Integer, ForeignKey("Visita.DIM_MedicoVisita.id"), nullable=False)
    tipo_visita: Mapped[str] = mapped_column(CHAR(1), nullable=False)  # V / R
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    comentario: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    productos: Mapped[str | None] = mapped_column(String(300), nullable=True)  # "producto:mencion|..."
    ejecutada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    acompanado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # visita acompañada por el GD
    causa_no_visita: Mapped[str | None] = mapped_column(String(80), nullable=True)
    registrado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    # Georreferencia y foto del centro capturadas al registrar (v2).
    latitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    foto: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    foto_mime: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PlaneacionCiclo(Base):
    """Planeación de visitas del ciclo (Parte 3 del spec). Una fila por médico y
    tipo (V/R). Reglas P01-P06 validadas al guardar."""
    __tablename__ = "PlaneacionCiclo"
    __table_args__ = (
        Index("IX_Planeacion_vm_ciclo", "vm_id", "ciclo_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    medico_id: Mapped[int] = mapped_column(Integer, ForeignKey("Visita.DIM_MedicoVisita.id"), nullable=False)
    tipo_visita: Mapped[str] = mapped_column(CHAR(1), nullable=False)  # V / R
    semana: Mapped[int] = mapped_column(Integer, nullable=False)       # 1 a 4
    dia_semana: Mapped[str | None] = mapped_column(String(12), nullable=True)  # Lunes..Viernes
    hora_estimada: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    modificado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)


class PlaneacionEvento(Base):
    """Bitácora de publicación/desbloqueo de la planeación de un VM en un ciclo.

    La planeación es el **denominador de la cobertura** (`visitados / planeados`): si se
    pudiera editar a mitad de ciclo, un VM subiría su cobertura quitando del plan a los
    médicos que no visitó, sin visitar a nadie más. Por eso, publicada = congelada.

    Estado = el ÚLTIMO evento de (vm_id, ciclo_id):
      · sin eventos    → BORRADOR (editable, se guarda cuantas veces haga falta)
      · PUBLICADA      → congelada; `guardar_planeacion` la rechaza
      · DESBLOQUEADA   → vuelve a borrador (solo ADMIN, con motivo obligatorio)

    Append-only por diseño (igual que las hojas de coaching): nunca se borra ni se edita
    una fila, así el rastro de quién desbloqueó, cuándo y por qué no se puede perder.
    """
    __tablename__ = "PlaneacionEvento"
    __table_args__ = (
        Index("IX_PlaneacionEvento_vm_ciclo", "vm_id", "ciclo_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    evento: Mapped[str] = mapped_column(String(14), nullable=False)   # PUBLICADA | DESBLOQUEADA
    fecha: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)  # obligatorio al desbloquear
    # Cuántas filas de planeación tenía al publicar: deja constancia de lo que se congeló.
    items: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CierreCicloVisita(Base):
    """Registro de un cierre de ciclo de visita (Parte 5 — Ruptura de Secuencia).

    Al cerrar un ciclo se hace rodar el contador `ciclos_sin_visita` de cada médico:
    se resetea a 0 si tuvo ≥1 visita ejecutada, o se incrementa si no tuvo ninguna.
    Esta tabla guarda el resumen del cierre y sirve de guard de idempotencia: un ciclo
    solo puede cerrarse una vez (evita doble incremento del contador)."""
    __tablename__ = "CierreCicloVisita"
    __table_args__ = (
        Index("IX_CierreVisita_ciclo", "ciclo_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    fecha_cierre: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    panel: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visitados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sin_visitar: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ruptura_nueva: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # contador incrementado este cierre
    ruptura_critica: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # quedaron con ≥3 ciclos sin visita
    cerrado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)


class ParrillaPromocional(Base):
    """Parrilla promocional del ciclo (Parte 6 del spec): qué productos y mensaje
    clave debe promover cada línea en el ciclo, con prioridad y meta de muestras.

    `producto` es texto libre (no hay catálogo de productos estable en el sistema,
    igual que `producto_foco` en otras tablas). La mantiene gestión (ADMIN/GER PROD)
    con patrón delete-then-insert por (ciclo, línea)."""
    __tablename__ = "ParrillaPromocional"
    __table_args__ = (
        Index("IX_Parrilla_ciclo_linea", "ciclo_id", "linea_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    linea_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False)
    producto_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Producto.id"), nullable=True)  # producto del catálogo
    producto: Mapped[str] = mapped_column(String(120), nullable=False)  # copia del código/nombre (display)
    mensaje_clave: Mapped[str | None] = mapped_column(String(300), nullable=True)
    segmento_target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prioridad: Mapped[int] = mapped_column(Integer, nullable=False, default=1)   # 1 = mayor
    meta_muestras: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # meta muestras / visita
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Publicación: el VM no ve la parrilla hasta que el Gerente de Producto la publica.
    publicada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fecha_publicacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publicada_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    modificado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)


class MuestraEntregada(Base):
    """Muestra médica entregada en una visita (Parte 6 del spec). El VM registra la
    entrega de un producto (por nombre, alineado con la parrilla) a un médico de su
    panel; alimenta el reporte de muestras vs meta."""
    __tablename__ = "MuestraEntregada"
    __table_args__ = (
        Index("IX_Muestra_vm_ciclo", "vm_id", "ciclo_id"),
        Index("IX_Muestra_medico", "medico_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    medico_id: Mapped[int] = mapped_column(Integer, ForeignKey("Visita.DIM_MedicoVisita.id"), nullable=False)
    producto: Mapped[str] = mapped_column(String(120), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fecha_entrega: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    registrado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)


class ParametroCosto(Base):
    """Parámetros de costo del ciclo para el análisis de Costo & ROI (Parte 8).

    Una fila por (ciclo, línea). `linea_id` NULL = valor por defecto del ciclo. La
    resolución es en cascada: (ciclo, línea) específica primero, luego (ciclo, NULL).
    Costos variables por contacto/muestra + un costo fijo del ciclo."""
    __tablename__ = "ParametroCosto"
    __table_args__ = (
        Index("IX_ParamCosto_ciclo_linea", "ciclo_id", "linea_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    costo_visita: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)      # por contacto ejecutado
    costo_muestra: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)     # por unidad entregada
    costo_fijo_ciclo: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)  # costos fijos del ciclo
    moneda: Mapped[str] = mapped_column(String(8), nullable=False, default="RD$")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    modificado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)


class CostoEstructura(Base):
    """Estructura de costo del representante + parámetros de planeación anual e impacto
    de cobertura, por (ciclo, línea). Configurado por Finanzas/Gerencia. Alimenta el
    módulo Costo & ROI de Visita (bloques: costo fijo, plan anual, impacto)."""
    __tablename__ = "CostoEstructura"
    __table_args__ = (
        Index("IX_CostoEstructura_ciclo_linea", "ciclo_id", "linea_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    moneda: Mapped[str] = mapped_column(String(8), nullable=False, default="RD$")
    # Estructura de costo del representante
    salario_mensual: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    cargas_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)      # % TSS/AFP/ARS/regalía
    viaticos_dia: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    materiales_ciclo: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    dias_campo: Mapped[int] = mapped_column(Integer, nullable=False, default=19)
    total_visitas: Mapped[int] = mapped_column(Integer, nullable=False, default=190)
    dias_mes: Mapped[int] = mapped_column(Integer, nullable=False, default=21)                # días hábiles/mes (prorrateo)
    # Planificación anual
    visitadores: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    visitas_ciclo_vm: Mapped[int] = mapped_column(Integer, nullable=False, default=190)
    ciclos_anio: Mapped[int] = mapped_column(Integer, nullable=False, default=11)
    # Impacto de cobertura (venta en riesgo)
    coef_conservador: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0.40)
    coef_optimista: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0.70)
    psp_a: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)            # PSP/contacto Cat A
    psp_b: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    psp_c: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    med_sin_visitar_a: Mapped[int | None] = mapped_column(Integer, nullable=True)              # override; si null → proyección
    med_sin_visitar_b: Mapped[int | None] = mapped_column(Integer, nullable=True)
    med_sin_visitar_c: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    modificado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)


class CostoProducto(Base):
    """Datos financieros por producto/ciclo/línea: costo de muestras, pool de ventas y
    presupuesto/precio anual. Ingresado por Finanzas/Gerencia (formulario, Excel o API)."""
    __tablename__ = "CostoProducto"
    __table_args__ = (
        Index("IX_CostoProducto_ciclo_linea", "ciclo_id", "linea_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    producto_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Producto.id"), nullable=True)
    producto: Mapped[str] = mapped_column(String(120), nullable=False)         # código (display)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Costo de muestras
    costo_unitario_muestra: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    cantidad_muestras: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Pool de ventas
    pool_ventas: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    visitas_detalladas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Plan anual
    presupuesto_anual: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    precio_prom: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
