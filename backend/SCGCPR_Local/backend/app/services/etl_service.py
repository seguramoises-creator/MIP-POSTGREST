"""
SCGCPR — Motor ETL: Procesamiento de archivos Excel
FIX C-01: Resuelve linea_id, gerente_id y capacitacion_id desde BD
          (ya no usa valores hardcodeados 0/1).
FIX C-03: Usa puntaje_service.convertir_a_puntaje() para
          convertir resultados operativos a puntos vía DIM_IndicadorTabla,
          filtrando también por pais_id.
FIX W-05: Cumplimiento acotado a 100% en todos los KPIs.
FIX C-04: Importación de puntaje_service movida al nivel de módulo
          (eliminada importación dentro del loop).

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
    CargaExcel, RendimientoComercial, Ventas, EvoIR,
    Coaching, CapacitacionFact, Auditoria,
)
from app.models.dimensiones import (
    RepresentanteMedico, Indicador, Ciclo, Gerente, CapacitacionDim, Linea
)
from app.services.puntaje_service import (
    convertir_a_puntaje,
    calcular_cumplimiento,
    calcular_puntaje_coaching,
)

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
    pais_id: Optional[int],
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

        # Fase 1: Leer (KPI_RM usa hoja específica)
        sheet = "FACT_KPI_RM" if tipo_archivo == "KPI_RM" else None
        df = _leer_excel(filepath, sheet_name=sheet)

        # Para KPI_RM: derivar pais_id real desde PAIS_CODIGO (no desde PAIS_ID del archivo)
        df.columns = [c.lower().strip() for c in df.columns]
        if tipo_archivo == "KPI_RM":
            # Construir mapa pais_codigo → pais_db_id desde BD
            from app.models.dimensiones import Pais as PaisModel
            paises_db = db.query(PaisModel).filter(PaisModel.activo == True).all()
            mapa_pais_codigo = {p.codigo.strip().upper(): p.id for p in paises_db}
            # pais_id se resuelve por PAIS_CODIGO del archivo
            if "pais_codigo" in df.columns and len(df) > 0:
                primer_codigo = str(df["pais_codigo"].dropna().iloc[0]).strip().upper()
                pais_id = mapa_pais_codigo.get(primer_codigo, pais_id)
                logger.info(f"ETL KPI_RM: pais_codigo='{primer_codigo}' → pais_db_id={pais_id}")
            if not ciclo_id and "ciclo_id" in df.columns:
                try: ciclo_id = int(df["ciclo_id"].dropna().iloc[0])
                except: pass

        # Fase 2: Validar estructura
        errores_struct = _validar_estructura(df, tipo_archivo)
        if errores_struct:
            raise ValueError(f"Errores de estructura: {'; '.join(errores_struct)}")

        # Fase 3: Validar integridad referencial + enriquecer con IDs
        df, advertencias, mapas = _validar_y_enriquecer(
            db, df, tipo_archivo, pais_id, ciclo_id
        )

        total_filas = len(df)
        exitosas, errores = 0, []

        # Fase 4: Cargar (solo en PRODUCCION)
        if modo == "PRODUCCION":
            exitosas, errores = _cargar_datos(
                db, df, tipo_archivo, pais_id, ciclo_id, mapas
            )
            db.commit()

            # Fase 5: Recalcular ranking automáticamente
            if exitosas > 0:
                _recalcular_y_ranking(db, pais_id, ciclo_id, usuario_id)
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


# ── Fases internas ────────────────────────────────────────────────────────────

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
    db: Session, df: pd.DataFrame, tipo: str, pais_id: int, ciclo_id: int
):
    """
    Construye mapas completos de códigos → IDs desde BD.
    Elimina filas con RM inválido y retorna mapas para uso en _cargar_datos.
    """
    advertencias = []
    df.columns   = [c.lower().strip() for c in df.columns]
    df           = df.fillna("").copy()

    # Para KPI_RM: construir mapa (nombre_canonico, pais_id) → ciclo_db_id
    # y mapa pais_codigo → pais_db_id
    mapa_ciclo: dict = {}
    mapa_pais_cod: dict = {}
    if tipo == "KPI_RM":
        from app.models.dimensiones import Pais as PaisModel
        for p in db.query(PaisModel).filter(PaisModel.activo == True).all():
            mapa_pais_cod[p.codigo.strip().upper()] = p.id
        ciclos_db = db.query(Ciclo).filter(Ciclo.activo == True).all()
        for c in ciclos_db:
            if c.nombre_canonico:
                mapa_ciclo[(c.nombre_canonico.strip(), c.pais_id)] = c.id
        logger.info(f"ETL: mapa_ciclo={len(mapa_ciclo)}, mapa_pais={len(mapa_pais_cod)}")
        # Validación rápida: verificar que al menos un ciclo del archivo exista
        if len(df) > 0 and "ciclo_nombre" in df.columns:
            primer_nombre = str(df["ciclo_nombre"].dropna().iloc[0]).strip()
            primer_pais   = int(df["pais_id"].dropna().iloc[0]) if "pais_id" in df.columns else pais_id
            if not any(k[0] == primer_nombre for k in mapa_ciclo):
                raise ValueError(f"Ciclo '{primer_nombre}' no encontrado en BD. Importa los ciclos primero.")
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
                (RepresentanteMedico.pais_id == pais_id, RepresentanteMedico.activo == True)
    rms_db = db.query(RepresentanteMedico).filter(*rm_filter).all()
    mapa_rm = {
        rm.codigo: {"id": rm.id, "linea_id": rm.linea_id, "gerente_id": rm.gerente_id, "pais_id": rm.pais_id}
        for rm in rms_db
    }

    mapa_gerente = {
        g.codigo: g.id
        for g in db.query(Gerente).filter(Gerente.pais_id == pais_id, Gerente.activo == True).all()
    }

    mapa_cap = {
        c.codigo: {"id": c.id, "puntaje_aprobacion": c.puntaje_aprobacion}
        for c in db.query(CapacitacionDim).filter(CapacitacionDim.activo == True).all()
    }

    # Mapa indicador — para KPI_RM cargamos de todos los países
    ind_filter = (Indicador.activo == True,) if tipo == "KPI_RM" else \
                 (Indicador.pais_id == pais_id, Indicador.activo == True)
    mapa_ind = {
        i.codigo: i.id
        for i in db.query(Indicador).filter(*ind_filter).all()
    }

    indices_invalidos = []
    for idx, row in df.iterrows():
        rm_codigo = str(row.get("rm_codigo", "")).strip()
        if rm_codigo not in mapa_rm:
            advertencias.append(f"Fila {idx + 2}: RM '{rm_codigo}' no encontrado en país {pais_id}")
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


def _cargar_datos(
    db: Session,
    df: pd.DataFrame,
    tipo: str,
    pais_id: int,
    ciclo_id: int,
    mapas: dict,
) -> tuple:
    """
    Carga los datos en las tablas de hechos correspondientes.
    El puntaje se obtiene de DIM_IndicadorTabla filtrado por (indicador_id, pais_id).
    """
    exitosas = 0
    errores  = []

    mapa_rm      = mapas["rm"]
    mapa_gerente = mapas["gerente"]
    mapa_cap     = mapas["cap"]
    mapa_ind     = mapas["ind"]
    mapa_ciclo      = mapas.get("ciclo", {})
    mapa_ciclo_pais = mapas.get("pais", {})

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
                ind_id     = mapa_ind.get(ind_codigo)
                if not ind_id:
                    errores.append(f"Fila {idx+2}: Indicador '{ind_codigo}' no encontrado")
                    continue

                valor_real = _to_decimal(row.get("valor_real", 0))

                # Resolver pais_id real desde pais_codigo de la fila
                ciclo_nombre = str(row.get("ciclo_nombre", "")).strip()
                fila_pais_codigo = str(row.get("pais_codigo", "")).strip().upper()
                fila_pais_id = mapa_ciclo_pais.get(fila_pais_codigo, pais_id) if fila_pais_codigo else pais_id

                fila_ciclo_id = mapa_ciclo.get((ciclo_nombre, fila_pais_id))
                if not fila_ciclo_id:
                    # Fallback: buscar solo por nombre sin importar país
                    fila_ciclo_id = next(
                        (v for (n, p), v in mapa_ciclo.items() if n == ciclo_nombre),
                        ciclo_id
                    )

                mes_id = None
                if "mes_id" in row and row.get("mes_id"):
                    try: mes_id = int(float(str(row["mes_id"])))
                    except: pass

                # Usar pais_id real del RM (no del archivo)
                rm_pais_id = rm_info.get("pais_id", fila_pais_id)

                obj = RendimientoComercial(
                    rm_id=rm_id, pais_id=rm_pais_id, ciclo_id=fila_ciclo_id,
                    indicador_id=ind_id, linea_id=linea_id, gerente_id=gerente_id,
                    mes_id=mes_id,
                    valor_real=valor_real,
                    valor_meta=None,
                    porcentaje_cumplimiento=None,
                    puntaje=None,
                    activo=True,
                )
                db.merge(obj)
                exitosas += 1

            elif tipo == "PRODUCTIVIDAD":
                ind_codigo = str(row.get("indicador_codigo", "")).strip().upper()
                ind_id     = mapa_ind.get(ind_codigo)
                if not ind_id:
                    errores.append(f"Fila {idx+2}: Indicador '{ind_codigo}' no encontrado")
                    continue

                valor_real   = _to_decimal(row.get("valor_real", 0))
                valor_meta   = _to_decimal(row.get("valor_meta", 0))
                cumplimiento = calcular_cumplimiento(valor_real, valor_meta)
                # FIX C-04: puntaje con filtro por pais_id (sin import dentro del loop)
                puntaje      = convertir_a_puntaje(db, ind_id, cumplimiento, pais_id)

                obj = RendimientoComercial(
                    rm_id=rm_id, pais_id=pais_id, ciclo_id=ciclo_id,
                    indicador_id=ind_id, linea_id=linea_id, gerente_id=gerente_id,
                    valor_real=valor_real, valor_meta=valor_meta,
                    porcentaje_cumplimiento=cumplimiento, puntaje=puntaje, activo=True,
                )
                db.merge(obj)
                exitosas += 1

            elif tipo == "COMERCIAL":
                ventas_reales = _to_decimal(row.get("ventas_reales", 0))
                cuota         = _to_decimal(row.get("cuota", 0))
                cumplimiento  = calcular_cumplimiento(ventas_reales, cuota)
                # Obtener puntaje de ventas si hay indicador configurado
                ind_id_ventas = mapa_ind.get("VENTAS")
                puntaje = convertir_a_puntaje(db, ind_id_ventas, cumplimiento, pais_id) if ind_id_ventas else Decimal("0")

                obj = Ventas(
                    rm_id=rm_id, pais_id=pais_id, ciclo_id=ciclo_id,
                    linea_id=linea_id,
                    ventas_reales=ventas_reales, cuota=cuota,
                    cumplimiento_pct=cumplimiento, puntaje=puntaje,
                )
                db.merge(obj)
                exitosas += 1

            elif tipo == "COACHING":
                gerente_codigo = str(row.get("gerente_codigo", "")).strip()
                g_id = mapa_gerente.get(gerente_codigo) or gerente_id
                if not g_id:
                    errores.append(f"Fila {idx+2}: Gerente '{gerente_codigo}' no encontrado")
                    continue

                programado    = int(_to_decimal(row.get("coaching_programado", 0)))
                ejecutado     = int(_to_decimal(row.get("coaching_ejecutado", 0)))
                calidad       = _to_decimal(row.get("calificacion_calidad", 0))
                cumplimiento  = calcular_cumplimiento(Decimal(ejecutado), Decimal(programado))
                puntaje       = calcular_puntaje_coaching(cumplimiento, calidad)

                obj = Coaching(
                    rm_id=rm_id, pais_id=pais_id, ciclo_id=ciclo_id,
                    gerente_id=g_id,
                    tipo=str(row.get("tipo", "INDIVIDUAL")).strip().upper(),
                    coaching_programado=programado,
                    coaching_ejecutado=ejecutado,
                    cumplimiento_pct=cumplimiento,
                    calificacion_calidad=calidad,
                    resultado_coaching=puntaje,
                    puntaje=puntaje,
                )
                db.merge(obj)
                exitosas += 1

            elif tipo == "CAPACITACION":
                cap_codigo = str(row.get("capacitacion_codigo", "")).strip()
                cap_info   = mapa_cap.get(cap_codigo)
                if not cap_info:
                    errores.append(f"Fila {idx+2}: Capacitación '{cap_codigo}' no encontrada")
                    continue

                calificacion = _to_decimal(row.get("calificacion", 0))
                aprobacion   = cap_info.get("puntaje_aprobacion") or Decimal("60")
                aprobado     = calificacion >= aprobacion
                puntaje      = calificacion if aprobado else Decimal("0")

                obj = CapacitacionFact(
                    rm_id=rm_id, pais_id=pais_id, ciclo_id=ciclo_id,
                    capacitacion_id=cap_info["id"],
                    asistio=str(row.get("asistio", "")).strip().upper() in ("1", "SI", "TRUE", "S"),
                    calificacion=calificacion,
                    aprobado=aprobado,
                    horas_completadas=_to_decimal(row.get("horas_completadas", 0)),
                    puntaje=puntaje,
                )
                db.merge(obj)
                exitosas += 1

        except KeyError:
            errores.append(f"Fila {idx+2}: RM no encontrado en mapa")
        except Exception as e:
            errores.append(f"Fila {idx+2}: {e}")

    db.commit()
    return exitosas, errores


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except Exception:
        return Decimal("0")


def _recalcular_y_ranking(db: Session, pais_id: int, ciclo_id: int, usuario_id: int):
    """Placeholder: lanzar recálculo de IUP y ranking post-carga."""
    logger.info(f"ETL: Disparando recálculo ranking — país={pais_id}, ciclo={ciclo_id}")
