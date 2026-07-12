# Guia del modelo de categorizacion medica

## Version actual

Esta guia corresponde al Excel `modelo_sqlserver_categorizacion_medica_excel.xlsx` ajustado con las hojas actuales:

- `DIM_PAIS`
- `DimComponente`
- `DimClasificacion`
- `DimRegla`
- `DimEquipo`
- `DIM_REPRESENTANTE_MEDICO`
- `DimEspecialidad`
- `DimCentroMedico`
- `DimGeografia`
- `FactMedicoInput`

## Correccion aplicada

Se corrigio el codigo de Republica Dominicana en `DIM_PAIS` de `RD` a `DO`, porque las demas hojas usan `pais_codigo = DO`. Esto evita errores de llaves foraneas y de busqueda durante la carga.

## Logica de calculo

Cada componente recibe un criterio de 1 a 5. El puntaje del componente se calcula como:

```text
PuntajeComponente = Criterio / 5 * PesoComponente
```

Componentes:

| CodigoComponente | Peso |
|---|---:|
| PACIENTES_SEMANA | 30% |
| PODER_ADQUISITIVO | 20% |
| POTENCIAL_PRESCRIPCION | 10% |
| UBICACION_TERRITORIAL_CM | 30% |
| KOL | 10% |

La categoria final sale de `DimClasificacion`.

## Estructura SQL Server

Schemas:

- `cat`: modelo final, dimensiones, facts y procedimiento de calculo.
- `stg`: staging de entrada desde Excel.

Tablas principales:

- `cat.DimPais`
- `cat.DimComponenteCategoria`
- `cat.DimClasificacionMedica`
- `cat.DimReglaCategoriaMedica`
- `cat.DimEquipo`
- `cat.DimRepresentanteMedico`
- `cat.DimEspecialidad`
- `cat.DimCentroMedico`
- `cat.DimGeografia`
- `cat.DimMedico`
- `stg.MedicoCategoriaInput`
- `cat.FactMedicoCategoriaSnapshot`
- `cat.FactMedicoCategoriaDetalle`

## Orden de carga

1. Ejecutar `modelo_sqlserver_categorizacion_medica.sql`.
2. Ejecutar `cargar_categorizacion_medica_excel_sqlserver.py`.
3. El Python hace `MERGE` de catalogos.
4. El Python carga `FactMedicoInput` en staging.
5. SQL Server ejecuta `cat.sp_CalcularCategoriaMedica`.
6. Revisar resultados en `cat.vwMedicoCategoriaConciliacion`.

## Nota tecnica importante

`FactMedicoInput` tiene formulas en `Equipo` y `linea_id`. El cargador Python usa `openpyxl` con `data_only=True` para leer los valores calculados, no el texto de la formula.

Si el archivo se edita fuera de Excel y las formulas no quedan recalculadas, abre y guarda el Excel antes de cargarlo a SQL Server.
