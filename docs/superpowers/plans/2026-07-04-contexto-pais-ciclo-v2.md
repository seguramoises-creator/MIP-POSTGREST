# Contexto País+Ciclo v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar el control global País+Ciclo por un modelo "barra superior informativa + encabezado por módulo con ciclo abierto por defecto", donde solo el ciclo abierto es editable y los ciclos cerrados/futuros son solo-lectura para todos.

**Architecture:** Un store Zustand distingue `cicloAbierto` (de trabajo, editable) de `cicloVer` (en consulta); `esSoloLectura` se deriva de compararlos. La barra superior muestra un badge informativo; un `CicloPaisHeader` reutilizable montado una sola vez en `MainLayout` da el selector de consulta a todos los módulos. Los módulos de captura leen `esSoloLectura` y apagan sus controles; el backend rechaza (409) cualquier escritura sobre un ciclo cerrado como defensa en profundidad.

**Tech Stack:** React 18 + TypeScript + Vite + MUI v6 + Zustand v5 (frontend); FastAPI + SQLAlchemy 2.0 + pytest (backend). Se construye en la edición **PostgreSQL** (`C:\Users\Lenovo\Proyecto\MSM-postgres`) y se porta a la edición **SQL Server** (`C:\Users\Lenovo\Proyecto\MSM`) con `git format-patch` / `git am`.

## Global Constraints

- **Barra superior = solo informativa**: muestra `paisCodigo` + `cicloAbierto` + chip "Abierto"; sin selección.
- **Encabezado por módulo**: País (Select solo si `puedeCambiarPais && paisesDisponibles.length > 1`, si no texto) + Ciclo (Select, default = ciclo abierto) + chip "Solo lectura"/"Abierto · editable".
- **Solo el ciclo abierto es editable**. Ciclos cerrados o futuros = solo lectura para TODOS los roles, incluido ADMIN. Sin excepción.
- **`esSoloLectura` es la única fuente de verdad** del guard de UX: `cicloId !== cicloAbiertoId` (o no hay ciclo abierto).
- **Defensa en profundidad**: los endpoints de captura rechazan ciclos cerrados con HTTP 409 vía `recalculo_service.validar_ciclo_abierto` — nunca confiar solo en el front.
- **Frontend sin runner de tests**: la verificación de cada tarea de frontend es `npm run build` (ejecuta `tsc -b` = type-check estricto + `vite build`). El backend usa pytest (TDD real).
- **No romper el contrato del store para consumidores existentes**: `cicloId` y `ciclo` siguen existiendo y representan el ciclo EN CONSULTA (default = abierto).
- **Comandos**: frontend en `C:\Users\Lenovo\Proyecto\MSM-postgres\frontend` (`npm run build`); backend en `C:\Users\Lenovo\Proyecto\MSM-postgres\backend` con venv activo (`python -m pytest`).

---

### Task 1: Backend — guard de escritura en endpoints de captura

Asegura que TODO endpoint que escribe datos ligados a un ciclo rechace ciclos cerrados con HTTP 409. `recalculo_service.validar_ciclo_abierto(db, ciclo_id)` y `CicloCerradoError` ya existen (`app/services/recalculo_service.py:46-69`). Parrilla, Costo y Cierre ya lo usan (`_guard_ciclo_abierto`). Faltan por auditar: **registro de visita** (`visita_registro_service.py`), **planeación** (`visita_planeacion_service.py`), **LSII evaluar** (`lsii_service.py`), **categorización captura** (`categorizacion_service.py` / router `categorizacion.py`).

**Files:**
- Read/Modify: `backend/app/services/visita_registro_service.py`
- Read/Modify: `backend/app/services/visita_planeacion_service.py`
- Read/Modify: `backend/app/services/lsii_service.py`
- Read/Modify: `backend/app/api/v1/routers/lsii.py`
- Read/Modify: `backend/app/api/v1/routers/categorizacion.py`
- Read/Modify: `backend/app/api/v1/routers/visita.py` (traducción `CicloCerradoError`/`ValueError("...solo lectura")` → `HTTPException(status_code=409)` donde falte)
- Test: `backend/tests/test_contexto_ciclo_guard.py` (Create)

**Interfaces:**
- Consumes: `recalculo_service.validar_ciclo_abierto(db: Session, ciclo_id: int) -> Ciclo` (raises `recalculo_service.CicloCerradoError` si `ciclo.cerrado`).
- Produces: cada función de captura ligada a un ciclo llama al guard antes de escribir; los routers devuelven **409** cuando el ciclo está cerrado.

- [ ] **Step 1: Auditar los servicios/rutas de captura**

Lee cada archivo listado y localiza las funciones que ESCRIBEN (INSERT/UPDATE/delete-then-insert) filas ligadas a un `ciclo_id`:
- `visita_registro_service.py`: la función que registra una visita / no-visita (recibe `ciclo_id` o lo resuelve del ciclo por defecto).
- `visita_planeacion_service.py`: la función que guarda la planeación del ciclo.
- `lsii_service.py`: la función que registra la evaluación (`evaluar` / `registrar_evaluacion`), que recibe `ciclo_id`.
- `categorizacion_service.py`: las funciones invocadas por `POST /categorizacion/calcular`, `/recalcular`, `/cargar`.

Anota, para cada una, si ya llama a `validar_ciclo_abierto` (o `_guard_ciclo_abierto`). Las que NO, se corrigen abajo.

- [ ] **Step 2: Escribir el test que falla (registro de visita en ciclo cerrado)**

Sigue el patrón de los guards ya probados en `backend/tests/test_visita_service.py` (busca los tests de "ciclo cerrado" de parrilla/costo para copiar el estilo de fixtures). Crea `backend/tests/test_contexto_ciclo_guard.py`:

```python
import pytest
from app.services import recalculo_service


def test_validar_ciclo_abierto_rechaza_cerrado(db_session, ciclo_cerrado):
    """El guard central levanta CicloCerradoError en un ciclo cerrado."""
    with pytest.raises(recalculo_service.CicloCerradoError):
        recalculo_service.validar_ciclo_abierto(db_session, ciclo_cerrado.id)


def test_validar_ciclo_abierto_ok_abierto(db_session, ciclo_abierto):
    """El guard devuelve el ciclo cuando está abierto."""
    c = recalculo_service.validar_ciclo_abierto(db_session, ciclo_abierto.id)
    assert c.id == ciclo_abierto.id
    assert c.cerrado is False
```

Reusa/crea los fixtures `db_session`, `ciclo_abierto`, `ciclo_cerrado` siguiendo `conftest.py` y `test_visita_service.py` existentes. Si ya existen fixtures equivalentes, impórtalos en vez de duplicarlos.

- [ ] **Step 3: Ejecutar el test (parte ya cubierta pasa, define la base)**

Run: `python -m pytest backend/tests/test_contexto_ciclo_guard.py -v`
Expected: los 2 tests del guard central PASAN (el guard ya existe). Sirven de red para no regresar.

- [ ] **Step 4: Añadir el guard donde falte**

En cada servicio de captura que en el Step 1 NO tenga guard, añade al inicio de la función de escritura (usando el mismo helper que Parrilla, `visita_parrilla_service.py:24-29`):

```python
from app.services import recalculo_service

def _guard_ciclo_abierto(db, ciclo_id):
    """Bloquea escrituras sobre ciclos cerrados (inmutables)."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        raise ValueError("El ciclo está cerrado — solo lectura")
```

Llama `_guard_ciclo_abierto(db, ciclo_id)` antes de la primera escritura. Si el módulo ya tiene un `_guard_ciclo_abierto` local, reúsalo. En los routers (`lsii.py`, `categorizacion.py`, `visita.py`), envuelve la llamada y traduce a HTTP 409:

```python
from fastapi import HTTPException

try:
    resultado = servicio.funcion_de_captura(db, ..., ciclo_id=ciclo_id)
except ValueError as e:
    if "cerrado" in str(e).lower() or "solo lectura" in str(e).lower():
        raise HTTPException(status_code=409, detail="El ciclo está cerrado — solo lectura")
    raise HTTPException(status_code=422, detail=str(e))
```

- [ ] **Step 5: Escribir tests de endpoint (captura en ciclo cerrado → 409)**

Añade a `test_contexto_ciclo_guard.py` un test por cada endpoint de captura corregido, usando el `TestClient` como en los tests de router existentes (busca en `tests/` un test que use `client.post(...)` con auth para copiar el patrón de token). Ejemplo para LSII:

```python
def test_lsii_evaluar_ciclo_cerrado_409(client, auth_headers_gerente, ciclo_cerrado, rm_demo):
    r = client.post("/api/v1/lsii/evaluar", headers=auth_headers_gerente, json={
        "pais_codigo": ciclo_cerrado.pais_codigo,
        "rm_id": rm_demo.id,
        "ciclo_id": ciclo_cerrado.id,
        "selecciones": [],
    })
    assert r.status_code == 409
```

Repite para: registrar visita, guardar planeación, categorización `/calcular`. Ajusta payloads mínimos según el schema real de cada endpoint (léelo antes de escribir el test).

- [ ] **Step 6: Ejecutar tests hasta verde**

Run: `python -m pytest backend/tests/test_contexto_ciclo_guard.py -v`
Expected: todos PASAN.

- [ ] **Step 7: Suite completa (sin regresiones)**

Run: `python -m pytest backend -q`
Expected: la suite completa pasa (los ~193 tests previos + los nuevos).

- [ ] **Step 8: Commit**

```bash
git add backend/app backend/tests/test_contexto_ciclo_guard.py
git commit -m "feat(contexto) guard 409 en endpoints de captura para ciclos cerrados"
```

---

### Task 2: Store `ciclo.store.ts` v2 (cicloAbierto + cicloVer + esSoloLectura)

**Files:**
- Modify: `frontend/src/store/ciclo.store.ts` (reemplazo completo)

**Interfaces:**
- Consumes: `GET /admin/paises`, `GET /admin/ciclos?pais_codigo=XX`, `GET /admin/ciclos/actual?pais_codigo=XX`, `GET /auth/me` (ya existentes).
- Produces (lo que leen las demás tareas):
  - `paisCodigo: string | null`
  - `cicloId: number | null` — ciclo EN CONSULTA (default = abierto)
  - `ciclo: Ciclo | null` — objeto del ciclo en consulta
  - `cicloAbiertoId: number | null` — ciclo abierto (de trabajo, editable)
  - `cicloAbierto: Ciclo | null`
  - `paisesDisponibles: string[]`, `ciclosDisponibles: Ciclo[]`, `puedeCambiarPais: boolean`
  - `esSoloLectura: boolean`
  - `init(): Promise<void>`, `setPais(codigo: string): Promise<void>`, `setCicloVer(id: number): void`

- [ ] **Step 1: Reemplazar el contenido del store**

Sobrescribe `frontend/src/store/ciclo.store.ts` con:

```ts
import { create } from 'zustand';
import { api } from '../services/api';

export type Ciclo = {
  id: number; nombre: string; nombre_canonico?: string;
  pais_codigo: string; anio: number; numero: number; cerrado: boolean;
};

const ROLES_MULTIPAIS = ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD'];

interface CicloState {
  paisCodigo: string | null;
  cicloId: number | null;          // ciclo EN CONSULTA (default = abierto)
  ciclo: Ciclo | null;
  cicloAbiertoId: number | null;   // ciclo ABIERTO (de trabajo) — único editable
  cicloAbierto: Ciclo | null;
  paisesDisponibles: string[];
  ciclosDisponibles: Ciclo[];
  puedeCambiarPais: boolean;
  esSoloLectura: boolean;          // cicloId !== cicloAbiertoId (o sin abierto)
  init: () => Promise<void>;
  setPais: (codigo: string) => Promise<void>;
  setCicloVer: (id: number) => void;
}

export const useCicloStore = create<CicloState>((set, get) => ({
  paisCodigo: null, cicloId: null, ciclo: null,
  cicloAbiertoId: null, cicloAbierto: null,
  paisesDisponibles: [], ciclosDisponibles: [], puedeCambiarPais: false,
  esSoloLectura: true,

  init: async () => {
    const me = (await api.get('/auth/me')).data as { pais_codigo?: string; rol: string };
    const multipais = ROLES_MULTIPAIS.includes(me.rol);
    let paises: string[];
    if (multipais) {
      const rows = (await api.get('/admin/paises')).data as { codigo: string }[];
      paises = rows.map((p) => p.codigo);
    } else {
      paises = me.pais_codigo ? [me.pais_codigo] : [];
    }
    set({ puedeCambiarPais: multipais, paisesDisponibles: paises });
    const inicial = me.pais_codigo || paises[0] || null;
    if (inicial) await get().setPais(inicial);
  },

  setPais: async (codigo) => {
    const ciclos = (await api.get(`/admin/ciclos?pais_codigo=${codigo}`)).data as Ciclo[];
    const actual = (await api.get(`/admin/ciclos/actual?pais_codigo=${codigo}`)).data as Ciclo | null;
    const abierto = actual || null;
    // El ciclo EN CONSULTA arranca en el abierto; si no hay abierto, en el último de la lista.
    const verInicial = abierto || ciclos[ciclos.length - 1] || null;
    set({
      paisCodigo: codigo,
      ciclosDisponibles: ciclos,
      cicloAbierto: abierto,
      cicloAbiertoId: abierto ? abierto.id : null,
      ciclo: verInicial,
      cicloId: verInicial ? verInicial.id : null,
      esSoloLectura: !abierto || !verInicial || verInicial.id !== abierto.id,
    });
  },

  setCicloVer: (id) => {
    const c = get().ciclosDisponibles.find((x) => x.id === id) || null;
    const abiertoId = get().cicloAbiertoId;
    set({ cicloId: id, ciclo: c, esSoloLectura: abiertoId == null || id !== abiertoId });
  },
}));
```

- [ ] **Step 2: Verificar build**

Run (en `frontend`): `npm run build`
Expected: `tsc -b` sin errores de tipo salvo los que provienen de que `CicloPaisSelector.tsx` usa `setCiclo` (eliminado). Ese archivo se reemplaza en Task 3 — si el build falla SOLO por `CicloPaisSelector.tsx`, es esperado; continúa a Task 3 y reverifica ahí. Cualquier otro error de tipo debe corregirse aquí.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/store/ciclo.store.ts
git commit -m "feat(contexto) store v2: cicloAbierto vs cicloVer + esSoloLectura"
```

---

### Task 3: `CicloPaisBadge` (barra superior informativa)

**Files:**
- Create: `frontend/src/components/CicloPaisBadge.tsx`
- Delete: `frontend/src/components/CicloPaisSelector.tsx`
- Modify: `frontend/src/components/layout/MainLayout.tsx:14` (import) y `:74` (uso)

**Interfaces:**
- Consumes: `useCicloStore` → `paisCodigo`, `cicloAbierto`, `init`.
- Produces: componente informativo (sin selección) para la barra superior; dispara `init()` una vez.

- [ ] **Step 1: Crear el badge**

Crea `frontend/src/components/CicloPaisBadge.tsx`:

```tsx
import { useEffect } from 'react';
import { Box, Chip, Typography } from '@mui/material';
import { useCicloStore } from '../store/ciclo.store';

/** Barra superior: informativa. Muestra el país y el CICLO ABIERTO (de trabajo).
 *  No permite seleccionar — el cambio de ciclo/país vive en CicloPaisHeader. */
export default function CicloPaisBadge() {
  const { paisCodigo, cicloAbierto, init } = useCicloStore();
  useEffect(() => {
    if (!paisCodigo) init().catch((e) => console.error('CicloPaisBadge: init failed', e));
  }, [paisCodigo, init]);

  if (!paisCodigo) return null;

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Typography variant="body2" fontWeight={700}>{paisCodigo}</Typography>
      <Typography variant="body2" color="text.secondary">
        {cicloAbierto ? (cicloAbierto.nombre_canonico || cicloAbierto.nombre) : 'Sin ciclo abierto'}
      </Typography>
      <Chip size="small" color={cicloAbierto ? 'success' : 'default'}
            label={cicloAbierto ? 'Abierto' : '—'} />
    </Box>
  );
}
```

- [ ] **Step 2: Cablear en MainLayout**

En `frontend/src/components/layout/MainLayout.tsx`:
- Línea 14: cambia `import CicloPaisSelector from '../CicloPaisSelector';` por `import CicloPaisBadge from '../CicloPaisBadge';`
- Línea 74: cambia `<CicloPaisSelector />` por `<CicloPaisBadge />`

- [ ] **Step 3: Eliminar el selector viejo**

```bash
git rm frontend/src/components/CicloPaisSelector.tsx
```

- [ ] **Step 4: Verificar build**

Run (en `frontend`): `npm run build`
Expected: PASS (sin errores). Si algún otro archivo importaba `CicloPaisSelector`, no debería (grep confirmó que solo MainLayout lo usa).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CicloPaisBadge.tsx frontend/src/components/layout/MainLayout.tsx
git commit -m "feat(contexto) barra superior informativa (CicloPaisBadge)"
```

---

### Task 4: `CicloPaisHeader` (encabezado por módulo, montado en MainLayout)

**Files:**
- Create: `frontend/src/components/CicloPaisHeader.tsx`
- Modify: `frontend/src/components/layout/MainLayout.tsx:141-143` (envolver el `<Outlet/>`)

**Interfaces:**
- Consumes: `useCicloStore` → `paisCodigo`, `cicloId`, `ciclosDisponibles`, `cicloAbiertoId`, `paisesDisponibles`, `puedeCambiarPais`, `esSoloLectura`, `setPais`, `setCicloVer`.
- Produces: encabezado que se renderiza UNA vez arriba del contenido; escribe país/ciclo-de-consulta en el store, de modo que todos los módulos (captura y solo-lectura) comparten el mismo contexto.

- [ ] **Step 1: Crear el encabezado**

Crea `frontend/src/components/CicloPaisHeader.tsx`:

```tsx
import { Box, MenuItem, Select, Chip, Typography, Paper } from '@mui/material';
import { LockOutlined } from '@mui/icons-material';
import { useCicloStore } from '../store/ciclo.store';

/** Encabezado del cuerpo de cada módulo (montado 1 vez en MainLayout).
 *  País: Select solo si el rol puede cambiar país; si no, texto fijo.
 *  Ciclo: Select con el ABIERTO por defecto; elegir otro pone el módulo en solo lectura. */
export default function CicloPaisHeader() {
  const {
    paisCodigo, cicloId, ciclosDisponibles, cicloAbiertoId,
    paisesDisponibles, puedeCambiarPais, esSoloLectura, setPais, setCicloVer,
  } = useCicloStore();

  if (!paisCodigo) return null;

  return (
    <Paper variant="outlined"
           sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 2, py: 1, mb: 2, flexWrap: 'wrap' }}>
      <Typography variant="caption"
                  sx={{ fontWeight: 700, textTransform: 'uppercase', color: 'text.secondary', letterSpacing: 0.5 }}>
        País
      </Typography>
      {puedeCambiarPais && paisesDisponibles.length > 1 ? (
        <Select size="small" value={paisCodigo} onChange={(e) => setPais(e.target.value)} sx={{ minWidth: 90 }}>
          {paisesDisponibles.map((p) => <MenuItem key={p} value={p}>{p}</MenuItem>)}
        </Select>
      ) : (
        <Typography variant="body2" fontWeight={700}>{paisCodigo}</Typography>
      )}

      <Typography variant="caption"
                  sx={{ fontWeight: 700, textTransform: 'uppercase', color: 'text.secondary', letterSpacing: 0.5, ml: 1 }}>
        Ciclo
      </Typography>
      <Select size="small" value={cicloId ?? ''} onChange={(e) => setCicloVer(Number(e.target.value))}
              sx={{ minWidth: 170 }} displayEmpty>
        {ciclosDisponibles.map((c) => (
          <MenuItem key={c.id} value={c.id}>
            {(c.nombre_canonico || c.nombre)}{c.id === cicloAbiertoId ? ' · Abierto' : ''}
          </MenuItem>
        ))}
      </Select>

      {esSoloLectura
        ? <Chip size="small" color="warning" icon={<LockOutlined />} label="Solo lectura" />
        : <Chip size="small" color="success" label="Abierto · editable" />}
    </Paper>
  );
}
```

- [ ] **Step 2: Montar en MainLayout, arriba del Outlet**

En `frontend/src/components/layout/MainLayout.tsx`, añade el import junto a los demás (después de la línea 14):

```tsx
import CicloPaisHeader from '../CicloPaisHeader';
```

Y reemplaza el bloque del contenido (líneas 141-143):

```tsx
        <Box sx={{ flexGrow: 1, p: 3, bgcolor: '#f5f6fa' }}>
          <CicloPaisHeader />
          <Outlet />
        </Box>
```

- [ ] **Step 3: Verificar build**

Run (en `frontend`): `npm run build`
Expected: PASS.

- [ ] **Step 4: Smoke en el navegador (preview)**

Levanta el frontend (`npm run dev` o el server de preview del harness) y verifica:
- La barra superior muestra `CR · Ciclo N · Abierto` (informativo, sin dropdown).
- Debajo del AppBar aparece el encabezado con País (Select si eres admin) y Ciclo (Select, marca el abierto con "· Abierto"); chip "Abierto · editable".
- Al elegir un ciclo distinto del abierto, el chip cambia a "Solo lectura".

Documenta el resultado (una captura o descripción textual del snapshot).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CicloPaisHeader.tsx frontend/src/components/layout/MainLayout.tsx
git commit -m "feat(contexto) encabezado por modulo (CicloPaisHeader) en MainLayout"
```

---

### Task 5: LSII usa el contexto global (arregla Ciclo vacío / país descuadrado)

`Lsii.tsx` hoy tiene estado local `paisId`/`cicloId` con selectores propios en el cuerpo, defaulteando país a "RD" y ciclo al global. Esto causa el Ciclo vacío y el país descuadrado. Se reemplaza por lectura directa del store; se elimina el selector local de País y Ciclo (los da el `CicloPaisHeader`); se conserva el selector de **Gerente**. El botón "Evaluar" se deshabilita cuando `esSoloLectura`.

**Files:**
- Modify: `frontend/src/pages/lsii/Lsii.tsx`

**Interfaces:**
- Consumes: `useCicloStore` → `paisCodigo`, `cicloId`, `esSoloLectura`.

- [ ] **Step 1: Leer país/ciclo del store en vez de estado local**

En `Lsii.tsx` (componente `Lsii`, ~línea 198+):
- Sustituye la línea `const cicloGlobal = useCicloStore((s) => s.cicloId);` y el estado local por:

```tsx
const paisCodigo = useCicloStore((s) => s.paisCodigo);
const cicloGlobal = useCicloStore((s) => s.cicloId);
const esSoloLectura = useCicloStore((s) => s.esSoloLectura);
const paisId = paisCodigo ?? '';
const cicloId = cicloGlobal != null ? String(cicloGlobal) : '';
```

- **Elimina** los estados locales `const [paisId, setPaisId] = useState('');` y `const [cicloId, setCicloId] = useState('');` (ahora derivados del store).
- **Elimina** el `useEffect` que hacía `if (cicloGlobal && !cicloId) setCicloId(...)` (líneas ~209-211) y el `useEffect` que autoseleccionaba "RD" en `paisId` (líneas ~218-222) — ya no aplican.
- Mantén `const [gerenteId, setGerenteId] = useState('');`.

- [ ] **Step 2: Quitar los selectores de País y Ciclo del JSX**

En el render, elimina los `<Select>`/controles de **País** y **Ciclo** del cuerpo de LSII (el `CicloPaisHeader` global ya los provee). Conserva el selector de **Gerente** y el de **RM** del formulario de evaluación. Las queries que usan `paisId`/`cicloId` siguen funcionando porque ahora vienen del store.

- [ ] **Step 3: Deshabilitar "Evaluar" en solo lectura**

En el botón/acción que dispara `mutEvaluar` (formulario "Nueva Evaluación"), añade `esSoloLectura` a la condición de deshabilitado:

```tsx
disabled={!formListo || mutEvaluar.isPending || esSoloLectura}
```

Y arriba del formulario, cuando `esSoloLectura`, muestra:

```tsx
{esSoloLectura && (
  <Alert severity="info" sx={{ mb: 2 }}>
    Estás consultando un ciclo cerrado/no abierto — solo lectura. Cambia al ciclo abierto para evaluar.
  </Alert>
)}
```

(`Alert` ya está importado en el archivo; si no, añádelo al import de `@mui/material`.)

- [ ] **Step 4: Verificar build**

Run (en `frontend`): `npm run build`
Expected: PASS. Corrige cualquier referencia a `setPaisId`/`setCicloId` que quedara colgando.

- [ ] **Step 5: Smoke**

En el navegador, entra a Matriz LSII: el cuerpo ya NO tiene un Ciclo vacío ni país "República Dominicana" descuadrado; usa el país/ciclo del encabezado global. En un ciclo cerrado, el botón Evaluar queda deshabilitado con el aviso.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/lsii/Lsii.tsx
git commit -m "fix(contexto) LSII usa pais/ciclo global; evaluar bloqueado en solo lectura"
```

---

### Task 6: Guards de captura — suite Visita

Cada página de captura de Visita debe apagar sus controles de crear/editar cuando `esSoloLectura`. Parrilla y Costo ya calculan un `soloLectura` basado en `ciclo.cerrado`; se generaliza a `esSoloLectura` del store (que cubre "ciclo distinto del abierto", no solo "cerrado").

**Files:**
- Modify: `frontend/src/pages/visita/ParrillaVisita.tsx:44-45`
- Modify: `frontend/src/pages/visita/CostoRoiVisita.tsx` (equivalente a Parrilla)
- Modify: `frontend/src/pages/visita/RegistrarVisita.tsx`
- Modify: `frontend/src/pages/visita/PlaneacionVisita.tsx` (Planeación del Ciclo)
- Modify: `frontend/src/pages/visita/RupturaVisita.tsx` (si tiene acción de cierre/registro)

**Interfaces:**
- Consumes: `useCicloStore` → `esSoloLectura` (y ya usan `cicloId`/`ciclo`).

- [ ] **Step 1: Parrilla — generalizar a esSoloLectura**

En `ParrillaVisita.tsx`:
- Línea 28: cambia `const { cicloId, ciclo } = useCicloStore();` por `const { cicloId, ciclo, esSoloLectura } = useCicloStore();`
- Líneas 44-45: cambia

```tsx
  const cerrado = !!ciclo?.cerrado;
  const soloLectura = !esGestor || vistaVM || cerrado;
```
por
```tsx
  const cerrado = esSoloLectura;               // "no editable" = ciclo != abierto (cubre cerrado y futuro)
  const soloLectura = !esGestor || vistaVM || esSoloLectura;
```

(Se conserva el nombre `cerrado` para no romper usos posteriores en el archivo; ahora refleja "no editable".)

- [ ] **Step 2: Costo/ROI — mismo cambio**

En `CostoRoiVisita.tsx` (línea ~34 `const { cicloId, ciclo } = useCicloStore();`): añade `esSoloLectura` al destructuring y sustituye cualquier `ciclo?.cerrado` usado para deshabilitar edición por `esSoloLectura`. Deshabilita los botones "Guardar"/"Importar Excel" con `|| esSoloLectura`.

- [ ] **Step 3: Registrar Visita — bloquear registro fuera del ciclo abierto**

En `RegistrarVisita.tsx`:
- Añade al inicio del componente: `const esSoloLectura = useCicloStore((s) => s.esSoloLectura);` (importa `useCicloStore` desde `'../../store/ciclo.store'`).
- Deshabilita el botón de "Guardar"/"Registrar visita" (y el de "No visita"): añade `|| esSoloLectura` a su `disabled`.
- Sobre la tarjeta de captura, cuando `esSoloLectura`, muestra `<Alert severity="info" sx={{ mb: 2 }}>Ciclo en solo lectura — el registro de visitas solo está disponible en el ciclo abierto.</Alert>` (`Alert` ya está importado).

- [ ] **Step 4: Planeación — bloquear guardar**

En `PlaneacionVisita.tsx` (Planeación del Ciclo): añade `const esSoloLectura = useCicloStore((s) => s.esSoloLectura);`, deshabilita el botón "GUARDAR PLANEACIÓN" con `|| esSoloLectura`, y muestra el mismo `<Alert>` de solo-lectura cuando aplique. (Si el archivo tiene otro nombre, localízalo por la ruta `/visita/planeacion` en `App.tsx`.)

- [ ] **Step 5: Ruptura/Cierre — bloquear la acción de cierre**

En `RupturaVisita.tsx` (o el componente de Ruptura/Cierre): si expone una acción de escritura (p. ej. "Cerrar ciclo"), deshabilítala con `|| esSoloLectura` y muestra el aviso. Si es puramente informativa, no requiere cambios (el encabezado global ya da el contexto).

- [ ] **Step 6: Verificar build**

Run (en `frontend`): `npm run build`
Expected: PASS.

- [ ] **Step 7: Smoke**

En el navegador, con el ciclo abierto: los botones de captura de Visita están habilitados. Cambia en el encabezado a un ciclo cerrado: los botones se deshabilitan y aparece el aviso de solo lectura. Registrar una visita en solo-lectura no es posible; forzando la llamada, el backend responde 409 (Task 1).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/visita
git commit -m "feat(contexto) suite Visita: captura solo en ciclo abierto (esSoloLectura)"
```

---

### Task 7: Guards de captura — Exámenes + Categorización

**Files:**
- Modify: `frontend/src/pages/examenes/ConsolidacionPanel.tsx:21`
- Modify: `frontend/src/pages/examenes/Examenes.tsx:69`
- Modify: `frontend/src/pages/categorizacion/Categorizacion.tsx` (captura, si la tiene)
- Modify: `frontend/src/pages/admin/CategorizacionAdmin.tsx` (carga Excel)

**Interfaces:**
- Consumes: `useCicloStore` → `esSoloLectura` (ya usan `cicloId`/`paisCodigo`/`ciclo`).

- [ ] **Step 1: Consolidación — bloquear consolidar fuera del abierto**

En `ConsolidacionPanel.tsx`:
- Línea 21: cambia `const { cicloId, paisCodigo, ciclo } = useCicloStore();` por `const { cicloId, paisCodigo, ciclo, esSoloLectura } = useCicloStore();`
- En el botón "CONSOLIDAR CICLO → KPI", añade `|| esSoloLectura` a su `disabled`.
- El panel ya muestra "Ciclo abierto"/"Pendiente"; cuando `esSoloLectura`, añade sobre el botón `<Alert severity="info">La consolidación solo se ejecuta sobre el ciclo abierto.</Alert>` (importa `Alert` si no está).

- [ ] **Step 2: Exámenes — crear examen solo en ciclo abierto**

En `Examenes.tsx`:
- Línea 69: cambia `const { cicloId } = useCicloStore();` por `const { cicloId, esSoloLectura } = useCicloStore();`
- Deshabilita los botones "CREAR BORRADOR" y "Crear examen con IA" con `|| esSoloLectura`, y muestra el aviso de solo-lectura sobre el formulario "Nuevo examen" cuando aplique.

- [ ] **Step 3: Categorización — captura/carga solo en ciclo abierto**

En `Categorizacion.tsx` y `CategorizacionAdmin.tsx`: añade `const esSoloLectura = useCicloStore((s) => s.esSoloLectura);` y deshabilita las acciones de escritura (`Calcular`, `Recalcular`, `Cargar Excel`) con `|| esSoloLectura`, con el mismo aviso. (Si `Categorizacion.tsx` es puramente de lectura, solo aplica a `CategorizacionAdmin.tsx`.)

- [ ] **Step 4: Verificar build**

Run (en `frontend`): `npm run build`
Expected: PASS.

- [ ] **Step 5: Smoke**

En el navegador: en el ciclo abierto, Exámenes deja crear y Consolidación deja consolidar. En un ciclo cerrado, ambos botones se deshabilitan con el aviso.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/examenes frontend/src/pages/categorizacion frontend/src/pages/admin/CategorizacionAdmin.tsx
git commit -m "feat(contexto) Examenes y Categorizacion: captura solo en ciclo abierto"
```

---

### Task 8: Docs + verificación final

**Files:**
- Modify: `CLAUDE.md` (§23, nota de "Contexto global País+Ciclo")
- Modify (si aplica): `C:\Users\Lenovo\Proyecto\MSM\CLAUDE.md` se actualiza en la Task 9 (porte).

**Interfaces:** ninguna (documentación + verificación).

- [ ] **Step 1: Actualizar la nota de contexto en CLAUDE.md**

En `MSM-postgres/CLAUDE.md`, §23 (Convenciones · Frontend), reemplaza la viñeta "**Contexto global País+Ciclo**" por:

```md
- **Contexto global País+Ciclo (v2)**: tienda Zustand en `frontend/src/store/ciclo.store.ts` distingue
  `cicloAbierto` (de trabajo, único editable) de `cicloId`/`ciclo` (en consulta, default = abierto);
  `esSoloLectura` se deriva de compararlos. La barra superior (`CicloPaisBadge`) es **informativa**;
  el `CicloPaisHeader` (montado 1 vez en `MainLayout`, arriba del `Outlet`) da país (Select solo para
  roles multipaís) y ciclo (default abierto) a todos los módulos. Los módulos de **captura** leen
  `esSoloLectura` para apagar sus controles; el backend rechaza (409) cualquier escritura sobre un ciclo
  cerrado vía `recalculo_service.validar_ciclo_abierto`. RM/Gerentes ven su país fijo; nadie edita ciclos
  cerrados/futuros (sin excepción para ADMIN).
```

- [ ] **Step 2: Build + suite completa**

```bash
cd C:\Users\Lenovo\Proyecto\MSM-postgres\frontend && npm run build
cd C:\Users\Lenovo\Proyecto\MSM-postgres\backend && python -m pytest -q
```
Expected: frontend build PASS; backend suite PASS.

- [ ] **Step 3: Smoke integral en el navegador**

Recorre: Dashboard, Ranking, Productividad (solo-lectura → solo encabezado), Matriz LSII, Exámenes, Planeación, Cobertura Visita, Registrar Visita, Parrilla, Costo. En cada uno el encabezado muestra País+Ciclo. En ciclo abierto se puede capturar; al cambiar a un ciclo cerrado, los módulos de captura quedan en solo lectura. La barra superior siempre muestra el ciclo abierto (informativa).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(contexto) actualizar convencion de contexto Pais+Ciclo v2"
```

---

### Task 9: Portar a la edición SQL Server (MSM)

Todo el cambio es ORM + React dialecto-agnóstico. Se porta con parches, como el control v1.

**Files:**
- (En `C:\Users\Lenovo\Proyecto\MSM`) los mismos archivos, aplicados vía `git am`.

**Interfaces:** ninguna nueva.

- [ ] **Step 1: Generar los parches desde MSM-postgres**

Desde `C:\Users\Lenovo\Proyecto\MSM-postgres`, identifica el rango de commits de esta rama (Tasks 1-8) y genera los parches a una carpeta temporal:

```bash
git format-patch <base>..HEAD -o C:/Users/Lenovo/AppData/Local/Temp/claude/contexto-v2-patches
```
(`<base>` = el commit anterior al primer commit de Task 1; usa `git log --oneline` para ubicarlo.)

- [ ] **Step 2: Aplicar en MSM (rama nueva)**

```bash
cd C:\Users\Lenovo\Proyecto\MSM
git checkout -b feat/contexto-pais-ciclo-v2
git am C:/Users/Lenovo/AppData/Local/Temp/claude/contexto-v2-patches/*.patch
```
Si algún parche falla por diferencias de ruta/dialecto, resuélvelo manualmente (`git am --show-current-patch=diff`, editar, `git add`, `git am --continue`). El frontend es idéntico entre ediciones; el backend solo difiere en dialecto, no en estos archivos de guard/router.

- [ ] **Step 3: Verificar en MSM**

```bash
cd C:\Users\Lenovo\Proyecto\MSM\frontend && npm run build
cd C:\Users\Lenovo\Proyecto\MSM\backend && python -m pytest -q
```
Expected: build PASS; pytest PASS (SQL Server). Si el backend no puede conectar a SQL Server en este entorno, corre al menos los tests que no requieren BD y documenta la limitación.

- [ ] **Step 4: Actualizar CLAUDE.md de MSM**

Aplica la misma edición del §23 (Step 1 de Task 8) en `C:\Users\Lenovo\Proyecto\MSM\CLAUDE.md` si el `git am` no la trajo idéntica.

- [ ] **Step 5: Commit (si quedó algo fuera de los parches)**

```bash
git add -A
git commit -m "docs(contexto) sincronizar CLAUDE.md contexto Pais+Ciclo v2 (edicion SQL Server)"
```

---

## Notas de ejecución

- **Orden**: Task 1 (backend) puede ir en paralelo conceptual con 2-4 (frontend base), pero el ejecutor secuencial las hace en orden. Tasks 5-7 dependen de 2-4 (store + header). Task 8 cierra PostgreSQL; Task 9 porta a SQL Server.
- **Rama**: crea una rama `feat/contexto-pais-ciclo-v2` en `MSM-postgres` antes de Task 1 (no trabajar sobre master).
- **Modelo de subagentes sugerido**: Task 1 (backend, integración) y Tasks 5-7 (varios archivos) → modelo estándar; Tasks 2-4, 8 (archivos acotados/mecánicos) → modelo económico; revisión final de rama → modelo más capaz.
