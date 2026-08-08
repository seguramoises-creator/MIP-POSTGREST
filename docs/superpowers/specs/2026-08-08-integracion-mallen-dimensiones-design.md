# Spec — Integración Mallén, sub-proyecto 2: Sincronización de dimensiones

**Fecha:** 2026-08-08
**Módulo:** Integración con Laboratorio Mallén (esquema `ext` → esquemas internos de VISTA).
**Alcance:** backend (modelo + migración + servicio + router + tests) y frontend (service + acción en la pantalla de lotes).
**Depende de:** sub-proyecto 1 (recepción y validación), ya en producción.

---

## 1. Objetivo

Llevar las **9 dimensiones** que Mallén deja en `ext` a los catálogos internos de VISTA (`Config.DIM_*`), sin duplicar lo que VISTA ya tiene cargado y sin destruir información histórica.

Sin esto, ningún hecho puede integrarse: una visita de `ext` referencia `rm_codigo` y `medico_codigo`, y VISTA necesita el `DIM_RM.id` y el `DIM_Medico.id` correspondientes.

## 2. El problema central: VISTA ya tiene datos

Producción es un piloto **con datos reales** cargados por Excel (representantes, médicos, gerentes, ciclos). Una sincronización ingenua —"busca por mi identificador externo; si no está, créalo"— duplicaría el maestro completo, porque los registros actuales de VISTA no tienen ningún identificador externo.

Además, varias dimensiones internas no tienen dónde guardar el código de Mallén:

| Dimensión interna | Situación |
|---|---|
| `DIM_Especialidad` | solo `nombre` único; **sin columna de código** |
| `DIM_Ciclo` | se identifica por (país, año, número); **sin código** |
| `DIM_Farmacia` | **sin código**, y exige `direccion` y `encargado` NOT NULL que `ext` no envía |
| `DIM_Gerente`, `DIM_RM` | `codigo` es `String(20)` y **único global**; en `ext` es `String(30)` y único por país |

## 3. La pieza que lo resuelve: tabla de equivalencias

**`Config.MapeoExterno`** — el puente entre el código de Mallén y el id interno.

```
id             Integer PK
entidad        String(30)   -- 'pais' | 'linea' | 'gerente' | 'representante' | 'ciclo'
                            -- | 'especialidad' | 'medico' | 'farmacia' | 'producto'
pais_codigo    String(10)   -- '' para entidades sin país (especialidad)
codigo_externo String(60)
id_interno     Integer      -- id en la DIM_* correspondiente
sincronizado_en DateTime
UNIQUE (entidad, pais_codigo, codigo_externo)
```

**Por qué una tabla y no una columna `codigo_externo` en cada `DIM_*`:**
- No toca ninguna tabla interna existente — riesgo mínimo sobre datos reales de producción.
- Funciona igual para las dimensiones que tienen código y para las que no (especialidad, ciclo, farmacia).
- Deja el mapeo **visible y corregible en un solo sitio** cuando algo se empareje mal, en vez de repartido por nueve tablas.
- No es una columna que el resto del sistema pueda leer por accidente y acoplarse al identificador de un tercero.

`id_interno` **no lleva FK**: apunta a nueve tablas distintas según `entidad`. La integridad la garantiza el servicio, y un registro interno borrado a mano deja un mapeo huérfano que la sincronización repara (ver §6).

**Migración**: crear `Config.MapeoExterno`. Nada más. Ninguna `DIM_*` se modifica.

## 4. El algoritmo: buscar, adoptar, crear

Para cada fila de cada dimensión de `ext`, en este orden:

1. **¿Existe mapeo?** (`entidad`, `pais_codigo`, `codigo_externo`) → **actualizar** los campos del registro interno apuntado.
2. **¿No hay mapeo, pero existe por clave natural?** → **ADOPTAR**: crear el mapeo apuntando al registro que ya está, y actualizar sus campos.
3. **¿No existe?** → **crear** el registro interno y su mapeo.

**El paso 2 es el que hace viable todo el sub-proyecto.** Sin él, la primera sincronización duplicaría cada representante, cada médico y cada gerente que VISTA ya tiene.

**Claves naturales de adopción:**

| Entidad | Clave natural en VISTA |
|---|---|
| país | `DIM_Pais.codigo` |
| línea | (`pais_codigo`, `codigo`) |
| gerente | `DIM_Gerente.codigo` (único global) |
| representante | `DIM_RM.codigo` (único global) |
| ciclo | (`pais_codigo`, `anio`, `numero`) |
| especialidad | `DIM_Especialidad.nombre` (normalizado: `strip()` + comparación sin distinguir mayúsculas) |
| médico | (`pais_codigo`, `codigo`); si no hay coincidencia y `ext` trae exequátur, por (`pais_codigo`, `exequatur`) |
| farmacia | (`pais_codigo`, `nombre_completo`) normalizado |
| producto | `DIM_Producto.codigo` (único global) |

La adopción por **exequátur** en médicos es deliberada: es el identificador profesional único, y el maestro de VISTA ya lo indexa. Si el código de Mallén no coincide pero el exequátur sí, es la misma persona.

## 5. Nunca borra

Un registro que desaparece de `ext` **no se elimina ni se toca**: hay hechos históricos apuntando a él (visitas, ventas, resultados de ciclos cerrados). La sincronización solo crea y actualiza.

`activo` sí se sincroniza: si Mallén marca un representante como inactivo, VISTA lo refleja. Es la vía correcta de "dar de baja" sin perder historia.

## 6. Mapeos huérfanos

Si `id_interno` apunta a un registro que ya no existe (borrado a mano en VISTA), la sincronización **borra el mapeo y vuelve a empezar** por el paso 2 para esa fila. Un mapeo es un dato derivado y reconstruible; no debe bloquear la sincronización.

## 7. Reglas especiales por dimensión

### 7.1 Ciclo — **nunca se toca `cerrado`** (decisión del cliente)
Se sincronizan `nombre`, `fecha_inicio`, `fecha_fin` y `dias_laborables`. El estado abierto/cerrado sigue siendo decisión de VISTA (Administración → Ciclos), porque de él dependen los recálculos, los premios y la inmutabilidad de los snapshots históricos. Si el `cerrado` de `ext` difiere del de VISTA, **se registra un hallazgo informativo** (severidad `aviso`) y se respeta el de VISTA.

`ciclo_codigo` de Mallén se guarda en `DIM_Ciclo.nombre_canonico` si está vacío — es informativo, no identificador.

### 7.2 Farmacia — campos obligatorios que `ext` no envía
`DIM_Farmacia.direccion` y `.encargado` son NOT NULL (marcados "F23/F24 bloqueante" en el modelo) y `ext.dimfarmacia` no los trae. Al **crear** desde `ext`:
- `direccion` y `encargado` quedan como cadena vacía, para completarse en VISTA.
- `origen = 'CONFIG'` (viene del sistema oficial, no de un VM solicitando alta).
- `estado = 'APROBADA'` (no entra al flujo de aprobación VM→GD: ya es maestro oficial).
- `nombre_completo` se arma con el `nombre` de `ext`; `es_cadena` queda en `False` (`ext` no distingue cadena/sucursal).

Al **actualizar** una farmacia existente **no se pisan** `direccion`, `encargado`, `estado` ni `origen`: son datos que VISTA enriqueció y `ext` no conoce.

### 7.3 Médico — arrastra tres catálogos auxiliares
`ext.dimmedico` trae `especialidad_codigo`, y `centro_trabajo`, `provincia` y `municipio` **como texto libre**, mientras que `DIM_Medico` los referencia por FK (`especialidad_id`, `centro_medico_id`, `provincia_id`, `municipio_id`).

- `especialidad_codigo` → se resuelve por el mapeo de la entidad `especialidad` (que se sincroniza antes).
- `centro_trabajo`, `provincia`, `municipio` → se resuelven en `DIM_CentroMedico`, `DIM_Provincia` y `DIM_Municipio` por nombre normalizado, **creándolos si no existen**. Son catálogos auxiliares sin identidad propia en el contrato; crearlos al vuelo es preferible a descartar el dato.
- Texto vacío o nulo → la FK queda en `NULL`, no se crea un registro "sin nombre".

### 7.4 Códigos que no caben — se omiten, no se truncan
`DIM_Gerente.codigo` y `DIM_RM.codigo` son `String(20)`; `ext` permite 30. Una fila cuyo código exceda el largo interno **se omite y se registra un hallazgo `error`**. Truncar crearía colisiones silenciosas entre dos códigos distintos que compartan los primeros 20 caracteres — exactamente el tipo de fallo que este módulo existe para evitar.

Lo mismo aplica a la unicidad: `ext` permite el mismo `gerente_codigo` en dos países, pero `DIM_Gerente.codigo` es único global. Si dos países traen el mismo código, el segundo se omite con hallazgo `error` explicando la colisión.

### 7.5 Producto
`ext.dimproducto.producto_codigo` → `DIM_Producto.codigo` (único global). Se sincronizan `nombre` y `activo`; `linea_codigo` se resuelve al `linea_id` interno por el mapeo. Los campos propios de VISTA (`area_terapeutica`, `segmento_target`, `meta_muestras_visita`, `gerente_producto`) **no se tocan**: `ext` no los conoce.

## 8. Orden de sincronización

Por dependencia, en una sola pasada:

`país → línea → gerente → representante → ciclo → especialidad → médico → farmacia → producto`

Cada dimensión se procesa entera antes de la siguiente, porque las posteriores resuelven FK contra las anteriores.

**Alcance de la ejecución:** se sincroniza **todo el contenido actual de las tablas `ext.dim*` de un país**, no un lote. Las dimensiones de `ext` no llevan `lote_id`: son el estado vigente del maestro, no un envío incremental.

## 9. Manejo de errores

Igual criterio que la validación del sub-proyecto 1: **una fila mala no detiene la sincronización.** Se registra un hallazgo en `Audit.IntegracionHallazgo` (la tabla ya existe) y se sigue con la siguiente.

Como los hallazgos de sincronización no pertenecen a un lote, `lote_id` no aplica. Para no alterar esa tabla (que tiene `lote_id` NOT NULL con FK), los hallazgos de sincronización se devuelven **en la respuesta del endpoint** y se registran en el log, sin persistirse. Persistirlos exigiría hacer `lote_id` nullable, y el histórico de sincronización no es lo que este sub-proyecto necesita resolver.

## 10. API

Prefijo `/integracion` (el router ya existe). **Roles: ADMIN y GERENTE_PRODUCTIVIDAD**, igual que el resto del módulo.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/integracion/dimensiones/sincronizar` | `?pais_codigo=XX` → ejecuta las 9 en orden |
| GET | `/integracion/dimensiones/resumen` | `?pais_codigo=XX` → cuántas filas hay en `ext` y cuántas mapeadas, por dimensión |

Respuesta de `POST /sincronizar`:
```json
{"pais_codigo": "DO",
 "dimensiones": [
   {"entidad": "representante", "en_ext": 48, "creados": 2, "adoptados": 45,
    "actualizados": 45, "omitidos": 1}
 ],
 "hallazgos": [
   {"entidad": "gerente", "codigo_externo": "GER-DISTRITO-NORTE-2026",
    "problema": "El código excede los 20 caracteres de DIM_Gerente.codigo.",
    "severidad": "error"}
 ]}
```

`adoptados` es la métrica clave de la primera corrida: dice cuántos registros existentes se emparejaron en vez de duplicarse.

## 11. Re-ejecución

Sincronizar es **idempotente**: correrlo dos veces seguidas da el mismo resultado (la segunda vez todo cae en el paso 1, "actualizar"). Es lo que permite programarlo o repetirlo tras corregir datos en `ext`.

## 12. Frontend

En la pantalla existente `/integracion/lotes`, una sección nueva **"Dimensiones"**:
- Tabla con las 9 dimensiones: filas en `ext`, filas mapeadas, y la diferencia.
- Botón **"Sincronizar dimensiones"** (requiere país en el contexto global).
- Tras ejecutar, el resultado por dimensión (creados / adoptados / actualizados / omitidos) y la lista de hallazgos, que es lo que se le devuelve a Mallén para corregir.

## 13. Fuera de alcance (YAGNI)

- Integrar **hechos** (visitas, ventas, prescripciones): sub-proyectos 3 y 4.
- Las 5 dimensiones del módulo IR (`dimperiodoir`, `dimmercadoir`, `dimproductoir`, `dimmedicoir`, `dimterritorio`): las usa el sub-proyecto 4.
- Automatizar el disparo (scheduler): sub-proyecto 5. Aquí se sincroniza con un botón.
- Editar el mapeo desde la UI: si un emparejamiento sale mal, se corrige por base de datos. Construir un editor antes de saber si hace falta es especular.
- Borrar registros internos que desaparecieron de `ext` (§5).
- Tocar el esquema `ext` de cualquier forma.

## 14. Verificación

**Backend** — tests en `backend/tests/test_integracion_dimensiones.py`, patrón PostgreSQL real:
1. **Adopción**: un `DIM_RM` preexistente con código `VM01` y un `ext.dimrepresentante` con `rm_codigo='VM01'` → **no se crea un segundo RM**; se crea el mapeo y `adoptados == 1`.
2. **Creación**: un representante que no existe en VISTA → se crea y se mapea.
3. **Idempotencia**: sincronizar dos veces no duplica ni cambia los conteos de la segunda corrida.
4. **Ciclo**: un `ext.dimciclo` con `cerrado=True` sobre un ciclo abierto en VISTA → el ciclo **sigue abierto** y se emite hallazgo `aviso`.
5. **Código largo**: un `gerente_codigo` de 25 caracteres → se omite con hallazgo `error` y **no se crea** el gerente.
6. **Colisión global**: el mismo `gerente_codigo` en dos países → el segundo se omite con hallazgo `error`.
7. **Médico con catálogos auxiliares**: un médico con `provincia`, `municipio` y `centro_trabajo` en texto → se crean/resuelven las tres FK.
8. **Adopción por exequátur**: un médico existente con exequátur `EX-123` y código distinto al de `ext` → se adopta, no se duplica.
9. **Mapeo huérfano**: un mapeo cuyo `id_interno` no existe → se reconstruye sin fallar.
10. **Farmacia**: se crea con `origen='CONFIG'`, `estado='APROBADA'`; al re-sincronizar no se pisan `direccion` ni `encargado` si VISTA los completó.

**Frontend** — `npm run build` + smoke: sembrar dimensiones en `ext` a mano, sincronizar, comprobar los conteos y que no haya duplicados en los catálogos.
