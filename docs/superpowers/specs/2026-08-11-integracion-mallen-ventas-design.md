# Integración de Ventas (Mallén) — Diseño

**Fecha:** 2026-08-11
**Sub-proyecto:** 5 de la integración VISTA ↔ Laboratorio Mallén
**Estado:** aprobado, pendiente de plan

## 1. Por qué existe

El §7.2 del requerimiento encarga a VISTA el módulo **Venta**: *"lectura del detalle con su cuota; cálculo de cumplimiento **e ingresos del ROI**"*, sustituyendo la carga de Excel de ventas.

Hoy `ext.factventa` **solo se valida**: `integracion_validacion_service` comprueba que llegó y cuadra los conteos, pero nadie la promueve a las tablas internas. Eso deja dos huecos:

- El indicador **`VENTAS`** (15% del Score) no se calcula desde Mallén.
- El **ROI del módulo de Visita** lee `DW.FACT_Ventas`, que sin el Excel se queda vacía — el ROI mostraría ingresos cero.

## 2. Origen y destino — la granularidad NO coincide

| | `ext.factventa` | `DW.FACT_Ventas` |
|---|---|---|
| Grano | **detalle**, con `producto_codigo` **opcional** | **una fila por país+línea+RM+ciclo** |
| Clave | `origen_id` único por país | **ninguna** (solo el `id` autoincrement) |
| Trae | `valor_venta`, `cuota`, `unidades`, `fecha`, `moneda` | `ventas_reales`, `cuota`, `cumplimiento_pct`, `crecimiento_pct`, `puntaje` |

**El integrador agrega**: agrupa por `(pais_codigo, ciclo_codigo, rm_codigo)` y suma `valor_venta` y `cuota`. El detalle por producto se descarta — `FACT_Ventas` no tiene dónde ponerlo y ningún consumidor lo pide. Las filas con `producto_codigo` nulo y las que lo traen se agrupan igual: para este grano, el producto es irrelevante.

**`linea_id` sale de `rm.linea_id`**, nunca del producto. `Config.DIM_Producto.linea_id` es nullable y el hecho puede llegar sin producto; el RM interno siempre tiene línea (`NOT NULL`). Es el mismo criterio que ya usa `integracion_indicadores_service`.

`ventas_reales`, `cuota`, `linea_id`, `rm_id`, `ciclo_id` y `pais_codigo` son los seis campos que se escriben. `crecimiento_pct` queda nulo: el contrato no envía el período anterior.

## 3. Idempotencia — la tabla no tiene llave natural

`DW.FACT_Ventas` es **la única tabla del ecosistema de integración sin ningún `UniqueConstraint`**. Re-integrar un ciclo duplicaría filas, y como el ROI **suma** `ventas_reales`, cada reintento inflaría los ingresos con dinero inexistente. Un reproceso rutinario corrompería el indicador financiero sin que nada avisara.

Se resuelve con el patrón ya establecido: **entidad nueva `ENT_VENTAS_RM_CICLO`** en `Config.MapeoExterno`, con `codigo_externo = f"{ciclo_codigo}/{rm_codigo}"` y `buscar_natural` por `(pais_codigo, ciclo_id, rm_id)`.

**Entidad nueva y no reutilizada**, por la misma razón documentada en `integracion_visitas_service`: `MapeoExterno` es único por `(entidad, país, código)` con un solo `id_interno`; compartir entidad entre dos destinos físicos corrompe el mapeo.

**Beneficio directo**: en producción hay **9 filas legacy** en `FACT_Ventas` (un país, un ciclo, cargadas por el ETL de Excel el 1-jul-2026). Como `resolver` **adopta por clave natural** antes de crear, esas filas se actualizan con el dato de Mallén en vez de duplicarse. No hay que borrarlas ni migrarlas a mano.

## 4. La cuota — se suma, pero se avisa

**Decisión del cliente (11-ago-2026):** se **suman** las cuotas del RM/ciclo, que es la lectura literal del contrato.

Pero hay un riesgo real: muchos ERP repiten **la cuota total del representante en cada fila de producto** en vez de repartirla. Con ese patrón, sumar la multiplica por el número de productos, el cumplimiento de **todos** los representantes se desploma, y nada lo delata — el número simplemente sale bajo.

Por eso el integrador **detecta la firma de ese patrón**: si un `(rm, ciclo)` tiene **más de una fila** y **todas** traen exactamente la misma `cuota`, emite un `Hallazgo` de severidad **aviso** diciendo que la cuota parece repetida y que el total podría estar multiplicado. **No cambia el cálculo** — sumar sigue siendo lo que hace — pero el operador se entera en la misma pantalla de integración, no tres meses después.

No se adivina ni se corrige automáticamente: adivinar aquí sería peor que el error, porque haría el número impredecible.

## 5. El indicador `VENTAS`

`VENTAS` tiene **`escala = 1`** en la base (verificado en producción), así que el motor multiplica por 100. **`resultado_real` se escribe como FRACCIÓN 0-1**, igual que los cuatro indicadores de visita.

> Es exactamente la trampa que ya costó una corrección en el sub-proyecto 3: escribir `88.0` queriendo decir 88% produce `8800`, que el motor acota a 100 → puntuación perfecta. La regla vuelve a aplicar: **el test debe atravesar `completar_puntajes` y afirmar sobre `puntos_obtenidos`**, no sobre `resultado_real`.

```
VENTAS = ventas_reales / cuota
```

Acotado **por abajo a 0** (una venta negativa por devoluciones no resta cumplimiento), **sin acotar por arriba**: el motor ya limita a 100 y sobrecumplir debe verse en el dato crudo.

**Si `cuota` es nula o cero, NO se escribe la fila** y se emite hallazgo `aviso`. Dividir por cero no es "cumplimiento cero": es ausencia de meta, y escribir un 0 penalizaría a un representante al que nadie le fijó cuota. Misma regla que el universo vacío de las coberturas.

El cálculo vive en `integracion_indicadores_service`, junto a los otros cuatro, y respeta lo que ya tiene: gate de estado del lote, guard de ciclo cerrado, y delete-then-insert acotado al código y al `(rm_id, ciclo_id)`.

`puntaje` y `cumplimiento_pct` de `FACT_Ventas` se rellenan con el criterio del ETL legacy (`calcular_cumplimiento` acotado a `[0,100]`), para no dejar la tabla a medias — pero **el Score no los usa**: su camino es `FACT_ResultadoIndicador`.

## 6. El ROI mezcla países — se arregla aquí

`visita_costo_service` calcula los ingresos filtrando **solo por `ciclo_id`**:

```python
iq = db.query(func.coalesce(func.sum(Ventas.ventas_reales), 0)).filter(Ventas.ciclo_id == ciclo_id)
```

Los ciclos son globales, no por país. Hoy no se nota porque las 9 filas existentes son de un solo país; **en cuanto Mallén integre un segundo país contra el mismo ciclo, el ROI de uno incluiría los ingresos del otro**.

**Decisión del cliente: se arregla en este trabajo.** Añadir el filtro por `pais_codigo` (y por los RM del alcance donde ya se filtra por `vm_id`). Es un cambio pequeño, con test, y este módulo es precisamente lo que activa el defecto: desplegarlo sabiendo que dará cifras falsas no es una opción.

## 7. Fuera de alcance (YAGNI)

- **Prescripciones IR y Conocimientos**: sub-proyectos aparte. `EVO_IR` además tiene `escala = 100` (verificado), así que su unidad es distinta — no copiar este módulo sin mirar.
- **El detalle por producto**: no se guarda. Si algún día se quiere, necesita tabla propia; `FACT_Ventas` no es el sitio.
- **`crecimiento_pct`**: el contrato no envía el período anterior. Queda nulo.
- **Reactivar `comercial.py`**: sigue siendo código muerto no registrado.
- **Tocar `motor_calculo_service`, `recalculo_service`, `cobertura_predictiva_service`, `cobertura_farmacia_service`** ni el esquema `ext`.
- **Migración**: este sub-proyecto **no lleva ninguna**. `MapeoExterno` ya existe y la entidad nueva es solo una constante.

## 8. Verificación

**Integración**
1. Tres filas de `ext.factventa` del mismo RM/ciclo con productos distintos → **una** fila en `FACT_Ventas` con `ventas_reales` sumadas.
2. Una fila con `producto_codigo` nulo se agrega igual que las que lo traen.
3. `linea_id` es el del RM, aunque el producto tenga otra línea o ninguna.
4. **Re-integrar el mismo ciclo NO duplica**: sigue habiendo una fila y `ventas_reales` no se dobla. Es el test que justifica el mapeo.
5. Una fila legacy preexistente (sin mapeo) se **adopta**: mismo `id`, valores actualizados.
6. Filas de un lote no `VALIDADO` se omiten con hallazgo.
7. Un RM sin mapeo se omite con hallazgo y el resto entra.

**La cuota**
8. Dos filas del mismo RM con cuotas **distintas** → se suman, **sin** hallazgo.
9. Dos filas del mismo RM con la **misma** cuota → se suman igual, **con** hallazgo `aviso`. Es el test que documenta la trampa del ERP.
10. Una sola fila con su cuota → sin hallazgo (una fila nunca dispara la sospecha).

**El indicador**
11. Ventas 88, cuota 100 → `resultado_real = 0.88`; tras `completar_puntajes`, `resultado_porcentaje = 88` y los puntos son el 88% de la ponderación. **Es el test que atraviesa el motor**, el que faltó en el sub-proyecto 3.
12. Sobrecumplimiento (ventas 120, cuota 100) → `resultado_real = 1.2`, y el motor lo acota a 100 al puntuar.
13. Venta negativa → `resultado_real = 0`, nunca negativo.
14. `cuota = 0` o nula → **no se escribe la fila** y hay hallazgo `aviso`.
15. Recalcular no duplica y no toca los otros indicadores del ciclo.
16. Ciclo cerrado → no se escribe nada.

**El ROI**
17. Dos países con ventas en el **mismo ciclo** → el ROI de cada uno cuenta **solo las suyas**. Contra el código actual este test falla; es la prueba del arreglo.
18. El ROI de un `vm_id` concreto sigue devolviendo lo mismo que antes del cambio (sin regresión).
