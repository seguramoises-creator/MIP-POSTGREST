# --- credenciales desde backend/.env (parametrizado, no hardcodear) ---
import os as _os, pathlib as _pl
try:
    from dotenv import load_dotenv as _ld
    _ld(_pl.Path(__file__).resolve().parents[2] / '.env')
except Exception:
    pass
os = _os
# ----------------------------------------------------------------------
"""
Script de reparacion puntual para el modulo LSII.

Crea SOLO las tablas DW.FACT_EvaluacionReceptividad y
DW.FACT_EvaluacionReceptividadDetalle si no existen todavia.

NO toca Config.DIM_ReceptividadOpcion (ya existe con sus 25 filas semilla
correctas) ni vuelve a insertar datos en ella.

Uso:
    cd C:\\Users\\Lenovo\\Proyecto\\MSM\\backend
    python _fix_lsii_tables.py
"""
import pymssql

conn = pymssql.connect(
    server="127.0.0.1",
    port=1433,
    user="segura",
    password=os.environ.get('DB_PASSWORD', ''),
    database="SCGCPR",
)
conn.autocommit(False)
cur = conn.cursor()


def existe_tabla(schema, tabla):
    cur.execute(
        "SELECT 1 FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id "
        "WHERE s.name = %s AND t.name = %s",
        (schema, tabla),
    )
    return cur.fetchone() is not None


try:
    if existe_tabla("Config", "DIM_ReceptividadOpcion"):
        print("OK   Config.DIM_ReceptividadOpcion ya existe (no se toca).")
    else:
        print("ADVERTENCIA: Config.DIM_ReceptividadOpcion no existe. Este script no la crea.")

    if existe_tabla("DW", "FACT_EvaluacionReceptividad"):
        print("OK   DW.FACT_EvaluacionReceptividad ya existe, no se crea de nuevo.")
    else:
        print("Creando DW.FACT_EvaluacionReceptividad ...")
        cur.execute("""
            CREATE TABLE [DW].[FACT_EvaluacionReceptividad] (
                id BIGINT NOT NULL IDENTITY(1,1) PRIMARY KEY,
                pais_id INT NOT NULL,
                rm_id INT NOT NULL,
                gerente_id INT NULL,
                ciclo_id INT NOT NULL,
                evaluador_usuario_id INT NULL,
                score_receptividad NUMERIC(6,2) NOT NULL DEFAULT 0,
                score_desempeno NUMERIC(6,2) NULL,
                nivel_lsii VARCHAR(5) NOT NULL,
                estilo_liderazgo VARCHAR(50) NOT NULL,
                observaciones TEXT NULL,
                activo BIT NOT NULL DEFAULT 1,
                fecha_evaluacion DATETIME NOT NULL,
                CONSTRAINT FK_EvalRecept_Ciclo FOREIGN KEY (ciclo_id) REFERENCES [Config].[DIM_Ciclo](id),
                CONSTRAINT FK_EvalRecept_Gerente FOREIGN KEY (gerente_id) REFERENCES [Config].[DIM_Gerente](id),
                CONSTRAINT FK_EvalRecept_Pais FOREIGN KEY (pais_id) REFERENCES [Config].[DIM_Pais](id),
                CONSTRAINT FK_EvalRecept_RM FOREIGN KEY (rm_id) REFERENCES [Config].[DIM_RM](id)
            )
        """)
        cur.execute("CREATE INDEX [ix_DW_FACT_EvaluacionReceptividad_pais_id] ON [DW].[FACT_EvaluacionReceptividad] (pais_id)")
        cur.execute("CREATE INDEX [ix_DW_FACT_EvaluacionReceptividad_rm_id] ON [DW].[FACT_EvaluacionReceptividad] (rm_id)")
        cur.execute("CREATE INDEX [ix_DW_FACT_EvaluacionReceptividad_ciclo_id] ON [DW].[FACT_EvaluacionReceptividad] (ciclo_id)")
        cur.execute("CREATE INDEX [ix_DW_FACT_EvaluacionReceptividad_fecha_evaluacion] ON [DW].[FACT_EvaluacionReceptividad] (fecha_evaluacion)")
        print("OK   DW.FACT_EvaluacionReceptividad creada con sus 4 indices.")

    if existe_tabla("DW", "FACT_EvaluacionReceptividadDetalle"):
        print("OK   DW.FACT_EvaluacionReceptividadDetalle ya existe, no se crea de nuevo.")
    else:
        print("Creando DW.FACT_EvaluacionReceptividadDetalle ...")
        cur.execute("""
            CREATE TABLE [DW].[FACT_EvaluacionReceptividadDetalle] (
                id BIGINT NOT NULL IDENTITY(1,1) PRIMARY KEY,
                evaluacion_id BIGINT NOT NULL,
                dimension_codigo VARCHAR(50) NOT NULL,
                opcion_id INT NOT NULL,
                score_oculto INT NOT NULL,
                peso_dimension NUMERIC(5,4) NOT NULL,
                CONSTRAINT FK_EvalReceptDet_Evaluacion FOREIGN KEY (evaluacion_id) REFERENCES [DW].[FACT_EvaluacionReceptividad](id),
                CONSTRAINT FK_EvalReceptDet_Opcion FOREIGN KEY (opcion_id) REFERENCES [Config].[DIM_ReceptividadOpcion](id)
            )
        """)
        cur.execute("CREATE INDEX [ix_DW_FACT_EvaluacionReceptividadDetalle_evaluacion_id] ON [DW].[FACT_EvaluacionReceptividadDetalle] (evaluacion_id)")
        print("OK   DW.FACT_EvaluacionReceptividadDetalle creada con su indice.")

    conn.commit()
    print("\nListo. Cambios confirmados (commit).")
except Exception as e:
    conn.rollback()
    print("ERROR, se revirtio todo:", e)
    raise
finally:
    cur.close()
    conn.close()
