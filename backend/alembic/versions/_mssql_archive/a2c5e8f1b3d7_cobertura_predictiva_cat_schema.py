"""Módulo Cobertura Predictiva — tablas cat.* + SP + Vista (Versión 2 — jun-2026)

Crea las entidades cat.* para el módulo de Cobertura Predictiva y Ritmo de Ejecución
integrado con el módulo de Categorización Médica:

  cat.DimCiclo               — ciclos promocionales con metas por país/línea
  cat.DimCalendario          — calendario hábil por país (base para NETWORKDAYS)
  cat.FactTargetMedicoCiclo  — universo de médicos programados por VM/ciclo
  cat.FactVisitaMedica       — bitácora de visitas realizadas
  cat.KpiCoberturaPredictiva — resultados calculados por el SP (tabla de salida)

  cat.sp_CalcularCoberturaPredictiva  — motor de cálculo en T-SQL
  cat.vwDashboardCoberturaPredictivaGD — vista del dashboard del GD

Merge heads: 2c771e676bd7, a1b2c3d4e5f6, a9b3c7d2e5f1, b1d4e7f2a9c3, e2f5b9c4a1d8

Revision ID: a2c5e8f1b3d7
Revises: 2c771e676bd7, a1b2c3d4e5f6, a9b3c7d2e5f1, b1d4e7f2a9c3, e2f5b9c4a1d8
Create Date: 2026-06-25 00:00:00.000000
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = 'a2c5e8f1b3d7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


# ─────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    # ── cat.DimCiclo ─────────────────────────────────────────────────────────
    op.execute("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                       WHERE TABLE_SCHEMA='cat' AND TABLE_NAME='DimCiclo')
        BEGIN
            CREATE TABLE [cat].[DimCiclo] (
                [CicloKey]           INT IDENTITY(1,1) NOT NULL,
                [PaisKey]            INT NOT NULL,
                [CodigoCiclo]        NVARCHAR(20) NOT NULL,
                [LineaId]            INT NULL,
                [Linea]              NVARCHAR(100) NULL,
                [FechaInicio]        DATE NOT NULL,
                [FechaFin]           DATE NOT NULL,
                [DiasHabilesCiclo]   INT NULL,
                [MetaCoberturaPct]   DECIMAL(5,4) NOT NULL CONSTRAINT [DF_DimCiclo_Meta] DEFAULT (0.90),
                [MetaContactosCiclo] INT NULL,
                [CicloNumeroAnual]   INT NULL,
                [Activo]             BIT NOT NULL CONSTRAINT [DF_DimCiclo_Activo] DEFAULT (1),
                [FechaCargaUtc]      DATETIME NOT NULL CONSTRAINT [DF_DimCiclo_Fecha] DEFAULT (GETUTCDATE()),
                CONSTRAINT [PK_DimCiclo] PRIMARY KEY ([CicloKey]),
                CONSTRAINT [UQ_DimCiclo_Pais_Codigo_Linea] UNIQUE ([PaisKey],[CodigoCiclo],[LineaId]),
                CONSTRAINT [FK_DimCiclo_DimPais] FOREIGN KEY ([PaisKey])
                    REFERENCES [cat].[DimPais]([PaisKey])
            );
        END
    """)

    # ── cat.DimCalendario ────────────────────────────────────────────────────
    op.execute("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                       WHERE TABLE_SCHEMA='cat' AND TABLE_NAME='DimCalendario')
        BEGIN
            CREATE TABLE [cat].[DimCalendario] (
                [FechaKey]      INT IDENTITY(1,1) NOT NULL,
                [PaisKey]       INT NOT NULL,
                [Fecha]         DATE NOT NULL,
                [CicloKey]      INT NULL,
                [EsHabil]       BIT NOT NULL CONSTRAINT [DF_DimCal_Habil]    DEFAULT (1),
                [EsFeriado]     BIT NOT NULL CONSTRAINT [DF_DimCal_Feriado]  DEFAULT (0),
                [Semana]        INT NULL,
                [Mes]           INT NULL,
                [Anio]          INT NULL,
                [Nota]          NVARCHAR(200) NULL,
                [FechaCargaUtc] DATETIME NOT NULL CONSTRAINT [DF_DimCal_Fecha] DEFAULT (GETUTCDATE()),
                CONSTRAINT [PK_DimCalendario] PRIMARY KEY ([FechaKey]),
                CONSTRAINT [UQ_DimCalendario_Pais_Fecha] UNIQUE ([PaisKey],[Fecha]),
                CONSTRAINT [FK_DimCalendario_DimPais]  FOREIGN KEY ([PaisKey])  REFERENCES [cat].[DimPais]([PaisKey]),
                CONSTRAINT [FK_DimCalendario_DimCiclo] FOREIGN KEY ([CicloKey]) REFERENCES [cat].[DimCiclo]([CicloKey])
            );
        END
    """)

    # ── cat.FactTargetMedicoCiclo ────────────────────────────────────────────
    op.execute("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                       WHERE TABLE_SCHEMA='cat' AND TABLE_NAME='FactTargetMedicoCiclo')
        BEGIN
            CREATE TABLE [cat].[FactTargetMedicoCiclo] (
                [TargetMedicoKey]    BIGINT IDENTITY(1,1) NOT NULL,
                [CicloKey]           INT NOT NULL,
                [PaisKey]            INT NOT NULL,
                [RepresentanteKey]   INT NOT NULL,
                [MedicoKey]          BIGINT NULL,
                [CodigoMedicoOrigen] NVARCHAR(50) NOT NULL,
                [NombreMedico]       NVARCHAR(200) NULL,
                [EspecialidadKey]    INT NULL,
                [Potencial]          NVARCHAR(5) NULL,
                [Territorio]         NVARCHAR(100) NULL,
                [FrecuenciaObjetivo] INT NULL,
                [ProgramadoFlag]     BIT NOT NULL CONSTRAINT [DF_Target_Prog] DEFAULT (1),
                [CategoriaMedica]    NVARCHAR(5) NULL,
                [Fuente]             NVARCHAR(100) NULL,
                [FechaCargaUtc]      DATETIME NOT NULL CONSTRAINT [DF_Target_Fecha] DEFAULT (GETUTCDATE()),
                CONSTRAINT [PK_FactTargetMedicoCiclo] PRIMARY KEY ([TargetMedicoKey]),
                CONSTRAINT [UQ_Target_Ciclo_Rep_Medico] UNIQUE ([CicloKey],[RepresentanteKey],[CodigoMedicoOrigen]),
                CONSTRAINT [FK_Target_DimCiclo]        FOREIGN KEY ([CicloKey])         REFERENCES [cat].[DimCiclo]([CicloKey]),
                CONSTRAINT [FK_Target_DimPais]         FOREIGN KEY ([PaisKey])          REFERENCES [cat].[DimPais]([PaisKey]),
                CONSTRAINT [FK_Target_DimRepresentante] FOREIGN KEY ([RepresentanteKey]) REFERENCES [cat].[DimRepresentanteMedico]([RepresentanteKey])
            );
        END
    """)

    # ── cat.FactVisitaMedica ─────────────────────────────────────────────────
    op.execute("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                       WHERE TABLE_SCHEMA='cat' AND TABLE_NAME='FactVisitaMedica')
        BEGIN
            CREATE TABLE [cat].[FactVisitaMedica] (
                [VisitaKey]          BIGINT IDENTITY(1,1) NOT NULL,
                [VisitaIdOrigen]     NVARCHAR(50) NULL,
                [FechaVisita]        DATE NOT NULL,
                [CicloKey]           INT NOT NULL,
                [PaisKey]            INT NOT NULL,
                [RepresentanteKey]   INT NOT NULL,
                [CodigoMedicoOrigen] NVARCHAR(50) NOT NULL,
                [MedicoKey]          BIGINT NULL,
                [TipoContacto]       NVARCHAR(50) NULL,
                [EstadoVisita]       NVARCHAR(50) NOT NULL CONSTRAINT [DF_Visita_Estado] DEFAULT (N'Realizada'),
                [ProductoFoco]       NVARCHAR(100) NULL,
                [Fuente]             NVARCHAR(100) NULL,
                [FechaCargaUtc]      DATETIME NOT NULL CONSTRAINT [DF_Visita_Fecha] DEFAULT (GETUTCDATE()),
                CONSTRAINT [PK_FactVisitaMedica] PRIMARY KEY ([VisitaKey]),
                CONSTRAINT [FK_Visita_DimCiclo]         FOREIGN KEY ([CicloKey])         REFERENCES [cat].[DimCiclo]([CicloKey]),
                CONSTRAINT [FK_Visita_DimPais]          FOREIGN KEY ([PaisKey])          REFERENCES [cat].[DimPais]([PaisKey]),
                CONSTRAINT [FK_Visita_DimRepresentante] FOREIGN KEY ([RepresentanteKey]) REFERENCES [cat].[DimRepresentanteMedico]([RepresentanteKey])
            );
            -- Índices para performance del SP
            CREATE INDEX [IX_FactVisita_Ciclo_Rep_Estado_Fecha]
                ON [cat].[FactVisitaMedica] ([CicloKey],[RepresentanteKey],[EstadoVisita],[FechaVisita]);
        END
    """)

    # ── cat.KpiCoberturaPredictiva ───────────────────────────────────────────
    op.execute("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                       WHERE TABLE_SCHEMA='cat' AND TABLE_NAME='KpiCoberturaPredictiva')
        BEGIN
            CREATE TABLE [cat].[KpiCoberturaPredictiva] (
                [KpiKey]                     BIGINT IDENTITY(1,1) NOT NULL,
                [FechaCorte]                 DATE NOT NULL,
                [CicloKey]                   INT NOT NULL,
                [PaisKey]                    INT NOT NULL,
                [Linea]                      NVARCHAR(100) NULL,
                [GD]                         NVARCHAR(150) NULL,
                [RepresentanteKey]           INT NOT NULL,
                [NombreVM]                   NVARCHAR(150) NULL,
                [MedicosProgramados]         INT NOT NULL CONSTRAINT [DF_Kpi_MedProg]   DEFAULT (0),
                [MedicosVisitadosUnicos]     INT NOT NULL CONSTRAINT [DF_Kpi_MedUni]    DEFAULT (0),
                [CoberturaActualPct]         DECIMAL(9,6) NOT NULL CONSTRAINT [DF_Kpi_CobAct]  DEFAULT (0),
                [CoberturaEsperadaPct]       DECIMAL(9,6) NOT NULL CONSTRAINT [DF_Kpi_CobEsp]  DEFAULT (0),
                [CoberturaProyectadaPct]     DECIMAL(9,6) NOT NULL CONSTRAINT [DF_Kpi_CobProy] DEFAULT (0),
                [MetaCoberturaPct]           DECIMAL(9,6) NOT NULL CONSTRAINT [DF_Kpi_Meta]    DEFAULT (0.9),
                [BrechaActualVsEsperada]     DECIMAL(9,6) NOT NULL CONSTRAINT [DF_Kpi_BrAct]   DEFAULT (0),
                [BrechaProyectadaVsMeta]     DECIMAL(9,6) NOT NULL CONSTRAINT [DF_Kpi_BrProy]  DEFAULT (0),
                [MedicosRequeridosMeta]      INT NOT NULL CONSTRAINT [DF_Kpi_MedReq] DEFAULT (0),
                [MedicosPendientesMeta]      INT NOT NULL CONSTRAINT [DF_Kpi_MedPend] DEFAULT (0),
                [MedicosDiariosRequeridos]   INT NOT NULL CONSTRAINT [DF_Kpi_MedDia] DEFAULT (0),
                [ContactosMetaCiclo]         INT NOT NULL CONSTRAINT [DF_Kpi_ContMeta] DEFAULT (0),
                [ContactosRealizados]        INT NOT NULL CONSTRAINT [DF_Kpi_ContReal] DEFAULT (0),
                [CumplimientoContactosPct]   DECIMAL(9,6) NOT NULL CONSTRAINT [DF_Kpi_CumCont] DEFAULT (0),
                [ContactosProyectados]       DECIMAL(12,4) NOT NULL CONSTRAINT [DF_Kpi_ContProy] DEFAULT (0),
                [ContactosPendientes]        DECIMAL(12,4) NOT NULL CONSTRAINT [DF_Kpi_ContPend] DEFAULT (0),
                [ContactosDiariosRequeridos] INT NOT NULL CONSTRAINT [DF_Kpi_ContDia] DEFAULT (0),
                [DiasHabilesTotales]         INT NOT NULL CONSTRAINT [DF_Kpi_DiasTot] DEFAULT (0),
                [DiasHabilesTranscurridos]   INT NOT NULL CONSTRAINT [DF_Kpi_DiasTrans] DEFAULT (0),
                [DiasHabilesRestantes]       INT NOT NULL CONSTRAINT [DF_Kpi_DiasRest] DEFAULT (0),
                [EstadoCobertura]            NVARCHAR(10) NOT NULL CONSTRAINT [DF_Kpi_EstCob] DEFAULT (N'Rojo'),
                [EstadoRitmo]                NVARCHAR(10) NOT NULL CONSTRAINT [DF_Kpi_EstRit] DEFAULT (N'Rojo'),
                [EstadoPSP]                  NVARCHAR(10) NOT NULL CONSTRAINT [DF_Kpi_EstPsp] DEFAULT (N'Rojo'),
                [LecturaAccionable]          NVARCHAR(2000) NULL,
                [FechaCargaUtc]              DATETIME NOT NULL CONSTRAINT [DF_Kpi_FechaCarga] DEFAULT (GETUTCDATE()),
                CONSTRAINT [PK_KpiCoberturaPredictiva] PRIMARY KEY ([KpiKey]),
                CONSTRAINT [UQ_Kpi_Corte_Ciclo_Rep] UNIQUE ([FechaCorte],[CicloKey],[RepresentanteKey]),
                CONSTRAINT [FK_Kpi_DimCiclo]         FOREIGN KEY ([CicloKey])         REFERENCES [cat].[DimCiclo]([CicloKey]),
                CONSTRAINT [FK_Kpi_DimPais]          FOREIGN KEY ([PaisKey])          REFERENCES [cat].[DimPais]([PaisKey]),
                CONSTRAINT [FK_Kpi_DimRepresentante] FOREIGN KEY ([RepresentanteKey]) REFERENCES [cat].[DimRepresentanteMedico]([RepresentanteKey])
            );
            CREATE INDEX [IX_Kpi_Ciclo_Corte] ON [cat].[KpiCoberturaPredictiva] ([CicloKey],[FechaCorte]);
        END
    """)

    # ── Stored Procedure: cat.sp_CalcularCoberturaPredictiva ─────────────────
    op.execute("""
        IF OBJECT_ID(N'cat.sp_CalcularCoberturaPredictiva', 'P') IS NOT NULL
            DROP PROCEDURE [cat].[sp_CalcularCoberturaPredictiva];
    """)

    op.execute("""
        CREATE PROCEDURE [cat].[sp_CalcularCoberturaPredictiva]
            @CodigoCiclo      NVARCHAR(20),
            @CodigoPais       NVARCHAR(2),
            @FechaCorte       DATE          = NULL,
            @RepresentanteKey INT           = NULL,
            @Linea            NVARCHAR(100) = NULL
        AS
        BEGIN
            SET NOCOUNT ON;

            IF @FechaCorte IS NULL SET @FechaCorte = CAST(GETDATE() AS DATE);

            -- ── Resolver PaisKey ─────────────────────────────────────────────
            DECLARE @PaisKey INT;
            SELECT @PaisKey = PaisKey FROM [cat].[DimPais] WHERE CodigoPais = @CodigoPais;
            IF @PaisKey IS NULL
            BEGIN
                RAISERROR(N'País no encontrado: %s', 16, 1, @CodigoPais);
                RETURN;
            END

            -- ── Resolver CicloKey ────────────────────────────────────────────
            DECLARE @CicloKey INT, @FechaInicio DATE, @FechaFin DATE,
                    @MetaCoberturaPct DECIMAL(5,4), @MetaContactosCiclo INT;
            SELECT TOP 1
                @CicloKey           = CicloKey,
                @FechaInicio        = FechaInicio,
                @FechaFin           = FechaFin,
                @MetaCoberturaPct   = MetaCoberturaPct,
                @MetaContactosCiclo = ISNULL(MetaContactosCiclo, 0)
            FROM [cat].[DimCiclo]
            WHERE CodigoCiclo = @CodigoCiclo
              AND PaisKey = @PaisKey
              AND Activo = 1
              AND (@Linea IS NULL OR Linea = @Linea)
            ORDER BY CicloKey;

            IF @CicloKey IS NULL
            BEGIN
                RAISERROR(N'Ciclo no encontrado: %s / País: %s', 16, 1, @CodigoCiclo, @CodigoPais);
                RETURN;
            END

            -- ── Días hábiles desde cat.DimCalendario ─────────────────────────
            DECLARE @DiasHabilesTotales INT       = 0;
            DECLARE @DiasHabilesTranscurridos INT = 0;
            DECLARE @FechaCorteEfectiva DATE      = CASE WHEN @FechaCorte > @FechaFin THEN @FechaFin ELSE @FechaCorte END;

            SELECT @DiasHabilesTotales = COUNT(*)
            FROM [cat].[DimCalendario]
            WHERE PaisKey = @PaisKey AND CicloKey = @CicloKey AND EsHabil = 1;

            -- Fallback: contar días L-V si no hay calendario cargado
            IF @DiasHabilesTotales = 0
            BEGIN
                ;WITH Dates AS (
                    SELECT @FechaInicio AS d
                    UNION ALL
                    SELECT DATEADD(DAY, 1, d) FROM Dates WHERE d < @FechaFin
                )
                SELECT @DiasHabilesTotales = COUNT(*)
                FROM Dates
                WHERE DATEPART(WEEKDAY, d) NOT IN (1,7)
                OPTION (MAXRECURSION 400);
            END

            SELECT @DiasHabilesTranscurridos = COUNT(*)
            FROM [cat].[DimCalendario]
            WHERE PaisKey = @PaisKey AND CicloKey = @CicloKey
              AND EsHabil = 1 AND Fecha <= @FechaCorteEfectiva AND Fecha >= @FechaInicio;

            -- Fallback si no hay calendario
            IF @DiasHabilesTranscurridos = 0 AND @FechaCorteEfectiva >= @FechaInicio
            BEGIN
                ;WITH Dates AS (
                    SELECT @FechaInicio AS d
                    UNION ALL
                    SELECT DATEADD(DAY, 1, d) FROM Dates WHERE d < @FechaCorteEfectiva
                )
                SELECT @DiasHabilesTranscurridos = COUNT(*)
                FROM Dates
                WHERE DATEPART(WEEKDAY, d) NOT IN (1,7)
                OPTION (MAXRECURSION 400);
                -- Incluir el día de corte si es hábil
                IF @FechaCorteEfectiva <= @FechaFin AND DATEPART(WEEKDAY, @FechaCorteEfectiva) NOT IN (1,7)
                    SET @DiasHabilesTranscurridos = @DiasHabilesTranscurridos + 1;
            END

            DECLARE @DiasHabilesRestantes INT = CASE
                WHEN @DiasHabilesTotales > @DiasHabilesTranscurridos
                THEN @DiasHabilesTotales - @DiasHabilesTranscurridos
                ELSE 0 END;

            -- ── Borrar resultados anteriores para este corte/ciclo ────────────
            DELETE FROM [cat].[KpiCoberturaPredictiva]
            WHERE CicloKey = @CicloKey
              AND FechaCorte = @FechaCorte
              AND (@RepresentanteKey IS NULL OR RepresentanteKey = @RepresentanteKey);

            -- ── Calcular e insertar KPIs por representante ───────────────────
            INSERT INTO [cat].[KpiCoberturaPredictiva] (
                FechaCorte, CicloKey, PaisKey, Linea, GD, RepresentanteKey, NombreVM,
                MedicosProgramados, MedicosVisitadosUnicos,
                CoberturaActualPct, CoberturaEsperadaPct, CoberturaProyectadaPct, MetaCoberturaPct,
                BrechaActualVsEsperada, BrechaProyectadaVsMeta,
                MedicosRequeridosMeta, MedicosPendientesMeta, MedicosDiariosRequeridos,
                ContactosMetaCiclo, ContactosRealizados, CumplimientoContactosPct,
                ContactosProyectados, ContactosPendientes, ContactosDiariosRequeridos,
                DiasHabilesTotales, DiasHabilesTranscurridos, DiasHabilesRestantes,
                EstadoCobertura, EstadoRitmo, EstadoPSP, LecturaAccionable, FechaCargaUtc
            )
            SELECT
                @FechaCorte                                                 AS FechaCorte,
                @CicloKey                                                   AS CicloKey,
                @PaisKey                                                    AS PaisKey,
                r.EquipoTexto                                               AS Linea,
                NULL                                                        AS GD,
                r.RepresentanteKey                                          AS RepresentanteKey,
                r.NombreRepresentante                                       AS NombreVM,

                -- J: Médicos programados
                ISNULL(t.MedicosProg, 0)                                    AS MedicosProgramados,

                -- L: Médicos únicos visitados (COUNT DISTINCT)
                ISNULL(v.MedicosUnicos, 0)                                  AS MedicosVisitadosUnicos,

                -- Z: Cobertura actual = L / J
                CASE WHEN ISNULL(t.MedicosProg, 0) > 0
                    THEN CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(9,6)) / t.MedicosProg
                    ELSE 0 END                                              AS CoberturaActualPct,

                -- Cobertura esperada al corte = Meta * (O / N)
                CASE WHEN @DiasHabilesTotales > 0
                    THEN CAST(@MetaCoberturaPct AS DECIMAL(9,6))
                         * CAST(@DiasHabilesTranscurridos AS DECIMAL(9,6)) / @DiasHabilesTotales
                    ELSE 0 END                                              AS CoberturaEsperadaPct,

                -- AA: Cobertura proyectada = MIN(1, (L/O * N) / J)
                CASE
                    WHEN ISNULL(t.MedicosProg,0) = 0 OR @DiasHabilesTranscurridos = 0 THEN 0
                    WHEN (CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(12,6))
                          / @DiasHabilesTranscurridos * @DiasHabilesTotales)
                         / t.MedicosProg > 1 THEN 1
                    ELSE (CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(12,6))
                          / @DiasHabilesTranscurridos * @DiasHabilesTotales)
                         / t.MedicosProg
                END                                                         AS CoberturaProyectadaPct,

                @MetaCoberturaPct                                           AS MetaCoberturaPct,

                -- Brecha actual vs esperada
                CASE WHEN ISNULL(t.MedicosProg,0) > 0 AND @DiasHabilesTotales > 0
                    THEN (CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(9,6)) / t.MedicosProg)
                         - (CAST(@MetaCoberturaPct AS DECIMAL(9,6))
                            * CAST(@DiasHabilesTranscurridos AS DECIMAL(9,6)) / @DiasHabilesTotales)
                    ELSE 0 END                                              AS BrechaActualVsEsperada,

                -- Brecha proyectada vs meta
                CASE
                    WHEN ISNULL(t.MedicosProg,0) = 0 OR @DiasHabilesTranscurridos = 0
                        THEN -CAST(@MetaCoberturaPct AS DECIMAL(9,6))
                    WHEN (CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(12,6))
                          / @DiasHabilesTranscurridos * @DiasHabilesTotales)
                         / t.MedicosProg > 1
                        THEN 1 - CAST(@MetaCoberturaPct AS DECIMAL(9,6))
                    ELSE (CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(12,6))
                          / @DiasHabilesTranscurridos * @DiasHabilesTotales)
                         / t.MedicosProg - CAST(@MetaCoberturaPct AS DECIMAL(9,6))
                END                                                         AS BrechaProyectadaVsMeta,

                -- K: Médicos requeridos para meta = CEILING(J * Meta)
                CASE WHEN ISNULL(t.MedicosProg,0) > 0
                    THEN CAST(CEILING(t.MedicosProg * @MetaCoberturaPct) AS INT)
                    ELSE 0 END                                              AS MedicosRequeridosMeta,

                -- Médicos pendientes = MAX(0, K - L)
                CASE
                    WHEN ISNULL(t.MedicosProg,0) = 0 THEN 0
                    WHEN CEILING(t.MedicosProg * @MetaCoberturaPct) > ISNULL(v.MedicosUnicos,0)
                        THEN CAST(CEILING(t.MedicosProg * @MetaCoberturaPct) AS INT) - ISNULL(v.MedicosUnicos,0)
                    ELSE 0
                END                                                         AS MedicosPendientesMeta,

                -- Médicos diarios requeridos = CEILING(pendientes / restantes)
                CASE
                    WHEN @DiasHabilesRestantes = 0 OR ISNULL(t.MedicosProg,0) = 0 THEN 0
                    WHEN CEILING(t.MedicosProg * @MetaCoberturaPct) > ISNULL(v.MedicosUnicos,0)
                        THEN CAST(CEILING(
                            CAST(CEILING(t.MedicosProg * @MetaCoberturaPct) - ISNULL(v.MedicosUnicos,0) AS DECIMAL(12,4))
                            / @DiasHabilesRestantes) AS INT)
                    ELSE 0
                END                                                         AS MedicosDiariosRequeridos,

                -- I: Meta contactos = medicos programados (default)
                ISNULL(t.MedicosProg, 0)                                    AS ContactosMetaCiclo,

                -- M: Contactos realizados (COUNT *)
                ISNULL(v.ContactosTotales, 0)                               AS ContactosRealizados,

                -- Cumplimiento contactos = M / I
                CASE WHEN ISNULL(t.MedicosProg,0) > 0
                    THEN CAST(ISNULL(v.ContactosTotales,0) AS DECIMAL(9,6)) / t.MedicosProg
                    ELSE 0 END                                              AS CumplimientoContactosPct,

                -- Contactos proyectados = (M/O) * N
                CASE WHEN @DiasHabilesTranscurridos > 0
                    THEN CAST(ISNULL(v.ContactosTotales,0) AS DECIMAL(12,4))
                         / @DiasHabilesTranscurridos * @DiasHabilesTotales
                    ELSE 0 END                                              AS ContactosProyectados,

                -- Contactos pendientes = MAX(0, I - M)
                CASE WHEN ISNULL(t.MedicosProg,0) > ISNULL(v.ContactosTotales,0)
                    THEN CAST(ISNULL(t.MedicosProg,0) - ISNULL(v.ContactosTotales,0) AS DECIMAL(12,4))
                    ELSE 0 END                                              AS ContactosPendientes,

                -- Contactos diarios requeridos = CEILING(V + X/P)
                CASE
                    WHEN @DiasHabilesRestantes = 0 OR @DiasHabilesTotales = 0 THEN 0
                    ELSE CAST(CEILING(
                        CAST(ISNULL(t.MedicosProg,0) AS DECIMAL(12,4)) / @DiasHabilesTotales
                        + CASE WHEN ISNULL(t.MedicosProg,0) > ISNULL(v.ContactosTotales,0)
                            THEN CAST(ISNULL(t.MedicosProg,0) - ISNULL(v.ContactosTotales,0) AS DECIMAL(12,4)) / @DiasHabilesRestantes
                            ELSE 0 END
                    ) AS INT)
                END                                                         AS ContactosDiariosRequeridos,

                @DiasHabilesTotales                                         AS DiasHabilesTotales,
                @DiasHabilesTranscurridos                                   AS DiasHabilesTranscurridos,
                @DiasHabilesRestantes                                       AS DiasHabilesRestantes,

                -- Estado cobertura (basado en proyección)
                CASE
                    WHEN ISNULL(t.MedicosProg,0) = 0 OR @DiasHabilesTranscurridos = 0 THEN N'Rojo'
                    WHEN CASE WHEN (CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(12,6)) / @DiasHabilesTranscurridos * @DiasHabilesTotales) / t.MedicosProg > 1 THEN 1
                         ELSE (CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(12,6)) / @DiasHabilesTranscurridos * @DiasHabilesTotales) / t.MedicosProg END >= @MetaCoberturaPct
                        THEN N'Verde'
                    WHEN CASE WHEN (CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(12,6)) / @DiasHabilesTranscurridos * @DiasHabilesTotales) / t.MedicosProg > 1 THEN 1
                         ELSE (CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(12,6)) / @DiasHabilesTranscurridos * @DiasHabilesTotales) / t.MedicosProg END >= 0.85
                        THEN N'Amarillo'
                    ELSE N'Rojo'
                END                                                         AS EstadoCobertura,

                -- Estado ritmo (cobertura actual vs esperada al corte)
                CASE
                    WHEN ISNULL(t.MedicosProg,0) = 0 OR @DiasHabilesTotales = 0 THEN N'Rojo'
                    WHEN CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(9,6)) / NULLIF(t.MedicosProg,0)
                         >= CAST(@MetaCoberturaPct AS DECIMAL(9,6)) * @DiasHabilesTranscurridos / NULLIF(@DiasHabilesTotales,0)
                        THEN N'Verde'
                    WHEN CAST(ISNULL(v.MedicosUnicos,0) AS DECIMAL(9,6)) / NULLIF(t.MedicosProg,0)
                         >= CAST(@MetaCoberturaPct AS DECIMAL(9,6)) * @DiasHabilesTranscurridos / NULLIF(@DiasHabilesTotales,0) - 0.05
                        THEN N'Amarillo'
                    ELSE N'Rojo'
                END                                                         AS EstadoRitmo,

                -- Estado PSP (contactos proyectados vs meta)
                CASE
                    WHEN ISNULL(t.MedicosProg,0) = 0 OR @DiasHabilesTranscurridos = 0 THEN N'Rojo'
                    WHEN CAST(ISNULL(v.ContactosTotales,0) AS DECIMAL(12,4)) / @DiasHabilesTranscurridos * @DiasHabilesTotales
                         >= t.MedicosProg THEN N'Verde'
                    WHEN CAST(ISNULL(v.ContactosTotales,0) AS DECIMAL(12,4)) / @DiasHabilesTranscurridos * @DiasHabilesTotales
                         >= t.MedicosProg * 0.9 THEN N'Amarillo'
                    ELSE N'Rojo'
                END                                                         AS EstadoPSP,

                -- Lectura accionable
                CONCAT(
                    N'Médicos diarios requeridos: ',
                    CAST(CASE
                        WHEN @DiasHabilesRestantes = 0 OR ISNULL(t.MedicosProg,0) = 0 THEN 0
                        WHEN CEILING(t.MedicosProg * @MetaCoberturaPct) > ISNULL(v.MedicosUnicos,0)
                            THEN CAST(CEILING(
                                CAST(CEILING(t.MedicosProg * @MetaCoberturaPct) - ISNULL(v.MedicosUnicos,0) AS DECIMAL(12,4))
                                / @DiasHabilesRestantes) AS INT)
                        ELSE 0
                    END AS NVARCHAR(10)),
                    N'. Contactos/día requeridos: ',
                    CAST(CASE
                        WHEN @DiasHabilesRestantes = 0 OR @DiasHabilesTotales = 0 THEN 0
                        ELSE CAST(CEILING(
                            CAST(ISNULL(t.MedicosProg,0) AS DECIMAL(12,4)) / @DiasHabilesTotales
                            + CASE WHEN ISNULL(t.MedicosProg,0) > ISNULL(v.ContactosTotales,0)
                                THEN CAST(ISNULL(t.MedicosProg,0) - ISNULL(v.ContactosTotales,0) AS DECIMAL(12,4)) / @DiasHabilesRestantes
                                ELSE 0 END) AS INT)
                    END AS NVARCHAR(10)),
                    N'. Días hábiles restantes: ', CAST(@DiasHabilesRestantes AS NVARCHAR(5)),
                    N'. Médicos pendientes: ',
                    CAST(CASE
                        WHEN ISNULL(t.MedicosProg,0) = 0 THEN 0
                        WHEN CEILING(t.MedicosProg * @MetaCoberturaPct) > ISNULL(v.MedicosUnicos,0)
                            THEN CAST(CEILING(t.MedicosProg * @MetaCoberturaPct) AS INT) - ISNULL(v.MedicosUnicos,0)
                        ELSE 0
                    END AS NVARCHAR(10)),
                    N' de ', CAST(ISNULL(t.MedicosProg,0) AS NVARCHAR(10)), N' programados.'
                )                                                           AS LecturaAccionable,

                GETUTCDATE()                                                AS FechaCargaUtc

            FROM [cat].[DimRepresentanteMedico] r
            INNER JOIN (
                SELECT RepresentanteKey, COUNT(*) AS MedicosProg
                FROM [cat].[FactTargetMedicoCiclo]
                WHERE CicloKey = @CicloKey AND PaisKey = @PaisKey AND ProgramadoFlag = 1
                  AND (@RepresentanteKey IS NULL OR RepresentanteKey = @RepresentanteKey)
                GROUP BY RepresentanteKey
            ) t ON t.RepresentanteKey = r.RepresentanteKey
            LEFT JOIN (
                SELECT
                    RepresentanteKey,
                    COUNT(DISTINCT CodigoMedicoOrigen) AS MedicosUnicos,
                    COUNT(*) AS ContactosTotales
                FROM [cat].[FactVisitaMedica]
                WHERE CicloKey = @CicloKey AND PaisKey = @PaisKey
                  AND EstadoVisita = N'Realizada'
                  AND FechaVisita <= @FechaCorte
                  AND (@RepresentanteKey IS NULL OR RepresentanteKey = @RepresentanteKey)
                GROUP BY RepresentanteKey
            ) v ON v.RepresentanteKey = r.RepresentanteKey
            WHERE r.Activo = 1
              AND (@Linea IS NULL OR r.EquipoTexto = @Linea);

            SELECT @@ROWCOUNT AS FilasInsertadas, @CicloKey AS CicloKey,
                   @FechaCorte AS FechaCorte, @DiasHabilesTotales AS DiasHabilesTotales,
                   @DiasHabilesTranscurridos AS DiasHabilesTranscurridos,
                   @DiasHabilesRestantes AS DiasHabilesRestantes;
        END;
    """)

    # ── Vista: cat.vwDashboardCoberturaPredictivaGD ──────────────────────────
    op.execute("""
        IF OBJECT_ID(N'cat.vwDashboardCoberturaPredictivaGD', 'V') IS NOT NULL
            DROP VIEW [cat].[vwDashboardCoberturaPredictivaGD];
    """)

    op.execute("""
        CREATE VIEW [cat].[vwDashboardCoberturaPredictivaGD]
        AS
        SELECT
            k.KpiKey,
            k.FechaCorte,
            p.CodigoPais,
            p.NombrePais,
            c.CodigoCiclo,
            c.FechaInicio                                                   AS CicloFechaInicio,
            c.FechaFin                                                      AS CicloFechaFin,
            ISNULL(k.Linea, r.EquipoTexto)                                  AS Linea,
            k.GD,
            r.CodigoRepresentante,
            r.NombreRepresentante,
            r.EquipoTexto,
            k.MedicosProgramados,
            k.MedicosVisitadosUnicos,
            CAST(k.CoberturaActualPct     * 100 AS DECIMAL(9,2))           AS CoberturaActualPct,
            CAST(k.CoberturaEsperadaPct   * 100 AS DECIMAL(9,2))           AS CoberturaEsperadaPct,
            CAST(k.CoberturaProyectadaPct * 100 AS DECIMAL(9,2))           AS CoberturaProyectadaPct,
            CAST(k.MetaCoberturaPct       * 100 AS DECIMAL(9,2))           AS MetaCoberturaPct,
            CAST(k.BrechaActualVsEsperada * 100 AS DECIMAL(9,2))           AS BrechaActualVsEsperadaPct,
            CAST(k.BrechaProyectadaVsMeta * 100 AS DECIMAL(9,2))           AS BrechaProyectadaVsMetaPct,
            k.MedicosRequeridosMeta,
            k.MedicosPendientesMeta,
            k.MedicosDiariosRequeridos,
            k.ContactosMetaCiclo,
            k.ContactosRealizados,
            CAST(k.CumplimientoContactosPct * 100 AS DECIMAL(9,2))         AS CumplimientoContactosPct,
            CAST(k.ContactosProyectados AS DECIMAL(12,1))                  AS ContactosProyectados,
            CAST(k.ContactosPendientes  AS DECIMAL(12,1))                  AS ContactosPendientes,
            k.ContactosDiariosRequeridos,
            k.DiasHabilesTotales,
            k.DiasHabilesTranscurridos,
            k.DiasHabilesRestantes,
            k.EstadoCobertura,
            k.EstadoRitmo,
            k.EstadoPSP,
            k.LecturaAccionable,
            k.FechaCargaUtc
        FROM [cat].[KpiCoberturaPredictiva] k
        INNER JOIN [cat].[DimCiclo]               c ON c.CicloKey       = k.CicloKey
        INNER JOIN [cat].[DimPais]                p ON p.PaisKey         = k.PaisKey
        INNER JOIN [cat].[DimRepresentanteMedico] r ON r.RepresentanteKey = k.RepresentanteKey;
    """)


# ─────────────────────────────────────────────────────────────────────────────
def downgrade() -> None:
    op.execute("IF OBJECT_ID(N'cat.vwDashboardCoberturaPredictivaGD','V') IS NOT NULL DROP VIEW [cat].[vwDashboardCoberturaPredictivaGD]")
    op.execute("IF OBJECT_ID(N'cat.sp_CalcularCoberturaPredictiva','P') IS NOT NULL DROP PROCEDURE [cat].[sp_CalcularCoberturaPredictiva]")
    op.execute("IF OBJECT_ID(N'cat.KpiCoberturaPredictiva','U') IS NOT NULL DROP TABLE [cat].[KpiCoberturaPredictiva]")
    op.execute("IF OBJECT_ID(N'cat.FactVisitaMedica','U') IS NOT NULL DROP TABLE [cat].[FactVisitaMedica]")
    op.execute("IF OBJECT_ID(N'cat.FactTargetMedicoCiclo','U') IS NOT NULL DROP TABLE [cat].[FactTargetMedicoCiclo]")
    op.execute("IF OBJECT_ID(N'cat.DimCalendario','U') IS NOT NULL DROP TABLE [cat].[DimCalendario]")
    op.execute("IF OBJECT_ID(N'cat.DimCiclo','U') IS NOT NULL DROP TABLE [cat].[DimCiclo]")
