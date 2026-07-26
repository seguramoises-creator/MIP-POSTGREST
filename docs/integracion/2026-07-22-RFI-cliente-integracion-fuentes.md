# Requerimiento de APIs REST — Integración de fuentes del cliente hacia VISTA

> **Qué es este documento:** especificación de las **APIs REST** que solicitamos al **equipo de TI/
> sistemas del cliente** para alimentar el sistema VISTA. No preguntamos "¿tienen API?"; describimos
> **la API que necesitamos**, endpoint por endpoint, mapeada a cada indicador que VISTA mide hoy.
>
> **Método de integración solicitado: API REST para TODA la información externa.** Leer archivos o
> conectarnos a una base de datos queda solo como **alternativa** si un endpoint no pudiera existir
> (sección 8).
>
> **Cómo usarlo:** envíalo al TI del cliente. Pide que confirmen cada endpoint (o su equivalente) y que
> entreguen **credenciales de sandbox + una respuesta de ejemplo** por cada uno (sección 9).

---

## 1. Qué pedimos, en una frase

APIs REST (JSON) que entreguen, por **país** y por **período**, los datos con los que VISTA calcula sus
indicadores. VISTA **extrae** (pull) de esas APIs una vez por ciclo/mes, valida, y calcula. El cliente
**no** empuja datos ni necesita conocer la lógica de VISTA: solo expone la información en crudo.

## 2. Los 8 indicadores de VISTA y de dónde sale cada uno

| # | Indicador | Período | Fuente | ¿API requerida? |
|---|---|---|---|---|
| 1 | **COB_MD_F1** — Cobertura Médicos Frecuencia 1 | CICLO | **SFA / visita médica** | ✅ API Visitas + Target |
| 2 | **COB_MD_F2** — Cobertura Médicos Frecuencia 2 | CICLO | SFA / visita médica | ✅ API Visitas + Target |
| 3 | **PROM_DIARIO** — Promedio Diario de Visitas | CICLO | SFA / visita médica | ✅ API Visitas + Días hábiles |
| 4 | **COB_FARMACIAS** — Cobertura de Farmacias | CICLO | SFA / visita médica | ✅ API Visitas (farmacias) + Target |
| 5 | **EVO_IR** — Evolución de Prescripciones | MES | **Close-Up** (BD intermedia del cliente) | ✅ API Recetas |
| 6 | **VENTAS** — Ventas vs. Cuota | MES | **ERP** | ✅ API Ventas + Cuotas |
| 7 | EVAL_CONOCIMIENTOS — Exámenes | MES | **VISTA** | ❌ Interno, sin integración |
| 8 | EVAL_COACHING — Coaching | MES | **VISTA** | ❌ Interno, sin integración |

> **6 de 8 requieren API externa**; **4 de esos 6** salen del **sistema de visitas (SFA)** — por eso el
> detalle mayor está en la sección 7.

## 3. Requisitos generales para todas las APIs

- **Protocolo:** HTTPS, respuesta **JSON**.
- **Autenticación:** OAuth 2.0 (client credentials) o API key por header. **No** credenciales en la URL.
- **Filtros obligatorios** en cada endpoint: `pais`, `periodo` (o `fecha_desde`/`fecha_hasta`).
- **Incremental (deseable):** parámetro `actualizado_desde` para traer solo lo cambiado.
- **Paginación:** `page`/`page_size` (o cursor), con total de registros en la respuesta.
- **Idempotencia/estabilidad:** los mismos parámetros devuelven el mismo resultado (para reproceso).
- **Versionado:** ruta versionada (`/v1/...`) para que un cambio no rompa la integración.
- **Errores:** códigos HTTP estándar + cuerpo con detalle.
- **Sandbox:** ambiente de pruebas con datos de ejemplo.
- **Rate limit y volumen:** indicar límites y filas aprox. por período/país.

## 4. API de Maestros (catálogos) — para poder cruzar todo

Necesarios para **mapear** las tres fuentes entre sí y con VISTA. Endpoints (o su equivalente):

| Endpoint | Devuelve (campos mínimos) |
|---|---|
| `GET /v1/maestros/medicos` | `medico_codigo`, `nombre`, `especialidad`, `territorio_codigo`, `activo` |
| `GET /v1/maestros/productos` | `producto_codigo`, `nombre`, `marca`, `linea_terapeutica` |
| `GET /v1/maestros/representantes` | `rep_codigo`, `nombre`, `territorio_codigo`, `gerente_codigo` |
| `GET /v1/maestros/territorios` | `territorio_codigo`, `nombre`, `zona`, `region`, `pais` |
| `GET /v1/maestros/farmacias` | `farmacia_codigo`, `nombre`, `territorio_codigo` |

> **⟦PREGUNTA⟧** ¿Los códigos de médico/producto/rep/territorio son **los mismos** en Close-Up, ERP y
> SFA? Si no, necesitamos la **tabla de equivalencias**. Este es el mayor riesgo de integración.

## 5. API de Recetas (Close-Up) → alimenta EVO_IR

```
GET /v1/recetas?pais={pais}&periodo={YYYY-MM}&page={n}
```
Cada fila:
| Campo | Uso |
|---|---|
| `periodo` | agrupación temporal |
| `medico_codigo` | análisis por médico (⟦PREGUNTA⟧ ¿viene a nivel médico o agregado?) |
| `especialidad` | análisis por especialidad |
| `producto_codigo` | **EVO_IR se calcula por producto** |
| `territorio_codigo` / `rep_codigo` | análisis por territorio/representante |
| `recetas_estimadas` | métrica principal |
| `recetas_captadas` | si Close-Up las separa |
| `recetas_mercado` | **recetas del mercado/competencia** → participación de mercado |

**Cálculo de EVO_IR:** Σ recetas por producto en el período actual vs. el período anterior →
evolución %. *(Requiere que la API entregue también períodos anteriores, o histórico — ver §6.)*

## 6. API de Ventas y Cuotas (ERP) → alimenta VENTAS

```
GET /v1/ventas?pais={pais}&periodo={YYYY-MM}&page={n}
GET /v1/cuotas?pais={pais}&periodo={YYYY-MM}
```
| Endpoint | Campos |
|---|---|
| `/ventas` | `periodo`, `rep_codigo`, `producto_codigo`, `ventas_reales` (importe), `unidades` (opcional) |
| `/cuotas` | `periodo`, `rep_codigo`, `producto_codigo` (o total), `cuota` (importe objetivo) |

**Cálculo de VENTAS:** `cumplimiento = ventas_reales / cuota`; `crecimiento` vs. período anterior.
**⟦PREGUNTA⟧** ¿la cuota sale del mismo ERP? ¿las devoluciones/notas de crédito ya vienen neteadas?

## 7. API de Visitas — el detalle completo (alimenta 4 indicadores)

Los indicadores de cobertura y visitas **no se calculan con un solo número**: VISTA necesita el
**detalle transaccional** de las visitas más el **universo objetivo** (target) y los **días hábiles**.
Con eso VISTA reproduce los 4 indicadores. Tres endpoints:

### 7.1 `GET /v1/visitas` — bitácora de visitas (transaccional)
```
GET /v1/visitas?pais={pais}&periodo={YYYY-MM}&fecha_desde=&fecha_hasta=&page={n}
```
| Campo | Uso |
|---|---|
| `fecha` | día de la visita (para promedio diario y ciclo) |
| `rep_codigo` | representante que visitó |
| `tipo_contacto` | **`MEDICO` o `FARMACIA`** (distingue cobertura médica de farmacias) |
| `contacto_codigo` | `medico_codigo` o `farmacia_codigo` según el tipo |
| `especialidad` | opcional, para análisis |
| `territorio_codigo` | opcional |
| `es_efectiva` | ⟦PREGUNTA⟧ ¿marcan si la visita fue efectiva/realizada vs. planeada? |

### 7.2 `GET /v1/target` — universo objetivo del período (denominador de cobertura)
```
GET /v1/target?pais={pais}&periodo={YYYY-MM}&rep={rep_codigo}
```
| Campo | Uso |
|---|---|
| `rep_codigo` | a quién pertenece el target |
| `tipo_contacto` | `MEDICO` o `FARMACIA` |
| `contacto_codigo` | médico o farmacia objetivo |
| `frecuencia_objetivo` | **`F1` o `F2`** (segmento de frecuencia del médico) |
| `visitas_requeridas` | nº de visitas exigidas en el ciclo para ese contacto |

### 7.3 `GET /v1/dias-habiles` — días trabajables por rep (denominador del promedio diario)
```
GET /v1/dias-habiles?pais={pais}&periodo={YYYY-MM}&rep={rep_codigo}
```
| Campo | Uso |
|---|---|
| `rep_codigo` | representante |
| `dias_habiles` | días laborables/de campo del período |

### 7.4 Cómo VISTA calcula cada indicador con estos datos
*(Fórmulas según el modelo actual de VISTA; **⟦PREGUNTA⟧ confirmar la definición exacta de F1/F2 y de "cubierto" con el cliente**.)*

| Indicador | Fórmula | Datos que usa |
|---|---|---|
| **COB_MD_F1** | médicos F1 **cubiertos** / médicos F1 objetivo × 100 | `/target` (F1) + `/visitas` (MEDICO) |
| **COB_MD_F2** | médicos F2 **cubiertos** / médicos F2 objetivo × 100 | `/target` (F2) + `/visitas` (MEDICO) |
| **PROM_DIARIO** | total visitas a médicos / `dias_habiles` | `/visitas` (MEDICO) + `/dias-habiles` |
| **COB_FARMACIAS** | farmacias visitadas / farmacias objetivo × 100 | `/target` (FARMACIA) + `/visitas` (FARMACIA) |

> "**Cubierto**" = el médico recibió al menos las `visitas_requeridas` de su frecuencia en el ciclo.
> Confirmar con el cliente si la regla es "al menos 1 visita" o "cumplir la frecuencia completa".

## 8. Alternativa si algún dato no puede exponerse por API

Solo como **fallback**, en este orden: (a) **vista de solo lectura** en una base de datos que el
cliente exponga (VPN/IP autorizada, usuario read-only); (b) **exportación de archivo** (CSV/Excel) por
SFTP con layout estable. VISTA ya soporta ambos, pero **la API es la vía preferida** por ser
automatizada, versionada y auditable.

## 9. Lo que más nos ayuda: sandbox + ejemplo por endpoint

Por **cada** endpoint de las secciones 4–7 pedimos:
1. **Credenciales de sandbox** para probar la conexión.
2. Una **respuesta JSON de ejemplo** real (1–2 períodos) con todos los campos.
3. El **diccionario** de cada campo (nombre, tipo, significado, valores posibles).

Con eso validamos el mapeo de catálogos y el cálculo de indicadores sin esperar la integración final.

## 10. Seguridad, contactos y SLA

- **Seguridad:** TLS obligatorio; credenciales entregadas por canal seguro; IPs de VISTA a autorizar.
- **Contacto técnico** por sistema (Close-Up-DB/API, ERP, SFA) para la integración e incidencias.
- **Cobertura de países:** confirmar qué países cubre cada API.
- **SLA:** fecha/hora comprometida de disponibilidad de cada período por endpoint.
- **Licenciamiento** de los datos de Close-Up (uso interno, mostrar competencia, retención).

---

*Gracias. Con las respuestas y los ejemplos de sandbox definimos el calendario de integración por API.*
