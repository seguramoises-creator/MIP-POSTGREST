# Control global País + Ciclo abierto — Diseño

**Edición:** PostgreSQL (`MSM-postgres`) únicamente.
**Fecha:** 2026-07-04

## Objetivo

Que toda la app tenga un **control global de País + Ciclo** en la barra superior
(arriba a la derecha), inicializado por defecto en el **ciclo abierto** del país del
usuario, y que los módulos operen sobre ese contexto en vez de armar cada uno su
propio desplegable de ciclos. Hoy módulos como Exámenes o la suite de Visita
muestran los **72 ciclos** (12 × 6 países) o no muestran país en absoluto.

## Estado actual (problema)

- **No existe** un contexto/estado global de país+ciclo. Cada página llama a
  `GET /admin/ciclos` y arma su propio dropdown sin filtrar → aparecen los 72.
- `GET /admin/ciclos` **ya acepta** `pais_codigo` y `anio` como filtros; el
  frontend simplemente no los usa. **No** existe un filtro por estado abierto.
- Módulos afectados (reportados por el usuario): **Exámenes** (dropdown de 72),
  y la **suite de Visita**: Panel Médico (falta país), Planeación de Ciclo
  (falta país+ciclo), Dashboard de Cobertura-Visita (debe indicar país+ciclo
  arriba-derecha), Proyección y Plan de Acción, Ruptura de Secuencia, Parrilla
  Promocional (falta país), Costo por Visita & ROI (falta país).
- **Dato:** los 72 ciclos están `cerrado=false`. La **fuente de verdad** del
  ciclo actual es el flag `cerrado` de `Config.DIM_Ciclo` (decisión del usuario).

## Fuente de verdad: el ciclo actual

El **ciclo abierto** (`cerrado = false`) de un país es su ciclo actual. Si un país
tiene más de uno abierto (situación actual por datos sin mantener), se toma el
**más reciente** (mayor `anio`, luego mayor `numero`). Así el control resuelve un
único ciclo por país aunque el dato esté sin depurar.

## Arquitectura (Enfoque aprobado: control global + store)

### 1. Backend

`app/api/v1/routers/admin.py` — extender `list_ciclos`:
- Nuevo query param `abierto: Optional[bool] = None`. Cuando `abierto=true`,
  filtra `DIM_Ciclo.cerrado == False`.
- Nuevo endpoint `GET /admin/ciclos/actual?pais_codigo=XX` → devuelve el ciclo
  abierto más reciente del país (o `null`/404 si no hay ninguno abierto).
  Roles: `LecturaCatalogos` (cualquier autenticado con lectura de catálogos).

Contrato de `CicloActual` (reutiliza el schema de ciclo existente):
`{ id, nombre, nombre_canonico, pais_codigo, anio, numero, cerrado }`.

### 2. Frontend — store global

`src/store/ciclo.store.ts` (Zustand), con persistencia ligera en memoria:
```
interface CicloState {
  paisCodigo: string | null;
  cicloId: number | null;
  ciclo: Ciclo | null;
  paisesDisponibles: string[];      // según RBAC
  ciclosDisponibles: Ciclo[];       // ciclos del país seleccionado
  setPais(codigo: string): void;    // al cambiar país, recarga ciclos y
                                    // auto-selecciona el ciclo abierto
  setCiclo(id: number): void;
  init(user): Promise<void>;         // resuelve país+ciclo abierto inicial
}
```
`init` resuelve el país inicial según el rol (ver RBAC) y llama a
`/admin/ciclos/actual?pais_codigo=XX` para fijar el ciclo abierto por defecto.

### 3. Frontend — componente de control

`src/components/CicloPaisSelector.tsx`, montado en el top-bar del layout
(`App.tsx`/layout, junto al nombre de usuario), a la derecha:
- Dos `Select` compactos: **País** → **Ciclo**.
- Muestra el ciclo activo; un `Chip` "Abierto"/"Cerrado" indica el estado.
- Al cambiar País, recarga sus ciclos y auto-selecciona el abierto.
- Cambiar a un ciclo cerrado es válido (consulta histórica); los módulos que ya
  bloquean edición en ciclos cerrados (Parrilla, Costo/ROI) siguen respetando su
  guard de solo-lectura.

### 4. RBAC (scope del país)

- `REPRESENTANTE_MEDICO`: país fijo al suyo (vía su `rm_id` → país del RM). Sin
  selector de país (solo muestra el suyo).
- `GERENTE_DISTRITO` / `GERENTE_MARCA`: país fijo al suyo.
- `ADMIN` / `PRESIDENCIA` / `DIR_COMERCIAL` / `GERENTE_PRODUCTIVIDAD`: pueden
  cambiar de país entre todos los disponibles.
El país inicial para roles con scope sale de su entidad; para roles amplios, el
primer país con ciclo abierto (orden alfabético de `pais_codigo`).

### 5. Wiring de módulos

**Se conectan al store** (leen `paisCodigo`+`cicloId`, eliminan su dropdown de 72):
- **Exámenes** (`ConsolidacionPanel.tsx` y el form de creación): el ciclo lo da
  el store; el panel de consolidación actúa sobre `(cicloId, paisCodigo)` del
  contexto global.
- **Suite Visita**: `PanelMedico`, `PlaneacionCiclo`, `CoberturaVisita`,
  `ProyeccionVisita`, `RupturaVisita`, `ParrillaVisita`, `CostoRoiVisita`.

**No cambian su lógica de datos, pero arrancan en el ciclo abierto por defecto**
(los que ya tienen selector propio y funcionan): Dashboard, Ranking, Cobertura
Predictiva, LSII, Categorización. Estos pueden leer el `cicloId` inicial del store
como valor por defecto; su selector propio se conserva. (Ajuste mínimo, opcional
por página; no es el foco.)

### 6. Dato (opcional, no bloqueante)

El control funciona con el dato actual (toma el más reciente abierto). De forma
**opcional** se puede depurar para dejar 1 ciclo abierto por país (cerrando los
viejos desde Admin → Cerrar ciclo, o con un script puntual). No es requisito del
control.

## Testing

- **Backend** (`pytest`): `list_ciclos(abierto=true)` filtra `cerrado=false`;
  `/admin/ciclos/actual` devuelve el más reciente abierto por país y 404/`null`
  si no hay abierto. Casos: país con 1 abierto, país con varios abiertos (toma el
  mayor), país sin abiertos.
- **Frontend** (`npm run build` + smoke): el control aparece en el top-bar, se
  inicializa al ciclo abierto; cambiar país recarga ciclos y auto-selecciona el
  abierto; Exámenes ya no lista 72 ciclos; la suite Visita muestra el país+ciclo
  del contexto.
- **RBAC**: un RM/GD ve su país fijo; un ADMIN puede cambiar de país.

## Fuera de alcance

- No se rediseña el selector interno de los módulos que ya funcionan (solo se les
  fija el default al ciclo abierto si es trivial).
- No se implementa cierre automático de ciclos por fecha (el flag `cerrado` se
  mantiene manualmente desde Admin, como hoy).
- Solo edición PostgreSQL (`MSM-postgres`); no se toca la edición SQL Server.
