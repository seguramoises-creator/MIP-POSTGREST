-- Baseline PostgreSQL — FOTO CONGELADA del esquema al 2026-07-04 (commit a7882c2).
--
-- NO REGENERAR desde los modelos. Este archivo existe precisamente porque el
-- baseline NO puede depender de `Base.metadata`: `env.py` importa todos los
-- modelos (autogenerate lo necesita), así que `create_all()` creaba lo que
-- existiera HOY, no lo que existía cuando se escribió la migración. Cada modelo
-- nuevo se colaba retroactivamente dentro del baseline y chocaba con la
-- migración posterior que de verdad lo crea. En una base ya instalada no se
-- nota (0001 no se vuelve a correr); solo aparece al instalar desde cero.
--
-- 1 tipo ENUM + 85 tablas, en orden topológico de dependencias (FKs).
-- Todo lo posterior a esta foto lo crean las migraciones 0002 en adelante.

-- El tipo `rol` lo creaba `create_all()` por su cuenta antes de las tablas;
-- `CreateTable` no lo emite, así que va explícito. PostgreSQL no admite
-- `CREATE TYPE IF NOT EXISTS`, de ahí el bloque con excepción.
DO $$ BEGIN
    CREATE TYPE rol AS ENUM ('ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL',
        'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA',
        'REPRESENTANTE_MEDICO', 'CONSULTA', 'CAPACITACION');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE "Audit"."FACT_Auditoria" (
	id BIGSERIAL NOT NULL, 
	fecha_hora TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	usuario_id INTEGER, 
	username VARCHAR(100), 
	rol VARCHAR(50), 
	accion VARCHAR(50) NOT NULL, 
	modulo VARCHAR(50), 
	tabla VARCHAR(100), 
	campo VARCHAR(100), 
	registro_id VARCHAR(50), 
	valor_anterior TEXT, 
	valor_nuevo TEXT, 
	ip_address VARCHAR(50), 
	user_agent VARCHAR(500), 
	exitoso BOOLEAN NOT NULL, 
	detalle TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE "Config"."DIM_Capacitacion" (
	id SERIAL NOT NULL, 
	codigo VARCHAR(50) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	tipo VARCHAR(50) NOT NULL, 
	duracion_horas NUMERIC(6, 2), 
	puntaje_aprobacion NUMERIC(5, 2), 
	obligatorio BOOLEAN NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE "Config"."DIM_CategoriaDesempeno" (
	id SERIAL NOT NULL, 
	codigo VARCHAR(30) NOT NULL, 
	nombre VARCHAR(100) NOT NULL, 
	score_min NUMERIC(10, 4), 
	score_max NUMERIC(10, 4), 
	color_dashboard VARCHAR(30), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE "Config"."DIM_CategoriaMedica" (
	id SERIAL NOT NULL, 
	codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(100) NOT NULL, 
	descripcion TEXT, 
	score_min NUMERIC(6, 4), 
	score_max NUMERIC(6, 4), 
	color_dashboard VARCHAR(30), 
	orden INTEGER NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE "Config"."DIM_ConfiguracionLSII" (
	id SERIAL NOT NULL, 
	corte_desempeno NUMERIC(5, 2) NOT NULL, 
	corte_receptividad NUMERIC(5, 2) NOT NULL, 
	actualizado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	actualizado_por VARCHAR(100), 
	PRIMARY KEY (id)
);

CREATE TABLE "Config"."DIM_CriterioCategoria" (
	id SERIAL NOT NULL, 
	codigo VARCHAR(50) NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	tipo_valor VARCHAR(20) NOT NULL, 
	peso NUMERIC(5, 4) NOT NULL, 
	orden INTEGER NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE "Config"."DIM_Especialidad" (
	id SERIAL NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (nombre)
);

CREATE TABLE "Config"."DIM_KpiDashboard" (
	id SERIAL NOT NULL, 
	codigo VARCHAR(50) NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	pagina_dashboard VARCHAR(100), 
	tipo_calculo VARCHAR(50), 
	descripcion TEXT, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE "Config"."DIM_Mes" (
	id SERIAL NOT NULL, 
	anio INTEGER NOT NULL, 
	mes INTEGER NOT NULL, 
	nombre VARCHAR(20) NOT NULL, 
	abrev VARCHAR(5), 
	ciclo_mes INTEGER, 
	trimestre INTEGER NOT NULL, 
	semestre INTEGER NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE "Config"."DIM_Pais" (
	id SERIAL NOT NULL, 
	codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(100) NOT NULL, 
	moneda VARCHAR(10), 
	zona_horaria VARCHAR(50), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE "Config"."DIM_Parametro" (
	clave VARCHAR(80) NOT NULL, 
	valor VARCHAR(400) NOT NULL, 
	actualizado TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (clave)
);

CREATE TABLE "Config"."DIM_Premio" (
	id SERIAL NOT NULL, 
	codigo VARCHAR(50) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	descripcion TEXT, 
	categoria VARCHAR(50) NOT NULL, 
	frecuencia VARCHAR(20) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE "Config"."DIM_ReceptividadOpcion" (
	id SERIAL NOT NULL, 
	dimension_codigo VARCHAR(50) NOT NULL, 
	dimension_nombre VARCHAR(200) NOT NULL, 
	dimension_descripcion TEXT, 
	orden_dimension INTEGER NOT NULL, 
	orden_opcion INTEGER NOT NULL, 
	texto_comportamiento TEXT NOT NULL, 
	score_oculto INTEGER NOT NULL, 
	peso_dimension NUMERIC(5, 4) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_ReceptividadOpcion_Dim_Orden" UNIQUE (dimension_codigo, orden_opcion)
);

CREATE TABLE "ETL"."FACT_CargaExcel" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10), 
	usuario_id INTEGER NOT NULL, 
	nombre_archivo VARCHAR(300) NOT NULL, 
	tipo_archivo VARCHAR(50) NOT NULL, 
	ciclo_id INTEGER, 
	modo VARCHAR(20) NOT NULL, 
	estado VARCHAR(20) NOT NULL, 
	total_filas INTEGER NOT NULL, 
	filas_exitosas INTEGER NOT NULL, 
	filas_error INTEGER NOT NULL, 
	filas_advertencia INTEGER NOT NULL, 
	log_errores TEXT, 
	log_advertencias TEXT, 
	duracion_segundos NUMERIC(8, 2), 
	fecha_inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	fecha_fin TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE "Security"."FACT_TokenRevocado" (
	id SERIAL NOT NULL, 
	jti VARCHAR(255) NOT NULL, 
	usuario_id INTEGER, 
	motivo VARCHAR(40), 
	expira_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	revocado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE cat."DimComponenteCategoria" (
	"ComponenteKey" SERIAL NOT NULL, 
	"CodigoComponente" VARCHAR(50) NOT NULL, 
	"NombreComponente" VARCHAR(150) NOT NULL, 
	"TipoEvaluacion" VARCHAR(30) NOT NULL, 
	"PesoComponentePct" NUMERIC(9, 6) NOT NULL, 
	"Requerido" BOOLEAN NOT NULL, 
	"Activo" BOOLEAN NOT NULL, 
	"FechaCargaUtc" TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY ("ComponenteKey"), 
	UNIQUE ("CodigoComponente")
);

CREATE TABLE cat."DimPais" (
	"PaisKey" SERIAL NOT NULL, 
	"PaisIdOrigen" INTEGER, 
	"CodigoPais" VARCHAR(2) NOT NULL, 
	"NombrePais" VARCHAR(100) NOT NULL, 
	"Moneda" VARCHAR(3), 
	"ZonaHoraria" VARCHAR(80), 
	"Activo" BOOLEAN NOT NULL, 
	"FechaCargaUtc" TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY ("PaisKey"), 
	UNIQUE ("CodigoPais")
);

CREATE TABLE cat."LoadBatch" (
	"LoadBatchKey" BIGSERIAL NOT NULL, 
	"ArchivoOrigen" VARCHAR(260) NOT NULL, 
	"Periodo" VARCHAR(7) NOT NULL, 
	"CodigoPaisDefault" VARCHAR(2), 
	"FechaCargaUtc" TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	"UsuarioCarga" VARCHAR(150), 
	"Estado" VARCHAR(20) NOT NULL, 
	"Mensaje" VARCHAR(1000), 
	PRIMARY KEY ("LoadBatchKey")
);

CREATE TABLE "Config"."DIM_Ciclo" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	anio INTEGER NOT NULL, 
	numero INTEGER NOT NULL, 
	nombre VARCHAR(50) NOT NULL, 
	nombre_canonico VARCHAR(50), 
	fecha_inicio DATE NOT NULL, 
	fecha_fin DATE NOT NULL, 
	dias_laborables INTEGER NOT NULL, 
	cerrado BOOLEAN NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo)
);

CREATE TABLE "Config"."DIM_CriterioCategoriaTabla" (
	id SERIAL NOT NULL, 
	criterio_id INTEGER NOT NULL, 
	pais_codigo VARCHAR(10), 
	rango_desde NUMERIC(12, 4), 
	rango_hasta NUMERIC(12, 4), 
	etiqueta VARCHAR(100), 
	nivel INTEGER NOT NULL, 
	descripcion VARCHAR(150), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(criterio_id) REFERENCES "Config"."DIM_CriterioCategoria" (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo)
);

CREATE TABLE "Config"."DIM_Feriado" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	fecha DATE NOT NULL, 
	nombre VARCHAR(150), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_Feriado_Pais_Fecha" UNIQUE (pais_codigo, fecha), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo)
);

CREATE TABLE "Config"."DIM_Indicador" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	codigo VARCHAR(50) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	descripcion TEXT, 
	rol VARCHAR(20) NOT NULL, 
	modulo VARCHAR(50) NOT NULL, 
	tipo_periodo VARCHAR(10) NOT NULL, 
	ponderacion_pct INTEGER NOT NULL, 
	escala INTEGER NOT NULL, 
	valor_min NUMERIC(10, 4), 
	valor_max NUMERIC(10, 4), 
	formula TEXT, 
	peso_iup NUMERIC(5, 4) NOT NULL, 
	unidad VARCHAR(30), 
	meta_global NUMERIC(10, 4), 
	activo BOOLEAN NOT NULL, 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_Indicador_Pais_Codigo" UNIQUE (pais_codigo, codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo)
);

CREATE TABLE "Config"."DIM_Indicador_V2" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	codigo VARCHAR(50) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	descripcion TEXT, 
	rol VARCHAR(20) NOT NULL, 
	modulo VARCHAR(50) NOT NULL, 
	tipo_periodo VARCHAR(10) NOT NULL, 
	ponderacion_pct INTEGER NOT NULL, 
	escala INTEGER NOT NULL, 
	valor_min NUMERIC(10, 4), 
	valor_max NUMERIC(10, 4), 
	formula TEXT, 
	peso_iup NUMERIC(5, 4) NOT NULL, 
	unidad VARCHAR(30), 
	meta_global NUMERIC(10, 4), 
	activo BOOLEAN NOT NULL, 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_Indicador_V2_Pais_Codigo" UNIQUE (pais_codigo, codigo), 
	CONSTRAINT "CK_Indicador_V2_Modulo" CHECK (modulo IN ('PRODUCTIVIDAD','COMERCIAL','COACHING','CAPACITACION','GESTION','RESULTADOS')), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo)
);

CREATE TABLE "Config"."DIM_Linea" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	codigo VARCHAR(20) NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	descripcion TEXT, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo)
);

CREATE TABLE "Config"."DIM_MedicoCobertura_V2" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	codigo VARCHAR(50) NOT NULL, 
	nombre VARCHAR(200), 
	especialidad VARCHAR(100), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_MedicoCobertura_V2_Pais_Codigo" UNIQUE (pais_codigo, codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo)
);

CREATE TABLE "Config"."DIM_Provincia" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_Provincia_Pais_Nombre" UNIQUE (pais_codigo, nombre), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo)
);

CREATE TABLE "ETL"."FACT_KPI_RAW" (
	id BIGSERIAL NOT NULL, 
	carga_id INTEGER NOT NULL, 
	fact_id INTEGER, 
	pais_id INTEGER, 
	pais_codigo VARCHAR(10), 
	rm_id INTEGER, 
	nombre_rm VARCHAR(200), 
	rm_codigo VARCHAR(50), 
	gerente_id INTEGER, 
	gerente_codigo VARCHAR(50), 
	linea_id INTEGER, 
	linea_codigo VARCHAR(50), 
	indicador_id INTEGER, 
	indicador_codigo VARCHAR(50), 
	tipo_periodo VARCHAR(20), 
	ciclo_id INTEGER, 
	ciclo_nombre VARCHAR(50), 
	mes_id INTEGER, 
	ciclo_mes INTEGER, 
	anio INTEGER, 
	valor_real NUMERIC(18, 6), 
	fecha_carga TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(carga_id) REFERENCES "ETL"."FACT_CargaExcel" (id)
);

CREATE TABLE cat."DimCiclo" (
	"CicloKey" SERIAL NOT NULL, 
	"PaisKey" INTEGER NOT NULL, 
	"CodigoCiclo" VARCHAR(20) NOT NULL, 
	"LineaId" INTEGER, 
	"Linea" VARCHAR(100), 
	"FechaInicio" DATE NOT NULL, 
	"FechaFin" DATE NOT NULL, 
	"DiasHabilesCiclo" INTEGER, 
	"MetaCoberturaPct" NUMERIC(5, 4) NOT NULL, 
	"MetaContactosCiclo" INTEGER, 
	"CicloNumeroAnual" INTEGER, 
	"Activo" BOOLEAN NOT NULL, 
	"FechaCargaUtc" TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY ("CicloKey"), 
	CONSTRAINT "UQ_DimCiclo_Pais_Codigo_Linea" UNIQUE ("PaisKey", "CodigoCiclo", "LineaId"), 
	FOREIGN KEY("PaisKey") REFERENCES cat."DimPais" ("PaisKey")
);

CREATE TABLE cat."DimClasificacionMedica" (
	"ClasificacionKey" SERIAL NOT NULL, 
	"PaisKey" INTEGER NOT NULL, 
	"Clase" VARCHAR(1) NOT NULL, 
	"PuntajeMinPct" NUMERIC(9, 6) NOT NULL, 
	"PuntajeMaxPct" NUMERIC(9, 6) NOT NULL, 
	"OrdenClase" SMALLINT NOT NULL, 
	"VigenteDesde" DATE NOT NULL, 
	"VigenteHasta" DATE, 
	"Activo" BOOLEAN NOT NULL, 
	"FechaCargaUtc" TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY ("ClasificacionKey"), 
	CONSTRAINT "UQ_DimClasificacion" UNIQUE ("PaisKey", "Clase", "VigenteDesde"), 
	FOREIGN KEY("PaisKey") REFERENCES cat."DimPais" ("PaisKey")
);

CREATE TABLE cat."DimEspecialidad" (
	"EspecialidadKey" SERIAL NOT NULL, 
	"PaisKey" INTEGER NOT NULL, 
	"Especialidad" VARCHAR(150) NOT NULL, 
	"Activo" BOOLEAN NOT NULL, 
	PRIMARY KEY ("EspecialidadKey"), 
	CONSTRAINT "UQ_DimEspecialidad" UNIQUE ("PaisKey", "Especialidad"), 
	FOREIGN KEY("PaisKey") REFERENCES cat."DimPais" ("PaisKey")
);

CREATE TABLE cat."DimRepresentanteMedico" (
	"RepresentanteKey" SERIAL NOT NULL, 
	"PaisKey" INTEGER NOT NULL, 
	"RepresentanteIdOrigen" INTEGER, 
	"CodigoRepresentante" VARCHAR(30) NOT NULL, 
	"NombreRepresentante" VARCHAR(150) NOT NULL, 
	"LineaIdOrigen" INTEGER, 
	"GerenteIdOrigen" INTEGER, 
	"Email" VARCHAR(150), 
	"Zona" VARCHAR(80), 
	"FechaIngreso" DATE, 
	"Cedula" VARCHAR(30), 
	"CodigoOrigenExcel" VARCHAR(50), 
	"EquipoTexto" VARCHAR(120), 
	"Activo" BOOLEAN NOT NULL, 
	PRIMARY KEY ("RepresentanteKey"), 
	CONSTRAINT "UQ_DimRepresentanteMedico" UNIQUE ("PaisKey", "CodigoRepresentante"), 
	FOREIGN KEY("PaisKey") REFERENCES cat."DimPais" ("PaisKey")
);

CREATE TABLE "Config"."DIM_Gerente" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_id INTEGER, 
	codigo VARCHAR(20) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	email VARCHAR(200), 
	tipo VARCHAR(50) NOT NULL, 
	fecha_ingreso DATE, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	UNIQUE (codigo)
);

CREATE TABLE "Config"."DIM_IndicadorTabla" (
	id SERIAL NOT NULL, 
	indicador_id INTEGER NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	codigo_indicador VARCHAR(50), 
	nombre_indicador VARCHAR(150), 
	rango_desde NUMERIC(10, 4) NOT NULL, 
	rango_hasta NUMERIC(10, 4) NOT NULL, 
	puntos NUMERIC(10, 4) NOT NULL, 
	descripcion VARCHAR(100), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(indicador_id) REFERENCES "Config"."DIM_Indicador" (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo)
);

CREATE TABLE "Config"."DIM_MetaIndicador" (
	id SERIAL NOT NULL, 
	indicador_id INTEGER NOT NULL, 
	peso NUMERIC(6, 2) NOT NULL, 
	minimo NUMERIC(10, 4), 
	objetivo NUMERIC(10, 4), 
	maximo NUMERIC(10, 4), 
	puntaje_maximo NUMERIC(10, 4), 
	meta_100 NUMERIC(10, 4), 
	tipo_calculo VARCHAR(30), 
	orden_dashboard INTEGER, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_MetaIndicador_Indicador" UNIQUE (indicador_id), 
	FOREIGN KEY(indicador_id) REFERENCES "Config"."DIM_Indicador" (id)
);

CREATE TABLE "Config"."DIM_Municipio" (
	id SERIAL NOT NULL, 
	provincia_id INTEGER NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_Municipio_Provincia_Nombre" UNIQUE (provincia_id, nombre), 
	FOREIGN KEY(provincia_id) REFERENCES "Config"."DIM_Provincia" (id)
);

CREATE TABLE "Config"."DIM_ParametroCobertura" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_id INTEGER, 
	ciclo_id INTEGER, 
	meta_cobertura NUMERIC(5, 4) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_ParametroCobertura_Pais_Linea_Ciclo" UNIQUE (pais_codigo, linea_id, ciclo_id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "Config"."DIM_Producto" (
	id SERIAL NOT NULL, 
	codigo VARCHAR(40) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	area_terapeutica VARCHAR(80), 
	descripcion VARCHAR(150), 
	segmento_target VARCHAR(120), 
	meta_muestras_visita INTEGER NOT NULL, 
	gerente_producto VARCHAR(150), 
	linea_id INTEGER, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id)
);

CREATE TABLE "Config"."DIM_ReglaElegibilidad" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_id INTEGER, 
	nombre VARCHAR(200) NOT NULL, 
	indicador_codigo VARCHAR(50) NOT NULL, 
	umbral_minimo NUMERIC(8, 4) NOT NULL, 
	aplica_ranking BOOLEAN NOT NULL, 
	aplica_reconocimiento BOOLEAN NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "DW"."FACT_DashboardEjecutivo" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	kpi_dashboard_id INTEGER NOT NULL, 
	valor NUMERIC(16, 4), 
	valor_anterior NUMERIC(16, 4), 
	variacion NUMERIC(16, 4), 
	unidad VARCHAR(30), 
	fuente_calculo VARCHAR(200), 
	fecha_calculo TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(kpi_dashboard_id) REFERENCES "Config"."DIM_KpiDashboard" (id)
);

CREATE TABLE "DW"."FACT_DistribucionEquipo" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	categoria_id INTEGER NOT NULL, 
	cantidad_rm INTEGER NOT NULL, 
	porcentaje_rm NUMERIC(6, 2), 
	fecha_calculo TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(categoria_id) REFERENCES "Config"."DIM_CategoriaDesempeno" (id)
);

CREATE TABLE "DW"."FACT_ScorecardIndicador" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	indicador_id INTEGER NOT NULL, 
	peso_indicador NUMERIC(6, 2), 
	resultado_promedio NUMERIC(14, 4), 
	score_promedio NUMERIC(10, 4), 
	categoria_id INTEGER, 
	variacion_vs_ciclo_anterior NUMERIC(8, 4), 
	fecha_calculo TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(indicador_id) REFERENCES "Config"."DIM_Indicador" (id), 
	FOREIGN KEY(categoria_id) REFERENCES "Config"."DIM_CategoriaDesempeno" (id)
);

CREATE TABLE "DW"."FACT_TendenciaCiclo" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	score_promedio NUMERIC(10, 4), 
	score_minimo NUMERIC(10, 4), 
	score_maximo NUMERIC(10, 4), 
	total_rm INTEGER NOT NULL, 
	fecha_calculo TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE cat."DimCalendario" (
	"FechaKey" SERIAL NOT NULL, 
	"PaisKey" INTEGER NOT NULL, 
	"Fecha" DATE NOT NULL, 
	"CicloKey" INTEGER, 
	"EsHabil" BOOLEAN NOT NULL, 
	"EsFeriado" BOOLEAN NOT NULL, 
	"Semana" INTEGER, 
	"Mes" INTEGER, 
	"Anio" INTEGER, 
	"Nota" VARCHAR(200), 
	"FechaCargaUtc" TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY ("FechaKey"), 
	CONSTRAINT "UQ_DimCalendario_Pais_Fecha" UNIQUE ("PaisKey", "Fecha"), 
	FOREIGN KEY("PaisKey") REFERENCES cat."DimPais" ("PaisKey"), 
	FOREIGN KEY("CicloKey") REFERENCES cat."DimCiclo" ("CicloKey")
);

CREATE TABLE cat."DimMedico" (
	"MedicoKey" BIGSERIAL NOT NULL, 
	"PaisKey" INTEGER NOT NULL, 
	"MedicoId" INTEGER, 
	"CodigoMedico" VARCHAR(50), 
	"NombreMedico" VARCHAR(200) NOT NULL, 
	"EspecialidadKey" INTEGER, 
	"Activo" BOOLEAN NOT NULL, 
	PRIMARY KEY ("MedicoKey"), 
	FOREIGN KEY("PaisKey") REFERENCES cat."DimPais" ("PaisKey"), 
	FOREIGN KEY("EspecialidadKey") REFERENCES cat."DimEspecialidad" ("EspecialidadKey")
);

CREATE TABLE cat."FactVisitaMedica" (
	"VisitaKey" BIGSERIAL NOT NULL, 
	"VisitaIdOrigen" VARCHAR(50), 
	"FechaVisita" DATE NOT NULL, 
	"CicloKey" INTEGER NOT NULL, 
	"PaisKey" INTEGER NOT NULL, 
	"RepresentanteKey" INTEGER NOT NULL, 
	"CodigoMedicoOrigen" VARCHAR(50) NOT NULL, 
	"MedicoKey" BIGINT, 
	"TipoContacto" VARCHAR(50), 
	"EstadoVisita" VARCHAR(50) NOT NULL, 
	"ProductoFoco" VARCHAR(100), 
	"Fuente" VARCHAR(100), 
	"FechaCargaUtc" TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY ("VisitaKey"), 
	FOREIGN KEY("CicloKey") REFERENCES cat."DimCiclo" ("CicloKey"), 
	FOREIGN KEY("PaisKey") REFERENCES cat."DimPais" ("PaisKey"), 
	FOREIGN KEY("RepresentanteKey") REFERENCES cat."DimRepresentanteMedico" ("RepresentanteKey")
);

CREATE TABLE cat."KpiCoberturaPredictiva" (
	"KpiKey" BIGSERIAL NOT NULL, 
	"FechaCorte" DATE NOT NULL, 
	"CicloKey" INTEGER NOT NULL, 
	"PaisKey" INTEGER NOT NULL, 
	"Linea" VARCHAR(100), 
	"GD" VARCHAR(150), 
	"RepresentanteKey" INTEGER NOT NULL, 
	"NombreVM" VARCHAR(150), 
	"MedicosProgramados" INTEGER NOT NULL, 
	"MedicosVisitadosUnicos" INTEGER NOT NULL, 
	"CoberturaActualPct" NUMERIC(9, 6) NOT NULL, 
	"CoberturaEsperadaPct" NUMERIC(9, 6) NOT NULL, 
	"CoberturaProyectadaPct" NUMERIC(9, 6) NOT NULL, 
	"MetaCoberturaPct" NUMERIC(9, 6) NOT NULL, 
	"BrechaActualVsEsperada" NUMERIC(9, 6) NOT NULL, 
	"BrechaProyectadaVsMeta" NUMERIC(9, 6) NOT NULL, 
	"MedicosRequeridosMeta" INTEGER NOT NULL, 
	"MedicosPendientesMeta" INTEGER NOT NULL, 
	"MedicosDiariosRequeridos" INTEGER NOT NULL, 
	"ContactosMetaCiclo" INTEGER NOT NULL, 
	"ContactosRealizados" INTEGER NOT NULL, 
	"CumplimientoContactosPct" NUMERIC(9, 6) NOT NULL, 
	"ContactosProyectados" NUMERIC(12, 4) NOT NULL, 
	"ContactosPendientes" NUMERIC(12, 4) NOT NULL, 
	"ContactosDiariosRequeridos" INTEGER NOT NULL, 
	"DiasHabilesTotales" INTEGER NOT NULL, 
	"DiasHabilesTranscurridos" INTEGER NOT NULL, 
	"DiasHabilesRestantes" INTEGER NOT NULL, 
	"EstadoCobertura" VARCHAR(10) NOT NULL, 
	"EstadoRitmo" VARCHAR(10) NOT NULL, 
	"EstadoPSP" VARCHAR(10) NOT NULL, 
	"LecturaAccionable" VARCHAR(2000), 
	"FechaCargaUtc" TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY ("KpiKey"), 
	CONSTRAINT "UQ_Kpi_Corte_Ciclo_Rep" UNIQUE ("FechaCorte", "CicloKey", "RepresentanteKey"), 
	FOREIGN KEY("CicloKey") REFERENCES cat."DimCiclo" ("CicloKey"), 
	FOREIGN KEY("PaisKey") REFERENCES cat."DimPais" ("PaisKey"), 
	FOREIGN KEY("RepresentanteKey") REFERENCES cat."DimRepresentanteMedico" ("RepresentanteKey")
);

CREATE TABLE "Config"."DIM_CentroMedico" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	provincia_id INTEGER, 
	municipio_id INTEGER, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_CentroMedico_Pais_Nombre" UNIQUE (pais_codigo, nombre), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(provincia_id) REFERENCES "Config"."DIM_Provincia" (id), 
	FOREIGN KEY(municipio_id) REFERENCES "Config"."DIM_Municipio" (id)
);

CREATE TABLE "Config"."DIM_RM" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_id INTEGER NOT NULL, 
	gerente_id INTEGER, 
	codigo VARCHAR(20) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	cedula VARCHAR(30), 
	email VARCHAR(200), 
	zona VARCHAR(100), 
	activo BOOLEAN NOT NULL, 
	fecha_ingreso DATE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id), 
	UNIQUE (codigo)
);

CREATE TABLE "Config"."DIM_RM_V2" (
	id SERIAL NOT NULL, 
	codigo_origen_excel VARCHAR(20), 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_id INTEGER NOT NULL, 
	gerente_id INTEGER, 
	codigo VARCHAR(20) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	cedula VARCHAR(30), 
	email VARCHAR(200), 
	zona VARCHAR(100), 
	activo BOOLEAN NOT NULL, 
	fecha_ingreso DATE, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_RM_V2_Pais_Codigo" UNIQUE (pais_codigo, codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id)
);

CREATE TABLE "DW"."FACT_RankingGerente" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	gerente_id INTEGER NOT NULL, 
	ciclo_id INTEGER, 
	score_total NUMERIC(10, 4) NOT NULL, 
	posicion INTEGER NOT NULL, 
	metodo_calculo VARCHAR(50), 
	fecha_generacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "Security"."DIM_Usuario" (
	id SERIAL NOT NULL, 
	username VARCHAR(100) NOT NULL, 
	email VARCHAR(200) NOT NULL, 
	hashed_password VARCHAR(255) NOT NULL, 
	nombre_completo VARCHAR(200) NOT NULL, 
	rol rol NOT NULL, 
	pais_codigo VARCHAR(10), 
	rm_id INTEGER, 
	gerente_id INTEGER, 
	activo BOOLEAN NOT NULL, 
	debe_cambiar_password BOOLEAN NOT NULL, 
	intentos_fallidos INTEGER NOT NULL, 
	bloqueado_hasta TIMESTAMP WITHOUT TIME ZONE, 
	ultimo_login TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id)
);

CREATE TABLE "Visita"."CostoProducto" (
	id SERIAL NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	linea_id INTEGER, 
	producto_id INTEGER, 
	producto VARCHAR(120) NOT NULL, 
	orden INTEGER NOT NULL, 
	costo_unitario_muestra NUMERIC(12, 2) NOT NULL, 
	cantidad_muestras INTEGER NOT NULL, 
	pool_ventas NUMERIC(16, 2) NOT NULL, 
	visitas_detalladas INTEGER NOT NULL, 
	presupuesto_anual NUMERIC(16, 2) NOT NULL, 
	precio_prom NUMERIC(12, 2) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(producto_id) REFERENCES "Config"."DIM_Producto" (id)
);

CREATE TABLE cat."FactMedicoCategoriaSnapshot" (
	"MedicoCategoriaKey" BIGSERIAL NOT NULL, 
	"LoadBatchKey" BIGINT, 
	"RowNumber" INTEGER NOT NULL, 
	"Periodo" VARCHAR(7) NOT NULL, 
	"PaisKey" INTEGER NOT NULL, 
	"MedicoKey" BIGINT NOT NULL, 
	"CentroMedicoKey" INTEGER, 
	"GeografiaKey" INTEGER, 
	"RepresentanteKey" INTEGER, 
	"Equipo" VARCHAR(120), 
	"Provincia" VARCHAR(120), 
	"Municipio" VARCHAR(120), 
	"LineaIdOrigen" INTEGER, 
	"PacientesSemana" NUMERIC(18, 4), 
	"CostoConsulta" NUMERIC(18, 4), 
	"RecetasSemana" VARCHAR(80), 
	"UbicacionTerritorialCM" VARCHAR(80), 
	"KOL" VARCHAR(150), 
	"PuntajeTotalPct" NUMERIC(9, 6), 
	"ClasificacionKey" INTEGER, 
	"CategoriaCalculada" VARCHAR(1), 
	"CategoriaExcel" VARCHAR(20), 
	"EstadoConciliacion" VARCHAR(30), 
	"EstadoCalculo" VARCHAR(20) NOT NULL, 
	"MensajeCalculo" VARCHAR(500), 
	PRIMARY KEY ("MedicoCategoriaKey"), 
	FOREIGN KEY("LoadBatchKey") REFERENCES cat."LoadBatch" ("LoadBatchKey"), 
	FOREIGN KEY("PaisKey") REFERENCES cat."DimPais" ("PaisKey"), 
	FOREIGN KEY("MedicoKey") REFERENCES cat."DimMedico" ("MedicoKey"), 
	FOREIGN KEY("ClasificacionKey") REFERENCES cat."DimClasificacionMedica" ("ClasificacionKey")
);

CREATE TABLE cat."FactTargetMedicoCiclo" (
	"TargetMedicoKey" BIGSERIAL NOT NULL, 
	"CicloKey" INTEGER NOT NULL, 
	"PaisKey" INTEGER NOT NULL, 
	"RepresentanteKey" INTEGER NOT NULL, 
	"MedicoKey" BIGINT, 
	"CodigoMedicoOrigen" VARCHAR(50) NOT NULL, 
	"NombreMedico" VARCHAR(200), 
	"EspecialidadKey" INTEGER, 
	"Potencial" VARCHAR(5), 
	"Territorio" VARCHAR(100), 
	"FrecuenciaObjetivo" INTEGER, 
	"ProgramadoFlag" BOOLEAN NOT NULL, 
	"CategoriaMedica" VARCHAR(5), 
	"Fuente" VARCHAR(100), 
	"FechaCargaUtc" TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY ("TargetMedicoKey"), 
	CONSTRAINT "UQ_Target_Ciclo_Rep_Medico" UNIQUE ("CicloKey", "RepresentanteKey", "CodigoMedicoOrigen"), 
	FOREIGN KEY("CicloKey") REFERENCES cat."DimCiclo" ("CicloKey"), 
	FOREIGN KEY("PaisKey") REFERENCES cat."DimPais" ("PaisKey"), 
	FOREIGN KEY("RepresentanteKey") REFERENCES cat."DimRepresentanteMedico" ("RepresentanteKey"), 
	FOREIGN KEY("MedicoKey") REFERENCES cat."DimMedico" ("MedicoKey")
);

CREATE TABLE "Config"."DIM_Medico" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	codigo VARCHAR(50), 
	nombre VARCHAR(200) NOT NULL, 
	especialidad_id INTEGER, 
	centro_medico_id INTEGER, 
	provincia_id INTEGER, 
	municipio_id INTEGER, 
	cedula VARCHAR(30), 
	email VARCHAR(200), 
	activo BOOLEAN DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(especialidad_id) REFERENCES "Config"."DIM_Especialidad" (id), 
	FOREIGN KEY(centro_medico_id) REFERENCES "Config"."DIM_CentroMedico" (id), 
	FOREIGN KEY(provincia_id) REFERENCES "Config"."DIM_Provincia" (id), 
	FOREIGN KEY(municipio_id) REFERENCES "Config"."DIM_Municipio" (id)
);

CREATE TABLE "Config"."DIM_TargetMedico" (
	id SERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	rm_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	medico_codigo VARCHAR(50) NOT NULL, 
	medico_nombre VARCHAR(200), 
	especialidad VARCHAR(100), 
	potencial VARCHAR(20), 
	programado BOOLEAN NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_TargetMedico_RM_Ciclo_Medico" UNIQUE (rm_id, ciclo_id, medico_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "DW"."FACT_Capacitacion" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	rm_id INTEGER NOT NULL, 
	capacitacion_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	asistio BOOLEAN NOT NULL, 
	calificacion NUMERIC(5, 2), 
	aprobado BOOLEAN NOT NULL, 
	horas_completadas NUMERIC(6, 2) NOT NULL, 
	fecha_actividad DATE, 
	puntaje NUMERIC(10, 4) NOT NULL, 
	fecha_carga TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(capacitacion_id) REFERENCES "Config"."DIM_Capacitacion" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "DW"."FACT_Coaching" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	gerente_id INTEGER NOT NULL, 
	rm_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	tipo VARCHAR(30) NOT NULL, 
	coaching_programado INTEGER NOT NULL, 
	coaching_ejecutado INTEGER NOT NULL, 
	cumplimiento_pct NUMERIC(8, 4) NOT NULL, 
	calificacion_calidad NUMERIC(5, 2) NOT NULL, 
	peso_cantidad NUMERIC(4, 2) NOT NULL, 
	peso_calidad NUMERIC(4, 2) NOT NULL, 
	resultado_coaching NUMERIC(10, 4) NOT NULL, 
	puntaje NUMERIC(10, 4) NOT NULL, 
	fecha_coaching DATE, 
	observaciones TEXT, 
	fecha_carga TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "DW"."FACT_EVOIR" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	rm_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	producto_codigo VARCHAR(50) NOT NULL, 
	producto_nombre VARCHAR(200) NOT NULL, 
	prescripciones_actuales NUMERIC(14, 4) NOT NULL, 
	prescripciones_anteriores NUMERIC(14, 4) NOT NULL, 
	evolucion_pct NUMERIC(8, 4), 
	puntaje NUMERIC(10, 4) NOT NULL, 
	fecha_carga TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "DW"."FACT_EvaluacionReceptividad" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	rm_id INTEGER NOT NULL, 
	gerente_id INTEGER, 
	ciclo_id INTEGER NOT NULL, 
	evaluador_usuario_id INTEGER, 
	score_receptividad NUMERIC(6, 2) NOT NULL, 
	score_desempeno NUMERIC(6, 2), 
	nivel_lsii VARCHAR(5) NOT NULL, 
	estilo_liderazgo VARCHAR(50) NOT NULL, 
	observaciones TEXT, 
	activo BOOLEAN NOT NULL, 
	fecha_evaluacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "DW"."FACT_RankingRM" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_id INTEGER, 
	gerente_id INTEGER, 
	rm_id INTEGER NOT NULL, 
	ciclo_id INTEGER, 
	tipo_ranking VARCHAR(30) NOT NULL, 
	score_total NUMERIC(10, 4) NOT NULL, 
	categoria_id INTEGER, 
	posicion_global INTEGER NOT NULL, 
	posicion_linea INTEGER, 
	posicion_anterior INTEGER, 
	elegible BOOLEAN NOT NULL, 
	fecha_generacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(categoria_id) REFERENCES "Config"."DIM_CategoriaDesempeno" (id)
);

CREATE TABLE "DW"."FACT_ReconocimientoRM" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_id INTEGER, 
	gerente_id INTEGER, 
	rm_id INTEGER, 
	premio_id INTEGER NOT NULL, 
	ciclo_id INTEGER, 
	score_total NUMERIC(10, 4) NOT NULL, 
	posicion_linea INTEGER, 
	posicion_ranking INTEGER, 
	elegible BOOLEAN NOT NULL, 
	certificado_generado BOOLEAN NOT NULL, 
	certificado_url VARCHAR(500), 
	aprobado_por VARCHAR(200), 
	observaciones TEXT, 
	fecha_calculo TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(premio_id) REFERENCES "Config"."DIM_Premio" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "DW"."FACT_ResultadoIndicador" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_id INTEGER NOT NULL, 
	gerente_id INTEGER, 
	rm_id INTEGER NOT NULL, 
	indicador_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	mes_id INTEGER, 
	resultado_real NUMERIC(14, 4) NOT NULL, 
	resultado_porcentaje NUMERIC(8, 4), 
	factor_aplicado NUMERIC(10, 4), 
	puntos_obtenidos NUMERIC(10, 4), 
	puntos_maximos NUMERIC(10, 4), 
	porcentaje_logro NUMERIC(8, 4), 
	carga_excel_id INTEGER, 
	fecha_carga TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	fecha_calculo TIMESTAMP WITHOUT TIME ZONE, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(indicador_id) REFERENCES "Config"."DIM_Indicador" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "DW"."FACT_ScoreIntegralRM" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_id INTEGER, 
	gerente_id INTEGER, 
	rm_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	score_total NUMERIC(10, 4) NOT NULL, 
	categoria_id INTEGER, 
	elegible_reconocimiento BOOLEAN NOT NULL, 
	fecha_calculo TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(categoria_id) REFERENCES "Config"."DIM_CategoriaDesempeno" (id)
);

CREATE TABLE "DW"."FACT_Ventas" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_id INTEGER NOT NULL, 
	rm_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	ventas_reales NUMERIC(16, 2) NOT NULL, 
	cuota NUMERIC(16, 2), 
	cumplimiento_pct NUMERIC(8, 4), 
	crecimiento_pct NUMERIC(8, 4), 
	puntaje NUMERIC(10, 4) NOT NULL, 
	fecha_carga TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "DW"."FACT_Visita" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	rm_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	medico_codigo VARCHAR(50) NOT NULL, 
	fecha_visita DATE NOT NULL, 
	tipo_contacto VARCHAR(50), 
	estado_visita VARCHAR(20) NOT NULL, 
	producto_foco VARCHAR(100), 
	carga_excel_id INTEGER, 
	fecha_carga TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE "DW"."FACT_Visita_V2" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	rm_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	medico_id INTEGER NOT NULL, 
	medico_codigo VARCHAR(50) NOT NULL, 
	fecha_visita DATE NOT NULL, 
	tipo_contacto VARCHAR(50), 
	estado_visita VARCHAR(20) NOT NULL, 
	producto_foco VARCHAR(100), 
	carga_excel_id INTEGER, 
	fecha_carga TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(medico_id) REFERENCES "Config"."DIM_MedicoCobertura_V2" (id)
);

CREATE TABLE "Visita"."CierreCicloVisita" (
	id SERIAL NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	fecha_cierre TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	panel INTEGER NOT NULL, 
	visitados INTEGER NOT NULL, 
	sin_visitar INTEGER NOT NULL, 
	ruptura_nueva INTEGER NOT NULL, 
	ruptura_critica INTEGER NOT NULL, 
	cerrado_por INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(cerrado_por) REFERENCES "Security"."DIM_Usuario" (id)
);

CREATE TABLE "Visita"."CostoEstructura" (
	id SERIAL NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	linea_id INTEGER, 
	moneda VARCHAR(8) NOT NULL, 
	salario_mensual NUMERIC(14, 2) NOT NULL, 
	cargas_pct NUMERIC(6, 2) NOT NULL, 
	viaticos_dia NUMERIC(12, 2) NOT NULL, 
	materiales_ciclo NUMERIC(12, 2) NOT NULL, 
	dias_campo INTEGER NOT NULL, 
	total_visitas INTEGER NOT NULL, 
	dias_mes INTEGER NOT NULL, 
	visitadores INTEGER NOT NULL, 
	visitas_ciclo_vm INTEGER NOT NULL, 
	ciclos_anio INTEGER NOT NULL, 
	coef_conservador NUMERIC(5, 2) NOT NULL, 
	coef_optimista NUMERIC(5, 2) NOT NULL, 
	psp_a NUMERIC(14, 2) NOT NULL, 
	psp_b NUMERIC(14, 2) NOT NULL, 
	psp_c NUMERIC(14, 2) NOT NULL, 
	med_sin_visitar_a INTEGER, 
	med_sin_visitar_b INTEGER, 
	med_sin_visitar_c INTEGER, 
	fecha_actualizacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	modificado_por INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(modificado_por) REFERENCES "Security"."DIM_Usuario" (id)
);

CREATE TABLE "Visita"."DIM_MedicoVisita" (
	id SERIAL NOT NULL, 
	vm_id INTEGER NOT NULL, 
	codigo VARCHAR(40), 
	nombre_completo VARCHAR(200) NOT NULL, 
	nombre VARCHAR(100), 
	apellidos VARCHAR(150), 
	especialidad_id INTEGER, 
	subespecialidad VARCHAR(120), 
	categoria CHAR(1) NOT NULL, 
	centro_trabajo VARCHAR(200), 
	institucion_tipo VARCHAR(20), 
	tipo_consultorio VARCHAR(60), 
	provincia VARCHAR(100), 
	municipio VARCHAR(100), 
	sector VARCHAR(100), 
	direccion VARCHAR(300), 
	latitud NUMERIC(10, 7), 
	longitud NUMERIC(10, 7), 
	telefono VARCHAR(40), 
	email VARCHAR(200), 
	exequatur VARCHAR(50), 
	dias_consulta VARCHAR(100), 
	horario_consulta VARCHAR(100), 
	frecuencia_visita VARCHAR(20), 
	acepta_visita BOOLEAN NOT NULL, 
	potencial_prescripcion VARCHAR(20), 
	kol BOOLEAN NOT NULL, 
	segmento VARCHAR(60), 
	observaciones VARCHAR(500), 
	ciclos_sin_visita INTEGER NOT NULL, 
	activo BOOLEAN NOT NULL, 
	fecha_alta DATE, 
	estado_aprobacion VARCHAR(16) NOT NULL, 
	ciclo_alta_id INTEGER, 
	ciclo_baja_id INTEGER, 
	solicitado_por INTEGER, 
	aprobado_por INTEGER, 
	fecha_solicitud TIMESTAMP WITHOUT TIME ZONE, 
	fecha_aprobacion TIMESTAMP WITHOUT TIME ZONE, 
	motivo VARCHAR(300), 
	fecha_registro TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	registrado_por INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(vm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(especialidad_id) REFERENCES "Config"."DIM_Especialidad" (id), 
	FOREIGN KEY(ciclo_alta_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(ciclo_baja_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(solicitado_por) REFERENCES "Security"."DIM_Usuario" (id), 
	FOREIGN KEY(aprobado_por) REFERENCES "Security"."DIM_Usuario" (id), 
	FOREIGN KEY(registrado_por) REFERENCES "Security"."DIM_Usuario" (id)
);

CREATE TABLE "Visita"."ParametroCosto" (
	id SERIAL NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	linea_id INTEGER, 
	costo_visita NUMERIC(14, 2) NOT NULL, 
	costo_muestra NUMERIC(14, 2) NOT NULL, 
	costo_fijo_ciclo NUMERIC(14, 2) NOT NULL, 
	moneda VARCHAR(8) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	fecha_actualizacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	modificado_por INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(modificado_por) REFERENCES "Security"."DIM_Usuario" (id)
);

CREATE TABLE "Visita"."ParrillaPromocional" (
	id SERIAL NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	linea_id INTEGER NOT NULL, 
	producto_id INTEGER, 
	producto VARCHAR(120) NOT NULL, 
	mensaje_clave VARCHAR(300), 
	segmento_target VARCHAR(120), 
	prioridad INTEGER NOT NULL, 
	meta_muestras INTEGER NOT NULL, 
	activo BOOLEAN NOT NULL, 
	publicada BOOLEAN NOT NULL, 
	fecha_publicacion TIMESTAMP WITHOUT TIME ZONE, 
	publicada_por INTEGER, 
	fecha_creacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	modificado_por INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(producto_id) REFERENCES "Config"."DIM_Producto" (id), 
	FOREIGN KEY(publicada_por) REFERENCES "Security"."DIM_Usuario" (id), 
	FOREIGN KEY(modificado_por) REFERENCES "Security"."DIM_Usuario" (id)
);

CREATE TABLE exam."DimExamen" (
	id SERIAL NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	producto VARCHAR(200), 
	nota_minima INTEGER NOT NULL, 
	tiempo_limite_min INTEGER, 
	estado VARCHAR(20) NOT NULL, 
	fuente VARCHAR(10) NOT NULL, 
	rand_preguntas BOOLEAN NOT NULL, 
	rand_opciones BOOLEAN NOT NULL, 
	creado_por_usuario_id INTEGER NOT NULL, 
	indicador_codigo VARCHAR(50), 
	ciclo_id INTEGER, 
	fecha_creacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	fecha_publicacion TIMESTAMP WITHOUT TIME ZONE, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(creado_por_usuario_id) REFERENCES "Security"."DIM_Usuario" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id)
);

CREATE TABLE exam."FactConsolidacionCiclo" (
	id SERIAL NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	estado VARCHAR(15) NOT NULL, 
	rms_consolidados INTEGER NOT NULL, 
	nota_promedio_equipo NUMERIC(5, 2), 
	fecha_consolidacion TIMESTAMP WITHOUT TIME ZONE, 
	consolidado_por_usuario_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_ConsolidacionCiclo_ciclo_pais" UNIQUE (ciclo_id, pais_codigo), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(consolidado_por_usuario_id) REFERENCES "Security"."DIM_Usuario" (id)
);

CREATE TABLE "DW"."FACT_CategorizacionMedica" (
	id BIGSERIAL NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_id INTEGER, 
	gerente_id INTEGER, 
	rm_id INTEGER NOT NULL, 
	medico_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	pacientes_semana NUMERIC(10, 2), 
	costo_consulta NUMERIC(12, 2), 
	potencial_prescripcion NUMERIC(10, 2), 
	ubicacion_territorial VARCHAR(50), 
	kol VARCHAR(100), 
	nivel_pacientes INTEGER, 
	nivel_poder_adquisitivo INTEGER, 
	nivel_prescripcion INTEGER, 
	nivel_ubicacion INTEGER, 
	nivel_kol INTEGER, 
	score_pacientes NUMERIC(6, 4) NOT NULL, 
	score_poder_adquisitivo NUMERIC(6, 4) NOT NULL, 
	score_prescripcion NUMERIC(6, 4) NOT NULL, 
	score_ubicacion NUMERIC(6, 4) NOT NULL, 
	score_kol NUMERIC(6, 4) NOT NULL, 
	score_total NUMERIC(6, 4) NOT NULL, 
	categoria_id INTEGER, 
	categoria_anterior_id INTEGER, 
	observaciones TEXT, 
	carga_excel_id INTEGER, 
	fecha_calculo TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	usuario_calculo VARCHAR(100), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_CategorizacionMedica_Medico_RM_Ciclo" UNIQUE (medico_id, rm_id, ciclo_id), 
	FOREIGN KEY(pais_codigo) REFERENCES "Config"."DIM_Pais" (codigo), 
	FOREIGN KEY(linea_id) REFERENCES "Config"."DIM_Linea" (id), 
	FOREIGN KEY(gerente_id) REFERENCES "Config"."DIM_Gerente" (id), 
	FOREIGN KEY(rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(medico_id) REFERENCES "Config"."DIM_Medico" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(categoria_id) REFERENCES "Config"."DIM_CategoriaMedica" (id), 
	FOREIGN KEY(categoria_anterior_id) REFERENCES "Config"."DIM_CategoriaMedica" (id)
);

CREATE TABLE "DW"."FACT_EvaluacionReceptividadDetalle" (
	id BIGSERIAL NOT NULL, 
	evaluacion_id BIGINT NOT NULL, 
	dimension_codigo VARCHAR(50) NOT NULL, 
	opcion_id INTEGER NOT NULL, 
	score_oculto INTEGER NOT NULL, 
	peso_dimension NUMERIC(5, 4) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evaluacion_id) REFERENCES "DW"."FACT_EvaluacionReceptividad" (id), 
	FOREIGN KEY(opcion_id) REFERENCES "Config"."DIM_ReceptividadOpcion" (id)
);

CREATE TABLE "Visita"."FactVisita" (
	id SERIAL NOT NULL, 
	vm_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	medico_id INTEGER NOT NULL, 
	tipo_visita CHAR(1) NOT NULL, 
	fecha_hora TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	comentario VARCHAR(1000), 
	productos VARCHAR(300), 
	ejecutada BOOLEAN NOT NULL, 
	causa_no_visita VARCHAR(80), 
	registrado_por INTEGER, 
	latitud NUMERIC(10, 7), 
	longitud NUMERIC(10, 7), 
	foto BYTEA, 
	foto_mime VARCHAR(40), 
	PRIMARY KEY (id), 
	FOREIGN KEY(vm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(medico_id) REFERENCES "Visita"."DIM_MedicoVisita" (id), 
	FOREIGN KEY(registrado_por) REFERENCES "Security"."DIM_Usuario" (id)
);

CREATE TABLE "Visita"."MuestraEntregada" (
	id SERIAL NOT NULL, 
	vm_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	medico_id INTEGER NOT NULL, 
	producto VARCHAR(120) NOT NULL, 
	cantidad INTEGER NOT NULL, 
	fecha_entrega TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	registrado_por INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(vm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(medico_id) REFERENCES "Visita"."DIM_MedicoVisita" (id), 
	FOREIGN KEY(registrado_por) REFERENCES "Security"."DIM_Usuario" (id)
);

CREATE TABLE "Visita"."PlaneacionCiclo" (
	id SERIAL NOT NULL, 
	vm_id INTEGER NOT NULL, 
	ciclo_id INTEGER NOT NULL, 
	medico_id INTEGER NOT NULL, 
	tipo_visita CHAR(1) NOT NULL, 
	semana INTEGER NOT NULL, 
	dia_semana VARCHAR(12), 
	hora_estimada VARCHAR(5), 
	fecha_creacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	modificado_por INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(vm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(ciclo_id) REFERENCES "Config"."DIM_Ciclo" (id), 
	FOREIGN KEY(medico_id) REFERENCES "Visita"."DIM_MedicoVisita" (id), 
	FOREIGN KEY(modificado_por) REFERENCES "Security"."DIM_Usuario" (id)
);

CREATE TABLE exam."DimPregunta" (
	id SERIAL NOT NULL, 
	examen_id INTEGER NOT NULL, 
	tipo VARCHAR(10) NOT NULL, 
	escenario TEXT, 
	texto TEXT NOT NULL, 
	explicacion TEXT, 
	orden INTEGER NOT NULL, 
	peso NUMERIC(6, 2), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(examen_id) REFERENCES exam."DimExamen" (id)
);

CREATE TABLE exam."FactAsignacionExamen" (
	id SERIAL NOT NULL, 
	examen_id INTEGER NOT NULL, 
	evaluado_tipo VARCHAR(10) NOT NULL, 
	evaluado_rm_id INTEGER, 
	evaluado_gerente_id INTEGER, 
	fecha_asignacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	fecha_limite TIMESTAMP WITHOUT TIME ZONE, 
	intentos_max INTEGER, 
	intentos_usados INTEGER NOT NULL, 
	estado VARCHAR(15) NOT NULL, 
	notif_activa BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "CK_AsignacionExamen_evaluado_coherente" CHECK ((evaluado_tipo = 'RM' AND evaluado_rm_id IS NOT NULL AND evaluado_gerente_id IS NULL) OR (evaluado_tipo = 'GERENTE' AND evaluado_gerente_id IS NOT NULL AND evaluado_rm_id IS NULL)), 
	FOREIGN KEY(examen_id) REFERENCES exam."DimExamen" (id), 
	FOREIGN KEY(evaluado_rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(evaluado_gerente_id) REFERENCES "Config"."DIM_Gerente" (id)
);

CREATE TABLE exam."FactFuenteIA" (
	id SERIAL NOT NULL, 
	examen_id INTEGER, 
	tipo_archivo VARCHAR(20), 
	nombre_archivo VARCHAR(300), 
	ruta_archivo VARCHAR(400), 
	texto_extraido_hash VARCHAR(64), 
	prompt_usado TEXT, 
	estado_generacion VARCHAR(15) NOT NULL, 
	mensaje_error TEXT, 
	cargado_por_usuario_id INTEGER, 
	fecha_carga TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(examen_id) REFERENCES exam."DimExamen" (id), 
	FOREIGN KEY(cargado_por_usuario_id) REFERENCES "Security"."DIM_Usuario" (id)
);

CREATE TABLE exam."DimPreguntaOpcion" (
	id SERIAL NOT NULL, 
	pregunta_id INTEGER NOT NULL, 
	texto_opcion TEXT NOT NULL, 
	indice_original INTEGER NOT NULL, 
	es_correcta BOOLEAN NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(pregunta_id) REFERENCES exam."DimPregunta" (id)
);

CREATE TABLE exam."FactIntentoExamen" (
	id SERIAL NOT NULL, 
	asignacion_id INTEGER NOT NULL, 
	evaluado_tipo VARCHAR(10) NOT NULL, 
	evaluado_rm_id INTEGER, 
	evaluado_gerente_id INTEGER, 
	fecha_inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	fecha_fin TIMESTAMP WITHOUT TIME ZONE, 
	score NUMERIC(5, 2), 
	aprobado BOOLEAN, 
	tiempo_usado_seg INTEGER, 
	orden_preguntas_json TEXT, 
	mapa_presentacion_json TEXT, 
	user_agent VARCHAR(400), 
	device_type VARCHAR(40), 
	plataforma VARCHAR(40), 
	ip_cliente VARCHAR(50), 
	PRIMARY KEY (id), 
	FOREIGN KEY(asignacion_id) REFERENCES exam."FactAsignacionExamen" (id), 
	FOREIGN KEY(evaluado_rm_id) REFERENCES "Config"."DIM_RM" (id), 
	FOREIGN KEY(evaluado_gerente_id) REFERENCES "Config"."DIM_Gerente" (id)
);

CREATE TABLE exam."FactIntentoRespuesta" (
	id SERIAL NOT NULL, 
	intento_id INTEGER NOT NULL, 
	pregunta_id INTEGER NOT NULL, 
	opcion_elegida_id INTEGER, 
	indice_opcion_presentada INTEGER, 
	indice_original_elegido INTEGER, 
	es_correcta BOOLEAN, 
	respuesta_texto TEXT, 
	puntos NUMERIC(6, 2), 
	mapa_opciones_json TEXT, 
	fecha_respuesta TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT "UQ_IntentoRespuesta_intento_pregunta" UNIQUE (intento_id, pregunta_id), 
	FOREIGN KEY(intento_id) REFERENCES exam."FactIntentoExamen" (id), 
	FOREIGN KEY(pregunta_id) REFERENCES exam."DimPregunta" (id), 
	FOREIGN KEY(opcion_elegida_id) REFERENCES exam."DimPreguntaOpcion" (id)
);