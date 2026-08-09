# Médicos TOP — Diseño

**Fecha:** 2026-08-09
**Sub-proyecto:** 4 de la integración VISTA ↔ Laboratorio Mallén
**Estado:** aprobado, pendiente de plan

## 1. Por qué existe

El §7.2 del *Requerimiento de Datos · VISTA · Laboratorios Mallén v2* enumera seis módulos que VISTA debe construir. Cinco reutilizan lecturas de `ext`. **Médicos TOP es el único marcado como "Nada: es desarrollo nuevo"** — y el único que el documento repite tres veces (§3.4, §7.3, §11.5) sin que nadie lo haya recogido.

Son tres reglas de negocio (§7.3, literal):

1. **Validación en la planeación.** Al publicar la programación del ciclo, VISTA verifica que todos los médicos TOP del panel estén incluidos. Si falta alguno, no permite publicar y muestra cuáles faltan.
2. **Control de visita y revisita.** Durante el ciclo, VISTA marca a los médicos TOP que aún no tienen visita o revisita registrada, en la pantalla del representante y en la del Gerente de Distrito.
3. **Recordatorios.** Cuando una visita programada a un médico TOP vence sin ejecutarse, el sistema notifica al representante. Si el ciclo avanza y sigue sin visitarse, escala al Gerente de Distrito.

El sub-proyecto 3 dejó el terreno preparado a propósito: **no escribió `prioridad` dentro de `DIM_TargetMedico.potencial`**, para que este sub-proyecto pudiera modelarla bien. El §11.5 advierte literalmente que *"marcar TOP no es marcar categoría A"*: categoría (A/B/C), frecuencia (F1/F2) y prioridad (TOP/REGULAR) son **tres criterios ortogonales**, y `ext.panelmedico` los envía en tres columnas separadas.

## 2. Dónde vive la prioridad

**Columna nueva `es_top` (Boolean, `NOT NULL`, default `False`) en `Visita.DIM_MedicoVisita`.** Migración `0034` — la primera del sub-proyecto.

Se eligió esa tabla porque es la que ya leen `visita_planeacion_service`, `visita_cobertura_service` y las tres pantallas del módulo de Visita. Poner la prioridad en cualquier otro sitio obligaría a una unión extra en todos los consumidores.

No hay columna reutilizable:
- `DIM_MedicoVisita.categoria` es A/B/C/D del motor de categorización.
- `DIM_MedicoVisita.potencial_prescripcion` es "Alto/Medio/Bajo", otro vocabulario y otro significado.
- `DIM_TargetMedico.potencial` es categoría, y además pertenece al módulo 4DX, no al de Visita.
- `ParrillaPromocional.prioridad` existe pero es un ranking numérico **de productos**, sin relación.

**Booleano y no cadena TOP/REGULAR**: el contrato solo define dos valores y el dominio ya está validado en la recepción del lote. Un booleano evita un segundo vocabulario que mantener sincronizado. YAGNI.

### Sincronización desde el SFA

`integrar_panel_medico` escribe `es_top = (fila.prioridad == "TOP")`, y **lo reafirma en cada integración**, igual que ya hace con `activo` — es dato maestro del SFA, no algo que el representante edite. Un médico que pasa de TOP a REGULAR entre ciclos se actualiza solo. (A diferencia de `nombre_completo`, que solo se escribe al crear para no pisar correcciones manuales del GD.)

La comparación es tolerante a la caja: `(fila.prioridad or "").strip().upper() == "TOP"`. El origen ha demostrado enviar variaciones.

### Ausencia de dato = NO es TOP

Los médicos que el representante da de alta a mano (`estado_aprobacion = PENDIENTE_ALTA`) nunca pasan por `ext.panelmedico`, así que la integración jamás los toca. El default `False` los deja fuera.

Es una decisión deliberada: tratar la ausencia como TOP bloquearía la publicación de la planeación por fichas que ni siquiera vienen del maestro de Mallén, y el representante no tendría forma de desbloquearse.

## 3. Regla 1 — no publicar una planeación que omita un TOP

### El bloqueo

En `visita_planeacion_service.publicar_planeacion()`, tras las validaciones que ya existen (ciclo abierto, no publicada, ≥1 ítem): todo médico con `es_top` que **cuente en el ciclo** debe tener al menos una fila en `PlaneacionCiclo` para ese `(vm_id, ciclo_id)`.

**El filtro es `visita_aprobacion_service.cuenta_en_ciclo`, no `activo` a secas.** Es la misma función que ya usa `visita_cobertura_service._cobertura_base` para decidir qué médicos pertenecen al ciclo. Con `activo` se exigiría planear médicos con alta pendiente de aprobación o que ya causaron baja — dos casos en que el representante no puede hacer nada.

Si falta alguno se levanta **`TopSinPlanearError`**, excepción propia del servicio, que el router traduce a **409** con los nombres en el mensaje.

409 y no 400 porque es un conflicto de estado (la planeación no está en condiciones de publicarse), coherente con `PlaneacionPublicadaError`. Esa excepción existe precisamente porque un `ValueError` genérico escapaba como 500 y el representante nunca leía el motivo real; repetir ese error sería gratuito.

### El aviso, antes del bloqueo

`resumen_planeacion` devuelve además `top_sin_planear: [{id, nombre}]`, que la pantalla muestra en un `Alert` no bloqueante mientras el representante edita — el mismo patrón que ya usa para "Cat. A sin Revisita".

El guardado en borrador **no se restringe**: el representante puede guardar cuantas veces quiera. El bloqueo llega solo al pulsar Publicar, y para entonces ya lleva rato viendo el aviso.

### TOP planeado sin revisita: se avisa, no se bloquea

El §7.3 exige que los TOP estén *"incluidos"*, así que el bloqueo se dispara solo cuando el médico falta por completo. Pero el §3.4 dice que un TOP no puede terminar sin visita **y** revisita: un TOP planeado solo con `V` ya está planeado para incumplir.

`resumen_planeacion` devuelve también `top_sin_revisita`, que se muestra como aviso. **No bloquea.** Respeta la letra del requerimiento y ayuda con su espíritu, sin inventar una restricción que el cliente no pidió.

## 4. Regla 2 — marcar los TOP sin cubrir

`visita_cobertura_service._cobertura_base` ya calcula, por médico del panel, si tiene visita (`V`), revisita (`R`), ambas o ninguna, y arma las listas `sin_visita` y `falta_revisita`. **No hay lógica nueva que escribir**: basta añadir `es_top` a cada ítem y derivar dos listas más, `top_sin_visita` y `top_falta_revisita`.

Solo cuentan las visitas **ejecutadas**, que es lo que ese servicio ya hace.

### Frontend

Un chip **"TOP"** junto al nombre del médico en las tres pantallas que ya existen: `PanelMedico.tsx`, `PlaneacionVisita.tsx` y `CoberturaDashboard.tsx`. Más una sección destacada en el dashboard de cobertura con los TOP pendientes.

**No se crea ninguna pantalla nueva**, y el Gerente de Distrito no necesita una propia: ve las mismas tres con su selector de representante, porque el alcance `R_TEAM` de la matriz RBAC ya se lo concede. No se toca RBAC.

El rótulo es **"TOP"**, nunca "Prioridad": `ParrillaPromocional.prioridad` ya ocupa esa palabra en pantallas vecinas con otro significado (orden de producto 1-N).

## 5. Regla 3 — recordatorio y escalamiento

### 5.1 El traductor de fechas (pieza nueva obligatoria)

`PlaneacionCiclo` **no guarda fechas**: guarda `semana` (1-4) y `dia_semana` (`"Lunes"`…`"Viernes"`, texto libre sin FK). Para saber si una visita programada "venció" hay que traducir `(ciclo.fecha_inicio, semana, dia_semana)` a una fecha de calendario real, saltando fines de semana y feriados.

Ese traductor no existe hoy. **Precisión añadida al escribir el plan:** la fecha planeada se deriva por **calendario puro** — lunes de la semana que contiene `fecha_inicio`, más `(semana-1)` semanas, más el desplazamiento del día — y se acota al rango `[fecha_inicio, fecha_fin]` del ciclo. Los feriados **no mueven** la fecha planeada: si alguien planeó para un día que resultó feriado, la fecha sigue siendo esa; lo que se mide en días hábiles es el **vencimiento** posterior.

Los feriados entran, por tanto, en dos sitios distintos: al contar los días hábiles transcurridos desde la fecha planeada (para el recordatorio) y al calcular el porcentaje del ciclo (para el escalamiento). Ahí sí se usan `cobertura_predictiva_service._networkdays` y `_feriados_pais`, que **sí consultan `Config.DIM_Feriado`**.

> **Trampa a evitar:** hay una segunda implementación de días hábiles en `visita_cobertura_service._dias_habiles` que solo excluye sábado y domingo, ignora `DIM_Feriado`, y usa `date.today()` en vez de la hora local del país. **No se usa esa.** Tampoco se refactoriza aquí — está fuera de alcance y toca un servicio en producción.

Si `dia_semana` viene nulo o con un valor irreconocible, la fila se trata como **no vencida** y se registra en el log. Un dato de planeación incompleto no debe generar un correo de reclamo.

### 5.2 Tabla de avisos enviados (pieza nueva obligatoria)

**`Visita.AvisoTopEnviado`** — migración `0034`, junto con `es_top`.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | Integer PK | |
| `vm_id` | Integer NOT NULL | FK `Config.DIM_RM.id` |
| `ciclo_id` | Integer NOT NULL | FK `Config.DIM_Ciclo.id` |
| `medico_id` | Integer NOT NULL | FK `Visita.DIM_MedicoVisita.id` |
| `tipo_visita` | CHAR(1) NOT NULL | `V` / `R` |
| `tipo_aviso` | String(20) NOT NULL | `RECORDATORIO` / `ESCALAMIENTO` |
| `fecha_envio` | DateTime NOT NULL | UTC |

`UNIQUE(vm_id, ciclo_id, medico_id, tipo_visita, tipo_aviso)`.

Sin esta tabla, un job diario reenviaría el mismo correo cada mañana mientras la visita siguiera vencida. El proyecto **no tiene hoy ningún registro de notificaciones enviadas**, así que no hay nada que reutilizar.

Append-only, como `PlaneacionEvento`. Nunca se borra: si el representante finalmente ejecuta la visita, el aviso ya enviado sigue siendo historia.

### 5.3 Job periódico de reconciliación

**Un job diario** en APScheduler, registrado en el arranque de `app/main.py` junto al scheduler que ya existe.

Es deliberadamente **un cron de reconciliación y no un temporizador por visita**. El único job del proyecto hoy (`programar_correcciones`, de exámenes) usa disparo puntual sobre un `MemoryJobStore` sin persistencia: **cualquier reinicio del contenedor lo pierde en silencio**, sin log de error. Con MSM corriendo en Docker eso no es teórico. Un job por visita planeada, además, serían cientos por ciclo.

El patrón elegido no tiene ese problema: cada corrida vuelve a preguntarle a la base qué está vencido, y el job se re-registra solo en cada arranque. Es el primer cron del proyecto; no hay precedente que copiar.

En cada corrida, para cada ciclo abierto:
- **Recordatorio al representante**: por cada fila de planeación de un médico TOP cuya fecha traducida venció hace ≥ `top_dias_recordatorio` días hábiles y que **no tiene** su visita ejecutada de ese `tipo_visita`. Un correo por representante, agrupando sus médicos pendientes.
- **Escalamiento al Gerente de Distrito**: cuando el ciclo lleva transcurrido ≥ `top_pct_ciclo_escalamiento` de sus días hábiles y el TOP sigue sin cubrir. Un correo por gerente, agrupando a sus representantes.

Ambos consultan `AvisoTopEnviado` antes de enviar y lo escriben después. Se agrupa por destinatario para no enviar veinte correos a la misma persona.

**Los dos avisos son independientes.** El escalamiento no exige que antes se haya enviado el recordatorio: un TOP planeado para la última semana puede cruzar el umbral de escalamiento sin que su fecha haya vencido todavía los `top_dias_recordatorio`. Cada uno tiene su propia fila en `AvisoTopEnviado` gracias a `tipo_aviso`, así que uno no suprime al otro.

**El registro se escribe solo si el envío ocurrió.** Las dos funciones de `notification_service` devuelven cuántos correos enviaron (0 cuando el correo no está configurado, siguiendo el contrato del módulo), y el job escribe `AvisoTopEnviado` únicamente cuando ese retorno es distinto de cero. Marcar como enviado lo que no salió dejaría al representante sin aviso para siempre, en silencio.

**Ciclos cerrados no se procesan.** Es la regla de siempre: son snapshots inmutables y nadie puede ya actuar sobre ellos.

### 5.4 Parámetros configurables

| Parámetro | Default | Significado |
|---|---|---|
| `top_dias_recordatorio` | `2` | Días hábiles tras la fecha planeada antes de avisar al representante |
| `top_pct_ciclo_escalamiento` | `70` | % de días hábiles del ciclo transcurridos antes de escalar al GD |

El porcentaje se mide como **días hábiles transcurridos ÷ días hábiles totales del ciclo**, ambos calculados con el `_networkdays` que respeta `DIM_Feriado` (§5.1), no sobre días naturales.

Editables desde Administración con el mecanismo de configuración en BD que ya usa el SMTP. **El pendiente nº 8 del §10 del requerimiento sigue abierto con Mallén** (si el recordatorio va al vencer la fecha, a mitad de ciclo, o a X días del cierre); cuando respondan, es cambiar un número en pantalla, sin tocar código ni redesplegar.

Los defaults son una posición razonable, no una decisión del cliente. Deben confirmarse.

### 5.5 Destinatarios

El camino que ya usa todo el módulo de notificaciones: `RepresentanteMedico.email` para el recordatorio, y `rm.gerente_id → Gerente.email` para el escalamiento. **No pasa por `Security.DIM_Usuario`.**

Dos funciones nuevas en `notification_service`, con el contrato del módulo: **best-effort, no-op silencioso** si el correo no está configurado, y nunca lanzan hacia el llamador. Un fallo de correo no puede tumbar el job.

Si un representante no tiene gerente asignado o el gerente no tiene correo, se registra en el log y se sigue con el resto.

## 6. Archivos

**Backend**
- `backend/alembic/versions/0034_*.py` — `es_top` + `AvisoTopEnviado`
- `backend/app/models/visita.py` — la columna y el modelo nuevos
- `backend/app/services/visita_top_service.py` — **nuevo**: el traductor de fechas, la detección de TOP sin cubrir y la lógica de los dos avisos
- `backend/app/services/visita_planeacion_service.py` — `TopSinPlanearError` y la validación al publicar
- `backend/app/services/visita_cobertura_service.py` — `es_top` en los ítems y las dos listas nuevas
- `backend/app/services/integracion_visitas_service.py` — poblar y reafirmar `es_top`
- `backend/app/services/notification_service.py` — los dos avisos
- `backend/app/core/scheduler.py` + `app/main.py` — el job diario
- `backend/app/api/v1/routers/visita.py` — traducir `TopSinPlanearError` a 409

**Frontend**
- `PlaneacionVisita.tsx`, `PanelMedico.tsx`, `CoberturaDashboard.tsx` — chip TOP y avisos
- `visita.service.ts` — los campos nuevos en los tipos

## 7. Fuera de alcance (YAGNI)

- **Nada del motor de Score, los indicadores o la integración de hechos.** Este módulo no escribe una sola fila de `FACT_ResultadoIndicador`.
- **Ninguna pantalla nueva**: se extienden las tres existentes.
- **No se toca RBAC**: los alcances `REG_OWN` / `R_TEAM` que existen ya cubren el caso.
- **No se unifican los dos cálculos de días hábiles.** Se usa el correcto y se documenta cuál es; refactorizar el otro toca un servicio en producción sin que este módulo lo necesite.
- **No se persiste el scheduler** ni se arregla el job de exámenes. El diseño de aquí no lo necesita; el de exámenes es un problema aparte que conviene anotar.
- **El GD no gana permiso de publicar ni desbloquear.** Su canal es el escalamiento por correo. Hoy publicar es `REG_OWN` del representante (y ADMIN), y desbloquear es solo ADMIN.

## 8. Verificación

**`es_top` y su sincronización**
1. Un `panelmedico` con `prioridad='TOP'` → `DIM_MedicoVisita.es_top` queda en `True`.
2. `prioridad='REGULAR'` → `False`. `prioridad='top'` (minúscula) → `True` (tolerancia de caja).
3. Un médico que era TOP y llega como REGULAR en el siguiente lote → **se reafirma a `False`**. Es el caso que distingue "reafirmar siempre" de "escribir solo al crear".
4. Un médico de alta manual (nunca en `ext`) → `es_top` es `False`, no nulo.

**Regla 1**
5. Planeación que omite un TOP que cuenta en el ciclo → publicar responde **409** y el mensaje nombra al médico.
6. Planeación que los incluye a todos → publica normal.
7. Un TOP con alta **pendiente de aprobación** omitido → **publica igual**. Es el caso que distingue `cuenta_en_ciclo` de `activo`; con el filtro equivocado el representante quedaría bloqueado sin poder hacer nada.
8. Un TOP dado de baja en un ciclo anterior, omitido → publica igual.
9. `resumen_planeacion` lista `top_sin_planear` mientras se edita, y **guardar en borrador nunca se bloquea**.
10. Un TOP planeado solo con `V` → aparece en `top_sin_revisita` pero **publica igual**.

**Regla 2**
11. Un TOP sin ninguna visita ejecutada → sale en `top_sin_visita`.
12. Un TOP con `V` pero sin `R` → sale en `top_falta_revisita`, no en `top_sin_visita`.
13. Un médico **no** TOP sin visitas → sale en `sin_visita` pero **no** en las listas TOP.
14. Una visita **no ejecutada** no saca al médico de la lista de pendientes.

**Regla 3**
15. El traductor: semana 2, "Miércoles", con un feriado en medio → devuelve la fecha correcta saltando fin de semana y feriado.
16. `dia_semana` nulo o irreconocible → no se considera vencida y no genera correo.
17. Visita a un TOP vencida hace menos de `top_dias_recordatorio` → **no** se avisa. Vencida hace más → se avisa una vez.
18. **Correr el job dos veces seguidas no reenvía el correo** (lo impide `AvisoTopEnviado`). Es el test que justifica la tabla.
19. Con el ciclo por debajo del `top_pct_ciclo_escalamiento` no se escala; por encima y con el TOP sin cubrir, sí.
20. Un ciclo **cerrado** no genera ningún aviso.
21. Un representante sin gerente asignado → se registra en el log y el resto de escalamientos sigue.
22. Con el correo **sin configurar**, el job corre completo sin lanzar y no escribe `AvisoTopEnviado` (no se marca como enviado lo que no se envió).

**Frontend**
23. `npm run build` en verde.
24. El chip TOP aparece en las tres pantallas y el aviso de publicación muestra los nombres que devuelve el 409.
