# Ampliación del Módulo de Formación — Plan de implementación

Fuente: `Prompt_Modulo_Formacion_Ampliado_Para_Moises.txt` v1.0 (jul-2026, Laboratorio Mallén).
Benchmark de contexto: `Benchmark_Modulo_Formacion_VISTA.html`.

**Objetivo:** convertir Formación de módulo aislado en el lazo cerrado
Formación → Competencia (LSII) → Calendario de Coaching → Refuerzo → KPI →
Plan de Cierre de Brechas, que retroalimenta a Formación.

---

## Lo que YA existe y no se recrea

Verificado leyendo el código, no asumido. Buena parte del §4-§12 se **integra** con
módulos vivos en vez de construirse desde cero:

| Pieza del prompt | Qué existe hoy en VISTA | Consecuencia |
|---|---|---|
| Matriz LSII (§6) | `DW.FACT_EvaluacionReceptividad` con **los dos ejes**: `score_receptividad` (X) y `score_desempeno` (Y) | **No hay eje nuevo que crear.** Cambia la FÓRMULA del eje Y — ver punto abierto 8 |
| Exámenes (§4 paso 3-8) | Esquema `exam` completo (`DimExamen`, `DimPregunta`, `FactAsignacionExamen`, `FactIntentoExamen`) | La ruta de Onboarding referencia exámenes existentes |
| Generación con IA | `examen_ia_service.py` + `exam.FactFuenteIA` | Ya hay material fuente para IA; **pero acoplado a Anthropic** (§20 es brecha real) |
| Coaching MORE (§6.2, §9.5) | Esquema `coaching` (`Sesion`, `ItemEvaluado`, `ItemCatalogo`), escala D/P/A/E | El promedio MORE sale de aquí |
| Certificaciones (§6.2, §8.2) | Vigencia 12 meses ya implementada | Alimenta Competencia y Ranking |
| Visibilidad por rol (§6.4, §11.5) | Matriz RBAC/ABAC con alcances `own/team/all` (§25 de CLAUDE.md) | **No se programa a mano**: se agregan recursos a la matriz |
| Ciclo/país global | `ciclo.store.ts` + guard de ciclo cerrado | Todo lo nuevo lo hereda |

**Esquema nuevo:** `formacion`, siguiendo la convención de `exam` / `coaching` / `cat`.

---

## Fases

Orden del §17 del prompt, ajustado por las dependencias reales encontradas.

### Fase 0 — Capa de abstracción de IA (§20) · PREREQUISITO
`§17.11` la exige antes de conectar cualquier proveedor. Hoy `examen_ia_service`
llama a Anthropic directo.
- `Security.DIM_IAConexion` (credenciales **cifradas en reposo**, §20.6).
- Adaptadores `texto` y `voz` con interfaz única; el resto del código nunca llama
  a un SDK concreto.
- Panel Superadmin con los 9 campos del §20.4, "Probar conexión" y auditoría.
- Migrar `examen_ia_service` a la capa (sin cambiar su comportamiento).

### Fase 1 — Modelo de datos completo (§17.1)
Las ~15 tablas de §4 a §12 + §20, con sus relaciones (§13). Migración escrita a
mano (convención del proyecto para esquemas nuevos).

### Fase 2 — Onboarding + Biblioteca (§4, §5)
Van juntas: el gating de exámenes del §5.3 es lo que hace funcionar el paso 6 de
la ruta. Incluye Productos de Línea (§4.3, principal/relacionado).

### Fase 3 — Eje Competencia en LSII (§6)
Prerequisito del Calendario. Cambia `resolver_score_desempeno`. **Bloqueado por el
punto abierto 8** hasta que el cliente decida.

### Fase 4 — Calendario de Coaching (§7)
Mapeo cuadrante→frecuencia **como parámetro configurable**, no hardcodeado (§17.5).
Desempate por menor ROI del ciclo anterior.

### Fase 5 — Refuerzo de Memoria (§10) + KPI (§11)
El corazón operativo. Dos métricas que nunca se mezclan (§10.8), revelado inmediato
(§10.7), notificación dual (§10.4).

### Fase 6 — Ranking gamificado (§8)
Depende de puntos de Refuerzo (§10.6) y de hitos de Onboarding.

### Fase 7 — Plan de Cierre de Brechas (§12)
Motor de reglas (no IA) sobre las vistas del §11. Umbrales configurables.

### Fase 8 — Simulacro IA (§9) · Fase 3 del roadmap, no bloqueante
Último por diseño. Voz sobre la capa de la Fase 0.

---

## Puntos abiertos — NO resolver en silencio

El §15 lista 7 y el §17.13 obliga a señalarlos. La revisión del código agrega uno más.

1. **(§4.5)** Bloqueo estricto vs. pasos en paralelo en la ruta.
2. **(§4.5)** Farmacología/Anatomía/Patología: ¿por línea o por producto cuando hay más de 2 principales?
3. **(§6.2)** Ponderación exacta del eje Competencia (peso igual certificaciones/MORE, u otro).
4. **(§7.2)** Tabla de frecuencia por cuadrante LSII.
5. **(§10.2.1)** Espaciado por defecto: fijo 48h (pedido) vs. creciente (recomendado por la literatura).
6. **(§12.3)** Umbrales de las 5 reglas del Plan de Cierre.
7. **(§20.8)** Lista cerrada de proveedores de IA a soportar desde el día uno.
8. **NUEVO — colisión con lo ya implementado.** El §6 asume que la Matriz LSII solo
   tiene el eje subjetivo "Compromiso" y que "Competencia" es un eje nuevo. **No es
   así:** el eje Y ya existe (`score_desempeno`) y hoy se alimenta del **score del
   ranking** (los 8 KPIs). Cambiarlo a `f(certificaciones, MORE)` **redefine el
   cuadrante de todos los RM ya evaluados** y rompe la comparabilidad con el
   histórico. Hay tres salidas y es decisión del cliente:
   - (a) Reemplazar la fórmula del eje Y — lo que pide el prompt literalmente.
   - (b) Añadir Competencia como **tercer** dato, mostrado junto al desempeño, sin
     cambiar la clasificación D1-D4 existente.
   - (c) Reemplazar, pero solo desde un ciclo en adelante, preservando el histórico.

---

## Verificación

Los 8 casos del §16, más los que exige la naturaleza del cambio:
aislamiento por distrito probado **por API y no solo por interfaz** (§16.3),
límites exactos de la tabla de participación (§16.5), e independencia de las dos
métricas (§16.7).
