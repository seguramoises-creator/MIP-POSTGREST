# --- credenciales desde backend/.env (parametrizado, no hardcodear) ---
import os as _os, pathlib as _pl
try:
    from dotenv import load_dotenv as _ld
    _ld(_pl.Path(__file__).resolve().parents[2] / '.env')
except Exception:
    pass
os = _os
# ----------------------------------------------------------------------
# Script: _fix_sp_provincia_municipio.py
# Hace dos cosas:
# 1. Backfill: actualiza Provincia, Municipio y EstadoConciliacion en los
#    registros existentes de cat.FactMedicoCategoriaSnapshot usando DimGeografia.
# 2. Recrea cat.sp_CalcularCategoriaMedica para que futuras cargas
#    pueblen esas columnas automaticamente.
#
# Correr desde backend/ con venv activo:
#   python _fix_sp_provincia_municipio.py

import sys
import pymssql

DB_SERVER   = "127.0.0.1"
DB_PORT     = 1433
DB_USER     = "segura"
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_NAME     = "SCGCPR"

# ── 1. Backfill de registros existentes ──────────────────────────────────────
# Usa cat.DimGeografia (via GeografiaKey existente) para llenar Provincia/Municipio.
# EstadoConciliacion se calcula comparando CategoriaCalculada vs CategoriaExcel.
BACKFILL_SQL = """
UPDATE f
SET
    f.Provincia          = ISNULL(g.Provincia, f.Provincia),
    f.Municipio          = ISNULL(g.Municipio, f.Municipio),
    f.EstadoConciliacion = CASE
        WHEN f.CategoriaExcel IS NULL OR LTRIM(RTRIM(f.CategoriaExcel)) = ''
             THEN 'SIN_CATEGORIA_EXCEL'
        WHEN UPPER(LTRIM(RTRIM(f.CategoriaCalculada))) =
             UPPER(LTRIM(RTRIM(f.CategoriaExcel)))
             THEN 'COINCIDE'
        ELSE 'DISCREPANCIA'
    END
FROM cat.FactMedicoCategoriaSnapshot f
LEFT JOIN cat.DimGeografia g ON g.GeografiaKey = f.GeografiaKey
WHERE f.Provincia IS NULL OR f.EstadoConciliacion IS NULL;
"""

# ── 2. Nueva version del SP ───────────────────────────────────────────────────
# Cambios respecto a la version original:
#   - INSERT incluye Provincia, Municipio, EstadoConciliacion, FechaCalculoUtc
#   - SELECT los toma de src.Provincia/src.Municipio (vienen de s.* del staging)
#   - EstadoConciliacion calculado inline comparando CategoriaCalculada vs CategoriaExcel
SP_SQL = """
CREATE OR ALTER PROCEDURE cat.sp_CalcularCategoriaMedica
    @LoadBatchKey BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @FechaCorte DATE = CAST(SYSUTCDATETIME() AS DATE);

    -- 1. Lookup: Especialidades -------------------------------------------------
    INSERT INTO cat.DimEspecialidad (PaisKey, Especialidad)
    SELECT DISTINCT p.PaisKey, LTRIM(RTRIM(s.Especialidad))
    FROM stg.MedicoCategoriaInput s
    JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
    WHERE s.LoadBatchKey = @LoadBatchKey AND s.Especialidad IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM cat.DimEspecialidad d
          WHERE d.PaisKey = p.PaisKey
            AND d.Especialidad = LTRIM(RTRIM(s.Especialidad)));

    -- 2. Lookup: Centros medicos ------------------------------------------------
    INSERT INTO cat.DimCentroMedico (PaisKey, CentroMedico)
    SELECT DISTINCT p.PaisKey, LTRIM(RTRIM(s.CentroMedico))
    FROM stg.MedicoCategoriaInput s
    JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
    WHERE s.LoadBatchKey = @LoadBatchKey AND s.CentroMedico IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM cat.DimCentroMedico d
          WHERE d.PaisKey = p.PaisKey
            AND d.CentroMedico = LTRIM(RTRIM(s.CentroMedico)));

    -- 3. Lookup: Geografias (Provincia + Municipio) ----------------------------
    INSERT INTO cat.DimGeografia (PaisKey, Provincia, Municipio)
    SELECT DISTINCT p.PaisKey, LTRIM(RTRIM(s.Provincia)), LTRIM(RTRIM(s.Municipio))
    FROM stg.MedicoCategoriaInput s
    JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
    WHERE s.LoadBatchKey = @LoadBatchKey
      AND s.Provincia IS NOT NULL AND s.Municipio IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM cat.DimGeografia d
          WHERE d.PaisKey = p.PaisKey
            AND d.Provincia = LTRIM(RTRIM(s.Provincia))
            AND d.Municipio = LTRIM(RTRIM(s.Municipio)));

    -- 4. Lookup: Representantes ------------------------------------------------
    INSERT INTO cat.DimRepresentanteMedico
           (PaisKey, CodigoRepresentante, NombreRepresentante,
            LineaIdOrigen, EquipoTexto, Activo)
    SELECT DISTINCT p.PaisKey, s.CodigoRepresentante,
           LTRIM(RTRIM(s.NombreRepresentante)), s.LineaIdOrigen,
           LTRIM(RTRIM(s.Equipo)), 1
    FROM stg.MedicoCategoriaInput s
    JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
    WHERE s.LoadBatchKey = @LoadBatchKey
      AND s.CodigoRepresentante IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM cat.DimRepresentanteMedico d
          WHERE d.PaisKey = p.PaisKey
            AND d.CodigoRepresentante = s.CodigoRepresentante);

    -- 5. Lookup: Medicos -------------------------------------------------------
    INSERT INTO cat.DimMedico (PaisKey, CodigoMedico, NombreMedico, EspecialidadKey)
    SELECT DISTINCT p.PaisKey, NULL, LTRIM(RTRIM(s.Medico)), esp.EspecialidadKey
    FROM stg.MedicoCategoriaInput s
    JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
    LEFT JOIN cat.DimEspecialidad esp
           ON esp.PaisKey = p.PaisKey
          AND esp.Especialidad = LTRIM(RTRIM(s.Especialidad))
    WHERE s.LoadBatchKey = @LoadBatchKey
      AND NOT EXISTS (
          SELECT 1 FROM cat.DimMedico d
          WHERE d.PaisKey = p.PaisKey
            AND d.NombreMedico = LTRIM(RTRIM(s.Medico))
            AND ISNULL(d.EspecialidadKey,-1) = ISNULL(esp.EspecialidadKey,-1));

    -- 6. Calcular scores y hacer INSERT en FactMedicoCategoriaSnapshot --------
    ;WITH src AS (
        SELECT s.*, p.PaisKey,
               med.MedicoKey, cm.CentroMedicoKey, geo.GeografiaKey, rep.RepresentanteKey
        FROM stg.MedicoCategoriaInput s
        JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
        LEFT JOIN cat.DimEspecialidad esp
               ON esp.PaisKey = p.PaisKey
              AND esp.Especialidad = LTRIM(RTRIM(s.Especialidad))
        JOIN cat.DimMedico med
               ON med.PaisKey = p.PaisKey
              AND med.NombreMedico = LTRIM(RTRIM(s.Medico))
              AND ISNULL(med.EspecialidadKey,-1) = ISNULL(esp.EspecialidadKey,-1)
        LEFT JOIN cat.DimCentroMedico cm
               ON cm.PaisKey = p.PaisKey
              AND cm.CentroMedico = LTRIM(RTRIM(s.CentroMedico))
        LEFT JOIN cat.DimGeografia geo
               ON geo.PaisKey = p.PaisKey
              AND geo.Provincia = LTRIM(RTRIM(s.Provincia))
              AND geo.Municipio = LTRIM(RTRIM(s.Municipio))
        LEFT JOIN cat.DimRepresentanteMedico rep
               ON rep.PaisKey = p.PaisKey
              AND rep.CodigoRepresentante = s.CodigoRepresentante
        WHERE s.LoadBatchKey = @LoadBatchKey
    ),
    comp AS (
        SELECT src.RowNumber, src.PaisKey, c.ComponenteKey, c.CodigoComponente,
               CASE c.CodigoComponente
                   WHEN 'PACIENTES_SEMANA'    THEN src.PacientesSemana
                   WHEN 'PODER_ADQUISITIVO'   THEN src.CostoConsulta
                   ELSE NULL
               END AS ValorNumero,
               CASE c.CodigoComponente
                   WHEN 'POTENCIAL_PRESCRIPCION'   THEN src.RecetasSemana
                   WHEN 'UBICACION_TERRITORIAL_CM' THEN src.UbicacionTerritorialCM
                   WHEN 'KOL'                      THEN src.KOL
                   ELSE NULL
               END AS ValorTexto
        FROM src CROSS JOIN cat.DimComponenteCategoria c
        WHERE c.Activo = 1
    ),
    match_regla AS (
        SELECT comp.RowNumber, comp.ComponenteKey, r.ReglaKey, r.Criterio, r.PuntajePct,
               ROW_NUMBER() OVER (
                   PARTITION BY comp.RowNumber, comp.ComponenteKey
                   ORDER BY r.Criterio DESC, r.ReglaKey
               ) AS rn
        FROM comp
        JOIN cat.DimReglaCategoriaMedica r
               ON r.PaisKey = comp.PaisKey
              AND r.ComponenteKey = comp.ComponenteKey
              AND r.Activo = 1
              AND r.VigenteDesde <= @FechaCorte
              AND (r.VigenteHasta IS NULL OR r.VigenteHasta >= @FechaCorte)
              AND (
                  (comp.ValorNumero IS NOT NULL
                   AND (r.ValorMinimo IS NULL OR comp.ValorNumero >= r.ValorMinimo)
                   AND (r.ValorMaximo IS NULL OR comp.ValorNumero <= r.ValorMaximo))
               OR (comp.ValorTexto IS NOT NULL
                   AND UPPER(LTRIM(RTRIM(comp.ValorTexto))) =
                       UPPER(LTRIM(RTRIM(r.ValorTexto))))
              )
    ),
    score AS (
        SELECT src.RowNumber,
               SUM(CASE WHEN mr.rn = 1 THEN mr.PuntajePct ELSE 0 END)      AS PuntajeTotalPct,
               COUNT(DISTINCT CASE WHEN mr.rn = 1 THEN mr.ComponenteKey END) AS ComponentesCalculados,
               COUNT(DISTINCT c.ComponenteKey)                                AS ComponentesRequeridos
        FROM src CROSS JOIN cat.DimComponenteCategoria c
        LEFT JOIN match_regla mr
               ON mr.RowNumber = src.RowNumber
              AND mr.ComponenteKey = c.ComponenteKey
              AND mr.rn = 1
        WHERE c.Activo = 1 AND c.Requerido = 1
        GROUP BY src.RowNumber
    )
    INSERT INTO cat.FactMedicoCategoriaSnapshot (
        LoadBatchKey, RowNumber, Periodo, PaisKey, MedicoKey,
        CentroMedicoKey, GeografiaKey, RepresentanteKey, Equipo,
        Provincia, Municipio,
        LineaIdOrigen, PacientesSemana, CostoConsulta, RecetasSemana,
        UbicacionTerritorialCM, KOL,
        PuntajeTotalPct, ClasificacionKey,
        CategoriaCalculada, CategoriaExcel, EstadoConciliacion,
        EstadoCalculo, MensajeCalculo
    )
    SELECT
        src.LoadBatchKey, src.RowNumber, src.Periodo, src.PaisKey, src.MedicoKey,
        src.CentroMedicoKey, src.GeografiaKey, src.RepresentanteKey, src.Equipo,
        LTRIM(RTRIM(src.Provincia)),
        LTRIM(RTRIM(src.Municipio)),
        src.LineaIdOrigen, src.PacientesSemana, src.CostoConsulta, src.RecetasSemana,
        src.UbicacionTerritorialCM, src.KOL,
        sc.PuntajeTotalPct, cl.ClasificacionKey, cl.Clase, src.CategoriaExcel,
        -- EstadoConciliacion: compara categoria calculada vs la del Excel
        CASE
            WHEN src.CategoriaExcel IS NULL
              OR LTRIM(RTRIM(src.CategoriaExcel)) = ''
                 THEN 'SIN_CATEGORIA_EXCEL'
            WHEN UPPER(LTRIM(RTRIM(cl.Clase))) =
                 UPPER(LTRIM(RTRIM(src.CategoriaExcel)))
                 THEN 'COINCIDE'
            ELSE 'DISCREPANCIA'
        END,
        CASE WHEN sc.ComponentesCalculados = sc.ComponentesRequeridos
             THEN 'CALCULADO' ELSE 'PENDIENTE' END,
        CASE WHEN sc.ComponentesCalculados = sc.ComponentesRequeridos
             THEN NULL
             ELSE CONCAT('Componentes calculados ', sc.ComponentesCalculados,
                         ' de ', sc.ComponentesRequeridos) END
    FROM src
    JOIN score sc ON sc.RowNumber = src.RowNumber
    LEFT JOIN cat.DimClasificacionMedica cl
           ON cl.PaisKey = src.PaisKey
          AND cl.Activo = 1
          AND cl.VigenteDesde <= @FechaCorte
          AND (cl.VigenteHasta IS NULL OR cl.VigenteHasta >= @FechaCorte)
          AND sc.PuntajeTotalPct BETWEEN cl.PuntajeMinPct AND cl.PuntajeMaxPct;

    -- 7. Detalle de componentes por medico ------------------------------------
    ;WITH src2 AS (
        SELECT s.*, p.PaisKey, f.MedicoCategoriaKey
        FROM stg.MedicoCategoriaInput s
        JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
        JOIN cat.FactMedicoCategoriaSnapshot f
               ON f.LoadBatchKey = s.LoadBatchKey
              AND f.RowNumber = s.RowNumber
        WHERE s.LoadBatchKey = @LoadBatchKey
    ),
    comp2 AS (
        SELECT src2.MedicoCategoriaKey, src2.PaisKey, c.ComponenteKey, c.CodigoComponente,
               CASE c.CodigoComponente
                   WHEN 'PACIENTES_SEMANA'   THEN src2.PacientesSemana
                   WHEN 'PODER_ADQUISITIVO'  THEN src2.CostoConsulta
                   ELSE NULL
               END AS ValorNumero,
               CASE c.CodigoComponente
                   WHEN 'POTENCIAL_PRESCRIPCION'   THEN src2.RecetasSemana
                   WHEN 'UBICACION_TERRITORIAL_CM' THEN src2.UbicacionTerritorialCM
                   WHEN 'KOL'                      THEN src2.KOL
                   ELSE NULL
               END AS ValorTexto
        FROM src2 CROSS JOIN cat.DimComponenteCategoria c
        WHERE c.Activo = 1
    ),
    match2 AS (
        SELECT comp2.*, r.ReglaKey, r.Criterio, r.PuntajePct,
               ROW_NUMBER() OVER (
                   PARTITION BY comp2.MedicoCategoriaKey, comp2.ComponenteKey
                   ORDER BY r.Criterio DESC, r.ReglaKey
               ) AS rn
        FROM comp2
        LEFT JOIN cat.DimReglaCategoriaMedica r
               ON r.PaisKey = comp2.PaisKey
              AND r.ComponenteKey = comp2.ComponenteKey
              AND r.Activo = 1
              AND r.VigenteDesde <= @FechaCorte
              AND (r.VigenteHasta IS NULL OR r.VigenteHasta >= @FechaCorte)
              AND (
                  (comp2.ValorNumero IS NOT NULL
                   AND (r.ValorMinimo IS NULL OR comp2.ValorNumero >= r.ValorMinimo)
                   AND (r.ValorMaximo IS NULL OR comp2.ValorNumero <= r.ValorMaximo))
               OR (comp2.ValorTexto IS NOT NULL
                   AND UPPER(LTRIM(RTRIM(comp2.ValorTexto))) =
                       UPPER(LTRIM(RTRIM(r.ValorTexto))))
              )
    )
    INSERT INTO cat.FactMedicoCategoriaDetalle
           (MedicoCategoriaKey, ComponenteKey, ReglaKey,
            ValorEntradaTexto, ValorEntradaNumero, Criterio, PuntajePct, EstadoComponente)
    SELECT MedicoCategoriaKey, ComponenteKey, ReglaKey,
           ValorTexto, ValorNumero, Criterio, PuntajePct,
           CASE WHEN ReglaKey IS NULL THEN 'SIN_REGLA' ELSE 'OK' END
    FROM match2 WHERE rn = 1;

    -- 8. Marcar batch como CALCULADO ------------------------------------------
    UPDATE cat.LoadBatch
    SET Estado = 'CALCULADO', Mensaje = 'Proceso de categorizacion ejecutado.'
    WHERE LoadBatchKey = @LoadBatchKey;

END
"""


def main():
    print(f"Conectando a {DB_SERVER}:{DB_PORT}/{DB_NAME} ...")
    try:
        conn = pymssql.connect(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME, port=DB_PORT)
    except Exception as e:
        print(f"ERROR de conexion: {e}")
        sys.exit(1)

    cur = conn.cursor()

    # ── Paso 1: backfill de registros existentes ──────────────────────────────
    print("\n[1/2] Backfill Provincia/Municipio/EstadoConciliacion en registros existentes...")
    try:
        cur.execute(BACKFILL_SQL)
        conn.commit()
        print(f"      OK — {cur.rowcount} fila(s) actualizadas.")
    except Exception as e:
        print(f"      ERROR en backfill: {e}")
        conn.rollback()
        conn.close()
        sys.exit(1)

    # ── Paso 2: recrear el SP ─────────────────────────────────────────────────
    print("\n[2/2] Recreando cat.sp_CalcularCategoriaMedica con nuevas columnas...")
    try:
        cur.execute(SP_SQL)
        conn.commit()
        print("      OK — SP recreado. Nuevas columnas: Provincia, Municipio, EstadoConciliacion.")
    except Exception as e:
        print(f"      ERROR al recrear SP: {e}")
        conn.rollback()
        conn.close()
        sys.exit(1)

    conn.close()
    print("\nListo.")
    print("- Los registros existentes ya tienen Provincia/Municipio (si existian en DimGeografia).")
    print("- Futuras cargas Excel llenaran esas columnas automaticamente.")
    print("- Reinicia uvicorn para que los cambios de modelos surtan efecto (si es necesario).")


if __name__ == "__main__":
    main()
