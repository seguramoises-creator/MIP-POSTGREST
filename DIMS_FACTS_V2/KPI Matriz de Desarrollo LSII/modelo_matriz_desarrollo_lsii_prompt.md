# Prompt 03 - Modulo Matriz de Desarrollo LSII

Actua como arquitecto de datos, analista senior de BI, desarrollador backend y consultor de liderazgo comercial con experiencia en SQL Server, Python, Excel, dashboards y diseno de modulos de evaluacion de colaboradores.

Necesito crear un tercer modulo separado llamado:

**Modulo de Matriz de Desarrollo LSII**

Este modulo debe convivir con los modulos anteriores:

1. Modulo de Categorizacion Medica
2. Modulo de Cobertura Predictiva
3. Modulo de Matriz de Desarrollo LSII

Debe mantenerse como modulo independiente, pero puede consumir informacion ya existente del sistema, especialmente:

- Pais
- Representante Medico / VM
- Gerente de Distrito / GD
- Linea
- Equipo
- Indicadores de desempeno
- Cobertura predictiva
- Productividad
- Cumplimiento
- Resultado territorial

No duplicar dimensiones si ya existen en los otros modulos.

## 1. Objetivo del modulo

El modulo debe ubicar visualmente a cada colaborador / VM en una matriz de dos ejes:

```text
Eje X = Receptividad / Compromiso
Eje Y = Desempeno / Competencia
```

El resultado debe permitir identificar:

- Nivel de desarrollo LSII: D1, D2, D3, D4
- Estilo de liderazgo sugerido:
  - Dirigir
  - Entrenar
  - Apoyar
  - Delegar
- Accion recomendada para el Gerente de Distrito

## 2. Logica general

La matriz cruza dos variables:

### A. Desempeno / Competencia

Debe venir de datos duros del sistema en escala de 0 a 100.

Puede construirse a partir de KPIs como:

- Cumplimiento
- Cobertura
- Frecuencia
- Productividad del contacto
- Cumplimiento de rutero
- Ejecucion promocional
- Resultado territorial
- Otros KPI duros disponibles

Para demo o MVP puede recibirse directamente:

```text
score_desempeno = 72
```

### B. Receptividad / Compromiso

Debe ser evaluada por el GD de forma conductual.

Regla importante:

El GD no debe colocar una nota numerica directa.

El GD solo debe seleccionar comportamientos observables.

El sistema internamente asigna un puntaje oculto.

Esto evita sesgos y evita evaluaciones directas tipo:

```text
Este colaborador tiene 8/10 en compromiso.
```

## 3. Dimensiones de receptividad

La receptividad se compone de 5 dimensiones:

1. Acepta nuevas responsabilidades
2. Interaccion con Gte./Coordinador
3. Interaccion con companeros
4. Motivacion
5. Modificacion de comportamientos sugeridos

Cada dimension tiene:

- 5 opciones conductuales
- score oculto de 1 a 5
- peso sugerido de 0.20

```text
weight = 0.20
```

## 4. Tabla DIMS_RECEPTIVIDAD

Crear una tabla de parametros conductuales:

```text
DIMS_RECEPTIVIDAD
```

Campos requeridos:

- dim_id
- variable
- dimension
- dimension_desc
- option_id
- behavior_text
- score_hidden
- weight
- sort_order_dim
- sort_order_option
- is_active

Esta tabla debe cargarse desde Excel o desde un CSV usando Python.

### Opciones por dimension

#### REC_01 - Acepta nuevas responsabilidades

Descripcion:

Evalua la disposicion del colaborador para asumir nuevos retos, tareas o responsabilidades.

Opciones:

- REC_01_05: Asume nuevas responsabilidades con iniciativa, autonomia y actitud positiva. Score 5.
- REC_01_04: Acepta nuevas responsabilidades con buena disposicion y poca resistencia. Score 4.
- REC_01_03: Acepta algunas responsabilidades pero requiere apoyo, claridad o seguimiento. Score 3.
- REC_01_02: Acepta responsabilidades solo cuando se le insiste o se le da seguimiento cercano. Score 2.
- REC_01_01: Evita, rechaza o posterga nuevas responsabilidades. Score 1.

#### REC_02 - Interaccion con Gte./Coordinador

Descripcion:

Evalua la apertura del colaborador frente al seguimiento, feedback, direccion y acompanamiento del gerente.

Opciones:

- REC_02_05: Busca activamente orientacion, recibe feedback con apertura y mantiene comunicacion fluida. Score 5.
- REC_02_04: Mantiene buena comunicacion y responde positivamente al seguimiento del gerente. Score 4.
- REC_02_03: Interactua de forma funcional aunque su apertura al feedback puede variar. Score 3.
- REC_02_02: Se comunica solo cuando es necesario y requiere seguimiento frecuente. Score 2.
- REC_02_01: Evita la interaccion, se muestra cerrado o defensivo ante el seguimiento. Score 1.

#### REC_03 - Interaccion con companeros

Descripcion:

Evalua la colaboracion, integracion y disposicion del colaborador para aportar al equipo.

Opciones:

- REC_03_05: Colabora activamente, comparte buenas practicas y aporta positivamente al equipo. Score 5.
- REC_03_04: Mantiene buena relacion con sus companeros y coopera cuando se le solicita. Score 4.
- REC_03_03: Se integra de manera adecuada aunque su participacion en el equipo es limitada. Score 3.
- REC_03_02: Participa poco o muestra baja disposicion a colaborar con sus companeros. Score 2.
- REC_03_01: Genera friccion, se aisla o afecta negativamente la dinamica del equipo. Score 1.

#### REC_04 - Motivacion

Descripcion:

Evalua energia, disposicion, iniciativa y actitud frente al rol comercial.

Opciones:

- REC_04_05: Muestra alta energia, iniciativa y deseo claro de mejorar sus resultados. Score 5.
- REC_04_04: Mantiene buena disposicion y actitud positiva frente a sus objetivos. Score 4.
- REC_04_03: Su motivacion es variable segun los resultados, la presion o el contexto. Score 3.
- REC_04_02: Muestra baja energia y requiere estimulo frecuente para accionar. Score 2.
- REC_04_01: Evidencia desinteres, apatia o actitud negativa frente al rol. Score 1.

#### REC_05 - Modificacion de comportamientos sugeridos

Descripcion:

Evalua si el colaborador aplica y sostiene cambios conductuales sugeridos por el gerente.

Opciones:

- REC_05_05: Aplica rapidamente los comportamientos sugeridos y los sostiene en el tiempo. Score 5.
- REC_05_04: Aplica los ajustes sugeridos con buena consistencia. Score 4.
- REC_05_03: Aplica algunos ajustes pero de forma irregular. Score 3.
- REC_05_02: Aplica cambios solo cuando el gerente da seguimiento cercano. Score 2.
- REC_05_01: No modifica comportamientos aunque reciba feedback o coaching. Score 1.

## 5. Calculo de receptividad

El formulario debe guardar las `option_id` seleccionadas por el GD.

Ejemplo:

```python
selected_option_ids = [
    "REC_01_04",
    "REC_02_04",
    "REC_03_03",
    "REC_04_04",
    "REC_05_04",
]
```

El sistema debe buscar el `score_hidden` y calcular:

```text
score_total = SUM(score_hidden * weight)
max_score_total = SUM(5 * weight)
score_receptividad = ROUND((score_total / max_score_total) * 100, 2)
```

Clasificacion:

```text
score_receptividad >= 80 => Alta
score_receptividad >= 60 y < 80 => Media
score_receptividad < 60 => Baja
```

Si no hay datos:

```text
nivel_receptividad = "Sin datos"
```

## 6. Clasificacion de desempeno

El `score_desempeno` debe venir del sistema en escala 0 a 100.

Regla MVP:

```text
score_desempeno >= 80 => Alto
score_desempeno < 80 => Bajo
```

El punto de corte de 80 debe quedar parametrizable.

## 7. Regla LSII

Cruce de variables:

```text
Desempeno / Competencia
Receptividad / Compromiso
```

Reglas:

| Desempeno | Receptividad | Nivel LSII | Liderazgo sugerido |
|---|---|---|---|
| Bajo | Alta | D1 | Dirigir |
| Bajo | Media o Baja | D2 | Entrenar |
| Alto | Media o Baja | D3 | Apoyar |
| Alto | Alta | D4 | Delegar |

Acciones recomendadas:

### D1 - Dirigir

Dar estructura clara, objetivos especificos, seguimiento cercano y guia paso a paso.

### D2 - Entrenar

Acompanamiento cercano, explicar el por que, reforzar habilidades y sostener motivacion.

### D3 - Apoyar

Escuchar barreras, reforzar confianza, involucrar al colaborador y acordar proximos pasos.

### D4 - Delegar

Dar autonomia, empoderar, definir resultados esperados y monitorear por hitos.

## 8. Visual esperado

El resultado no debe verse solo como tabla.

Debe verse como una matriz visual tipo Coaching Plan.

Ejes:

```text
X = Receptividad / Compromiso
Y = Desempeno / Competencia
```

Ambos ejes deben ir de 0 a 100.

Cortes:

```text
Corte X = 80
Corte Y = 80
```

Cuadrantes:

| Ubicacion | Condicion | Nivel LSII | Liderazgo |
|---|---|---|---|
| Abajo derecha | Bajo desempeno + alta receptividad | D1 | Dirigir |
| Abajo izquierda | Bajo desempeno + baja/media receptividad | D2 | Entrenar |
| Arriba izquierda | Alto desempeno + baja/media receptividad | D3 | Apoyar |
| Arriba derecha | Alto desempeno + alta receptividad | D4 | Delegar |

## 9. Dataset demo para matriz visual

Crear una tabla demo:

```text
LSII_VM_MATRIX_DATA
```

Campos:

- vm_id
- vm_name
- gd
- linea
- pais_codigo
- score_desempeno
- score_receptividad
- nivel_desempeno
- nivel_receptividad
- nivel_lsii
- liderazgo_sugerido
- accion_recomendada

Datos ejemplo:

| vm_id | vm_name | score_desempeno | score_receptividad | nivel_lsii | liderazgo |
|---|---|---:|---:|---|---|
| VM_001 | Juan Perez | 72 | 76 | D2 | Entrenar |
| VM_002 | Maria Gomez | 58 | 88 | D1 | Dirigir |
| VM_003 | Carlos Ruiz | 86 | 64 | D3 | Apoyar |
| VM_004 | Laura Mendez | 91 | 90 | D4 | Delegar |
| VM_005 | Pedro Castillo | 67 | 91 | D1 | Dirigir |
| VM_006 | Ana Torres | 84 | 72 | D3 | Apoyar |

## 10. Reglas de interfaz

Pantalla del GD:

1. Mostrar las 5 dimensiones.
2. Cada dimension debe mostrar sus 5 comportamientos visibles.
3. El GD selecciona 1 comportamiento por dimension.
4. El GD no debe ver:
   - score oculto
   - peso
   - score numerico por comportamiento
5. El sistema si debe guardar:
   - colaborador evaluado
   - dimension
   - option_id seleccionada
   - score_hidden interno
   - score total de receptividad
   - nivel LSII resultante
   - liderazgo sugerido

## 11. Resultado esperado individual

Ejemplo:

```text
Colaborador: Juan Perez
Desempeno / Competencia: 72
Receptividad / Compromiso: Media
Nivel de desarrollo LSII: D2
Estilo de liderazgo sugerido: Entrenar
Accion sugerida: Acompanamiento cercano, explicar el por que, reforzar habilidades y sostener motivacion.
```

Ademas de este detalle individual, debe mostrarse la matriz general donde todos los VM aparezcan ubicados visualmente.

## 12. Estructura SQL Server esperada

Crear el modulo separado con schema sugerido:

```text
lsii
```

Tablas sugeridas:

### lsii.DimsReceptividad

Equivalente a `DIMS_RECEPTIVIDAD`.

Campos:

- ReceptividadDimKey
- DimId
- Variable
- Dimension
- DimensionDesc
- OptionId
- BehaviorText
- ScoreHidden
- Weight
- SortOrderDim
- SortOrderOption
- IsActive

### lsii.DimParametroLSII

Campos:

- ParametroKey
- CodigoParametro
- ValorNumerico
- ValorTexto
- Descripcion
- Activo

Parametros minimos:

- CORTE_DESEMPENO_ALTO = 80
- CORTE_RECEPTIVIDAD_ALTA = 80
- CORTE_RECEPTIVIDAD_MEDIA = 60

### lsii.FactEvaluacionReceptividad

Una fila por evaluacion del GD a un colaborador/VM.

Campos:

- EvaluacionKey
- FechaEvaluacion
- PaisKey
- RepresentanteKey
- GerenteKey o GD
- CicloKey opcional
- EvaluadorUsuario
- EstadoEvaluacion
- ScoreReceptividad
- NivelReceptividad

### lsii.FactEvaluacionReceptividadDetalle

Una fila por dimension evaluada.

Campos:

- EvaluacionDetalleKey
- EvaluacionKey
- DimId
- OptionId
- ScoreHidden
- Weight
- ScorePonderado

### lsii.FactScoreDesempenoVM

Score duro del sistema.

Campos:

- ScoreDesempenoKey
- FechaCorte
- PaisKey
- RepresentanteKey
- CicloKey opcional
- ScoreDesempeno
- FuenteScore
- CumplimientoPct
- CoberturaPct
- ProductividadPct
- FrecuenciaPct
- RuteroPct

### lsii.FactResultadoLSII

Resultado final.

Campos:

- ResultadoLSIIKey
- FechaCorte
- PaisKey
- RepresentanteKey
- ScoreDesempeno
- NivelDesempeno
- ScoreReceptividad
- NivelReceptividad
- NivelLSII
- LiderazgoSugerido
- AccionRecomendada
- CuadranteX
- CuadranteY

## 13. Integracion con modulos existentes

Debe consumir:

### Desde Categorizacion Medica

- `cat.DimPais`
- `cat.DimRepresentanteMedico`
- `cat.DimEquipo`
- `cat.DimMedico`, si aplica
- categoria medica A/B/C/D, si se quiere enriquecer el perfil

### Desde Cobertura Predictiva

- cobertura actual
- cobertura proyectada
- contactos realizados
- productividad
- cumplimiento de meta

Estos indicadores pueden alimentar `score_desempeno`.

## 14. Python esperado

Crear o proponer un loader:

```text
cargar_matriz_desarrollo_lsii_excel_sqlserver.py
```

Debe:

1. Cargar `DIMS_RECEPTIVIDAD`.
2. Cargar respuestas del formulario conductual.
3. Calcular `score_receptividad`.
4. Leer o recibir `score_desempeno`.
5. Calcular LSII.
6. Guardar resultado en SQL Server.
7. Generar dataset para matriz visual.

Funciones minimas:

- `calcular_receptividad(selected_option_ids, dims_df)`
- `clasificar_desempeno(score_desempeno)`
- `clasificar_lsii(score_desempeno, score_receptividad)`

## 15. Vista para dashboard

Crear una vista:

```text
lsii.vwMatrizDesarrolloLSII
```

Campos:

- pais_codigo
- fecha_corte
- gd
- vm_id
- vm_name
- linea
- score_desempeno
- nivel_desempeno
- score_receptividad
- nivel_receptividad
- nivel_lsii
- liderazgo_sugerido
- accion_recomendada
- x_receptividad
- y_desempeno

Esta vista debe servir para una visual tipo scatter plot.

## 16. Visualizacion esperada

El frontend debe mostrar:

1. Matriz 2x2 con ejes 0 a 100.
2. Linea vertical en X=80.
3. Linea horizontal en Y=80.
4. Cada VM como punto.
5. Color por nivel LSII.
6. Tooltip con:
   - VM
   - GD
   - score desempeno
   - score receptividad
   - nivel LSII
   - liderazgo sugerido
   - accion recomendada

## 17. Criterios de aceptacion

El modulo sera correcto si:

1. El GD nunca ve el score oculto por comportamiento.
2. El GD selecciona exactamente 1 comportamiento por dimension.
3. El sistema calcula receptividad de 0 a 100.
4. El desempeno viene de datos duros o de un score ya calculado.
5. El punto de corte de desempeno y receptividad es parametrizable.
6. El resultado clasifica correctamente D1, D2, D3 o D4.
7. El liderazgo sugerido coincide con el nivel LSII.
8. La matriz visual ubica cada VM segun X=receptividad y Y=desempeno.
9. El modulo queda separado de Categorizacion Medica y Cobertura Predictiva.
10. El modulo puede consumir indicadores existentes sin duplicar dimensiones.

## 18. Entregables esperados

La respuesta debe producir:

1. Excel de estructura del modulo LSII.
2. SQL Server DDL del schema `lsii`.
3. Procedimientos o vistas para calcular LSII.
4. Python loader y funciones de calculo.
5. Guia funcional y tecnica.
6. Prompt/documento separado del modulo.

Nombrar los archivos con el prefijo:

```text
modelo_matriz_desarrollo_lsii
```

Mantener todo en una carpeta separada:

```text
modulo_matriz_desarrollo_lsii
```
