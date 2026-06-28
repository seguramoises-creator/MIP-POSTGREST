"""
SCRIPT: aplicar_migracion_pais_codigo.py
========================================
Aplica el cambio pais_id → pais_codigo en la base de datos SQL Server.

Estrategia (datos de prueba — wipe & reload):
  1. Borra todos los datos de DW / ETL / Audit
  2. Borra todas las tablas de Config.DIM_* (excepto DIM_Pais que se conserva)
  3. Borra DIM_Pais
  4. Recrea TODO el esquema desde los modelos SQLAlchemy actualizados
  5. Aplica los nuevos Stored Procedures vía Alembic
  6. Marca Alembic en HEAD

Uso:
    cd C:\\Users\\Lenovo\\Proyecto\\MSM\\backend
    .\\venv\\Scripts\\activate
    python aplicar_migracion_pais_codigo.py
"""
import os, sys, subprocess, time

# ── Leer .env ────────────────────────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), ".env")
env = {}
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")

server   = env.get("DB_SERVER", "127.0.0.1")
port     = int(env.get("DB_PORT", 1433))
database = env.get("DB_NAME", "SCGCPR")
user     = env.get("DB_USER", "segura")
password = env.get("DB_PASSWORD", "")

print(f"Conectando a {server}:{port} / {database}")

try:
    import pymssql
except ImportError:
    print("ERROR: instala pymssql:  pip install pymssql --break-system-packages")
    sys.exit(1)

conn = pymssql.connect(server=server, port=port, database=database,
                       user=user, password=password, as_dict=True,
                       login_timeout=10)
cur = conn.cursor()
print("Conexión OK\n")

# ── FASE 1: Borrar datos y tablas ────────────────────────────────────────────
print("═" * 60)
print("FASE 1: Eliminando datos y tablas existentes")
print("═" * 60)

# Drops en orden correcto (FACT antes que DIM, DIM que referencian antes que DIM_Pais)
drops = [
    # Stored procedures primero
    "IF OBJECT_ID('DW.sp_CompletarPuntajesCiclo','P') IS NOT NULL DROP PROCEDURE DW.sp_CompletarPuntajesCiclo",
    "IF OBJECT_ID('DW.sp_GenerarRankingCiclo','P')    IS NOT NULL DROP PROCEDURE DW.sp_GenerarRankingCiclo",
    "IF OBJECT_ID('DW.sp_RecalcularCiclo','P')        IS NOT NULL DROP PROCEDURE DW.sp_RecalcularCiclo",
    # FACT DW
    "IF OBJECT_ID('DW.FACT_EvaluacionReceptividadDetalle') IS NOT NULL DROP TABLE DW.FACT_EvaluacionReceptividadDetalle",
    "IF OBJECT_ID('DW.FACT_EvaluacionReceptividad')        IS NOT NULL DROP TABLE DW.FACT_EvaluacionReceptividad",
    "IF OBJECT_ID('DW.FACT_TendenciaCiclo')                IS NOT NULL DROP TABLE DW.FACT_TendenciaCiclo",
    "IF OBJECT_ID('DW.FACT_DashboardEjecutivo')            IS NOT NULL DROP TABLE DW.FACT_DashboardEjecutivo",
    "IF OBJECT_ID('DW.FACT_DistribucionEquipo')            IS NOT NULL DROP TABLE DW.FACT_DistribucionEquipo",
    "IF OBJECT_ID('DW.FACT_ScorecardIndicador')            IS NOT NULL DROP TABLE DW.FACT_ScorecardIndicador",
    "IF OBJECT_ID('DW.FACT_ReconocimientoRM')              IS NOT NULL DROP TABLE DW.FACT_ReconocimientoRM",
    "IF OBJECT_ID('DW.FACT_RankingGerente')                IS NOT NULL DROP TABLE DW.FACT_RankingGerente",
    "IF OBJECT_ID('DW.FACT_RankingRM')                     IS NOT NULL DROP TABLE DW.FACT_RankingRM",
    "IF OBJECT_ID('DW.FACT_ScoreIntegralRM')               IS NOT NULL DROP TABLE DW.FACT_ScoreIntegralRM",
    "IF OBJECT_ID('DW.FACT_CategorizacionMedica')          IS NOT NULL DROP TABLE DW.FACT_CategorizacionMedica",
    "IF OBJECT_ID('DW.FACT_Visita_V2')                     IS NOT NULL DROP TABLE DW.FACT_Visita_V2",
    "IF OBJECT_ID('DW.FACT_Visita')                        IS NOT NULL DROP TABLE DW.FACT_Visita",
    "IF OBJECT_ID('DW.FACT_Coaching')                      IS NOT NULL DROP TABLE DW.FACT_Coaching",
    "IF OBJECT_ID('DW.FACT_Capacitacion')                  IS NOT NULL DROP TABLE DW.FACT_Capacitacion",
    "IF OBJECT_ID('DW.FACT_EVOIR')                         IS NOT NULL DROP TABLE DW.FACT_EVOIR",
    "IF OBJECT_ID('DW.FACT_Ventas')                        IS NOT NULL DROP TABLE DW.FACT_Ventas",
    "IF OBJECT_ID('DW.FACT_ResultadoIndicador')            IS NOT NULL DROP TABLE DW.FACT_ResultadoIndicador",
    # ETL
    "IF OBJECT_ID('ETL.FACT_KPI_RAW')    IS NOT NULL DROP TABLE ETL.FACT_KPI_RAW",
    "IF OBJECT_ID('ETL.FACT_CargaExcel') IS NOT NULL DROP TABLE ETL.FACT_CargaExcel",
    # Audit
    "IF OBJECT_ID('Audit.FACT_Auditoria') IS NOT NULL DROP TABLE Audit.FACT_Auditoria",
    # Security
    "IF OBJECT_ID('Security.DIM_Usuario') IS NOT NULL DROP TABLE Security.DIM_Usuario",
    # Config DIM (primero los que referencian otros DIM)
    "IF OBJECT_ID('Config.DIM_Medico')                IS NOT NULL DROP TABLE Config.DIM_Medico",
    "IF OBJECT_ID('Config.DIM_CriterioCategoriaTabla') IS NOT NULL DROP TABLE Config.DIM_CriterioCategoriaTabla",
    "IF OBJECT_ID('Config.DIM_CriterioCategoria')     IS NOT NULL DROP TABLE Config.DIM_CriterioCategoria",
    "IF OBJECT_ID('Config.DIM_CategoriaMedica')       IS NOT NULL DROP TABLE Config.DIM_CategoriaMedica",
    "IF OBJECT_ID('Config.DIM_CentroMedico')          IS NOT NULL DROP TABLE Config.DIM_CentroMedico",
    "IF OBJECT_ID('Config.DIM_Municipio')             IS NOT NULL DROP TABLE Config.DIM_Municipio",
    "IF OBJECT_ID('Config.DIM_Provincia')             IS NOT NULL DROP TABLE Config.DIM_Provincia",
    "IF OBJECT_ID('Config.DIM_Especialidad')          IS NOT NULL DROP TABLE Config.DIM_Especialidad",
    "IF OBJECT_ID('Config.DIM_MedicoCobertura_V2')    IS NOT NULL DROP TABLE Config.DIM_MedicoCobertura_V2",
    "IF OBJECT_ID('Config.DIM_TargetMedico')          IS NOT NULL DROP TABLE Config.DIM_TargetMedico",
    "IF OBJECT_ID('Config.DIM_Feriado')               IS NOT NULL DROP TABLE Config.DIM_Feriado",
    "IF OBJECT_ID('Config.DIM_ParametroCobertura')    IS NOT NULL DROP TABLE Config.DIM_ParametroCobertura",
    "IF OBJECT_ID('Config.DIM_ReceptividadOpcion')    IS NOT NULL DROP TABLE Config.DIM_ReceptividadOpcion",
    "IF OBJECT_ID('Config.DIM_ConfiguracionLSII')     IS NOT NULL DROP TABLE Config.DIM_ConfiguracionLSII",
    "IF OBJECT_ID('Config.DIM_KpiDashboard')          IS NOT NULL DROP TABLE Config.DIM_KpiDashboard",
    "IF OBJECT_ID('Config.DIM_CategoriaDesempeno')    IS NOT NULL DROP TABLE Config.DIM_CategoriaDesempeno",
    "IF OBJECT_ID('Config.DIM_MetaIndicador')         IS NOT NULL DROP TABLE Config.DIM_MetaIndicador",
    "IF OBJECT_ID('Config.DIM_ReglaElegibilidad')     IS NOT NULL DROP TABLE Config.DIM_ReglaElegibilidad",
    "IF OBJECT_ID('Config.DIM_Premio')                IS NOT NULL DROP TABLE Config.DIM_Premio",
    "IF OBJECT_ID('Config.DIM_IndicadorTabla')        IS NOT NULL DROP TABLE Config.DIM_IndicadorTabla",
    "IF OBJECT_ID('Config.DIM_Indicador_V2')          IS NOT NULL DROP TABLE Config.DIM_Indicador_V2",
    "IF OBJECT_ID('Config.DIM_Indicador')             IS NOT NULL DROP TABLE Config.DIM_Indicador",
    "IF OBJECT_ID('Config.DIM_Ciclo')                 IS NOT NULL DROP TABLE Config.DIM_Ciclo",
    "IF OBJECT_ID('Config.DIM_Mes')                   IS NOT NULL DROP TABLE Config.DIM_Mes",
    "IF OBJECT_ID('Config.DIM_Capacitacion')          IS NOT NULL DROP TABLE Config.DIM_Capacitacion",
    "IF OBJECT_ID('Config.DIM_RM_V2')                 IS NOT NULL DROP TABLE Config.DIM_RM_V2",
    "IF OBJECT_ID('Config.DIM_RM')                    IS NOT NULL DROP TABLE Config.DIM_RM",
    "IF OBJECT_ID('Config.DIM_Gerente')               IS NOT NULL DROP TABLE Config.DIM_Gerente",
    "IF OBJECT_ID('Config.DIM_Linea')                 IS NOT NULL DROP TABLE Config.DIM_Linea",
    "IF OBJECT_ID('Config.DIM_Pais')                  IS NOT NULL DROP TABLE Config.DIM_Pais",
    # alembic version (para reestablecer)
    "IF OBJECT_ID('dbo.alembic_version') IS NOT NULL TRUNCATE TABLE dbo.alembic_version",
]

for sql in drops:
    cur.execute(sql)
    conn.commit()
    nombre = sql.split("DROP")[-1].strip().split()[1] if "DROP" in sql else sql[:40]
    print(f"  ✓ {nombre}")

cur.close()
conn.close()
print("\nFASE 1 completada.\n")

# ── FASE 2: Recrear tablas con nuevo esquema ──────────────────────────────────
print("═" * 60)
print("FASE 2: Recreando tablas (nuevo esquema con pais_codigo)")
print("═" * 60)

result = subprocess.run(
    [sys.executable, "_crear_tablas.py"],
    capture_output=True, text=True,
    cwd=os.path.dirname(__file__) or ".",
)
print(result.stdout)
if result.returncode != 0:
    print("ERROR en _crear_tablas.py:")
    print(result.stderr)
    sys.exit(1)
print("FASE 2 completada.\n")

# ── FASE 3: Aplicar migración Alembic (SPs nuevos) ───────────────────────────
print("═" * 60)
print("FASE 3: Crear Stored Procedures (pais_codigo VERSION)")
print("═" * 60)

SP_COMPLETAR = r"""
CREATE OR ALTER PROCEDURE DW.sp_CompletarPuntajesCiclo
    @ciclo_id INT, @pais_codigo VARCHAR(10) = NULL, @filas_actualizadas INT OUTPUT
AS BEGIN
    SET NOCOUNT ON;
    DECLARE @ahora DATETIME2 = SYSUTCDATETIME();
    SET @filas_actualizadas = 0;
    ;WITH calc AS (
        SELECT ri.id, ri.resultado_real,
            CASE WHEN ind.escala=1 THEN ri.resultado_real*100.0 ELSE ri.resultado_real END AS valor_pct,
            CAST(ind.ponderacion_pct AS DECIMAL(18,6)) AS ponderacion
        FROM DW.FACT_ResultadoIndicador ri
        INNER JOIN Config.DIM_Indicador ind ON ind.id = ri.indicador_id
        WHERE ri.ciclo_id=@ciclo_id AND ri.activo=1 AND ri.resultado_real IS NOT NULL
          AND (@pais_codigo IS NULL OR ri.pais_codigo=@pais_codigo)
    ), cumpl AS (
        SELECT c.id, c.ponderacion,
            CASE WHEN c.valor_pct<0 THEN 0.0 WHEN c.valor_pct>100.0 THEN 100.0 ELSE c.valor_pct END AS cumplimiento_pct
        FROM calc c
    )
    UPDATE ri SET ri.resultado_porcentaje=c.cumplimiento_pct,
        ri.puntos_obtenidos=(c.cumplimiento_pct/100.0)*c.ponderacion, ri.fecha_calculo=@ahora
    FROM DW.FACT_ResultadoIndicador ri INNER JOIN cumpl c ON c.id=ri.id;
    SET @filas_actualizadas=@@ROWCOUNT;
    UPDATE ri SET ri.factor_aplicado=m.peso, ri.puntos_maximos=m.puntaje_maximo,
        ri.porcentaje_logro=CASE
            WHEN m.meta_100 IS NOT NULL AND m.meta_100<>0 THEN
                CASE WHEN (ri.resultado_real/m.meta_100)*100.0>100.0 THEN 100.0 ELSE (ri.resultado_real/m.meta_100)*100.0 END
            WHEN m.meta_100 IS NOT NULL AND m.meta_100=0 THEN 0
            WHEN m.objetivo IS NOT NULL AND m.objetivo<>0 THEN
                CASE WHEN (ri.resultado_real/m.objetivo)*100.0>100.0 THEN 100.0 ELSE (ri.resultado_real/m.objetivo)*100.0 END
            WHEN m.objetivo IS NOT NULL AND m.objetivo=0 THEN 0 ELSE ri.porcentaje_logro END
    FROM DW.FACT_ResultadoIndicador ri
    INNER JOIN Config.DIM_MetaIndicador m ON m.indicador_id=ri.indicador_id AND m.activo=1
    WHERE ri.ciclo_id=@ciclo_id AND ri.activo=1 AND ri.resultado_real IS NOT NULL
      AND (@pais_codigo IS NULL OR ri.pais_codigo=@pais_codigo);
END
"""

SP_RANKING = r"""
CREATE OR ALTER PROCEDURE DW.sp_GenerarRankingCiclo
    @ciclo_id INT, @pais_codigo VARCHAR(10) = NULL, @registros_generados INT OUTPUT
AS BEGIN
    SET NOCOUNT ON;
    DECLARE @ahora DATETIME2 = SYSUTCDATETIME();
    SET @registros_generados=0;
    IF NOT EXISTS (SELECT 1 FROM DW.FACT_ResultadoIndicador ri
        WHERE ri.ciclo_id=@ciclo_id AND ri.activo=1 AND ri.puntos_obtenidos IS NOT NULL
          AND (@pais_codigo IS NULL OR ri.pais_codigo=@pais_codigo)) BEGIN RETURN; END
    IF OBJECT_ID('tempdb..#resultados') IS NOT NULL DROP TABLE #resultados;
    ;WITH iup AS (
        SELECT ri.rm_id, ri.pais_codigo,
            SUM(CAST(ri.puntos_obtenidos AS DECIMAL(18,6)))*100.0
                /NULLIF(SUM(CAST(ind.ponderacion_pct AS DECIMAL(18,6))),0) AS score_total
        FROM DW.FACT_ResultadoIndicador ri
        INNER JOIN Config.DIM_Indicador ind ON ind.id=ri.indicador_id
        WHERE ri.ciclo_id=@ciclo_id AND ri.activo=1 AND ri.puntos_obtenidos IS NOT NULL
          AND (@pais_codigo IS NULL OR ri.pais_codigo=@pais_codigo)
        GROUP BY ri.rm_id, ri.pais_codigo
    ), scores AS (
        SELECT i.rm_id, i.pais_codigo, rm.linea_id, rm.gerente_id,
            CAST(CASE WHEN i.score_total>100.0 THEN 100.0 WHEN i.score_total<0.0 THEN 0.0 ELSE i.score_total END AS DECIMAL(10,4)) AS score_total
        FROM iup i INNER JOIN Config.DIM_RM rm ON rm.id=i.rm_id
    ), con_cat AS (
        SELECT s.*, (SELECT TOP 1 cat.id FROM Config.DIM_CategoriaDesempeno cat
            WHERE cat.activo=1 AND ISNULL(cat.score_min,-1)<=s.score_total
              AND ISNULL(cat.score_max,999999)>=s.score_total ORDER BY cat.id ASC) AS categoria_id
        FROM scores s
    )
    SELECT c.*, ROW_NUMBER() OVER(ORDER BY c.score_total DESC,c.rm_id ASC) AS posicion_global,
        ROW_NUMBER() OVER(PARTITION BY c.linea_id ORDER BY c.score_total DESC,c.rm_id ASC) AS posicion_linea
    INTO #resultados FROM con_cat c;
    DECLARE @ant TABLE(rm_id INT PRIMARY KEY, posicion_anterior INT);
    INSERT INTO @ant SELECT rm_id,posicion_global FROM DW.FACT_RankingRM
        WHERE ciclo_id=@ciclo_id AND tipo_ranking='MENSUAL'
          AND (@pais_codigo IS NULL OR pais_codigo=@pais_codigo);
    DELETE FROM DW.FACT_ScoreIntegralRM WHERE ciclo_id=@ciclo_id
      AND (@pais_codigo IS NULL OR pais_codigo=@pais_codigo);
    DELETE FROM DW.FACT_RankingRM WHERE ciclo_id=@ciclo_id AND tipo_ranking='MENSUAL'
      AND (@pais_codigo IS NULL OR pais_codigo=@pais_codigo);
    INSERT INTO DW.FACT_ScoreIntegralRM(pais_codigo,linea_id,gerente_id,rm_id,ciclo_id,score_total,categoria_id,elegible_reconocimiento,fecha_calculo)
    SELECT r.pais_codigo,r.linea_id,r.gerente_id,r.rm_id,@ciclo_id,r.score_total,r.categoria_id,
        CASE WHEN r.score_total>=90.0 THEN 1 ELSE 0 END,@ahora FROM #resultados r;
    INSERT INTO DW.FACT_RankingRM(pais_codigo,linea_id,gerente_id,rm_id,ciclo_id,tipo_ranking,score_total,categoria_id,posicion_global,posicion_linea,posicion_anterior,elegible,fecha_generacion)
    SELECT r.pais_codigo,r.linea_id,r.gerente_id,r.rm_id,@ciclo_id,'MENSUAL',r.score_total,r.categoria_id,
        r.posicion_global,r.posicion_linea,a.posicion_anterior,
        CASE WHEN r.score_total>=90.0 THEN 1 ELSE 0 END,@ahora
    FROM #resultados r LEFT JOIN @ant a ON a.rm_id=r.rm_id;
    SET @registros_generados=@@ROWCOUNT;
    DROP TABLE #resultados;
END
"""

SP_RECALCULAR = r"""
CREATE OR ALTER PROCEDURE DW.sp_RecalcularCiclo
    @ciclo_id INT, @pais_codigo VARCHAR(10) = NULL
AS BEGIN
    SET NOCOUNT ON;
    DECLARE @cerrado BIT, @nombre VARCHAR(50);
    SELECT @cerrado=cerrado, @nombre=nombre FROM Config.DIM_Ciclo WHERE id=@ciclo_id;
    IF @cerrado IS NULL BEGIN
        DECLARE @msg NVARCHAR(300)=CONCAT(N'Ciclo ID=',@ciclo_id,N' no encontrado');
        THROW 51001,@msg,1; RETURN;
    END
    IF @cerrado=1 BEGIN
        DECLARE @mot NVARCHAR(500)=CONCAT(N'Ciclo ''',@nombre,N''' (id=',@ciclo_id,N') esta CERRADO');
        SELECT @ciclo_id AS ciclo_id,CAST(1 AS BIT) AS abortado,@mot AS motivo,
               0 AS filas_kpi_actualizadas,0 AS rankings_generados; RETURN;
    END
    DECLARE @kpi INT=0, @rank INT=0;
    EXEC DW.sp_CompletarPuntajesCiclo @ciclo_id=@ciclo_id,@pais_codigo=@pais_codigo,@filas_actualizadas=@kpi OUTPUT;
    EXEC DW.sp_GenerarRankingCiclo @ciclo_id=@ciclo_id,@pais_codigo=@pais_codigo,@registros_generados=@rank OUTPUT;
    SELECT @ciclo_id AS ciclo_id,CAST(0 AS BIT) AS abortado,CAST(NULL AS NVARCHAR(500)) AS motivo,
           @kpi AS filas_kpi_actualizadas,@rank AS rankings_generados;
END
"""

conn2 = pymssql.connect(server=server, port=port, database=database,
                        user=user, password=password, as_dict=True, login_timeout=10)
cur2 = conn2.cursor()
for nombre_sp, sql_sp in [("sp_CompletarPuntajesCiclo", SP_COMPLETAR),
                           ("sp_GenerarRankingCiclo",    SP_RANKING),
                           ("sp_RecalcularCiclo",        SP_RECALCULAR)]:
    cur2.execute(sql_sp)
    conn2.commit()
    print(f"  ✓ {nombre_sp}")

# Marcar HEAD de Alembic directamente en la BD
cur2.execute("IF OBJECT_ID('dbo.alembic_version') IS NOT NULL DELETE FROM dbo.alembic_version")
cur2.execute("INSERT INTO dbo.alembic_version (version_num) VALUES ('d9e2f5a8b1c6')")
conn2.commit()
print("  ✓ alembic_version → d9e2f5a8b1c6 (HEAD)")
cur2.close()
conn2.close()
print("FASE 3 completada.\n")

# ── FASE 4: Crear usuario admin por defecto ───────────────────────────────────
print("═" * 60)
print("FASE 4: Creando usuario admin")
print("═" * 60)

crear_bd_path = os.path.join(os.path.dirname(__file__) or ".", "_crear_bd.py")
if os.path.exists(crear_bd_path):
    result = subprocess.run(
        [sys.executable, "_crear_bd.py"],
        capture_output=True, text=True,
        cwd=os.path.dirname(__file__) or ".",
    )
    print(result.stdout)
    if result.returncode != 0:
        print("AVISO (_crear_bd.py):", result.stderr[:200])
else:
    print("  (archivo _crear_bd.py no encontrado — crear usuario manualmente)")

print("\n" + "═" * 60)
print("¡MIGRACIÓN COMPLETADA!")
print("═" * 60)
print("""
Próximos pasos:
  1. Inicia el backend:
       cd C:\\Users\\Lenovo\\Proyecto\\MSM\\backend
       .\\venv\\Scripts\\activate
       uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

  2. Importar catálogos (http://localhost:8000/api/v1/docs):
       POST /dims/importar  →  sube DIM_MIP_FINAL.xlsx

  3. Importar KPIs:
       POST /etl/cargar  →  sube FACT_KPI_RM_VF.xlsx  (tipo=KPI_RM, modo=PRODUCCION)
       (El recálculo IUP/Ranking se dispara automáticamente)

  4. Para Cobertura Predictiva:
       POST /cobertura-predictiva/cargar/target-medicos  →  DIM_TARGET_MEDICOS.xlsx
       POST /cobertura-predictiva/cargar/visitas         →  FACT_VISITAS.xlsx

NOTA: diagnostico_recalculo.py quedó OBSOLETO con este cambio.
      No lo ejecutes — su lógica era para pais_id INT (esquema anterior).
""")
