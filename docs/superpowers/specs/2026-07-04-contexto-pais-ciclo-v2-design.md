# Contexto País+Ciclo v2 — Rediseño — Diseño

**Editorial:** se construye en la edición **PostgreSQL** (`MSM-postgres`) y se porta a la
edición **SQL Server** (`MSM`) con `git am` (código dialecto-agnóstico).
**Fecha:** 2026-07-04
**Reemplaza** el comportamiento de la v1 (control global selector en la barra superior).

## Problema (feedback del usuario sobre la v1)

El control v1 quedó como un **selector** en la barra superior, y varios módulos no lo
usan bien: LSII muestra su Ciclo del cuerpo **vacío** y un país que **no coincide** con la
barra; Planeación / Cobertura-Dashboard / Registrar Visita **no muestran** el ciclo. El
usuario quiere otro modelo.

## Modelo objetivo

1. **Barra superior (arriba-derecha) = solo informativa.** Muestra `país · ciclo abierto`,
   sin selección. Es un espejo del contexto, no un control.
2. **Encabezado en el cuerpo de cada módulo.** Cada módulo muestra, arriba de su cuerpo, un
   encabezado **"País: X · Ciclo: Y — Abierto"** con el ciclo que se está trabajando.
3. **Defaults por rol.** RM y Gerentes: su **país** (fijo, el suyo) + su **ciclo abierto**
   (default). Admin / roles amplios: pueden **cambiar de país**; el ciclo por defecto es el
   abierto de ese país.
4. **Consulta de otros ciclos = solo lectura.** Se puede elegir un ciclo **cerrado (pasado)**
   para **ver** su información; un ciclo **futuro** sale **en blanco**. Nunca se crea/edita.
5. **Guard universal (regla dura).** **Nadie** —incluido Admin— crea o modifica datos en un
   ciclo que no sea el abierto. Solo el ciclo abierto permite capturar/editar. Cerrados y
   futuros = solo lectura, snapshot inmutable (consistente con el motor de cálculo, que ya
   bloquea ciclos cerrados vía `validar_ciclo_abierto`).
6. **Alcance:** revisar TODOS los módulos; aplicar en **ambas ediciones**.

## Arquitectura

### Store global (`frontend/src/store/ciclo.store.ts`)

Se reorienta a "contexto informativo + selección acotada":
- `paisCodigo`: país activo (default = país del usuario; Admin puede cambiarlo).
- `cicloAbierto`: el ciclo abierto de `paisCodigo` (vía `GET /admin/ciclos/actual`). Es el
  ciclo "de trabajo" — el único donde se puede crear/editar.
- `cicloVer`: el ciclo que se está **consultando** en el módulo actual (default = `cicloAbierto`).
- `puedeCambiarPais`: bool por rol.
- `esSoloLectura`: derivado — `cicloVer.id !== cicloAbierto.id` (o `cicloAbierto` nulo).
- `ciclosDisponibles`: lista para el selector de consulta.
- Acciones: `init()`, `setPais(codigo)` (Admin), `setCicloVer(id)`.

### Componentes

- **`CicloPaisBadge`** (reemplaza `CicloPaisSelector`): en la barra superior de `MainLayout`,
  **solo lectura** — `país · ciclo abierto` + chip "Abierto". Sin interacción.
- **`CicloPaisHeader`** (nuevo, reutilizable): se coloca al inicio del cuerpo de cada módulo.
  Muestra `País: X · Ciclo: Y`. Para Admin, `País` es un `Select`; para RM/Gerente es texto.
  `Ciclo` es un `Select` que default­ea a `cicloAbierto` y permite elegir otros para
  **consulta**; al elegir uno ≠ abierto, marca chip **"Solo lectura"**. Escribe en el store
  (`setPais`/`setCicloVer`), de modo que el badge superior refleja el mismo contexto.

### Guard de solo-lectura

- **Frontend (UX):** los módulos de captura leen `esSoloLectura` del store y **deshabilitan**
  botones/inputs de crear/editar cuando el ciclo consultado no es el abierto (patrón que ya
  usan Parrilla/Costo con su `cerrado`). Ciclo futuro → cuerpo en blanco/vacío.
- **Backend (seguridad, no confiar solo en el front):** todos los endpoints de captura que
  reciben `ciclo_id` deben **rechazar** ciclos no-abiertos (reusar/extender
  `validar_ciclo_abierto` / los `_guard_ciclo_abierto` de Visita). Devolver 409/403 claro.
  Auditar qué endpoints de captura aún no lo hacen y agregarlo.

### Clasificación de módulos

- **Captura/edición (aplican `CicloPaisHeader` + guard):** Registrar Visita, Planeación Ciclo,
  Parrilla & Muestras, Costo & ROI, Ruptura/Cierre, Exámenes (crear + consolidar), Matriz LSII
  (Nueva Evaluación), Categorización (captura/carga).
- **Solo lectura (aplican `CicloPaisHeader` solo como display):** Dashboard Ejecutivo, Ranking,
  Productividad, Indicadores, Cobertura Visita (dashboard), Proyección Visita, Cobertura
  Predictiva, Categorización (resumen/listado), Matriz LSII (vista de matriz), Reconocimiento,
  Reportes.

### RBAC

- RM (`REPRESENTANTE_MEDICO`) / Gerentes (`GERENTE_DISTRITO`, `GERENTE_MARCA`): país fijo (el
  suyo), sin `Select` de país. Ciclo default abierto; pueden consultar cerrados en solo lectura.
- Admin / `PRESIDENCIA` / `DIR_COMERCIAL` / `GERENTE_PRODUCTIVIDAD`: `Select` de país habilitado.
- El guard de escritura aplica **a todos por igual** (sin excepción para Admin).

## Testing

- **Backend (pytest):** cada endpoint de captura rechaza `ciclo_id` cerrado (extiende los
  tests de guard existentes de Visita/Exámenes; casos: crear en abierto → OK, crear en cerrado
  → 409/403).
- **Frontend (`npm run build` + smoke):** el badge superior es informativo; cada módulo muestra
  `CicloPaisHeader` con el ciclo abierto por defecto; elegir un ciclo cerrado deshabilita
  crear/editar; LSII ya no sale con Ciclo vacío ni país descuadrado; Admin cambia país y el
  contexto (badge + headers) se actualiza; RM/Gerente ve su país fijo.

## Fuera de alcance

- Cambiar la regla de negocio del ciclo abierto (sigue siendo el flag `cerrado`).
- Migración de datos o cierre automático de ciclos.
- La verificación runtime del contenedor (deploy).

## Porte a la edición SQL Server

Igual que el control v1: se construye en `MSM-postgres`, se generan parches con
`git format-patch` y se aplican en `MSM` con `git am` (todo es ORM + React, dialecto-agnóstico).
