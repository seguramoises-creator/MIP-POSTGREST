# Historial accionable del Simulacro — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hacer clicables las tarjetas del historial "Mis prácticas" en el Simulacro: "En curso" reanuda en la ronda pendiente; "Finalizada" abre la pantalla de resultado.

**Architecture:** Cambio frontend-only en `Simulacro.tsx`. Se reutiliza el estado existente (`sesion/idx/feedback/seleccion/resultado`) y el service `detalleSimulacro(sesionId)` (ya existe, apunta a `GET /formacion/simulacro/sesion/{id}`). Una mutation de React Query `abrir` orquesta la apertura y ramifica según si la sesión trae `resultado` (finalizada) o no (en curso → primera ronda pendiente, con borde de finalización directa).

**Tech Stack:** React 18 + TypeScript, MUI v6, TanStack Query v5, Vite.

## Global Constraints

- Cero cambios de backend, modelo, migración o tipos: `detalleSimulacro` y todos los tipos (`SesionSimulacro`, `RondaSimulacro`, `ResultadoSimulacro`) ya existen en `frontend/src/services/formacion.service.ts`.
- El único archivo a modificar es `frontend/src/pages/formacion/Simulacro.tsx`.
- No agregar tests automatizados (lógica de presentación; el motor de la Fase 8 ya está cubierto). Verificación = build (`tsc`) + smoke en vivo.
- Seguir el estilo del archivo: MUI `sx`, mutations de React Query, español en copy de UI.
- No introducir estado manual redundante donde una mutation de React Query ya da `isPending`/`variables`.

---

### Task 1: Helper de apertura + ramificación (reanudar / ver resultado / finalizar)

Introduce la lógica de abrir una sesión del historial. No toca aún el JSX de las tarjetas (Task 2), pero deja lista y probada por build la función que consumen.

**Files:**
- Modify: `frontend/src/pages/formacion/Simulacro.tsx`

**Interfaces:**
- Consumes (de `services/formacion.service.ts`, ya existentes):
  - `detalleSimulacro(sesionId: number): Promise<{ sesion: SesionSimulacro; rondas: RondaSimulacro[]; resultado: ResultadoSimulacro | null }>`
  - `finalizarSimulacro(sesionId: number): Promise<ResultadoSimulacro>`
  - tipos `SimulacroIniciado = { sesion: SesionSimulacro; rondas: RondaSimulacro[] }`
- Produce (para Task 2):
  - una mutation `abrir` con forma `{ mutate: (id: number) => void; isPending: boolean; variables?: number; isError: boolean; reset: () => void }`

- [ ] **Step 1: Importar `detalleSimulacro` en el bloque de imports del service**

En el import desde `'../../services/formacion.service'` (actualmente trae `iniciarSimulacro, responderRonda, finalizarSimulacro, vozRonda, misSesionesSimulacro, resumenSimulacro` + tipos), añadir `detalleSimulacro`:

```tsx
import {
  iniciarSimulacro, responderRonda, finalizarSimulacro, vozRonda,
  misSesionesSimulacro, resumenSimulacro, detalleSimulacro,
  type SimulacroIniciado, type RondaSimulacro, type ResultadoSimulacro,
} from '../../services/formacion.service';
```

- [ ] **Step 2: Añadir la mutation `abrir` dentro del componente `Simulacro`**

Colocarla junto a las mutations `iniciar`/`responder`/`finalizar` (después de `finalizar`, antes de `reproducir`). Encapsula toda la ramificación de §4.1 del spec:

```tsx
const abrir = useMutation({
  mutationFn: (id: number) => detalleSimulacro(id),
  onSuccess: (d) => {
    // Finalizada: el detalle trae el resultado → pantalla de resultado.
    if (d.resultado) {
      setResultado(d.resultado);
      return;
    }
    // En curso: hidratar y caer en la primera ronda pendiente.
    const pendiente = d.rondas.findIndex((r) => r.opcion_seleccionada === null);
    if (pendiente === -1) {
      // Todas respondidas pero sin finalizar: cerrar la práctica directo.
      finalizar.mutate(d.sesion.id);
      return;
    }
    setSesion({ sesion: d.sesion, rondas: d.rondas });
    setIdx(pendiente);
    setFeedback(null);
    setSeleccion(null);
    reproducir(d.rondas[pendiente]);
  },
});
```

Notas:
- `setResultado`, `setSesion`, `setIdx`, `setFeedback`, `setSeleccion`, `reproducir` y la mutation `finalizar` ya existen en el componente.
- El tipo de `setSesion` es `SimulacroIniciado | null`; `{ sesion: d.sesion, rondas: d.rondas }` encaja (mismo shape, `resultado` se descarta).

- [ ] **Step 3: Verificar que compila (tsc)**

Run: `cd frontend && npm run build`
Expected: build OK, sin errores de TypeScript. (La mutation aún no se usa en el JSX; TypeScript no marca variables de hook sin usar como error, pero si el linter del build fallara por "unused", el Task 2 la consume en el mismo push — para mantener el paso verde, continuar a Task 2 antes de dar por cerrada la verificación de build. Si `npm run build` marcara `abrir` como no usada aquí, hacer Steps de Task 2 y correr el build una sola vez al final.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/formacion/Simulacro.tsx
git commit -m "feat(formacion) Simulacro: helper de apertura de sesion (reanudar/ver resultado)"
```

---

### Task 2: Tarjetas del historial clicables + estado de carga + error

Conecta la mutation `abrir` (Task 1) a la UI: tarjetas clicables en `PantallaInicio`, spinner en la que se abre, y Alert de error. `PantallaInicio` recibe `abrir` por props desde `Simulacro`.

**Files:**
- Modify: `frontend/src/pages/formacion/Simulacro.tsx`

**Interfaces:**
- Consumes: la mutation `abrir` de Task 1.
- Produce: UI final; no expone nada a tareas posteriores.

- [ ] **Step 1: Pasar `abrir` a `PantallaInicio` en el render de la pantalla de inicio**

Reemplazar la línea actual:

```tsx
  if (!sesion) {
    return <PantallaInicio iniciar={iniciar} />;
  }
```

por:

```tsx
  if (!sesion) {
    return <PantallaInicio iniciar={iniciar} abrir={abrir} />;
  }
```

- [ ] **Step 2: Ampliar la firma de `PantallaInicio` para recibir `abrir`**

Reemplazar la firma actual:

```tsx
function PantallaInicio({ iniciar }: {
  iniciar: { isPending: boolean; isError: boolean; mutate: () => void };
}) {
```

por (añade el prop `abrir` con la forma mínima que se usa: `mutate(id)`, `isPending`, `variables`, `isError`):

```tsx
function PantallaInicio({ iniciar, abrir }: {
  iniciar: { isPending: boolean; isError: boolean; mutate: () => void };
  abrir: { isPending: boolean; isError: boolean; variables?: number; mutate: (id: number) => void };
}) {
```

- [ ] **Step 3: Añadir el import de `CircularProgress` si no está, y usarlo — ya está importado**

Verificar el bloque de imports de MUI: `CircularProgress` ya aparece (se usa en la pantalla de ronda). No añadir import duplicado. Si por refactor se hubiera quitado, reincorporarlo al import de `@mui/material`.

- [ ] **Step 4: Hacer clicable cada tarjeta "Mis prácticas" con spinner y bloqueo**

Reemplazar el bloque del `.map` del historial del RM (el que hoy renderiza cada `<Card key={s.id} ...>` con el `<Chip>` de estado) por una versión clicable:

```tsx
          ) : (historial.data || []).map((s) => {
            const abriendoEsta = abrir.isPending && abrir.variables === s.id;
            return (
              <Card key={s.id} elevation={0} role="button"
                onClick={() => { if (!abrir.isPending) abrir.mutate(s.id); }}
                sx={{
                  border: '1px solid #e0e7ef', borderRadius: 2, mb: 1,
                  cursor: abrir.isPending ? 'default' : 'pointer',
                  opacity: abrir.isPending && !abriendoEsta ? 0.6 : 1,
                  '&:hover': { borderColor: abrir.isPending ? '#e0e7ef' : '#90a4c4' },
                }}>
                <CardContent sx={{ py: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{s.medico} · {s.estilo}</span>
                  <Stack direction="row" spacing={1} alignItems="center">
                    {abriendoEsta && <CircularProgress size={16} />}
                    <Chip size="small" label={s.finalizada ? 'Finalizada' : 'En curso'}
                      color={s.finalizada ? 'success' : 'default'} />
                  </Stack>
                </CardContent>
              </Card>
            );
          })}
```

- [ ] **Step 5: Añadir el Alert de error de apertura sobre la lista del RM**

Justo antes del `<Typography variant="subtitle1" fontWeight={700} mb={1}>Mis prácticas</Typography>` (dentro del `esRM ?` branch), insertar:

```tsx
          {abrir.isError && (
            <Alert severity="warning" sx={{ mb: 2 }}>No se pudo abrir la práctica.</Alert>
          )}
```

(`Alert` y `Stack` ya están importados de `@mui/material`.)

- [ ] **Step 6: Verificar que compila (tsc + build)**

Run: `cd frontend && npm run build`
Expected: build OK, sin errores de TypeScript ni de linter (la mutation `abrir` ahora sí se consume en el JSX).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/formacion/Simulacro.tsx
git commit -m "feat(formacion) Simulacro: historial clicable (reanudar En curso / ver resultado Finalizada)"
```

---

## Verificación en vivo (tras Task 2, no es un commit)

Manual/asistida, minteando JWT (nunca escribir contraseña):

1. Iniciar práctica, responder **1 de 3** rondas, recargar la página → volver a la pantalla de inicio.
2. Click en la tarjeta "En curso" → debe caer en la **ronda 2** (primera pendiente), reproducir su voz, sin fuga de la respuesta correcta.
3. Terminar la práctica; click en esa tarjeta ya "Finalizada" → pantalla de resultado D/P/A/E.
4. Borde: responder las 3 rondas sin pulsar "Ver resultado", recargar, click "En curso" → finaliza directo y muestra el resultado.
5. Forzar un 404 (id inexistente) o abrir con otro RM → Alert "No se pudo abrir la práctica.", se queda en inicio.

---

## Self-Review

- **Cobertura del spec:**
  - §4.1 reanudar/ver-resultado/borde → Task 1 (mutation `abrir`).
  - §4.2 tarjetas clicables + spinner + bloqueo → Task 2 Steps 4.
  - §4.3 estado con mutation (isPending/variables) → Task 1 Step 2 + Task 2 Step 4.
  - §5 manejo de errores → Task 2 Step 5.
  - §6 fuera de alcance → respetado (sin replay, sin backend, solo `mis-sesiones`).
  - §7 verificación → sección "Verificación en vivo".
- **Placeholder scan:** sin TBD/TODO; todo el código de cada paso está completo.
- **Consistencia de tipos:** `abrir.mutate(id: number)`, `abrir.variables?: number`, `detalleSimulacro(id): Promise<{sesion, rondas, resultado}>`, `setSesion(SimulacroIniciado | null)` — coherentes entre Task 1 y Task 2.
