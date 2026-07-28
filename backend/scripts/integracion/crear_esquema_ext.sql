-- ===========================================================================
-- VISTA · Laboratorios Mallen — esquema de recepcion de datos `ext`
-- ===========================================================================
-- Requerimiento de Datos v1.0 (25-jul-2026), secciones 3 a 6.
-- PostgreSQL 17.
--
-- Mallen ESCRIBE en estas 22 tablas; VISTA las LEE y desde ahi alimenta sus
-- estructuras internas. VISTA nunca se conecta al SQL Server de Mallen.
--
-- Este archivo lo genera scripts/integracion/generar_ddl_ext.py a partir de los
-- modelos de la aplicacion: es exactamente el esquema que corre en produccion.
-- No editarlo a mano.
--
-- TRES DIFERENCIAS RESPECTO AL DDL IMPRESO EN EL DOCUMENTO
-- --------------------------------------------------------
-- 1. Los nombres van en MINUSCULAS y sin comillas. El documento crea las tablas
--    sin comillas (`CREATE TABLE ext.DimPais`, que PostgreSQL pliega a
--    `ext.dimpais`) pero luego las referencia entrecomilladas en las claves
--    foraneas y los indices (`ext."DimPais"`, que exige ese uso exacto de
--    mayusculas); corridas en ese orden, las sentencias de la seccion 6.4
--    fallan con "no existe la relacion". Se unifico sin comillas porque asi
--    `ext.DimPais`, `ext.dimpais` y `EXT.DIMPAIS` funcionan las tres desde
--    cualquier herramienta.
-- 2. Se incluyen las claves foraneas que el documento omite "por brevedad"
--    (seccion 6.4, ultima nota): lote_id, ciclo y representante en el resto de
--    las tablas de hecho.
-- 3. Se incluyen los indices unicos (pais_codigo, origen_id) de
--    factevaluacionconocimiento y factprescripciondetalle. La seccion 5.2 exige
--    idempotencia para TODOS los hechos, pero la 6.5 solo los declaraba para
--    tres: sin ellos, reenviar uno de esos dos lotes duplicaria filas.
--
-- Los dominios acotados (tipo_visita, frecuencia_objetivo, prioridad, estado)
-- NO llevan CHECK a proposito: la seccion 7.1 pide que las inconsistencias se
-- registren "sin detener el lote completo", y un CHECK rechazaria la fila
-- entera. VISTA valida esos dominios al integrar y deja constancia.
-- ===========================================================================

CREATE SCHEMA IF NOT EXISTS ext;


-- --- Tablas (en orden de dependencia) ---

CREATE TABLE ext.dimespecialidad (
	especialidad_codigo VARCHAR(30) NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (especialidad_codigo)
);

CREATE TABLE ext.dimmercadoir (
	mercado_codigo VARCHAR(40) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	nivel VARCHAR(30), 
	mercado_padre VARCHAR(40), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (mercado_codigo)
);

CREATE TABLE ext.dimpais (
	pais_codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(100) NOT NULL, 
	moneda VARCHAR(10), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo)
);

CREATE TABLE ext.controlcarga (
	lote_id BIGINT NOT NULL, 
	sistema_origen VARCHAR(30) NOT NULL, 
	modulo VARCHAR(40) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_codigo VARCHAR(20), 
	periodo VARCHAR(20), 
	fecha_extraccion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	fecha_recepcion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	filas_enviadas INTEGER NOT NULL, 
	estado VARCHAR(20) NOT NULL, 
	mensaje VARCHAR(500), 
	PRIMARY KEY (lote_id), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo)
);

CREATE TABLE ext.dimciclo (
	ciclo_codigo VARCHAR(20) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	anio INTEGER NOT NULL, 
	numero INTEGER NOT NULL, 
	nombre VARCHAR(100), 
	fecha_inicio DATE NOT NULL, 
	fecha_fin DATE NOT NULL, 
	dias_laborables INTEGER NOT NULL, 
	cerrado BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, ciclo_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo)
);

CREATE TABLE ext.dimfarmacia (
	farmacia_codigo VARCHAR(40) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	tipo VARCHAR(40), 
	provincia VARCHAR(120), 
	municipio VARCHAR(120), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, farmacia_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo)
);

CREATE TABLE ext.dimlinea (
	linea_codigo VARCHAR(30) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(100) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, linea_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo)
);

CREATE TABLE ext.dimmedico (
	medico_codigo VARCHAR(40) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	especialidad_codigo VARCHAR(30), 
	exequatur VARCHAR(50), 
	centro_trabajo VARCHAR(200), 
	provincia VARCHAR(120), 
	municipio VARCHAR(120), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, medico_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo), 
	FOREIGN KEY(especialidad_codigo) REFERENCES ext.dimespecialidad (especialidad_codigo)
);

CREATE TABLE ext.dimterritorio (
	territorio_codigo VARCHAR(40) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	provincia VARCHAR(120), 
	region VARCHAR(120), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, territorio_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo)
);

CREATE TABLE ext.dimgerente (
	gerente_codigo VARCHAR(30) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_codigo VARCHAR(30), 
	nombre VARCHAR(150) NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	email VARCHAR(200), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, gerente_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo), 
	FOREIGN KEY(pais_codigo, linea_codigo) REFERENCES ext.dimlinea (pais_codigo, linea_codigo)
);

CREATE TABLE ext.dimmedicoir (
	medico_ir_codigo VARCHAR(50) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	exequatur VARCHAR(50) NOT NULL, 
	medico_codigo VARCHAR(40), 
	especialidad_codigo VARCHAR(30), 
	territorio_codigo VARCHAR(40), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, medico_ir_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo), 
	FOREIGN KEY(especialidad_codigo) REFERENCES ext.dimespecialidad (especialidad_codigo), 
	FOREIGN KEY(pais_codigo, territorio_codigo) REFERENCES ext.dimterritorio (pais_codigo, territorio_codigo), 
	FOREIGN KEY(pais_codigo, medico_codigo) REFERENCES ext.dimmedico (pais_codigo, medico_codigo)
);

CREATE TABLE ext.dimperiodoir (
	periodo_codigo VARCHAR(20) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	anio INTEGER NOT NULL, 
	mes INTEGER NOT NULL, 
	fecha_inicio DATE NOT NULL, 
	fecha_fin DATE NOT NULL, 
	ciclo_codigo VARCHAR(20), 
	cerrado BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, periodo_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo), 
	FOREIGN KEY(pais_codigo, ciclo_codigo) REFERENCES ext.dimciclo (pais_codigo, ciclo_codigo)
);

CREATE TABLE ext.dimproducto (
	producto_codigo VARCHAR(50) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	linea_codigo VARCHAR(30), 
	presentacion VARCHAR(120), 
	codigo_closeup VARCHAR(50), 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, producto_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo), 
	FOREIGN KEY(pais_codigo, linea_codigo) REFERENCES ext.dimlinea (pais_codigo, linea_codigo)
);

CREATE TABLE ext.dimproductoir (
	producto_ir_codigo VARCHAR(50) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	laboratorio VARCHAR(150), 
	mercado_codigo VARCHAR(40), 
	molecula VARCHAR(200), 
	presentacion VARCHAR(120), 
	producto_codigo VARCHAR(50), 
	es_propio BOOLEAN NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, producto_ir_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo), 
	FOREIGN KEY(mercado_codigo) REFERENCES ext.dimmercadoir (mercado_codigo), 
	FOREIGN KEY(pais_codigo, producto_codigo) REFERENCES ext.dimproducto (pais_codigo, producto_codigo)
);

CREATE TABLE ext.dimrepresentante (
	rm_codigo VARCHAR(30) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	linea_codigo VARCHAR(30), 
	gerente_codigo VARCHAR(30), 
	nombre VARCHAR(150) NOT NULL, 
	cedula VARCHAR(30), 
	email VARCHAR(200), 
	zona VARCHAR(100), 
	fecha_ingreso DATE, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (pais_codigo, rm_codigo), 
	FOREIGN KEY(pais_codigo) REFERENCES ext.dimpais (pais_codigo), 
	FOREIGN KEY(pais_codigo, linea_codigo) REFERENCES ext.dimlinea (pais_codigo, linea_codigo), 
	FOREIGN KEY(pais_codigo, gerente_codigo) REFERENCES ext.dimgerente (pais_codigo, gerente_codigo)
);

CREATE TABLE ext.factevaluacionconocimiento (
	id BIGSERIAL NOT NULL, 
	lote_id BIGINT NOT NULL, 
	origen_id VARCHAR(60) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_codigo VARCHAR(20) NOT NULL, 
	rm_codigo VARCHAR(30) NOT NULL, 
	fecha_evaluacion DATE NOT NULL, 
	nota NUMERIC(10, 4) NOT NULL, 
	tema VARCHAR(200), 
	PRIMARY KEY (id), 
	FOREIGN KEY(lote_id) REFERENCES ext.controlcarga (lote_id), 
	FOREIGN KEY(pais_codigo, ciclo_codigo) REFERENCES ext.dimciclo (pais_codigo, ciclo_codigo), 
	FOREIGN KEY(pais_codigo, rm_codigo) REFERENCES ext.dimrepresentante (pais_codigo, rm_codigo)
);

CREATE TABLE ext.factprescripciondetalle (
	id BIGSERIAL NOT NULL, 
	lote_id BIGINT NOT NULL, 
	origen_id VARCHAR(60) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	periodo_codigo VARCHAR(20) NOT NULL, 
	producto_ir_codigo VARCHAR(50) NOT NULL, 
	mercado_codigo VARCHAR(40), 
	territorio_codigo VARCHAR(40), 
	medico_ir_codigo VARCHAR(50) NOT NULL, 
	rm_codigo VARCHAR(30), 
	unidades NUMERIC(14, 4) NOT NULL, 
	valor NUMERIC(18, 4), 
	version_fuente VARCHAR(30), 
	PRIMARY KEY (id), 
	FOREIGN KEY(lote_id) REFERENCES ext.controlcarga (lote_id), 
	FOREIGN KEY(pais_codigo, periodo_codigo) REFERENCES ext.dimperiodoir (pais_codigo, periodo_codigo), 
	FOREIGN KEY(pais_codigo, producto_ir_codigo) REFERENCES ext.dimproductoir (pais_codigo, producto_ir_codigo), 
	FOREIGN KEY(mercado_codigo) REFERENCES ext.dimmercadoir (mercado_codigo), 
	FOREIGN KEY(pais_codigo, territorio_codigo) REFERENCES ext.dimterritorio (pais_codigo, territorio_codigo), 
	FOREIGN KEY(pais_codigo, medico_ir_codigo) REFERENCES ext.dimmedicoir (pais_codigo, medico_ir_codigo), 
	FOREIGN KEY(pais_codigo, rm_codigo) REFERENCES ext.dimrepresentante (pais_codigo, rm_codigo)
);

CREATE TABLE ext.factventa (
	id BIGSERIAL NOT NULL, 
	lote_id BIGINT NOT NULL, 
	origen_id VARCHAR(60) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_codigo VARCHAR(20) NOT NULL, 
	rm_codigo VARCHAR(30) NOT NULL, 
	producto_codigo VARCHAR(50), 
	fecha DATE, 
	unidades NUMERIC(14, 4), 
	valor_venta NUMERIC(18, 4) NOT NULL, 
	cuota NUMERIC(18, 4) NOT NULL, 
	moneda VARCHAR(10), 
	PRIMARY KEY (id), 
	FOREIGN KEY(lote_id) REFERENCES ext.controlcarga (lote_id), 
	FOREIGN KEY(pais_codigo, ciclo_codigo) REFERENCES ext.dimciclo (pais_codigo, ciclo_codigo), 
	FOREIGN KEY(pais_codigo, rm_codigo) REFERENCES ext.dimrepresentante (pais_codigo, rm_codigo), 
	FOREIGN KEY(pais_codigo, producto_codigo) REFERENCES ext.dimproducto (pais_codigo, producto_codigo)
);

CREATE TABLE ext.factvisitafarmacia (
	id BIGSERIAL NOT NULL, 
	lote_id BIGINT NOT NULL, 
	origen_id VARCHAR(60) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_codigo VARCHAR(20) NOT NULL, 
	rm_codigo VARCHAR(30) NOT NULL, 
	farmacia_codigo VARCHAR(40) NOT NULL, 
	fecha_visita DATE NOT NULL, 
	ejecutada BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lote_id) REFERENCES ext.controlcarga (lote_id), 
	FOREIGN KEY(pais_codigo, ciclo_codigo) REFERENCES ext.dimciclo (pais_codigo, ciclo_codigo), 
	FOREIGN KEY(pais_codigo, rm_codigo) REFERENCES ext.dimrepresentante (pais_codigo, rm_codigo), 
	FOREIGN KEY(pais_codigo, farmacia_codigo) REFERENCES ext.dimfarmacia (pais_codigo, farmacia_codigo)
);

CREATE TABLE ext.factvisitamedico (
	id BIGSERIAL NOT NULL, 
	lote_id BIGINT NOT NULL, 
	origen_id VARCHAR(60) NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_codigo VARCHAR(20) NOT NULL, 
	rm_codigo VARCHAR(30) NOT NULL, 
	medico_codigo VARCHAR(40) NOT NULL, 
	fecha_visita DATE NOT NULL, 
	tipo_visita CHAR(1) NOT NULL, 
	ejecutada BOOLEAN NOT NULL, 
	acompanado BOOLEAN NOT NULL, 
	gerente_codigo VARCHAR(30), 
	causa_no_visita VARCHAR(80), 
	productos VARCHAR(300), 
	PRIMARY KEY (id), 
	FOREIGN KEY(lote_id) REFERENCES ext.controlcarga (lote_id), 
	FOREIGN KEY(pais_codigo, ciclo_codigo) REFERENCES ext.dimciclo (pais_codigo, ciclo_codigo), 
	FOREIGN KEY(pais_codigo, rm_codigo) REFERENCES ext.dimrepresentante (pais_codigo, rm_codigo), 
	FOREIGN KEY(pais_codigo, medico_codigo) REFERENCES ext.dimmedico (pais_codigo, medico_codigo), 
	FOREIGN KEY(pais_codigo, gerente_codigo) REFERENCES ext.dimgerente (pais_codigo, gerente_codigo)
);

CREATE TABLE ext.panelmedico (
	id BIGSERIAL NOT NULL, 
	lote_id BIGINT NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_codigo VARCHAR(20) NOT NULL, 
	rm_codigo VARCHAR(30) NOT NULL, 
	medico_codigo VARCHAR(40) NOT NULL, 
	frecuencia_objetivo CHAR(2) NOT NULL, 
	prioridad VARCHAR(10) NOT NULL, 
	categoria CHAR(1), 
	visitas_programadas INTEGER, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lote_id) REFERENCES ext.controlcarga (lote_id), 
	FOREIGN KEY(pais_codigo, ciclo_codigo) REFERENCES ext.dimciclo (pais_codigo, ciclo_codigo), 
	FOREIGN KEY(pais_codigo, rm_codigo) REFERENCES ext.dimrepresentante (pais_codigo, rm_codigo), 
	FOREIGN KEY(pais_codigo, medico_codigo) REFERENCES ext.dimmedico (pais_codigo, medico_codigo)
);

CREATE TABLE ext.targetfarmacia (
	id BIGSERIAL NOT NULL, 
	lote_id BIGINT NOT NULL, 
	pais_codigo VARCHAR(10) NOT NULL, 
	ciclo_codigo VARCHAR(20) NOT NULL, 
	rm_codigo VARCHAR(30) NOT NULL, 
	farmacia_codigo VARCHAR(40) NOT NULL, 
	visitas_programadas INTEGER, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lote_id) REFERENCES ext.controlcarga (lote_id), 
	FOREIGN KEY(pais_codigo, ciclo_codigo) REFERENCES ext.dimciclo (pais_codigo, ciclo_codigo), 
	FOREIGN KEY(pais_codigo, rm_codigo) REFERENCES ext.dimrepresentante (pais_codigo, rm_codigo), 
	FOREIGN KEY(pais_codigo, farmacia_codigo) REFERENCES ext.dimfarmacia (pais_codigo, farmacia_codigo)
);


-- --- Indices ---

CREATE UNIQUE INDEX ux_dm_exequatur ON ext.dimmedico (pais_codigo, exequatur) WHERE exequatur IS NOT NULL;

CREATE UNIQUE INDEX ux_dmir_exequatur ON ext.dimmedicoir (pais_codigo, exequatur);

CREATE UNIQUE INDEX ux_fec_origen ON ext.factevaluacionconocimiento (pais_codigo, origen_id);

CREATE INDEX ix_fp_periodo ON ext.factprescripciondetalle (pais_codigo, periodo_codigo);

CREATE UNIQUE INDEX ux_fp_origen ON ext.factprescripciondetalle (pais_codigo, origen_id);

CREATE INDEX ix_fv_ciclo_rm ON ext.factventa (pais_codigo, ciclo_codigo, rm_codigo);

CREATE UNIQUE INDEX ux_fv_origen ON ext.factventa (pais_codigo, origen_id);

CREATE UNIQUE INDEX ux_fvf_origen ON ext.factvisitafarmacia (pais_codigo, origen_id);

CREATE INDEX ix_fvm_ciclo_rm ON ext.factvisitamedico (pais_codigo, ciclo_codigo, rm_codigo);

CREATE INDEX ix_fvm_lote ON ext.factvisitamedico (lote_id);

CREATE UNIQUE INDEX ux_fvm_origen ON ext.factvisitamedico (pais_codigo, origen_id);

CREATE UNIQUE INDEX ux_tm_clave ON ext.panelmedico (pais_codigo, ciclo_codigo, rm_codigo, medico_codigo);

CREATE UNIQUE INDEX ux_tf_clave ON ext.targetfarmacia (pais_codigo, ciclo_codigo, rm_codigo, farmacia_codigo);


-- ===========================================================================
-- Usuario de integracion — ver crear_usuario_mallen.sql
-- ===========================================================================
