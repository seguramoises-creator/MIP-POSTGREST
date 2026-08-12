# Equivalencias de Prescripción IR y diagnóstico de enlazabilidad — Diseño

**Fecha:** 2026-08-11
**Sub-proyecto:** 6 de la integración VISTA ↔ Laboratorio Mallén
**Estado:** aprobado, pendiente de plan

## 1. Por qué existe

El §7.2 del requerimiento encarga a VISTA el módulo **Prescripción (IR)**: *"lectura del detalle y sus cinco dimensiones; equivalencia de producto y de médico prescriptor, y cálculo de la evolución"*. Es el único módulo cuya casilla "Reemplaza a" dice *"Nada: es desarrollo nuevo"*.

Este sub-proyecto construye **la equivalencia**, no la evolución. La razón está en el §2.

## 2. Por qué el indicador NO entra todavía

El propio requerimiento aparta este módulo de los demás, en tres lugares:

- **§10, pendiente 1** — *"Definición del indicador IR y formato real del archivo de Close-Up"*, responsable **Laboratorio Mallén**, y lo que se ajusta es *"la estructura de FactPrescripcion, hoy preliminar"*.
- **§10, pendiente 6** — si Close-Up entrega el exequátur del prescriptor y si está informado en el maestro de médicos de Mallén.
- **§11.9** — *"La definición del indicador IR. Es el único módulo cuya estructura todavía puede cambiar"*, y sobre el exequátur: *"conviene verificarla con una muestra real antes de desarrollar: si no coincide, el IR se calcula pero no se puede atribuir"*.

Construir el indicador ahora sería construir contra una estructura que el cliente se reservó por escrito el derecho de cambiar, y sobre una llave de atribución que el documento manda comprobar **antes** de desarrollar. Este sub-proyecto produce justamente esa comprobación.

**La fórmula, en cambio, ya es deducible** y conviene dejarla escrita para que nadie la reinvente mal. En producción (11-ago-2026, país DO):

| Indicador | `escala` | `ponderacion_pct` | `tipo_periodo` | filas | mín | máx | promedio |
|---|---|---|---|---|---|---|---|
| `EVO_IR` | **100** | 20 | CICLO | 175 | 22 | 248 | 110 |
| `VENTAS` | 1 | 15 | MES | 176 | 0.47 | 1.25 | 0.97 |

`EVO_IR` es un **índice centrado en 100** — 100 significa "igual que el período anterior", no "cumplió el 100% de una meta". Su unidad es la contraria a la de `VENTAS`, que va como fracción 0-1. Copiar el módulo de Ventas sin mirar esto produciría el error de unidades que ya costó una corrección en el sub-proyecto 3.

## 3. Los tres puentes

`ext` trae cinco dimensiones IR y **ninguna tiene contraparte interna**: no existe `DIM_PeriodoIR`, `DIM_MercadoIR`, `DIM_ProductoIR`, `DIM_MedicoIR` ni `DIM_Territorio`. Crearlas sería levantar cinco catálogos que ninguna pantalla muestra.

Lo que el §7.2 encarga no es copiarlas, sino **la equivalencia**. Se resuelve con tres entidades nuevas de `Config.MapeoExterno` — mismo patrón, ninguna tabla nueva, **sin migración**:

| Entidad | De `ext` | Hacia | Para qué |
|---|---|---|---|
| `medico_ir` | `dimmedicoir.exequatur` | `Config.DIM_Medico` | lleva la receta al panel del representante |
| `producto_ir` | `dimproductoir.producto_codigo` | `Config.DIM_Producto` | separa producto propio de competencia y aporta la línea |
| `periodo_ir` | `dimperiodoir.ciclo_codigo` | `Config.DIM_Ciclo` | convierte el mes de Close-Up en ciclo |

`dimmercadoir` y `dimterritorio` **no se sincronizan**: sin contraparte interna y sin consumidor, mapearlas sería trabajo especulativo. Siguen disponibles en `ext` el día que existan tableros de mercado.

### 3.1 El prescriptor NO crea médicos

Es la decisión más importante del sub-proyecto, y es deliberadamente distinta de las otras nueve dimensiones, que sí crean el registro interno cuando no existe.

`sincronizar_medico_ir` **solo enlaza**: busca el exequátur en `Config.DIM_Medico` y, si no está, no lo inventa. Cuenta la fila como no enlazable y la reporta.

El maestro de médicos es país-level y alimenta paneles, categorización y cobertura. Un prescriptor que solo existe en Close-Up y que ningún representante trabaja entraría como médico del universo de VISTA y contaminaría esos denominadores — el mismo daño silencioso que la cobertura ya sufrió una vez. Y el §3.2 del requerimiento lo dice de frente: *una receta cuyo prescriptor no se pueda enlazar se cuenta para el mercado pero no se atribuye a ningún representante*.

El emparejamiento **reutiliza `maestro_medico_service._resolver_por_llave_dura`**, que es el criterio con el que el maestro decide si dos médicos son el mismo. Ese criterio compara el exequátur **exacto** (a diferencia del nombre, que sí normaliza), y filtra por país y `activo`.

No se inventa una normalización propia del exequátur, aunque subiría la tasa de enlace. Es la lección del sub-proyecto 2 en su forma inversa: un criterio privado enlazaría como el mismo médico a dos que la deduplicación del maestro considera distintos, y el desacuerdo solo se descubriría cuando las cifras no cuadraran. Si Close-Up envía `12.345` donde el maestro tiene `12345`, eso **no es un enlace**: es un dato que hay que arreglar en el origen, y el trabajo del diagnóstico es sacarlo a la luz, no taparlo.

Para que sea accionable, el diagnóstico distingue dos clases de no-enlace: el **huérfano real** (ese exequátur no existe en el maestro de ninguna forma) y el **casi-enlace** (existe uno que solo difiere en mayúsculas, espacios o signos de puntuación). El casi-enlace **no se enlaza** — solo se cuenta y se muestra, porque convierte "no cruzan 400 médicos" en "380 no existen y 20 están mal escritos", que son dos conversaciones distintas con Mallén.

### 3.4 Los prescriptores no enlazados se CUENTAN, no se reportan uno a uno

`dimmedicoir` trae el universo de Close-Up, que es **todo el mercado**: el §9.1 dimensiona unos 10.000 médicos. Que la mayoría no esté en el panel de nadie es lo normal, no una anomalía.

Por eso el sincronizador **no emite un `Hallazgo` por prescriptor no enlazado**. Los cuenta, y el diagnóstico los muestra con una muestra de ejemplos. Emitir uno por fila produciría miles de líneas en la pantalla de hallazgos, y una lista que nadie puede leer es una lista que nadie lee: enterraría los pocos hallazgos que sí exigen acción.

Los `Hallazgo` quedan reservados para lo acotado y accionable, que vive en catálogos de decenas de filas, no de miles:
- producto `es_propio = true` sin equivalencia → **error**;
- período sin `ciclo_codigo` → **aviso**;
- exequátur duplicado en el maestro (dos médicos con el mismo) → **error**, porque impide decidir a cuál enlazar y es un defecto del maestro, no de Close-Up.

### 3.2 Los productos de la competencia no son un error

`dimproductoir` incluye a propósito productos de otros laboratorios, con la equivalencia vacía, porque hacen falta para medir participación de mercado (§11.8). Que no mapeen es lo esperado, y **no genera hallazgo**.

Lo que sí es hallazgo —de severidad error— es un producto marcado `es_propio = true` cuyo `producto_codigo` no cruza con `Config.DIM_Producto`: ahí hay un producto de Mallén cuyas recetas nadie va a poder contar.

### 3.3 El período sin ciclo

Si `dimperiodoir.ciclo_codigo` viene nulo, ese mes de Close-Up no pertenece a ningún ciclo y sus recetas no se pueden ubicar en el tiempo de VISTA. Se emite aviso y no se mapea. No se adivina el ciclo por fechas: `dimperiodoir` ya trae `fecha_inicio`/`fecha_fin`, pero derivar la pertenencia de ahí sustituiría una decisión de Mallén por una inferencia nuestra, y un mes puede solapar dos ciclos.

## 4. La cadena de atribución

Se define aquí, la ejercita el diagnóstico y la reutiliza el indicador en el sub-proyecto siguiente. Para cada fila de `ext.factprescripciondetalle`:

1. **Si `rm_codigo` viene informado**, ese es el representante: Mallén ya atribuyó y su decisión manda.
2. **Si no**, exequátur → `DIM_Medico` → filas de `Visita.DIM_MedicoVisita` con ese `maestro_medico_id` → candidatos (su `vm_id` es el representante).
3. **Se filtran por pertenencia al panel EN EL CICLO de la receta**, reutilizando `visita_aprobacion_service.cuenta_en_ciclo(m, ciclo_orden, ordenes)` — el mismo helper que ya usan `visita_planeacion_service._medicos_del_ciclo` y `visita_cobertura_service._cobertura_base`.
4. **Si el producto tiene línea**, se filtran los candidatos por `DIM_RM.linea_id`. Un médico trabajado por dos representantes de líneas distintas deja de ser ambiguo en cuanto la receta es de un producto de una de las dos.
5. **Un solo candidato** → atribuida. **Cero o más de uno** → no se atribuye; cuenta como mercado y el diagnóstico lo registra en su propio balde.

El desempate por línea es la razón por la que `producto_ir` es un puente y no un adorno: sin él, todo médico compartido queda ambiguo.

### 4.1 Por qué `cuenta_en_ciclo` y no `estado_aprobacion == "APROBADO"`

En el módulo de Visita conviven **dos criterios distintos a propósito**, y `visita_top_service` documenta que no deben unificarse porque responden preguntas distintas:

- `cuenta_en_ciclo` — *¿este médico forma parte del panel efectivo de este ciclo?* Admite `PENDIENTE_BAJA`, porque una baja solicitada **sigue contando el ciclo actual** (`visita_aprobacion_service`), y es sensible al ciclo: respeta el ciclo de alta y el de baja.
- `estado_aprobacion == "APROBADO"` — *¿se le puede registrar una visita hoy?* Más estricto.

La atribución de una receta es la **primera** pregunta, no la segunda: se pregunta de quién era ese médico cuando se emitió la receta. Usar el criterio estricto dejaría sin atribuir las recetas de todo médico en proceso de baja, que son justamente las de un representante que sí lo trabajó ese ciclo.

Que el criterio sea sensible al ciclo importa además por una razón temporal: la receta pertenece a un período, y el período a un ciclo. La pertenencia al panel se evalúa **para el ciclo de la receta**, no para hoy — si no, reprocesar un lote viejo devolvería una atribución distinta según el día en que se corriera.

## 5. El diagnóstico

`diagnosticar_ir(db, pais_codigo) -> dict` es el entregable que el §11.9 pide antes de desarrollar. Cuatro bloques:

| Bloque | Qué reporta |
|---|---|
| Prescriptores | total en `dimmedicoir`; cuántos enlazan por exequátur al maestro; cuántos de esos están en algún panel; cuántos **casi-enlazan** (§3.1) y cuántos son huérfanos reales, con una muestra de ejemplos de cada clase |
| Productos | total IR; cuántos propios; cuántos con equivalencia resuelta; **cuántos propios sin equivalencia** |
| Períodos | cuántos con ciclo asignado y cuántos sin |
| Recetas | filas de `factprescripciondetalle` por balde: atribuidas por `rm_codigo`, atribuidas por la cadena, **ambiguas**, huérfanas |

El bloque de recetas es el número que decide el sub-proyecto siguiente. Si la mayoría cae en huérfanas, el problema es de Close-Up y no se arregla con código.

El diagnóstico es **de solo lectura**: no escribe en `FACT_*` ni cierra lotes. Puede correrse las veces que haga falta sin efecto.

## 6. Fuera de alcance (YAGNI)

- **El indicador `EVO_IR` y `DW.FACT_EVOIR`**: sub-proyecto siguiente, con los números del diagnóstico delante.
- **`dimmercadoir` y `dimterritorio`**: sin contraparte ni consumidor.
- **Tableros de IR, participación de mercado, análisis territorial**: no existen en VISTA y nadie los pidió para esta fase.
- **Tocar el esquema `ext`** (`app/models/integracion_ext.py`, migración `0030`, el SQL entregado): contrato firmado.
- **Tocar `motor_calculo_service`, `recalculo_service`, `cobertura_predictiva_service`, `cobertura_farmacia_service`, `visita_costo_service`.**
- **Migración**: este sub-proyecto no lleva ninguna. Las tres entidades nuevas son constantes.

## 7. Superficie

`POST /integracion/ir/sincronizar` y `GET /integracion/ir/diagnostico`, con el mismo patrón y RBAC que `/dimensiones/*` y `/visitas/*` en `integracion.py`. Sección nueva "Prescripción IR" en `LotesIntegracion.tsx`, con el diagnóstico como tabla de conteos y la lista de huérfanos como detalle desplegable.

Servicio nuevo `app/services/integracion_ir_service.py`. No se amplía `integracion_dimensiones_service`: los sincronizadores de ahí crean el registro interno cuando falta, y el de prescriptor deliberadamente no lo hace (§3.1) — mezclarlos invitaría a "unificar" ambos comportamientos.

## 8. Verificación

**Los puentes**
1. Un prescriptor cuyo exequátur existe en el maestro se mapea; el mapeo apunta al `DIM_Medico.id` correcto.
2. Un prescriptor cuyo exequátur NO existe **no crea ningún médico**: `DIM_Medico` no crece y la fila se cuenta como no enlazable. Es el test que protege los denominadores de cobertura.
3. Un exequátur que difiere solo en puntuación o espacios (`12.345` vs `12345`) **NO se enlaza**, y se cuenta como casi-enlace, no como huérfano. Es el test que impide que alguien "mejore" el emparejamiento con una normalización privada que el maestro no comparte.
4. Un producto `es_propio = false` sin equivalencia se omite **sin hallazgo**.
5. Un producto `es_propio = true` sin equivalencia produce hallazgo de severidad error.
6. Un período con `ciclo_codigo` nulo no se mapea y produce aviso.
7. Re-sincronizar no duplica mapeos ni cambia conteos.
7b. **Cien prescriptores huérfanos producen CERO hallazgos** y un conteo de cien. Es el test que protege la pantalla de hallazgos de quedar inservible (§3.4).
7c. Dos médicos del maestro con el mismo exequátur → no se enlaza y se emite hallazgo de error.

**La atribución**
8. Fila con `rm_codigo` informado → atribuida a ese representante, sin consultar el panel.
9. Fila sin `rm_codigo`, médico en un solo panel aprobado → atribuida a ese representante.
10. Médico en paneles de DOS representantes de líneas distintas, receta de un producto de una de esas líneas → atribuida a ese, **no ambigua**. Es el test que justifica el puente de producto.
11. Mismo caso pero con producto **sin línea** → ambigua, no atribuida.
12. Médico en paneles de dos representantes de la MISMA línea → ambigua, no atribuida.
13. Médico en un panel `PENDIENTE_ALTA` → no cuenta como candidato.
14. Médico en un panel `PENDIENTE_BAJA` → **SÍ cuenta** y la receta se atribuye. Es el test que impide "endurecer" el criterio a `APROBADO` y perder las recetas de todo médico en proceso de baja.
15. Médico dado de alta en el panel en un ciclo POSTERIOR al de la receta → no cuenta para esa receta. Fija que la pertenencia se evalúa para el ciclo de la receta, no para hoy.
16. Prescriptor huérfano → no atribuida, contada como mercado.

**El diagnóstico**
17. Los cuatro baldes de recetas suman exactamente el total de filas del país: ninguna receta se pierde ni se cuenta dos veces.
18. Correrlo dos veces devuelve lo mismo y no escribe nada.
