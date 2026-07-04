"""cat + stg schemas — Nuevo módulo Categorización Médica

Revision ID: a3c7e9f2b4d1
Revises: d9e2f5a8b1c6
Create Date: 2026-06-24
"""
from alembic import op

revision = 'a3c7e9f2b4d1'
down_revision = 'd9e2f5a8b1c6'
branch_labels = None
depends_on = None


def upgrade():
    # ── Schemas ────────────────────────────────────────────────────────────────
    op.execute("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name='cat') EXEC('CREATE SCHEMA cat')")
    op.execute("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name='stg') EXEC('CREATE SCHEMA stg')")

    # ── cat.LoadBatch ──────────────────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='LoadBatch' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.LoadBatch (
            LoadBatchKey      BIGINT IDENTITY(1,1) NOT NULL,
            ArchivoOrigen     NVARCHAR(260) NOT NULL,
            Periodo           CHAR(7)       NOT NULL,
            CodigoPaisDefault CHAR(2)       NULL,
            FechaCargaUtc     DATETIME2(0)  NOT NULL CONSTRAINT DF_LoadBatch_Fecha DEFAULT SYSUTCDATETIME(),
            UsuarioCarga      NVARCHAR(150) NULL,
            Estado            VARCHAR(20)   NOT NULL CONSTRAINT DF_LoadBatch_Estado DEFAULT 'RECIBIDO',
            Mensaje           NVARCHAR(1000) NULL,
            CONSTRAINT PK_LoadBatch PRIMARY KEY CLUSTERED (LoadBatchKey),
            CONSTRAINT CK_LoadBatch_Estado CHECK (Estado IN ('RECIBIDO','VALIDADO','CALCULADO','ERROR'))
        )
    END
    """)

    # ── cat.DimPais ────────────────────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='DimPais' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.DimPais (
            PaisKey       INT IDENTITY(1,1) NOT NULL,
            PaisIdOrigen  INT           NULL,
            CodigoPais    CHAR(2)       NOT NULL,
            NombrePais    NVARCHAR(100) NOT NULL,
            Moneda        CHAR(3)       NULL,
            ZonaHoraria   NVARCHAR(80)  NULL,
            Activo        BIT           NOT NULL CONSTRAINT DF_DimPais_Activo DEFAULT 1,
            FechaCargaUtc DATETIME2(0)  NOT NULL CONSTRAINT DF_DimPais_Fecha DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_DimPais PRIMARY KEY CLUSTERED (PaisKey),
            CONSTRAINT UQ_DimPais_CodigoPais UNIQUE (CodigoPais)
        )
    END
    """)

    # ── cat.DimComponenteCategoria ─────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='DimComponenteCategoria' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.DimComponenteCategoria (
            ComponenteKey     INT IDENTITY(1,1) NOT NULL,
            CodigoComponente  VARCHAR(50)   NOT NULL,
            NombreComponente  NVARCHAR(150) NOT NULL,
            TipoEvaluacion    VARCHAR(30)   NOT NULL,
            PesoComponentePct DECIMAL(9,6)  NOT NULL,
            Requerido         BIT           NOT NULL CONSTRAINT DF_DimComponente_Requerido DEFAULT 1,
            Activo            BIT           NOT NULL CONSTRAINT DF_DimComponente_Activo DEFAULT 1,
            FechaCargaUtc     DATETIME2(0)  NOT NULL CONSTRAINT DF_DimComponente_Fecha DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_DimComponenteCategoria PRIMARY KEY CLUSTERED (ComponenteKey),
            CONSTRAINT UQ_DimComponenteCategoria UNIQUE (CodigoComponente),
            CONSTRAINT CK_DimComponente_Tipo CHECK (TipoEvaluacion IN ('RANGO','LISTA','LISTA_RANGO_TEXTO')),
            CONSTRAINT CK_DimComponente_Peso CHECK (PesoComponentePct >= 0 AND PesoComponentePct <= 1)
        )
    END
    """)

    # ── cat.DimClasificacionMedica ─────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='DimClasificacionMedica' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.DimClasificacionMedica (
            ClasificacionKey INT IDENTITY(1,1) NOT NULL,
            PaisKey          INT          NOT NULL,
            Clase            CHAR(1)      NOT NULL,
            PuntajeMinPct    DECIMAL(9,6) NOT NULL,
            PuntajeMaxPct    DECIMAL(9,6) NOT NULL,
            OrdenClase       TINYINT      NOT NULL,
            VigenteDesde     DATE         NOT NULL,
            VigenteHasta     DATE         NULL,
            Activo           BIT          NOT NULL CONSTRAINT DF_DimClasificacion_Activo DEFAULT 1,
            FechaCargaUtc    DATETIME2(0) NOT NULL CONSTRAINT DF_DimClasificacion_Fecha DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_DimClasificacionMedica PRIMARY KEY CLUSTERED (ClasificacionKey),
            CONSTRAINT FK_DimClasificacion_Pais FOREIGN KEY (PaisKey) REFERENCES cat.DimPais(PaisKey),
            CONSTRAINT UQ_DimClasificacion UNIQUE (PaisKey, Clase, VigenteDesde),
            CONSTRAINT CK_DimClasificacion_Clase CHECK (Clase IN ('A','B','C','D'))
        )
    END
    """)

    # ── cat.DimReglaCategoriaMedica ────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='DimReglaCategoriaMedica' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.DimReglaCategoriaMedica (
            ReglaKey          INT IDENTITY(1,1) NOT NULL,
            PaisKey           INT           NOT NULL,
            ComponenteKey     INT           NOT NULL,
            CodigoRegla       VARCHAR(80)   NOT NULL,
            Detalle           NVARCHAR(200) NOT NULL,
            ValorMinimo       DECIMAL(18,4) NULL,
            ValorMaximo       DECIMAL(18,4) NULL,
            ValorTexto        NVARCHAR(200) NULL,
            Criterio          TINYINT       NOT NULL,
            PesoComponentePct DECIMAL(9,6)  NOT NULL,
            PuntajePct        DECIMAL(9,6)  NOT NULL,
            VigenteDesde      DATE          NOT NULL,
            VigenteHasta      DATE          NULL,
            Activo            BIT           NOT NULL CONSTRAINT DF_DimRegla_Activo DEFAULT 1,
            FechaCargaUtc     DATETIME2(0)  NOT NULL CONSTRAINT DF_DimRegla_Fecha DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_DimReglaCategoriaMedica PRIMARY KEY CLUSTERED (ReglaKey),
            CONSTRAINT FK_DimRegla_Pais FOREIGN KEY (PaisKey) REFERENCES cat.DimPais(PaisKey),
            CONSTRAINT FK_DimRegla_Componente FOREIGN KEY (ComponenteKey) REFERENCES cat.DimComponenteCategoria(ComponenteKey),
            CONSTRAINT UQ_DimRegla UNIQUE (PaisKey, ComponenteKey, CodigoRegla, VigenteDesde),
            CONSTRAINT CK_DimRegla_Criterio CHECK (Criterio BETWEEN 1 AND 5)
        )
        CREATE INDEX IX_DimRegla_Busqueda ON cat.DimReglaCategoriaMedica
            (PaisKey, ComponenteKey, Activo, VigenteDesde, VigenteHasta, ValorMinimo, ValorMaximo)
            INCLUDE (ValorTexto, Criterio, PuntajePct, Detalle)
    END
    """)

    # ── cat.DimEquipo ──────────────────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='DimEquipo' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.DimEquipo (
            EquipoKey    INT IDENTITY(1,1) NOT NULL,
            PaisKey      INT           NOT NULL,
            CodigoEquipo VARCHAR(30)   NOT NULL,
            NombreEquipo NVARCHAR(120) NOT NULL,
            Descripcion  NVARCHAR(250) NULL,
            Activo       BIT           NOT NULL CONSTRAINT DF_DimEquipo_Activo DEFAULT 1,
            CONSTRAINT PK_DimEquipo PRIMARY KEY CLUSTERED (EquipoKey),
            CONSTRAINT FK_DimEquipo_Pais FOREIGN KEY (PaisKey) REFERENCES cat.DimPais(PaisKey),
            CONSTRAINT UQ_DimEquipo UNIQUE (PaisKey, CodigoEquipo)
        )
    END
    """)

    # ── cat.DimRepresentanteMedico ─────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='DimRepresentanteMedico' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.DimRepresentanteMedico (
            RepresentanteKey    INT IDENTITY(1,1) NOT NULL,
            PaisKey             INT           NOT NULL,
            RepresentanteIdOrigen INT         NULL,
            CodigoRepresentante VARCHAR(30)   NOT NULL,
            NombreRepresentante NVARCHAR(150) NOT NULL,
            LineaIdOrigen       INT           NULL,
            GerenteIdOrigen     INT           NULL,
            Email               NVARCHAR(150) NULL,
            Zona                NVARCHAR(80)  NULL,
            FechaIngreso        DATE          NULL,
            Cedula              VARCHAR(30)   NULL,
            CodigoOrigenExcel   VARCHAR(50)   NULL,
            EquipoTexto         NVARCHAR(120) NULL,
            Activo              BIT           NOT NULL CONSTRAINT DF_DimRepresentante_Activo DEFAULT 1,
            CONSTRAINT PK_DimRepresentanteMedico PRIMARY KEY CLUSTERED (RepresentanteKey),
            CONSTRAINT FK_DimRepresentante_Pais FOREIGN KEY (PaisKey) REFERENCES cat.DimPais(PaisKey),
            CONSTRAINT UQ_DimRepresentanteMedico UNIQUE (PaisKey, CodigoRepresentante)
        )
    END
    """)

    # ── cat.DimEspecialidad ────────────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='DimEspecialidad' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.DimEspecialidad (
            EspecialidadKey INT IDENTITY(1,1) NOT NULL,
            PaisKey         INT           NOT NULL,
            Especialidad    NVARCHAR(150) NOT NULL,
            Activo          BIT           NOT NULL CONSTRAINT DF_DimEspecialidad_Activo DEFAULT 1,
            CONSTRAINT PK_DimEspecialidad PRIMARY KEY CLUSTERED (EspecialidadKey),
            CONSTRAINT FK_DimEspecialidad_Pais FOREIGN KEY (PaisKey) REFERENCES cat.DimPais(PaisKey),
            CONSTRAINT UQ_DimEspecialidad UNIQUE (PaisKey, Especialidad)
        )
    END
    """)

    # ── cat.DimCentroMedico ────────────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='DimCentroMedico' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.DimCentroMedico (
            CentroMedicoKey INT IDENTITY(1,1) NOT NULL,
            PaisKey         INT           NOT NULL,
            CentroMedico    NVARCHAR(200) NOT NULL,
            Activo          BIT           NOT NULL CONSTRAINT DF_DimCentroMedico_Activo DEFAULT 1,
            CONSTRAINT PK_DimCentroMedico PRIMARY KEY CLUSTERED (CentroMedicoKey),
            CONSTRAINT FK_DimCentroMedico_Pais FOREIGN KEY (PaisKey) REFERENCES cat.DimPais(PaisKey),
            CONSTRAINT UQ_DimCentroMedico UNIQUE (PaisKey, CentroMedico)
        )
    END
    """)

    # ── cat.DimGeografia ──────────────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='DimGeografia' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.DimGeografia (
            GeografiaKey INT IDENTITY(1,1) NOT NULL,
            PaisKey      INT           NOT NULL,
            Provincia    NVARCHAR(120) NOT NULL,
            Municipio    NVARCHAR(120) NOT NULL,
            Activo       BIT           NOT NULL CONSTRAINT DF_DimGeografia_Activo DEFAULT 1,
            CONSTRAINT PK_DimGeografia PRIMARY KEY CLUSTERED (GeografiaKey),
            CONSTRAINT FK_DimGeografia_Pais FOREIGN KEY (PaisKey) REFERENCES cat.DimPais(PaisKey),
            CONSTRAINT UQ_DimGeografia UNIQUE (PaisKey, Provincia, Municipio)
        )
    END
    """)

    # ── cat.DimMedico ──────────────────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='DimMedico' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.DimMedico (
            MedicoKey       BIGINT IDENTITY(1,1) NOT NULL,
            PaisKey         INT           NOT NULL,
            CodigoMedico    VARCHAR(50)   NULL,
            NombreMedico    NVARCHAR(200) NOT NULL,
            EspecialidadKey INT           NULL,
            Activo          BIT           NOT NULL CONSTRAINT DF_DimMedico_Activo DEFAULT 1,
            CONSTRAINT PK_DimMedico PRIMARY KEY CLUSTERED (MedicoKey),
            CONSTRAINT FK_DimMedico_Pais FOREIGN KEY (PaisKey) REFERENCES cat.DimPais(PaisKey),
            CONSTRAINT FK_DimMedico_Especialidad FOREIGN KEY (EspecialidadKey) REFERENCES cat.DimEspecialidad(EspecialidadKey),
            CONSTRAINT UQ_DimMedico UNIQUE (PaisKey, NombreMedico, EspecialidadKey)
        )
    END
    """)

    # ── stg.MedicoCategoriaInput ───────────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='MedicoCategoriaInput' AND schema_id=SCHEMA_ID('stg'))
    BEGIN
        CREATE TABLE stg.MedicoCategoriaInput (
            LoadBatchKey           BIGINT        NOT NULL,
            RowNumber              INT           NOT NULL,
            CodigoPais             CHAR(2)       NOT NULL,
            Periodo                CHAR(7)       NOT NULL,
            Equipo                 NVARCHAR(120) NULL,
            LineaIdOrigen          INT           NULL,
            CodigoRepresentante    VARCHAR(30)   NULL,
            NombreRepresentante    NVARCHAR(150) NULL,
            Medico                 NVARCHAR(200) NOT NULL,
            CentroMedico           NVARCHAR(200) NULL,
            Especialidad           NVARCHAR(150) NULL,
            Provincia              NVARCHAR(120) NULL,
            Municipio              NVARCHAR(120) NULL,
            PacientesSemana        DECIMAL(18,4) NULL,
            CostoConsulta          DECIMAL(18,4) NULL,
            RecetasSemana          NVARCHAR(80)  NULL,
            UbicacionTerritorialCM NVARCHAR(80)  NULL,
            KOL                    NVARCHAR(150) NULL,
            CategoriaExcel         VARCHAR(20)   NULL,
            Activo                 BIT           NOT NULL CONSTRAINT DF_stgInput_Activo DEFAULT 1,
            CONSTRAINT PK_stgMedicoCategoriaInput PRIMARY KEY CLUSTERED (LoadBatchKey, RowNumber),
            CONSTRAINT FK_stgInput_LoadBatch FOREIGN KEY (LoadBatchKey) REFERENCES cat.LoadBatch(LoadBatchKey)
        )
    END
    """)

    # ── cat.FactMedicoCategoriaSnapshot ───────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='FactMedicoCategoriaSnapshot' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.FactMedicoCategoriaSnapshot (
            MedicoCategoriaKey     BIGINT IDENTITY(1,1) NOT NULL,
            LoadBatchKey           BIGINT        NOT NULL,
            RowNumber              INT           NOT NULL,
            Periodo                CHAR(7)       NOT NULL,
            PaisKey                INT           NOT NULL,
            MedicoKey              BIGINT        NOT NULL,
            CentroMedicoKey        INT           NULL,
            GeografiaKey           INT           NULL,
            RepresentanteKey       INT           NULL,
            Equipo                 NVARCHAR(120) NULL,
            LineaIdOrigen          INT           NULL,
            PacientesSemana        DECIMAL(18,4) NULL,
            CostoConsulta          DECIMAL(18,4) NULL,
            RecetasSemana          NVARCHAR(80)  NULL,
            UbicacionTerritorialCM NVARCHAR(80)  NULL,
            KOL                    NVARCHAR(150) NULL,
            PuntajeTotalPct        DECIMAL(9,6)  NULL,
            ClasificacionKey       INT           NULL,
            CategoriaCalculada     CHAR(1)       NULL,
            CategoriaExcel         VARCHAR(20)   NULL,
            EstadoCalculo          VARCHAR(20)   NOT NULL,
            MensajeCalculo         NVARCHAR(500) NULL,
            FechaCalculoUtc        DATETIME2(0)  NOT NULL CONSTRAINT DF_FactSnapshot_Fecha DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_FactMedicoCategoriaSnapshot PRIMARY KEY CLUSTERED (MedicoCategoriaKey),
            CONSTRAINT UQ_FactSnapshot_LoadRow UNIQUE (LoadBatchKey, RowNumber),
            CONSTRAINT FK_FactSnapshot_LoadBatch FOREIGN KEY (LoadBatchKey) REFERENCES cat.LoadBatch(LoadBatchKey),
            CONSTRAINT FK_FactSnapshot_Pais FOREIGN KEY (PaisKey) REFERENCES cat.DimPais(PaisKey),
            CONSTRAINT FK_FactSnapshot_Medico FOREIGN KEY (MedicoKey) REFERENCES cat.DimMedico(MedicoKey),
            CONSTRAINT FK_FactSnapshot_Clasificacion FOREIGN KEY (ClasificacionKey) REFERENCES cat.DimClasificacionMedica(ClasificacionKey)
        )
    END
    """)

    # ── cat.FactMedicoCategoriaDetalle ─────────────────────────────────────────
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='FactMedicoCategoriaDetalle' AND schema_id=SCHEMA_ID('cat'))
    BEGIN
        CREATE TABLE cat.FactMedicoCategoriaDetalle (
            MedicoCategoriaDetalleKey BIGINT IDENTITY(1,1) NOT NULL,
            MedicoCategoriaKey        BIGINT        NOT NULL,
            ComponenteKey             INT           NOT NULL,
            ReglaKey                  INT           NULL,
            ValorEntradaTexto         NVARCHAR(200) NULL,
            ValorEntradaNumero        DECIMAL(18,4) NULL,
            Criterio                  TINYINT       NULL,
            PuntajePct                DECIMAL(9,6)  NULL,
            EstadoComponente          VARCHAR(20)   NOT NULL,
            CONSTRAINT PK_FactMedicoCategoriaDetalle PRIMARY KEY CLUSTERED (MedicoCategoriaDetalleKey),
            CONSTRAINT FK_FactDetalle_Snapshot FOREIGN KEY (MedicoCategoriaKey) REFERENCES cat.FactMedicoCategoriaSnapshot(MedicoCategoriaKey),
            CONSTRAINT FK_FactDetalle_Componente FOREIGN KEY (ComponenteKey) REFERENCES cat.DimComponenteCategoria(ComponenteKey),
            CONSTRAINT FK_FactDetalle_Regla FOREIGN KEY (ReglaKey) REFERENCES cat.DimReglaCategoriaMedica(ReglaKey)
        )
    END
    """)

    # ── Vista de conciliación ──────────────────────────────────────────────────
    op.execute("""
    EXEC('
    CREATE OR ALTER VIEW cat.vwMedicoCategoriaConciliacion AS
    SELECT
        f.Periodo,
        p.CodigoPais,
        r.CodigoRepresentante,
        r.NombreRepresentante,
        m.NombreMedico,
        e.Especialidad,
        f.Equipo,
        f.LineaIdOrigen,
        ROUND(f.PuntajeTotalPct * 100, 2) AS PuntajeTotalPct,
        f.CategoriaCalculada,
        f.CategoriaExcel,
        CASE
            WHEN f.CategoriaExcel IS NULL THEN ''SIN_CATEGORIA_EXCEL''
            WHEN f.CategoriaCalculada = f.CategoriaExcel THEN ''OK''
            ELSE ''DIFERENCIA''
        END AS EstadoConciliacion,
        f.EstadoCalculo,
        f.MensajeCalculo,
        f.LoadBatchKey,
        f.MedicoCategoriaKey
    FROM cat.FactMedicoCategoriaSnapshot f
    JOIN cat.DimPais p ON p.PaisKey = f.PaisKey
    JOIN cat.DimMedico m ON m.MedicoKey = f.MedicoKey
    LEFT JOIN cat.DimEspecialidad e ON e.EspecialidadKey = m.EspecialidadKey
    LEFT JOIN cat.DimRepresentanteMedico r ON r.RepresentanteKey = f.RepresentanteKey
    ')
    """)

    # ── Stored Procedure ───────────────────────────────────────────────────────
    op.execute("""
    EXEC('
    CREATE OR ALTER PROCEDURE cat.sp_CalcularCategoriaMedica
        @LoadBatchKey BIGINT
    AS
    BEGIN
        SET NOCOUNT ON;
        DECLARE @FechaCorte DATE = CAST(SYSUTCDATETIME() AS DATE);

        INSERT INTO cat.DimEspecialidad (PaisKey, Especialidad)
        SELECT DISTINCT p.PaisKey, LTRIM(RTRIM(s.Especialidad))
        FROM stg.MedicoCategoriaInput s
        JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
        WHERE s.LoadBatchKey = @LoadBatchKey AND s.Especialidad IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM cat.DimEspecialidad d WHERE d.PaisKey = p.PaisKey AND d.Especialidad = LTRIM(RTRIM(s.Especialidad)));

        INSERT INTO cat.DimCentroMedico (PaisKey, CentroMedico)
        SELECT DISTINCT p.PaisKey, LTRIM(RTRIM(s.CentroMedico))
        FROM stg.MedicoCategoriaInput s
        JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
        WHERE s.LoadBatchKey = @LoadBatchKey AND s.CentroMedico IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM cat.DimCentroMedico d WHERE d.PaisKey = p.PaisKey AND d.CentroMedico = LTRIM(RTRIM(s.CentroMedico)));

        INSERT INTO cat.DimGeografia (PaisKey, Provincia, Municipio)
        SELECT DISTINCT p.PaisKey, LTRIM(RTRIM(s.Provincia)), LTRIM(RTRIM(s.Municipio))
        FROM stg.MedicoCategoriaInput s
        JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
        WHERE s.LoadBatchKey = @LoadBatchKey AND s.Provincia IS NOT NULL AND s.Municipio IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM cat.DimGeografia d WHERE d.PaisKey = p.PaisKey AND d.Provincia = LTRIM(RTRIM(s.Provincia)) AND d.Municipio = LTRIM(RTRIM(s.Municipio)));

        INSERT INTO cat.DimRepresentanteMedico (PaisKey, CodigoRepresentante, NombreRepresentante, LineaIdOrigen, EquipoTexto, Activo)
        SELECT DISTINCT p.PaisKey, s.CodigoRepresentante, LTRIM(RTRIM(s.NombreRepresentante)), s.LineaIdOrigen, LTRIM(RTRIM(s.Equipo)), 1
        FROM stg.MedicoCategoriaInput s
        JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
        WHERE s.LoadBatchKey = @LoadBatchKey AND s.CodigoRepresentante IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM cat.DimRepresentanteMedico d WHERE d.PaisKey = p.PaisKey AND d.CodigoRepresentante = s.CodigoRepresentante);

        INSERT INTO cat.DimMedico (PaisKey, CodigoMedico, NombreMedico, EspecialidadKey)
        SELECT DISTINCT p.PaisKey, NULL, LTRIM(RTRIM(s.Medico)), esp.EspecialidadKey
        FROM stg.MedicoCategoriaInput s
        JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
        LEFT JOIN cat.DimEspecialidad esp ON esp.PaisKey = p.PaisKey AND esp.Especialidad = LTRIM(RTRIM(s.Especialidad))
        WHERE s.LoadBatchKey = @LoadBatchKey
          AND NOT EXISTS (SELECT 1 FROM cat.DimMedico d WHERE d.PaisKey = p.PaisKey AND d.NombreMedico = LTRIM(RTRIM(s.Medico)) AND ISNULL(d.EspecialidadKey,-1) = ISNULL(esp.EspecialidadKey,-1));

        ;WITH src AS (
            SELECT s.*, p.PaisKey, med.MedicoKey, cm.CentroMedicoKey, geo.GeografiaKey, rep.RepresentanteKey
            FROM stg.MedicoCategoriaInput s
            JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
            LEFT JOIN cat.DimEspecialidad esp ON esp.PaisKey = p.PaisKey AND esp.Especialidad = LTRIM(RTRIM(s.Especialidad))
            JOIN cat.DimMedico med ON med.PaisKey = p.PaisKey AND med.NombreMedico = LTRIM(RTRIM(s.Medico)) AND ISNULL(med.EspecialidadKey,-1) = ISNULL(esp.EspecialidadKey,-1)
            LEFT JOIN cat.DimCentroMedico cm ON cm.PaisKey = p.PaisKey AND cm.CentroMedico = LTRIM(RTRIM(s.CentroMedico))
            LEFT JOIN cat.DimGeografia geo ON geo.PaisKey = p.PaisKey AND geo.Provincia = LTRIM(RTRIM(s.Provincia)) AND geo.Municipio = LTRIM(RTRIM(s.Municipio))
            LEFT JOIN cat.DimRepresentanteMedico rep ON rep.PaisKey = p.PaisKey AND rep.CodigoRepresentante = s.CodigoRepresentante
            WHERE s.LoadBatchKey = @LoadBatchKey
        ),
        comp AS (
            SELECT src.RowNumber, src.PaisKey, c.ComponenteKey, c.CodigoComponente,
                   CASE c.CodigoComponente WHEN ''PACIENTES_SEMANA'' THEN src.PacientesSemana WHEN ''PODER_ADQUISITIVO'' THEN src.CostoConsulta ELSE NULL END AS ValorNumero,
                   CASE c.CodigoComponente WHEN ''POTENCIAL_PRESCRIPCION'' THEN src.RecetasSemana WHEN ''UBICACION_TERRITORIAL_CM'' THEN src.UbicacionTerritorialCM WHEN ''KOL'' THEN src.KOL ELSE NULL END AS ValorTexto
            FROM src CROSS JOIN cat.DimComponenteCategoria c WHERE c.Activo = 1
        ),
        match_regla AS (
            SELECT comp.RowNumber, comp.ComponenteKey, r.ReglaKey, r.Criterio, r.PuntajePct,
                   ROW_NUMBER() OVER (PARTITION BY comp.RowNumber, comp.ComponenteKey ORDER BY r.Criterio DESC, r.ReglaKey) AS rn
            FROM comp
            JOIN cat.DimReglaCategoriaMedica r ON r.PaisKey = comp.PaisKey AND r.ComponenteKey = comp.ComponenteKey AND r.Activo = 1
              AND r.VigenteDesde <= @FechaCorte AND (r.VigenteHasta IS NULL OR r.VigenteHasta >= @FechaCorte)
              AND ((comp.ValorNumero IS NOT NULL AND (r.ValorMinimo IS NULL OR comp.ValorNumero >= r.ValorMinimo) AND (r.ValorMaximo IS NULL OR comp.ValorNumero <= r.ValorMaximo))
                OR (comp.ValorTexto IS NOT NULL AND UPPER(LTRIM(RTRIM(comp.ValorTexto))) = UPPER(LTRIM(RTRIM(r.ValorTexto)))))
        ),
        score AS (
            SELECT src.RowNumber,
                   SUM(CASE WHEN mr.rn = 1 THEN mr.PuntajePct ELSE 0 END) AS PuntajeTotalPct,
                   COUNT(DISTINCT CASE WHEN mr.rn = 1 THEN mr.ComponenteKey END) AS ComponentesCalculados,
                   COUNT(DISTINCT c.ComponenteKey) AS ComponentesRequeridos
            FROM src CROSS JOIN cat.DimComponenteCategoria c
            LEFT JOIN match_regla mr ON mr.RowNumber = src.RowNumber AND mr.ComponenteKey = c.ComponenteKey AND mr.rn = 1
            WHERE c.Activo = 1 AND c.Requerido = 1
            GROUP BY src.RowNumber
        )
        INSERT INTO cat.FactMedicoCategoriaSnapshot (
            LoadBatchKey, RowNumber, Periodo, PaisKey, MedicoKey, CentroMedicoKey, GeografiaKey,
            RepresentanteKey, Equipo, LineaIdOrigen, PacientesSemana, CostoConsulta, RecetasSemana,
            UbicacionTerritorialCM, KOL, PuntajeTotalPct, ClasificacionKey,
            CategoriaCalculada, CategoriaExcel, EstadoCalculo, MensajeCalculo
        )
        SELECT src.LoadBatchKey, src.RowNumber, src.Periodo, src.PaisKey, src.MedicoKey, src.CentroMedicoKey,
               src.GeografiaKey, src.RepresentanteKey, src.Equipo, src.LineaIdOrigen, src.PacientesSemana,
               src.CostoConsulta, src.RecetasSemana, src.UbicacionTerritorialCM, src.KOL,
               sc.PuntajeTotalPct, cl.ClasificacionKey, cl.Clase, src.CategoriaExcel,
               CASE WHEN sc.ComponentesCalculados = sc.ComponentesRequeridos THEN ''CALCULADO'' ELSE ''PENDIENTE'' END,
               CASE WHEN sc.ComponentesCalculados = sc.ComponentesRequeridos THEN NULL ELSE CONCAT(''Componentes calculados '', sc.ComponentesCalculados, '' de '', sc.ComponentesRequeridos) END
        FROM src JOIN score sc ON sc.RowNumber = src.RowNumber
        LEFT JOIN cat.DimClasificacionMedica cl ON cl.PaisKey = src.PaisKey AND cl.Activo = 1
          AND cl.VigenteDesde <= @FechaCorte AND (cl.VigenteHasta IS NULL OR cl.VigenteHasta >= @FechaCorte)
          AND sc.PuntajeTotalPct BETWEEN cl.PuntajeMinPct AND cl.PuntajeMaxPct;

        ;WITH src2 AS (
            SELECT s.*, p.PaisKey, f.MedicoCategoriaKey
            FROM stg.MedicoCategoriaInput s
            JOIN cat.DimPais p ON p.CodigoPais = s.CodigoPais
            JOIN cat.FactMedicoCategoriaSnapshot f ON f.LoadBatchKey = s.LoadBatchKey AND f.RowNumber = s.RowNumber
            WHERE s.LoadBatchKey = @LoadBatchKey
        ),
        comp2 AS (
            SELECT src2.MedicoCategoriaKey, src2.PaisKey, c.ComponenteKey, c.CodigoComponente,
                   CASE c.CodigoComponente WHEN ''PACIENTES_SEMANA'' THEN src2.PacientesSemana WHEN ''PODER_ADQUISITIVO'' THEN src2.CostoConsulta ELSE NULL END AS ValorNumero,
                   CASE c.CodigoComponente WHEN ''POTENCIAL_PRESCRIPCION'' THEN src2.RecetasSemana WHEN ''UBICACION_TERRITORIAL_CM'' THEN src2.UbicacionTerritorialCM WHEN ''KOL'' THEN src2.KOL ELSE NULL END AS ValorTexto
            FROM src2 CROSS JOIN cat.DimComponenteCategoria c WHERE c.Activo = 1
        ),
        match2 AS (
            SELECT comp2.*, r.ReglaKey, r.Criterio, r.PuntajePct,
                   ROW_NUMBER() OVER (PARTITION BY comp2.MedicoCategoriaKey, comp2.ComponenteKey ORDER BY r.Criterio DESC, r.ReglaKey) AS rn
            FROM comp2
            LEFT JOIN cat.DimReglaCategoriaMedica r ON r.PaisKey = comp2.PaisKey AND r.ComponenteKey = comp2.ComponenteKey AND r.Activo = 1
              AND r.VigenteDesde <= @FechaCorte AND (r.VigenteHasta IS NULL OR r.VigenteHasta >= @FechaCorte)
              AND ((comp2.ValorNumero IS NOT NULL AND (r.ValorMinimo IS NULL OR comp2.ValorNumero >= r.ValorMinimo) AND (r.ValorMaximo IS NULL OR comp2.ValorNumero <= r.ValorMaximo))
                OR (comp2.ValorTexto IS NOT NULL AND UPPER(LTRIM(RTRIM(comp2.ValorTexto))) = UPPER(LTRIM(RTRIM(r.ValorTexto)))))
        )
        INSERT INTO cat.FactMedicoCategoriaDetalle (MedicoCategoriaKey, ComponenteKey, ReglaKey, ValorEntradaTexto, ValorEntradaNumero, Criterio, PuntajePct, EstadoComponente)
        SELECT MedicoCategoriaKey, ComponenteKey, ReglaKey, ValorTexto, ValorNumero, Criterio, PuntajePct,
               CASE WHEN ReglaKey IS NULL THEN ''SIN_REGLA'' ELSE ''OK'' END
        FROM match2 WHERE rn = 1;

        UPDATE cat.LoadBatch SET Estado = ''CALCULADO'', Mensaje = ''Proceso de categorizacion ejecutado.''
        WHERE LoadBatchKey = @LoadBatchKey;
    END
    ')
    """)


def downgrade():
    op.execute("IF OBJECT_ID('cat.vwMedicoCategoriaConciliacion','V') IS NOT NULL DROP VIEW cat.vwMedicoCategoriaConciliacion")
    op.execute("IF OBJECT_ID('cat.sp_CalcularCategoriaMedica','P') IS NOT NULL DROP PROCEDURE cat.sp_CalcularCategoriaMedica")
    op.execute("IF OBJECT_ID('cat.FactMedicoCategoriaDetalle','U') IS NOT NULL DROP TABLE cat.FactMedicoCategoriaDetalle")
    op.execute("IF OBJECT_ID('cat.FactMedicoCategoriaSnapshot','U') IS NOT NULL DROP TABLE cat.FactMedicoCategoriaSnapshot")
    op.execute("IF OBJECT_ID('stg.MedicoCategoriaInput','U') IS NOT NULL DROP TABLE stg.MedicoCategoriaInput")
    op.execute("IF OBJECT_ID('cat.DimMedico','U') IS NOT NULL DROP TABLE cat.DimMedico")
    op.execute("IF OBJECT_ID('cat.DimGeografia','U') IS NOT NULL DROP TABLE cat.DimGeografia")
    op.execute("IF OBJECT_ID('cat.DimCentroMedico','U') IS NOT NULL DROP TABLE cat.DimCentroMedico")
    op.execute("IF OBJECT_ID('cat.DimEspecialidad','U') IS NOT NULL DROP TABLE cat.DimEspecialidad")
    op.execute("IF OBJECT_ID('cat.DimRepresentanteMedico','U') IS NOT NULL DROP TABLE cat.DimRepresentanteMedico")
    op.execute("IF OBJECT_ID('cat.DimEquipo','U') IS NOT NULL DROP TABLE cat.DimEquipo")
    op.execute("IF OBJECT_ID('cat.DimReglaCategoriaMedica','U') IS NOT NULL DROP TABLE cat.DimReglaCategoriaMedica")
    op.execute("IF OBJECT_ID('cat.DimClasificacionMedica','U') IS NOT NULL DROP TABLE cat.DimClasificacionMedica")
    op.execute("IF OBJECT_ID('cat.DimComponenteCategoria','U') IS NOT NULL DROP TABLE cat.DimComponenteCategoria")
    op.execute("IF OBJECT_ID('cat.DimPais','U') IS NOT NULL DROP TABLE cat.DimPais")
    op.execute("IF OBJECT_ID('cat.LoadBatch','U') IS NOT NULL DROP TABLE cat.LoadBatch")
