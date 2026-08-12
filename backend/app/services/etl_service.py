"""
SCGCPR — Motor ETL: Procesamiento de archivos Excel
FIX C-01: Resuelve linea_id, gerente_id y capacitacion_id desde BD
          (ya no usa valores hardcodeados 0/1).
FIX C-03: Usa puntaje_service.convertir_a_puntaje() para
          convertir resultados operativos a puntos vía DIM_IndicadorTabla,
          filtrando también por pais_codigo.
FIX W-05: Cumplimiento acotado a 100% en todos los KPIs.
FIX C-04: Importación de puntaje_service movida al nivel de módulo
          (eliminada importación dentro del loop).

REDISEÑO (jun-2026): la tabla de entrada del ETL pasó de
FACT_RendimientoComercial a FACT_ResultadoIndicador (modelo
ResultadoIndicador en app.models.hechos). Cambios de nombre de columnas:
  valor_real → resultado_real
  porcentaje_cumplimiento → resultado_porcentaje
  puntaje → puntos_obtenidos
  valor_meta se elimina (las metas ahora viven en Config.DIM_MetaIndicador
  y se resuelven en el motor de recálculo, no en la carga).
Nuevos campos (factor_aplicado, puntos_maximos, porcentaje_logro) se dejan
en None durante la carga — los completa recalculo_service en la Fase 1.

Fases: Recepción → Validación → Transformación → Carga → Recálculo → Ranking
"""
import os
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session
from loguru import logger

from app.db.database import SessionLocal
from app.models.hechos import (
    CargaExcel, ResultadoIndicador, Ventas, EvoIR,
    Coaching, CapacitacionFact, Auditoria, KpiRaw,
)
from app.models.dimensiones import (
    RepresentanteMedico, Indicador, Ciclo, Gerente, CapacitacionDim, Linea
)
from app.services.puntaje_service import (
    convertir_a_puntaje,
    calcular_cumplimiento,
    calcular_puntaje_coaching,
)

# ── Utilidades internas ──────────────────────────────────────────────────────

# Alias de código de país: el Excel FACT_KPI_RM trae PAIS_CODIGO="DO" (ISO-2)
# para República Dominicana, mientras Config.DIM_Pais.codigo usa la
# abreviatura local "RD". Mismo país, dos convenciones — se normaliza aquí
# en vez de exigir que el Excel cambie su estructura (instrucción explícita
# del usuario: adaptar el código, no las tablas DIMS/FACT). Mismo alias que
# PAIS_CODIGO_ALIAS en app/api/v1/routers/dims.py — mantener sincronizados.
PAIS_CODIGO_ALIAS: dict[str, str] = {}  # vacío: DO es el código canónico



def _expandir_alias_pais(mapa_codigo_a_id: dict) -> dict:
    """Agrega entradas alias (ej. 'DO' -> mismo id que 'RD') a un mapa
    pais_codigo -> pais_codigo, sin pisar claves ya existentes en el mapa."""
    expandido = dict(mapa_codigo_a_id)
    for alias, real in PAIS_CODIGO_ALIAS.items():
        if real in mapa_codigo_a_id and alias not in expandido:
            expandido[alias] = mapa_codigo_a_id[real]
    return expandido


def _to_decimal(value) -> Decimal:
    """Convierte cualquier valor escalar a Decimal, manejando None/NaN."""
    if value is None:
        return Decimal("0")
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return Decimal("0")
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


#: Indicadores que el Excel YA NO alimenta. Decisión del cliente (12-ago-2026):
#: "nunca más Excel para este proceso". EVAL_CONOCIMIENTOS se captura en la
#: pantalla de Conocimientos, o llega por exámenes, o lo envía Mallén — las tres
#: dejan autoría y fecha, cosa que una hoja de cálculo no hace.
INDICADORES_SIN_EXCEL: frozenset[str] = frozenset({"EVAL_CONOCIMIENTOS"})


def _omitida_por_excel(ind_codigo: str) -> bool:
    """¿Este indicador dejó de alimentarse por Excel?

    Vive fuera de las ramas por tipo de archivo A PROPÓSITO: el guard nació solo
    en `KPI_RM` y la rama legacy `PRODUCTIVIDAD` —que también escribe en
    `FACT_ResultadoIndicador`— quedó como puerta abierta. Cualquier rama nueva
    que escriba en esa tabla debe llamarlo justo después de resolver
    `ind_codigo`, para no reabrir la misma puerta.
    """
    return ind_codigo in INDICADORES_SIN_EXCEL


# ── Columnas requeridas por tipo de archivo ──────────────────────────────────
COLUMNAS_REQUERIDAS = {
    # Tipo principal: FACT_KPI_RM — todos los KPIs de RM en un solo archivo
    "KPI_RM": ["rm_codigo", "indicador_codigo", "valor_real", "pais_codigo", "ciclo_id"],
    # Tipos legacy (mantenidos para compatibilidad)
    "PRODUCTIVIDAD": ["rm_codigo", "indicador_codigo", "valor_real", "valor_meta"],
    "COMERCIAL":     ["rm_codigo", "ventas_reales", "cuota"],
    "COACHING":      [
        "rm_codigo", "gerente_codigo", "tipo",
        "coaching_programado", "coaching_ejecutado", "calificacion_calidad"
    ],
    "CAPACITACION":  [
        "rm_codigo", "capacitacion_codigo", "asistio",
        "calificacion", "horas_completadas"
    ],
}


def procesar_excel_task(
    job_id: int,
    filepath: str,
    tipo_archivo: str,
    pais_codigo: Optional[str],
    ciclo_id: Optional[int],
    modo: str,
    usuario_id: int,
):
    """
    Task asíncrono ejecutado en background por FastAPI BackgroundTasks.
    Crea su propia sesión de BD para evitar conflictos con la sesión HTTP.
    """
    db: Session = SessionLocal()
    inicio = time.time()

    job = db.query(CargaExcel).filter(CargaExcel.id == job_id).first()
    if not job:
        logger.error(f"ETL: Job {job_id} no encontrado")
        db.close()
        return

    try:
        job.estado = "PROCESANDO"
        job.fecha_inicio = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"ETL [{job_id}] Iniciando — tipo={tipo_archivo}, modo={modo}")

        # Fase 1: Leer — la hoja de datos se identifica por sus COLUMNAS,
        # NO por su nombre (el archivo puede traer la hoja con cualquier nombre,
        # p.ej. "FACT_KPI_RM_VF" en lugar de "FACT_KPI_RM")
        sheet = _detectar_hoja_datos(filepath, tipo_archivo)
        df = _leer_excel(filepath, sheet_name=sheet)

        # Para KPI_RM: derivar pais_codigo real desde PAIS_CODIGO (no desde PAIS_ID del archivo)
        df.columns = [c.lower().strip() for c in df.columns]
        if tipo_archivo == "KPI_RM":
            # pais_codigo ya es el código canónico (DO, etc.) — se toma directo del Excel
            if "pais_codigo" in df.columns and len(df) > 0:
                primer_codigo = str(df["pais_codigo"].dropna().iloc[0]).strip().upper()
                pais_codigo = primer_codigo  # sin resolución a int
                logger.info(f"ETL KPI_RM: pais_codigo='{pais_codigo}' (canónico)")
            if not ciclo_id and "ciclo_id" in df.columns:
                try: ciclo_id = int(df["ciclo_id"].dropna().iloc[0])
                except: pass

        # Fase 2: Validar estructura
        errores_struct = _validar_estructura(df, tipo_archivo)
        if errores_struct:
            raise ValueError(f"Errores de estructura: {'; '.join(errores_struct)}")

        # Fase 2b: Guardar datos RAW en staging (siempre, antes de cualquier transformación)
        # Permite validar/auditar los datos originales del Excel sin transformar.
        if tipo_archivo == "KPI_RM":
            _guardar_staging_raw(db, df, job_id)
            db.commit()
            logger.info(f"ETL [{job_id}] Staging: {len(df)} filas guardadas en ETL.FACT_KPI_RAW")

        # Fase 3: Validar integridad referencial + enriquecer con IDs
        df, advertencias, mapas = _validar_y_enriquecer(
            db, df, tipo_archivo, pais_codigo, ciclo_id
        )

        total_filas = len(df)
        exitosas, errores = 0, []

        # Fase 4: Cargar (solo en PRODUCCION)
        if modo == "PRODUCCION":
            exitosas, errores, advertencias_carga = _cargar_datos(
                db, df, tipo_archivo, pais_codigo, ciclo_id, mapas
            )
            advertencias.extend(advertencias_carga)
            db.commit()

            # Fase 5: Recalcular ranking automáticamente para TODOS los ciclos del archivo
            if exitosas > 0:
                if "ciclo_id" in df.columns:
                    ciclos_unicos = sorted(
                        int(float(str(c)))
                        for c in df["ciclo_id"].dropna().unique()
                        if str(c).strip() not in ("", "nan")
                    )
                else:
                    ciclos_unicos = [ciclo_id] if ciclo_id else []
                logger.info(f"ETL [{job_id}] Fase5: recalculando ciclos {ciclos_unicos}")
                for cid in ciclos_unicos:
                    _recalcular_y_ranking(db, pais_codigo, cid, usuario_id)
        else:
            # Simulación: validar sin escribir
            exitosas = total_filas
            logger.info(f"ETL [{job_id}] SIMULACIÓN — {total_filas} filas válidas para cargar")

        duracion = round(time.time() - inicio, 2)
        now = datetime.now(timezone.utc)

        job.estado            = "EXITOSO"
        job.total_filas       = total_filas
        job.filas_exitosas    = exitosas if modo == "PRODUCCION" else 0
        job.filas_error       = len(errores)
        job.filas_advertencia = len(advertencias)
        job.log_errores       = json.dumps(errores[:100])     if errores     else None
        job.log_advertencias  = json.dumps(advertencias[:50]) if advertencias else None
        job.duracion_segundos = duracion
        job.fecha_fin         = now
        db.commit()

        db.add(Auditoria(
            usuario_id = usuario_id,
            accion     = "ETL",
            modulo     = "ETL",
            tabla      = f"FACT_{tipo_archivo.title()}",
            exitoso    = True,
            detalle    = (
                f"Job {job_id} | {tipo_archivo} | {modo} | "
                f"{exitosas}/{total_filas} filas | {duracion}s"
            ),
            fecha_hora = now,
        ))
        db.commit()

        logger.info(
            f"ETL [{job_id}] Completado en {duracion}s — "
            f"{exitosas}/{total_filas} exitosas, {len(errores)} errores"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"ETL [{job_id}] Error crítico: {e}")
        job = db.query(CargaExcel).filter(CargaExcel.id == job_id).first()
        if job:
            job.estado      = "ERROR"
            job.log_errores = str(e)[:2000]
            job.fecha_fin   = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


# ── Recálculo automático post-carga ──────────────────────────────────────────

def _recalcular_y_ranking(
    db: Session,
    pais_codigo: Optional[str],
    ciclo_id: Optional[int],
    usuario_id: int,
) -> None:
    """
    Fase 5 del ETL: dispara DW.sp_RecalcularCiclo para calcular
    puntos_obtenidos y regenerar FACT_ScoreIntegralRM + FACT_RankingRM.

    ciclo_id llega como el valor del Excel (que con el id explícito coincide
    con DIM_Ciclo.id). Si no coincide, se busca también por numero.
    Los errores se registran pero NO abortan el job ETL (el usuario puede
    relanzar el recálculo manualmente desde la pantalla de ETL).
    """
    from app.services.recalculo_service import recalcular_ciclo

    if not ciclo_id:
        logger.warning("ETL Fase5: ciclo_id vacío — recálculo omitido")
        return

    # Resolver el DB id: primero como PK directa, luego por numero+pais
    db_ciclo_id: Optional[int] = None
    ciclo_obj = db.query(Ciclo).filter(Ciclo.id == ciclo_id).first()
    if ciclo_obj:
        db_ciclo_id = ciclo_obj.id
    elif pais_codigo:
        ciclo_obj = db.query(Ciclo).filter(
            Ciclo.pais_codigo == pais_codigo,
            Ciclo.numero  == ciclo_id,
            Ciclo.activo  == True,
        ).first()
        if ciclo_obj:
            db_ciclo_id = ciclo_obj.id

    if not db_ciclo_id:
        logger.warning(
            f"ETL Fase5: no se encontró DIM_Ciclo para ciclo_id={ciclo_id} "
            f"pais_codigo={pais_codigo} — recálculo omitido"
        )
        return

    try:
        resultado = recalcular_ciclo(db, ciclo_id=db_ciclo_id, pais_codigo=pais_codigo)
        if resultado.get("abortado"):
            logger.warning(f"ETL Fase5: recálculo abortado — {resultado.get('motivo')}")
        else:
            logger.info(
                f"ETL Fase5: recálculo OK — "
                f"{resultado['filas_kpi_actualizadas']} KPIs, "
                f"{resultado['rankings_generados']} rankings"
            )
    except Exception as exc:
        logger.error(f"ETL Fase5: recálculo falló (no crítico, reintente manualmente): {exc}")


# ── Fases internas ────────────────────────────────────────────────────────────

def _detectar_hoja_datos(filepath: str, tipo_archivo: str) -> Optional[str]:
    """
    Identifica la hoja del Excel que contiene los datos esperados según sus
    COLUMNAS, sin depender de cómo se llame la hoja (FIX: antes se exigía el
    nombre exacto 'FACT_KPI_RM' y la carga fallaba con archivos como
    'FACT_KPI_RM_VF.xlsx' que traían la hoja con otro nombre).

    Estrategia:
      1. Si el archivo tiene una sola hoja → se usa esa, sin importar su nombre.
      2. Si tiene varias → se inspecciona el encabezado de cada una y se elige
         la PRIMERA que contenga TODAS las columnas requeridas para
         `tipo_archivo` (comparación insensible a mayúsculas/espacios).
      3. Si ninguna calza → error claro listando hojas disponibles y columnas
         esperadas, para que el usuario corrija el archivo sin adivinar nombres.
    """
    requeridas = {c.lower().strip() for c in COLUMNAS_REQUERIDAS.get(tipo_archivo, [])}
    if not requeridas:
        return None  # tipo sin columnas definidas: usar la primera hoja del archivo

    xl = pd.ExcelFile(filepath)
    hojas = xl.sheet_names

    if len(hojas) == 1:
        logger.info(f"ETL: archivo con una sola hoja ('{hojas[0]}') — se usa directamente")
        return hojas[0]

    for hoja in hojas:
        try:
            encabezados = {
                str(c).lower().strip()
                for c in pd.read_excel(filepath, sheet_name=hoja, nrows=0).columns
            }
        except Exception:
            continue
        if requeridas.issubset(encabezados):
            logger.info(f"ETL: hoja de datos detectada por columnas: '{hoja}' (de {hojas})")
            return hoja

    raise ValueError(
        f"No se encontró ninguna hoja con las columnas requeridas para '{tipo_archivo}' "
        f"({', '.join(sorted(requeridas))}). Hojas disponibles en el archivo: {', '.join(hojas)}."
    )


def _leer_excel(filepath: str, sheet_name: str = None) -> pd.DataFrame:
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in (".xlsx", ".xls"):
        raise ValueError(f"Formato de archivo no soportado: {ext}")
    df = pd.read_excel(filepath, sheet_name=sheet_name or 0, dtype=str)
    # Normalizar solo enteros con sufijo ".0": "1.0"→"1", "24.0"→"24"
    # NO tocar decimales reales como "0.625", "84.99"
    def _fix_int(v):
        if isinstance(v, str) and v.endswith('.0'):
            base = v[:-2]
            if base.lstrip('-').isdigit():
                return base
        return v
    for col in df.columns:
        df[col] = df[col].apply(_fix_int)
    return df


def _validar_estructura(df: pd.DataFrame, tipo: str) -> list:
    requeridas = COLUMNAS_REQUERIDAS.get(tipo, [])
    actuales   = {c.lower().strip() for c in df.columns}
    return [f"Columna faltante: '{c}'" for c in requeridas if c not in actuales]


def _validar_y_enriquecer(
    db: Session, df: pd.DataFrame, tipo: str, pais_codigo: str, ciclo_id: int
):
    """
    Construye mapas completos de códigos → IDs desde BD.
    Elimina filas con RM inválido y retorna mapas para uso en _cargar_datos.
    """
    advertencias = []
    df.columns   = [c.lower().strip() for c in df.columns]
    df           = df.fillna("").copy()

    # Para KPI_RM: construir mapa (pais_codigo, anio, numero) → ciclo_db_id
    # FIX: se resuelve por clave numérica estable (anio + numero de ciclo) en
    # lugar de nombre_canonico — evita romper la carga si cambia el formato
    # del nombre del ciclo en BD (p.ej. "Ciclo 1 2026" vs "CICLO-01-2026").
    # y mapa pais_codigo → pais_db_id
    mapa_ciclo: dict = {}
    mapa_pais_cod: dict = {}
    if tipo == "KPI_RM":
        from app.models.dimensiones import Pais as PaisModel
        for p in db.query(PaisModel).filter(PaisModel.activo == True).all():
            mapa_pais_cod[p.codigo.strip().upper()] = p.codigo.strip().upper()
        mapa_pais_cod = _expandir_alias_pais(mapa_pais_cod)
        ciclos_db = db.query(Ciclo).filter(Ciclo.activo == True).all()
        for c in ciclos_db:
            mapa_ciclo[(c.pais_codigo, c.anio, c.numero)] = c.id
        logger.info(f"ETL: mapa_ciclo={len(mapa_ciclo)}, mapa_pais={len(mapa_pais_cod)}")
        # Validación rápida: verificar que al menos el ciclo de la primera fila exista
        if len(df) > 0 and "anio" in df.columns and "ciclo_id" in df.columns:
            primera = df.iloc[0]
            try:
                p_anio   = int(float(str(primera.get("anio", ""))))
                p_numero = int(float(str(primera.get("ciclo_id", ""))))
            except (ValueError, TypeError):
                p_anio = p_numero = None
            if p_anio is not None and not any(k[1] == p_anio and k[2] == p_numero for k in mapa_ciclo):
                raise ValueError(
                    f"Ciclo {p_numero}/{p_anio} no encontrado en BD. Importa los ciclos primero."
                )
    else:
        # Tipos legacy: resolver por ID único
        ciclo = db.query(Ciclo).filter(Ciclo.id == ciclo_id).first() if ciclo_id else None
        if not ciclo:
            raise ValueError(f"Ciclo ID={ciclo_id} no encontrado. Verifica que los ciclos estén importados.")
        if ciclo.cerrado:
            raise ValueError(f"Ciclo '{ciclo.nombre}' está cerrado — no se permite carga")

    # Para KPI_RM cargamos RMs de todos los países (el archivo puede tener múltiples)
    # Para otros tipos solo del país especificado
    rm_filter = (RepresentanteMedico.activo == True,) if tipo == "KPI_RM" else \
                (RepresentanteMedico.pais_codigo == pais_codigo, RepresentanteMedico.activo == True)
    rms_db = db.query(RepresentanteMedico).filter(*rm_filter).all()
    mapa_rm = {
        rm.codigo: {"id": rm.id, "linea_id": rm.linea_id, "gerente_id": rm.gerente_id, "pais_codigo": rm.pais_codigo}
        for rm in rms_db
    }

    mapa_gerente = {
        g.codigo: g.id
        for g in db.query(Gerente).filter(Gerente.pais_codigo == pais_codigo, Gerente.activo == True).all()
    }

    mapa_cap = {
        c.codigo: {"id": c.id, "puntaje_aprobacion": c.puntaje_aprobacion}
        for c in db.query(CapacitacionDim).filter(CapacitacionDim.activo == True).all()
    }

    # Mapa indicador — clave (pais_codigo, codigo) para evitar colisiones cuando el
    # mismo codigo existe en múltiples países (p.ej. COB_MD_F2 en RD y en PR).
    # Para KPI_RM se cargan todos los países; para otros tipos solo el del job.
    ind_filter = (Indicador.activo == True,) if tipo == "KPI_RM" else \
                 (Indicador.pais_codigo == pais_codigo, Indicador.activo == True)
    mapa_ind: dict = {}
    for _i in db.query(Indicador).filter(*ind_filter).all():
        mapa_ind[(_i.pais_codigo, _i.codigo)] = _i.id
        # Alias sin pais para compatibilidad con tipos legacy (PRODUCTIVIDAD, etc.)
        if tipo != "KPI_RM":
            mapa_ind[_i.codigo] = _i.id

    indices_invalidos = []
    for idx, row in df.iterrows():
        rm_codigo = str(row.get("rm_codigo", "")).strip()
        if rm_codigo not in mapa_rm:
            advertencias.append(f"Fila {idx + 2}: RM '{rm_codigo}' no encontrado en país {pais_codigo}")
            indices_invalidos.append(idx)

    if indices_invalidos:
        logger.warning(f"ETL: {len(indices_invalidos)} filas eliminadas por RM inválido")
    df = df.drop(index=indices_invalidos).reset_index(drop=True)

    mapas = {
        "rm":      mapa_rm,
        "gerente": mapa_gerente,
        "cap":     mapa_cap,
        "ind":     mapa_ind,
        "ciclo":   mapa_ciclo,
        "pais":    mapa_pais_cod,
    }
    return df, advertencias, mapas


def _guardar_staging_raw(db: Session, df: pd.DataFrame, carga_id: int) -> None:
    """Guarda el DataFrame KPI_RM en ETL.FACT_KPI_RAW tal como viene del Excel.

    Borra primero las filas anteriores del mismo ciclo (de CUALQUIER carga previa)
    para evitar duplicados al re-subir el mismo archivo. Si no se pueden determinar
    los ciclos, borra solo las filas de esta carga (fallback).
    Columnas opcionales (como mes_id) se dejan en None si no existen en el DF.
    """
    # Identificar ciclos únicos en el archivo (valor numérico raw, ej: 3)
    ciclos_raw: list = []
    if "ciclo_id" in df.columns:
        for x in df["ciclo_id"].dropna().unique():
            try:
                ciclos_raw.append(int(float(str(x))))
            except (ValueError, TypeError):
                pass

    if ciclos_raw:
        # Borrar staging anterior de esos mismos ciclos (sin importar carga_id)
        deleted = db.query(KpiRaw).filter(KpiRaw.ciclo_id.in_(ciclos_raw)).delete(synchronize_session=False)
        logger.debug(f"ETL staging: eliminados {deleted} registros previos de ciclos {ciclos_raw}")
    else:
        # Fallback: solo borrar filas de esta carga
        db.query(KpiRaw).filter(KpiRaw.carga_id == carga_id).delete(synchronize_session=False)

    now = datetime.now(timezone.utc)
    filas = []
    for _, row in df.iterrows():
        def _get(col):
            val = row.get(col)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            return val

        def _get_int(col):
            # FIX: algunas columnas "*_id" del Excel ahora pueden traer un
            # código de negocio (p.ej. rm_id='VM-1') en vez de un ID numérico
            # — cambio de estructura relacionado a RM. ETL.FACT_KPI_RAW es
            # tabla de staging sin FK, así que si no es numérico se guarda
            # NULL aquí (el código de negocio igual queda en *_codigo); la
            # resolución real a ID ocurre después en _validar_y_enriquecer/
            # _cargar_datos vía mapa_rm[rm_codigo].
            val = _get(col)
            if val is None:
                return None
            try:
                return int(float(str(val)))
            except (ValueError, TypeError):
                return None

        filas.append(KpiRaw(
            carga_id         = carga_id,
            fact_id          = _get_int("fact_id"),
            pais_codigo      = str(_get("pais_codigo")).strip() if _get("pais_codigo") is not None else None,
            rm_id            = _get_int("rm_id"),
            nombre_rm        = str(_get("nombre_rm")).strip() if _get("nombre_rm") is not None else None,
            rm_codigo        = str(_get("rm_codigo")).strip() if _get("rm_codigo") is not None else None,
            gerente_id       = _get_int("gerente_id"),
            gerente_codigo   = str(_get("gerente_codigo")).strip() if _get("gerente_codigo") is not None else None,
            linea_id         = _get_int("linea_id"),
            linea_codigo     = str(_get("linea_codigo")).strip() if _get("linea_codigo") is not None else None,
            indicador_id     = _get_int("indicador_id"),
            indicador_codigo = str(_get("indicador_codigo")).strip() if _get("indicador_codigo") is not None else None,
            tipo_periodo     = str(_get("tipo_periodo")).strip() if _get("tipo_periodo") is not None else None,
            ciclo_id         = _get_int("ciclo_id"),
            ciclo_nombre     = str(_get("ciclo_nombre")).strip() if _get("ciclo_nombre") is not None else None,
            mes_id           = _get_int("mes_id"),
            ciclo_mes        = _get_int("ciclo_mes"),
            anio             = _get_int("anio"),
            valor_real       = _get("valor_real"),
            fecha_carga      = now,
        ))

    db.bulk_save_objects(filas)


def _cargar_datos(
    db: Session,
    df: pd.DataFrame,
    tipo: str,
    pais_codigo: str,
    ciclo_id: int,
    mapas: dict,
) -> tuple:
    """
    Carga los datos en las tablas de hechos correspondientes.
    El puntaje se obtiene de DIM_IndicadorTabla filtrado por (indicador_id, pais_codigo).
    """
    exitosas = 0
    errores  = []
    advertencias_carga: list[str] = []
    # Cuenta por indicador en vez de una advertencia por fila: un archivo real
    # trae ~170 filas por indicador/país, y una advertencia por fila desborda
    # el log (json.dumps(advertencias[:50]) trunca y desplaza las advertencias
    # de RM inválido que ya vienen de _validar_y_enriquecer).
    omitidos_por_excel: dict[str, int] = {}

    mapa_rm      = mapas["rm"]
    mapa_gerente = mapas["gerente"]
    mapa_cap     = mapas["cap"]
    mapa_ind     = mapas["ind"]
    mapa_ciclo      = mapas.get("ciclo", {})
    mapa_ciclo_pais = mapas.get("pais", {})

    # ── Para KPI_RM: borrar datos anteriores del mismo ciclo antes de insertar.
    # db.merge() sin 'id' es INSERT (no UPSERT), por lo que sin este borrado
    # cada carga duplica todas las filas en FACT_ResultadoIndicador.
    # Estrategia de resolución de ciclo_db_id:
    #   1. Intentar con (pais_codigo, anio, numero) si el archivo trae columna 'anio'.
    #   2. Si 'anio' falta, usar fallback: buscar en DIM_Ciclo por (pais_codigo, numero).
    if tipo == "KPI_RM":
        ciclos_a_limpiar: set = set()
        if "ciclo_id" in df.columns and "pais_codigo" in df.columns:
            cols_delete = ["pais_codigo", "ciclo_id"]
            if "anio" in df.columns:
                cols_delete.append("anio")
            pares = df[cols_delete].drop_duplicates()
            for _, r in pares.iterrows():
                try:
                    pais_cod = str(r.get("pais_codigo", "")).strip().upper()
                    p_id_loc = mapa_ciclo_pais.get(pais_cod, pais_codigo)
                    num_loc  = int(float(str(r.get("ciclo_id", ""))))

                    cid = None
                    # Intento 1: clave completa (pais, anio, numero)
                    if "anio" in r.index:
                        try:
                            anio_loc = int(float(str(r.get("anio", ""))))
                            cid = mapa_ciclo.get((p_id_loc, anio_loc, num_loc))
                            if not cid:
                                cid = next(
                                    (v for (p, a, n), v in mapa_ciclo.items() if a == anio_loc and n == num_loc),
                                    None,
                                )
                        except (ValueError, TypeError):
                            pass

                    # Intento 2 (fallback): buscar en DIM_Ciclo por pais_codigo + numero
                    if not cid:
                        ciclo_obj = (
                            db.query(Ciclo)
                              .filter(Ciclo.pais_codigo == p_id_loc, Ciclo.numero == num_loc)
                              .first()
                        )
                        if ciclo_obj:
                            cid = ciclo_obj.id
                        else:
                            # Último recurso: cualquier ciclo con ese numero
                            ciclo_any = db.query(Ciclo).filter(Ciclo.numero == num_loc).first()
                            if ciclo_any:
                                cid = ciclo_any.id

                    if cid:
                        ciclos_a_limpiar.add(cid)
                except (ValueError, TypeError):
                    pass

        if ciclos_a_limpiar:
            # El borrado se acota a los indicadores que ESTE archivo trae. Antes
            # barría el ciclo entero: cuando todo venía del Excel era coherente
            # —borraba lo suyo y lo reponía—, pero desde la integración de Mallén
            # destruía en silencio los cuatro indicadores de visita y VENTAS, que
            # el Excel no repone. La regla es: un cargador solo puede reemplazar
            # lo que él mismo vuelve a escribir.
            codigos_archivo = {
                str(c).strip().upper()
                for c in df.get("indicador_codigo", pd.Series(dtype=str)).dropna()
            } - INDICADORES_SIN_EXCEL
            ids_a_limpiar = [i for (_p, c), i in mapa_ind.items()
                             if isinstance(c, str) and c in codigos_archivo]
            if ids_a_limpiar:
                deleted = (
                    db.query(ResultadoIndicador)
                      .filter(ResultadoIndicador.ciclo_id.in_(list(ciclos_a_limpiar)),
                              ResultadoIndicador.indicador_id.in_(ids_a_limpiar))
                      .delete(synchronize_session=False)
                )
                db.flush()
                logger.info(f"ETL: eliminados {deleted} registros previos de "
                            f"FACT_ResultadoIndicador (ciclos {ciclos_a_limpiar}, "
                            f"{len(ids_a_limpiar)} indicadores del archivo)")
            else:
                logger.info("ETL: el archivo no trae indicadores que el Excel "
                            "pueda reponer — no se borra nada")
        else:
            logger.warning("ETL: no se pudo determinar ciclos_a_limpiar — se omite borrado previo")

    # DEBUG: log mapa_ind keys para diagnóstico (primeros 5)
    if tipo == "KPI_RM":
        sample_keys = list(mapa_ind.keys())[:5]
        logger.info(f"ETL _cargar_datos DEBUG: mapa_ind keys (primeros 5): {sample_keys}")
        logger.info(f"ETL _cargar_datos DEBUG: mapa_rm keys (primeros 5): {list(mapa_rm.keys())[:5]}")
        logger.info(f"ETL _cargar_datos DEBUG: pais_codigo={pais_codigo}, df cols={list(df.columns)[:10]}")

    first_error_logged = False
    for idx, row in df.iterrows():
        try:
            rm_codigo  = str(row.get("rm_codigo", "")).strip()
            rm_info    = mapa_rm[rm_codigo]
            rm_id      = rm_info["id"]
            linea_id   = rm_info["linea_id"]
            gerente_id = rm_info["gerente_id"]

            if tipo == "KPI_RM":
                # Formato FACT_KPI_RM: un registro por RM + indicador + periodo
                ind_codigo = str(row.get("indicador_codigo", "")).strip().upper()
                if _omitida_por_excel(ind_codigo):
                    omitidos_por_excel[ind_codigo] = omitidos_por_excel.get(ind_codigo, 0) + 1
                    continue

                # Usar pais_codigo del RM para resolver el indicador_id correcto.
                # Esto evita la colisión cuando el mismo codigo existe en varios países.
                rm_pais_codigo_temp = rm_info.get("pais_codigo", pais_codigo)
                ind_id = mapa_ind.get((rm_pais_codigo_temp, ind_codigo))
                if not ind_id:
                    # Fallback: buscar por codigo en cualquier país
                    ind_id = next(
                        (v for (p, c), v in mapa_ind.items() if isinstance(c, str) and c == ind_codigo),
                        None,
                    )
                if not ind_id:
                    if not first_error_logged:
                        logger.error(f"ETL DEBUG primer error: ind_codigo='{ind_codigo}', rm_pais_codigo={rm_pais_codigo_temp}, mapa_ind_sample={list(mapa_ind.keys())[:8]}")
                        first_error_logged = True
                    errores.append(f"Fila {idx+2}: Indicador '{ind_codigo}' no encontrado para país {rm_pais_codigo_temp}")
                    continue

                valor_real = _to_decimal(row.get("valor_real", 0))

                # Resolver pais_codigo real desde pais_codigo de la fila
                fila_pais_codigo = str(row.get("pais_codigo", "")).strip().upper()
                fila_pais_codigo = mapa_ciclo_pais.get(fila_pais_codigo, pais_codigo) if fila_pais_codigo else pais_codigo

                # FIX: resolver ciclo por clave numérica (pais_codigo, anio, numero) —
                # el archivo trae 'anio' y 'ciclo_id' (numero relativo del ciclo,
                # NO el id real de DIM_Ciclo), no por nombre_canonico (frágil).
                try:
                    fila_anio   = int(float(str(row.get("anio", ""))))
                    fila_numero = int(float(str(row.get("ciclo_id", ""))))
                except (ValueError, TypeError):
                    fila_anio = fila_numero = None

                fila_ciclo_id = mapa_ciclo.get((fila_pais_codigo, fila_anio, fila_numero))
                if not fila_ciclo_id:
                    # Fallback: buscar por (anio, numero) sin importar país
                    fila_ciclo_id = next(
                        (v for (p, a, n), v in mapa_ciclo.items() if a == fila_anio and n == fila_numero),
                        ciclo_id
                    )

                mes_id = None
                if "mes_id" in row and row.get("mes_id"):
                    try: mes_id = int(float(str(row["mes_id"])))
                    except: pass


                # Usar pais_codigo real del RM (no del archivo)
                rm_pais_codigo = rm_info.get("pais_codigo", fila_pais_codigo)

                obj = ResultadoIndicador(
                    rm_id=rm_id, pais_codigo=rm_pais_codigo, ciclo_id=fila_ciclo_id,
                    indicador_id=ind_id, linea_id=linea_id, gerente_id=gerente_id,
                    mes_id=mes_id,
                    resultado_real=valor_real,
                    resultado_porcentaje=None,
                    factor_aplicado=None,
                    puntos_obtenidos=None,
                    puntos_maximos=None,
                    porcentaje_logro=None,
                    activo=True,
                )
                db.add(obj)
                exitosas += 1

            elif tipo == "PRODUCTIVIDAD":
                ind_codigo = str(row.get("indicador_codigo", "")).strip().upper()
                if _omitida_por_excel(ind_codigo):
                    omitidos_por_excel[ind_codigo] = omitidos_por_excel.get(ind_codigo, 0) + 1
                    continue

                ind_id     = mapa_ind.get(ind_codigo)
                if not ind_id:
                    errores.append(f"Fila {idx+2}: Indicador '{ind_codigo}' no encontrado")
                    continue

                valor_real   = _to_decimal(row.get("valor_real", 0))
                valor_meta   = _to_decimal(row.get("valor_meta", 0))
                cumplimiento = calcular_cumplimiento(valor_real, valor_meta)
                puntaje      = convertir_a_puntaje(db, ind_id, cumplimiento, pais_codigo)

                obj = ResultadoIndicador(
                    rm_id=rm_id, pais_codigo=pais_codigo, ciclo_id=ciclo_id,
                    indicador_id=ind_id, linea_id=linea_id, gerente_id=gerente_id,
                    resultado_real=valor_real,
                    resultado_porcentaje=cumplimiento,
                    factor_aplicado=None,
                    puntos_obtenidos=puntaje,
                    puntos_maximos=None,
                    porcentaje_logro=None,
                    activo=True,
                )
                db.add(obj)
                exitosas += 1

            elif tipo == "COMERCIAL":
                ventas_reales = _to_decimal(row.get("ventas_reales", 0))
                cuota         = _to_decimal(row.get("cuota", 0))
                cumplimiento  = calcular_cumplimiento(ventas_reales, cuota)
                ind_id_ventas = mapa_ind.get("VENTAS")
                puntaje = convertir_a_puntaje(db, ind_id_ventas, cumplimiento, pais_codigo) if ind_id_ventas else Decimal("0")

                obj = Ventas(
                    rm_id=rm_id, pais_codigo=pais_codigo, ciclo_id=ciclo_id,
                    linea_id=linea_id,
                    ventas_reales=ventas_reales, cuota=cuota,
                    cumplimiento_pct=cumplimiento, puntaje=puntaje,
                )
                db.add(obj)
                exitosas += 1

            elif tipo == "COACHING":
                gerente_codigo   = str(row.get("gerente_codigo", "")).strip()
                gerente_id_local = mapa_gerente.get(gerente_codigo)
                coaching_tipo    = str(row.get("tipo", "")).strip()
                prog    = _to_decimal(row.get("coaching_programado", 0))
                ejec    = _to_decimal(row.get("coaching_ejecutado", 0))
                cal     = _to_decimal(row.get("calificacion_calidad", 0))
                puntaje = calcular_puntaje_coaching(prog, ejec, cal)

                obj = Coaching(
                    gerente_id=gerente_id_local, rm_id=rm_id,
                    pais_codigo=pais_codigo, ciclo_id=ciclo_id, linea_id=linea_id,
                    tipo=coaching_tipo,
                    coaching_programado=prog,
                    coaching_ejecutado=ejec,
                    calificacion_calidad=cal,
                    puntaje=puntaje,
                )
                db.add(obj)
                exitosas += 1

            elif tipo == "CAPACITACION":
                cap_codigo = str(row.get("capacitacion_codigo", "")).strip()
                cap_info   = mapa_cap.get(cap_codigo)
                if not cap_info:
                    errores.append(f"Fila {idx+2}: Capacitacion '{cap_codigo}' no encontrada")
                    continue

                asistio      = str(row.get("asistio", "")).strip().upper() in ("1", "TRUE", "SI", "YES", "S")
                calificacion = _to_decimal(row.get("calificacion", 0))
                horas        = _to_decimal(row.get("horas_completadas", 0))
                aprobado     = asistio and calificacion >= _to_decimal(str(cap_info.get("puntaje_aprobacion") or 60))

                obj = CapacitacionFact(
                    rm_id=rm_id, pais_codigo=pais_codigo, ciclo_id=ciclo_id,
                    capacitacion_id=cap_info["id"],
                    asistio=asistio,
                    calificacion=calificacion,
                    aprobado=aprobado,
                    horas_completadas=horas,
                    puntaje=calificacion if asistio else Decimal("0"),
                )
                db.add(obj)
                exitosas += 1

        except KeyError:
            rm_cod = str(row.get("rm_codigo", ""))
            msg = f"Fila {idx+2}: RM '{rm_cod}' no encontrado"
            if not first_error_logged:
                rm_keys = list(mapa_rm.keys())[:5]
                logger.error(f"ETL DEBUG KeyError primer error: {msg} | mapa_rm_keys={rm_keys}")
                first_error_logged = True
            errores.append(msg)
        except Exception as exc:
            if not first_error_logged:
                logger.error(f"ETL DEBUG Exception primer error fila {idx+2}: {type(exc).__name__}: {exc}")
                first_error_logged = True
            errores.append(f"Fila {idx+2}: {exc}")

    # Una sola advertencia agregada por indicador omitido, no una por fila
    # (ver comentario junto a omitidos_por_excel más arriba).
    for ind_codigo, n in omitidos_por_excel.items():
        advertencias_carga.append(
            f"{n} fila(s) de {ind_codigo} omitidas: ya no se carga por Excel; "
            f"se captura en la pantalla de Conocimientos, llega por exámenes "
            f"o la envía Mallén, según la fuente del país.")

    return exitosas, errores, advertencias_carga
