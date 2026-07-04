# Control global País + Ciclo abierto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir un control global de País + Ciclo en la barra superior que arranca por defecto en el ciclo abierto del país del usuario, y conectar los módulos de Exámenes y la suite de Visita a ese contexto (en vez de listar los 72 ciclos).

**Architecture:** Backend expone el ciclo abierto (filtro `abierto` en `/admin/ciclos` + endpoint `/admin/ciclos/actual`). Un store Zustand (`ciclo.store.ts`) mantiene el país+ciclo global; un componente `CicloPaisSelector` en `MainLayout` lo edita; los módulos leen del store.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (backend, PostgreSQL), React 18 + TypeScript + Vite + MUI v6 + Zustand (frontend). Tests: pytest (backend), `npm run build` + smoke (frontend, como el resto del repo).

## Global Constraints

- Solo la edición **PostgreSQL** (`C:\Users\Lenovo\Proyecto\MSM-postgres`). No tocar la edición SQL Server.
- Fuente de verdad del ciclo actual: flag `Config.DIM_Ciclo.cerrado`. El "ciclo actual" de un país = el ciclo abierto (`cerrado=false`) más reciente (`max(anio, numero)`).
- RBAC del país: `REPRESENTANTE_MEDICO`/`GERENTE_DISTRITO`/`GERENTE_MARCA` fijos a `user.pais_codigo`; `ADMIN`/`PRESIDENCIA`/`DIR_COMERCIAL`/`GERENTE_PRODUCTIVIDAD` pueden cambiar de país.
- Backend: `Mapped[]`/`mapped_column`, `from loguru import logger`, nunca `print()`.
- Frontend: componentes funcionales TS estricto, MUI `sx`, llamadas API en `services/api.ts`.
- Commits en cada tarea. Rama de trabajo (no `master`).

---

### Task 1: Backend — filtro `abierto` + endpoint `/admin/ciclos/actual`

**Files:**
- Modify: `backend/app/api/v1/routers/admin.py` (función `list_ciclos` ~línea 443; añadir helper `_ciclo_actual_de` y endpoint `ciclo_actual`)
- Test: `backend/tests/test_ciclo_actual.py` (crear)

**Interfaces:**
- Produces:
  - `_ciclo_actual_de(ciclos: list) -> Ciclo | None` — pura; toma el abierto más reciente.
  - `GET /admin/ciclos?abierto=true` — filtra `cerrado == False`.
  - `GET /admin/ciclos/actual?pais_codigo=XX` → `CicloResponse | null`.

- [ ] **Step 1: Escribir el test que falla (función pura)**

Crear `backend/tests/test_ciclo_actual.py`:
```python
from types import SimpleNamespace
from app.api.v1.routers.admin import _ciclo_actual_de


def _c(anio, numero, cerrado):
    return SimpleNamespace(anio=anio, numero=numero, cerrado=cerrado)


def test_toma_el_abierto_mas_reciente():
    ciclos = [_c(2026, 1, False), _c(2026, 3, False), _c(2026, 2, True)]
    assert _ciclo_actual_de(ciclos).numero == 3


def test_ignora_los_cerrados():
    ciclos = [_c(2026, 5, True), _c(2026, 2, False)]
    assert _ciclo_actual_de(ciclos).numero == 2


def test_none_si_ninguno_abierto():
    assert _ciclo_actual_de([_c(2026, 1, True)]) is None


def test_none_si_lista_vacia():
    assert _ciclo_actual_de([]) is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_ciclo_actual.py -q`
Expected: FAIL con `ImportError: cannot import name '_ciclo_actual_de'`.

- [ ] **Step 3: Implementar el helper y el endpoint**

En `backend/app/api/v1/routers/admin.py`, junto a los endpoints de ciclos (después de `list_ciclos`), añadir el helper y el endpoint. Modificar `list_ciclos` para el filtro `abierto`:
```python
def _ciclo_actual_de(ciclos):
    """Ciclo abierto (cerrado=False) más reciente: max por (anio, numero)."""
    abiertos = [c for c in ciclos if not c.cerrado]
    if not abiertos:
        return None
    return max(abiertos, key=lambda c: (c.anio, c.numero))


@router.get("/ciclos/actual", response_model=Optional[CicloResponse],
            summary="Ciclo abierto actual de un país")
def ciclo_actual(pais_codigo: str, db: Session = Depends(get_db), _=LecturaCatalogos):
    ciclos = (db.query(Ciclo)
              .filter(Ciclo.activo == True, Ciclo.pais_codigo == pais_codigo)
              .all())
    return _ciclo_actual_de(ciclos)
```
Y reemplazar la firma/cuerpo de `list_ciclos` para aceptar `abierto`:
```python
@router.get("/ciclos", response_model=List[CicloResponse], summary="Listar ciclos")
def list_ciclos(pais_codigo: Optional[str] = None, anio: Optional[int] = None,
                abierto: Optional[bool] = None,
                db: Session = Depends(get_db), _=LecturaCatalogos):
    q = db.query(Ciclo).filter(Ciclo.activo == True)
    if pais_codigo:
        q = q.filter(Ciclo.pais_codigo == pais_codigo)
    if anio:
        q = q.filter(Ciclo.anio == anio)
    if abierto is not None:
        q = q.filter(Ciclo.cerrado == (not abierto))
    return q.order_by(Ciclo.anio, Ciclo.numero).all()
```
Verificar que `Optional` está importado (arriba del archivo ya se usa `Optional`).

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_ciclo_actual.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Verificar el endpoint en vivo (opcional, si el backend PG corre en 8010)**

Run:
```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8010/api/v1/auth/login -d "username=admin&password=Admin1234!" | ./venv/Scripts/python.exe -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s "http://127.0.0.1:8010/api/v1/admin/ciclos/actual?pais_codigo=DO" -H "Authorization: Bearer $TOKEN"
```
Expected: JSON del ciclo abierto más reciente de DO (p. ej. `C12-2026`), no error.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/routers/admin.py backend/tests/test_ciclo_actual.py
git commit -m "feat(ciclos) filtro abierto + endpoint /admin/ciclos/actual (ciclo abierto por pais)"
```

---

### Task 2: Frontend — store global `ciclo.store.ts`

**Files:**
- Create: `frontend/src/store/ciclo.store.ts`
- Referencia de patrón: `frontend/src/store/auth.store.ts`, `frontend/src/services/api.ts`

**Interfaces:**
- Consumes: `GET /auth/me` (`{ pais_codigo, rol }`), `GET /admin/paises`, `GET /admin/ciclos?pais_codigo`, `GET /admin/ciclos/actual?pais_codigo` (Task 1).
- Produces: hook `useCicloStore()` con:
  ```ts
  interface CicloState {
    paisCodigo: string | null;
    cicloId: number | null;
    ciclo: Ciclo | null;
    paisesDisponibles: string[];
    ciclosDisponibles: Ciclo[];
    puedeCambiarPais: boolean;
    init: () => Promise<void>;
    setPais: (codigo: string) => Promise<void>;
    setCiclo: (id: number) => void;
  }
  type Ciclo = { id: number; nombre: string; nombre_canonico?: string; pais_codigo: string; anio: number; numero: number; cerrado: boolean };
  ```

- [ ] **Step 1: Crear el store**

Crear `frontend/src/store/ciclo.store.ts`:
```ts
import { create } from 'zustand';
import api from '../services/api';

export type Ciclo = {
  id: number; nombre: string; nombre_canonico?: string;
  pais_codigo: string; anio: number; numero: number; cerrado: boolean;
};

const ROLES_MULTIPAIS = ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD'];

interface CicloState {
  paisCodigo: string | null;
  cicloId: number | null;
  ciclo: Ciclo | null;
  paisesDisponibles: string[];
  ciclosDisponibles: Ciclo[];
  puedeCambiarPais: boolean;
  init: () => Promise<void>;
  setPais: (codigo: string) => Promise<void>;
  setCiclo: (id: number) => void;
}

export const useCicloStore = create<CicloState>((set, get) => ({
  paisCodigo: null, cicloId: null, ciclo: null,
  paisesDisponibles: [], ciclosDisponibles: [], puedeCambiarPais: false,

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
    const elegido = actual || ciclos[ciclos.length - 1] || null;
    set({ paisCodigo: codigo, ciclosDisponibles: ciclos, ciclo: elegido, cicloId: elegido ? elegido.id : null });
  },

  setCiclo: (id) => {
    const c = get().ciclosDisponibles.find((x) => x.id === id) || null;
    set({ cicloId: id, ciclo: c });
  },
}));
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK, sin errores TS (el store aún no se usa; solo debe tipar bien).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/store/ciclo.store.ts
git commit -m "feat(ciclo) store global Pais+Ciclo (default en ciclo abierto)"
```

---

### Task 3: Frontend — componente `CicloPaisSelector` en la barra superior

**Files:**
- Create: `frontend/src/components/CicloPaisSelector.tsx`
- Modify: `frontend/src/components/layout/MainLayout.tsx` (montar el control en el `Box` derecho del `Toolbar`, ~línea 72; llamar `init()` en un `useEffect`)

**Interfaces:**
- Consumes: `useCicloStore()` (Task 2).

- [ ] **Step 1: Crear el componente**

Crear `frontend/src/components/CicloPaisSelector.tsx`:
```tsx
import { useEffect } from 'react';
import { Box, MenuItem, Select, Chip, Typography } from '@mui/material';
import { useCicloStore } from '../store/ciclo.store';

export default function CicloPaisSelector() {
  const {
    paisCodigo, cicloId, ciclo, paisesDisponibles, ciclosDisponibles,
    puedeCambiarPais, init, setPais, setCiclo,
  } = useCicloStore();

  useEffect(() => { if (!paisCodigo) init().catch(() => {}); }, [paisCodigo, init]);

  if (!paisCodigo) return null;

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      {puedeCambiarPais && paisesDisponibles.length > 1 && (
        <Select size="small" value={paisCodigo} onChange={(e) => setPais(e.target.value)}
                sx={{ minWidth: 90, bgcolor: 'background.paper' }}>
          {paisesDisponibles.map((p) => <MenuItem key={p} value={p}>{p}</MenuItem>)}
        </Select>
      )}
      {!puedeCambiarPais && <Typography variant="body2" fontWeight={600}>{paisCodigo}</Typography>}
      <Select size="small" value={cicloId ?? ''} onChange={(e) => setCiclo(Number(e.target.value))}
              sx={{ minWidth: 150, bgcolor: 'background.paper' }} displayEmpty>
        {ciclosDisponibles.map((c) => (
          <MenuItem key={c.id} value={c.id}>{c.nombre_canonico || c.nombre}</MenuItem>
        ))}
      </Select>
      <Chip size="small" color={ciclo?.cerrado ? 'default' : 'success'}
            label={ciclo?.cerrado ? 'Cerrado' : 'Abierto'} />
    </Box>
  );
}
```

- [ ] **Step 2: Montar en MainLayout**

En `frontend/src/components/layout/MainLayout.tsx`, importar y colocar el control dentro del `Box` derecho del `Toolbar` (el que tiene `display:'flex', alignItems:'center', gap:1.5`, ~línea 72), como primer hijo (antes del nombre de usuario):
```tsx
import CicloPaisSelector from '../CicloPaisSelector';
// ...dentro del <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
<CicloPaisSelector />
```

- [ ] **Step 3: Build + smoke**

Run: `cd frontend && npm run build`
Expected: build OK.
Smoke (con backend PG en 8010 y frontend en 5173, login admin/Admin1234!): el control aparece arriba-derecha, muestra un país (p. ej. `DO`) y su ciclo abierto con Chip verde "Abierto". Cambiar país recarga el ciclo.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/CicloPaisSelector.tsx frontend/src/components/layout/MainLayout.tsx
git commit -m "feat(ciclo) control global Pais+Ciclo en la barra superior"
```

---

### Task 4: Wire Exámenes al store (quitar el dropdown de 72)

**Files:**
- Modify: `frontend/src/pages/examenes/ConsolidacionPanel.tsx` (quitar `useState<Ciclo[]>` + `api.get('/admin/ciclos')` + el `<TextField select>` de ciclos; leer `cicloId`/`paisCodigo`/`ciclo` de `useCicloStore()`)
- Modify: el formulario de creación de examen que tiene el dropdown de ciclos (buscar en `frontend/src/pages/examenes/*.tsx` el `api.get('/admin/ciclos')` o el `<Select>`/`<TextField select label="Ciclo">`)

**Interfaces:**
- Consumes: `useCicloStore()` (`paisCodigo`, `cicloId`, `ciclo`).

- [ ] **Step 1: Localizar los selectores de ciclo en Exámenes**

Run: `cd frontend && grep -rn "admin/ciclos\|label=\"Ciclo\"\|Ciclo seleccionado" src/pages/examenes/`
Anotar cada archivo/línea con un dropdown de ciclos a reemplazar.

- [ ] **Step 2: Reemplazar en `ConsolidacionPanel.tsx`**

Quitar el estado local de ciclos y su `<TextField select>`. Sustituir por el contexto global. Patrón:
```tsx
// ANTES: const [ciclos, setCiclos] = useState<Ciclo[]>([]); ... api.get('/admin/ciclos')...
// ANTES: <TextField select ... >{ciclos.map(...)}</TextField>
// DESPUÉS:
import { useCicloStore } from '../../store/ciclo.store';
// dentro del componente:
const { cicloId, paisCodigo, ciclo } = useCicloStore();
// usar cicloId + paisCodigo del store en cargarEstado/consolidar; mostrar `ciclo?.nombre_canonico` como etiqueta de solo lectura.
useEffect(() => { if (cicloId && paisCodigo) cargarEstado(cicloId, paisCodigo); }, [cicloId, paisCodigo]);
```
El botón "Consolidar" usa `consolidarCiclo(cicloId, paisCodigo)`.

- [ ] **Step 3: Reemplazar en el form de creación de examen**

En el archivo detectado en Step 1, sustituir el dropdown local por `useCicloStore().cicloId` (y `paisCodigo` si el payload lo requiere). El examen se crea contra el ciclo del contexto global.

- [ ] **Step 4: Build + smoke**

Run: `cd frontend && npm run build`
Expected: build OK.
Smoke: en Exámenes ya **no** aparece el desplegable con 72 ciclos; el módulo opera sobre el ciclo del control global.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/examenes/
git commit -m "feat(examenes) usar el contexto global Pais+Ciclo (fin del dropdown de 72 ciclos)"
```

---

### Task 5: Wire la suite Visita al store

**Files (todos en `frontend/src/pages/visita/`):**
- Modify: `PanelMedico.tsx`, `PlaneacionCiclo.tsx` (o el nombre real — verificar), `CoberturaVisita.tsx`, `ProyeccionVisita.tsx`, `RupturaVisita.tsx`, `ParrillaVisita.tsx`, `CostoRoiVisita.tsx`

**Interfaces:**
- Consumes: `useCicloStore()` (`paisCodigo`, `cicloId`, `ciclo`).

- [ ] **Step 1: Inventariar los archivos y sus selectores de ciclo/país**

Run: `cd frontend && ls src/pages/visita/ && grep -rn "admin/ciclos\|cicloId\|pais" src/pages/visita/`
Anotar en cada archivo dónde está el `useState`/`api.get('/admin/ciclos')`/dropdown a reemplazar.

- [ ] **Step 2: Reemplazar el patrón en cada página (ejemplo con `CostoRoiVisita.tsx`)**

Patrón de transformación (aplicar a las 7 páginas):
```tsx
// ANTES (CostoRoiVisita.tsx ~línea 14, 64, 123):
//   const [ciclos, setCiclos] = useState<CicloOpt[]>([]);
//   api.get<CicloOpt[]>('/admin/ciclos').then(...)
//   <TextField select value={cicloId} ...>{ciclos.map(...)}</TextField>
// DESPUÉS:
import { useCicloStore } from '../../store/ciclo.store';
const { cicloId, ciclo } = useCicloStore();
const cerrado = !!ciclo?.cerrado;   // conserva el guard de solo-lectura existente
// eliminar el estado local `ciclos` y su <TextField select> del ciclo;
// donde antes se leía cicloSel/cicloId local, usar el `cicloId`/`ciclo` del store.
```
Para las páginas que además necesitan país (Panel Médico, Parrilla, Costo/ROI), usar `paisCodigo` del store en las llamadas API que lo requieran. Mantener intactos los guards de solo-lectura de ciclos cerrados (Parrilla/Costo).

- [ ] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: build OK. Corregir cualquier referencia a variables locales de ciclo eliminadas.

- [ ] **Step 4: Smoke por página**

Con backend PG (8010) + frontend (5173): recorrer Panel Médico, Planeación, Cobertura, Proyección, Ruptura, Parrilla, Costo/ROI. Cada una debe operar sobre el país+ciclo del control global (sin su propio dropdown de 72). Cambiar el ciclo en el control global se refleja en la página.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/visita/
git commit -m "feat(visita) suite usa el contexto global Pais+Ciclo (Panel/Planeacion/Cobertura/Proyeccion/Ruptura/Parrilla/Costo)"
```

---

### Task 6: Default al ciclo abierto en módulos que ya tienen selector (ajuste mínimo)

**Files:**
- Modify (solo si es trivial, 1-2 líneas por archivo): las páginas con selector propio que hoy arrancan en otro ciclo — Dashboard, Ranking, Cobertura Predictiva, LSII, Categorización.

**Interfaces:**
- Consumes: `useCicloStore()` (`cicloId` inicial).

- [ ] **Step 1: Para cada página con selector propio, inicializar su `cicloId` local al del store**

Patrón: donde la página hace `const [cicloId, setCicloId] = useState<number|''>('')`, inicializarlo desde el store:
```tsx
import { useCicloStore } from '../../store/ciclo.store';
const cicloGlobal = useCicloStore((s) => s.cicloId);
const [cicloId, setCicloId] = useState<number | ''>('');
useEffect(() => { if (cicloGlobal && cicloId === '') setCicloId(cicloGlobal); }, [cicloGlobal]);
```
Aplicar solo donde sea de bajo riesgo. Si una página es compleja, dejarla como está (fuera de alcance según el spec).

- [ ] **Step 2: Build + smoke**

Run: `cd frontend && npm run build`
Expected: build OK. Smoke: Dashboard/Ranking arrancan mostrando el ciclo abierto por defecto.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/
git commit -m "feat(ciclo) paginas con selector propio arrancan en el ciclo abierto por defecto"
```

---

### Task 7: Documentación + cierre

**Files:**
- Modify: `CLAUDE.md` (nota breve sobre el control global País+Ciclo y el endpoint `/admin/ciclos/actual`)

- [ ] **Step 1: Documentar en CLAUDE.md**

Añadir en la sección de Admin/Ciclos una línea: `GET /admin/ciclos/actual?pais_codigo=XX` (ciclo abierto actual) y `?abierto=true`; y en Frontend, mencionar el store `ciclo.store.ts` + `CicloPaisSelector` como contexto global.

- [ ] **Step 2: Suite completa + build**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -k "not caracterizacion" -q` (esperar verde) y `cd frontend && npm run build` (OK).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(ciclo) control global Pais+Ciclo + endpoint /admin/ciclos/actual"
```

---

## Notas de ejecución

- Correr el backend PG en 8010 y el frontend en 5173 para los smokes (como en la sesión de prueba), con `frontend/.env.local` → `VITE_API_URL=http://127.0.0.1:8010/api/v1`.
- El dato tiene los 72 ciclos abiertos; el control tomará el más reciente por país. Opcional (fuera de este plan): cerrar los ciclos viejos desde Admin para dejar 1 abierto por país.
