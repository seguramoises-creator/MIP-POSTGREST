# Prompt 04 - Modulo de Examenes

Actua como arquitecto de datos, analista senior de producto, desarrollador backend, experto en SQL Server, Python, APIs, frontend responsive y experiencia movil.

Necesito crear un modulo separado llamado:

**Modulo de Examenes - Evaluacion de Visitadores Medicos**

Este modulo pertenece a la Plataforma KPI de fuerza de ventas farmaceutica. Debe permitir que el equipo de Capacitacion / Asesoria Medica cree examenes sobre productos farmaceuticos, los asigne a visitadores medicos, y obtenga resultados automaticos.

Los visitadores medicos deben poder tomar los examenes desde:

- smartphone
- iPhone
- telefonos Android
- tablets Android
- iPad
- laptops
- computadoras de escritorio

El modulo debe ser web responsive, mobile first, usable desde navegador moderno y preparado para evolucionar a PWA si se requiere.

## 1. Contexto

El modulo permite:

1. Crear examenes manualmente.
2. Crear examenes con IA desde documentos fuente.
3. Asignar examenes a visitadores medicos.
4. Permitir que cada visitador tome el examen desde cualquier dispositivo.
5. Corregir automaticamente al entregar.
6. Mostrar retroalimentacion inmediata individual.
7. Enviar reporte por correo si aplica.
8. Generar KPIs para capacitacion, gerentes y visitadores.

## 2. Roles y permisos

### Capacitacion / Asesor Medico

Puede:

- Crear examenes manuales.
- Crear examenes con IA.
- Configurar parametros del examen.
- Publicar examenes.
- Asignar examenes a visitadores.
- Ver todos los resultados.
- Descargar reportes.
- Ver analisis por pregunta.
- Ver historico de resultados.

### Gerente de Zona / GD

Puede:

- Ver resultados de su equipo.
- Comparar visitadores.
- Descargar reportes.
- Ver ranking.
- Ver preguntas con mayor error.
- Identificar brechas de conocimiento.

### Visitador Medico

Puede:

- Ver examenes asignados.
- Tomar examenes pendientes.
- Ver reporte inmediato al terminar.
- Consultar historial de examenes.
- Imprimir o guardar reporte si se permite.

## 3. Flujo general del modulo

1. Capacitacion crea el examen, manual o IA.
2. El examen queda en estado `borrador`.
3. Capacitacion revisa preguntas y respuestas.
4. Capacitacion publica el examen, estado `activo`.
5. Capacitacion asigna el examen a visitadores con fecha limite.
6. Visitador ve el examen pendiente en su panel.
7. Visitador inicia el intento.
8. Sistema presenta preguntas y opciones.
9. Visitador responde y entrega.
10. Plataforma corrige automaticamente.
11. Visitador recibe reporte inmediato.
12. Capacitacion/GD ve resultados consolidados.
13. El sistema conserva historial completo de intentos.

## 4. Modelo funcional

### Objeto Examen

```text
Examen {
  id             : INT autoincremental
  nombre         : STRING
  producto       : STRING
  nota_minima    : INT porcentaje aprobatorio, ej. 70
  tiempo_limite  : INT minutos
  estado         : ENUM [borrador | activo | completado | archivado]
  fuente         : ENUM [manual | ia]
  rand_preguntas : BOOL
  rand_opciones  : BOOL
  creado_por     : FK Usuario
  fecha_creacion : DATETIME
  preguntas      : [Pregunta]
}
```

### Objeto Pregunta

```text
Pregunta {
  id          : INT
  examen_id   : FK Examen
  tipo        : ENUM [multi | caso]
  escenario   : TEXT nullable, solo tipo = caso
  texto       : TEXT
  opciones    : [STRING] exactamente 4 opciones
  correcta    : INT indice 0-3 de la opcion correcta original
  explicacion : TEXT retroalimentacion al visitador
  orden       : INT posicion original
}
```

### Objeto Asignacion

```text
Asignacion {
  id              : INT
  examen_id       : FK Examen
  visitador_id    : FK Usuario / Representante
  fecha_limite    : DATE
  intentos_max    : INT nullable, null = ilimitados
  intentos_usados : INT
  estado          : ENUM [pendiente | completado | vencido]
  notif_activa    : BOOL
}
```

### Objeto Intento

```text
Intento {
  id              : INT
  asignacion_id   : FK Asignacion
  visitador_id    : FK Usuario / Representante
  fecha_inicio    : DATETIME
  fecha_fin       : DATETIME
  score           : INT porcentaje calculado
  aprobado        : BOOL
  orden_preguntas : [INT] IDs en orden presentado
  respuestas      : JSON {pregunta_id: indice_opcion_elegida}
}
```

## 5. Creacion de examenes

### 5.1 Modo manual

El encargado ingresa preguntas directamente en la interfaz.

Cada pregunta debe tener:

- tipo: opcion multiple o caso clinico
- escenario, si aplica
- enunciado
- 4 opciones
- opcion correcta
- explicacion de retroalimentacion

El creador debe poder:

- agregar preguntas
- editar preguntas
- eliminar preguntas
- reordenar preguntas
- guardar borrador
- publicar examen

### 5.2 Modo IA

El encargado puede:

- subir PDF
- subir Word
- subir PowerPoint
- pegar texto

La plataforma extrae texto y envia el contenido al API de IA.

Extraccion sugerida:

- PDF: `pdfplumber` o `PyMuPDF`
- Word: `python-docx`
- PowerPoint: `python-pptx`
- Texto pegado: usar directamente

Prompt base para IA:

```text
Eres un experto en capacitacion farmaceutica. Analiza el siguiente documento y genera exactamente {N} preguntas de evaluacion:

- {N_MULTI} de opcion multiple
- {N_CASOS} casos clinicos

Para cada pregunta devuelve JSON con este esquema:

tipo        : 'multi' | 'caso'
escenario   : string, solo para caso
texto       : string
opciones    : [string, string, string, string], exactamente 4
correcta    : 0|1|2|3
explicacion : string

DOCUMENTO:
{contenido_del_archivo}
```

Regla:

Las preguntas generadas por IA siempre deben mostrarse a Capacitacion para revision y edicion antes de guardar o publicar.

## 6. Aleatorizacion

El examen puede configurar:

- `rand_preguntas`
- `rand_opciones`

Si `rand_preguntas = TRUE`, cada intento puede tener un orden distinto de preguntas.

Si `rand_opciones = TRUE`, cada pregunta puede presentar opciones en orden distinto.

El sistema debe guardar:

- orden de preguntas presentado
- orden de opciones presentado
- mapa de opciones original vs presentado
- respuesta elegida por el usuario
- respuesta correcta presentada

### Algoritmo Fisher-Yates

```text
FUNCION shuffle(array):
  PARA i DESDE len(array)-1 HASTA 1:
    j = numero_aleatorio_entero(0, i)
    intercambiar array[i] con array[j]
  RETORNAR array
```

## 7. Correccion automatica

Al entregar el examen:

```text
total = numero de preguntas
correctas = respuestas correctas
score = ROUND((correctas / total) * 100)
aprobado = score >= nota_minima
```

Luego:

1. Guardar fecha_fin.
2. Guardar score.
3. Guardar aprobado.
4. Incrementar intentos_usados.
5. Si aprobado o intentos_usados >= intentos_max, marcar asignacion como completada.
6. Mostrar reporte inmediato.

## 8. Reporte inmediato al visitador

Despues de entregar, la plataforma debe mostrar:

- nombre del examen
- producto
- visitador
- fecha/hora
- score %
- aprobado / reprobado
- correctas de total
- nota minima requerida
- revision pregunta por pregunta
- opcion elegida
- opcion correcta
- explicacion
- boton imprimir / guardar PDF

Si `notif_activa = TRUE`, enviar correo.

### Correo electronico

Asunto:

```text
Resultado de Examen - {nombre_examen} - {score}%
```

Cuerpo:

- nombre del visitador
- nombre del examen
- producto
- score
- estado aprobado/reprobado
- numero de respuestas correctas
- fecha y hora
- link para ver reporte en plataforma

## 9. KPIs y reportes

KPIs requeridos:

| KPI | Formula / Logica | Nivel |
|---|---|---|
| Promedio del equipo | promedio(score) de todos los intentos del examen | Examen |
| % aprobacion | count(aprobado=true) / count(total_intentos) * 100 | Examen |
| Completitud | count(asignaciones completadas) / count(asignaciones totales) * 100 | Examen |
| Score individual | score del ultimo intento de cada visitador | Visitador |
| Ranking | visitadores ordenados por score descendente | Examen |
| % error por pregunta | count(incorrectas) / count(intentos) * 100 por pregunta | Pregunta |
| Evolucion | score por examen a lo largo del tiempo | Visitador |
| Promedio historico | promedio(score) de todos los examenes de un visitador | Visitador |

## 10. Pantallas requeridas

### Capacitacion

- Dashboard Capacitacion
- Lista de Examenes
- Crear Examen Manual
- Crear Examen con IA
- Revision de preguntas generadas por IA
- Asignar Examen
- Resultados
- Analisis por Pregunta
- Historial Equipo

### Visitador Medico

- Panel Visitador - Pendientes
- Tomar Examen
- Reporte de Resultados
- Historial Visitador

### Gerente de Zona / GD

- Resultados de equipo
- Ranking
- Comparativo por visitador
- Analisis por pregunta
- Exportar reportes

## 11. Reglas de negocio

| ID | Regla |
|---|---|
| RN-01 | Un examen en borrador no puede ser tomado por ningun visitador. |
| RN-02 | Para publicar debe tener al menos 1 pregunta. |
| RN-03 | La correccion es automatica al entregar; no requiere revision manual. |
| RN-04 | Con rand_preguntas=true, cada intento puede tener un orden distinto. |
| RN-05 | Con rand_opciones=true, el sistema rastrea el mapeo para correccion exacta. |
| RN-06 | Al agotar intentos_max, el examen se bloquea para ese visitador. |
| RN-07 | El visitador siempre ve retroalimentacion, incluso si reprobo. |
| RN-08 | El % de error por pregunta se calcula sobre todos los intentos. |
| RN-09 | El historial conserva todos los intentos; el ranking usa el ultimo intento. |
| RN-10 | El archivo fuente IA se guarda para auditoria y no es visible al visitador. |

## 12. Requisitos mobile / multidispositivo

El examen debe poder tomarse correctamente desde:

- iPhone
- Android
- iPad
- tablets Android
- laptop
- desktop

Requisitos UI/UX:

1. Diseno mobile first.
2. Botones grandes y tactiles.
3. Opciones de respuesta con area clic/touch amplia.
4. Una pregunta por pantalla en mobile.
5. Barra de progreso visible.
6. Boton `Siguiente`, `Anterior` y `Entregar`.
7. Confirmacion antes de entregar si hay preguntas sin responder.
8. Temporizador visible si el examen tiene tiempo limite.
9. Layout responsive para tablet/laptop.
10. No depender de hover para acciones importantes.
11. Guardar avance parcial localmente si hay perdida temporal de conexion.
12. Evitar perdida de respuestas al cambiar orientacion de pantalla.
13. Compatible con navegadores modernos:
    - Safari iOS
    - Chrome Android
    - Chrome desktop
    - Edge
    - Safari iPadOS

Requisitos tecnicos sugeridos:

- Web responsive.
- Preparado para PWA.
- Soporte para instalacion en pantalla de inicio opcional.
- Guardado automatico de respuestas cada vez que el usuario selecciona una opcion.
- Control de sesion y token seguro.
- No permitir modificar respuestas despues de entregar.

## 13. Modelo SQL Server esperado

Crear schema separado:

```text
exam
```

Tablas sugeridas:

### exam.DimExamen

- ExamenKey
- Nombre
- Producto
- NotaMinima
- TiempoLimiteMinutos
- Estado
- Fuente
- RandPreguntas
- RandOpciones
- CreadoPorUsuarioKey
- FechaCreacion
- FechaPublicacion
- Activo

### exam.DimPregunta

- PreguntaKey
- ExamenKey
- TipoPregunta
- Escenario
- TextoPregunta
- Explicacion
- Orden
- Activo

### exam.DimPreguntaOpcion

- OpcionKey
- PreguntaKey
- TextoOpcion
- IndiceOriginal
- EsCorrecta
- Activo

### exam.FactAsignacionExamen

- AsignacionKey
- ExamenKey
- VisitadorKey
- FechaAsignacion
- FechaLimite
- IntentosMax
- IntentosUsados
- EstadoAsignacion
- NotificacionActiva

### exam.FactIntentoExamen

- IntentoKey
- AsignacionKey
- VisitadorKey
- FechaInicio
- FechaFin
- Score
- Aprobado
- TiempoUsadoSegundos
- OrdenPreguntasJson
- UserAgent
- DeviceType
- Plataforma
- IpCliente

### exam.FactIntentoRespuesta

- RespuestaKey
- IntentoKey
- PreguntaKey
- OpcionElegidaKey
- IndiceOpcionPresentada
- IndiceOriginalElegido
- EsCorrecta
- MapaOpcionesJson
- FechaRespuesta

### exam.FactFuenteIA

- FuenteIAKey
- ExamenKey
- TipoArchivo
- NombreArchivo
- RutaArchivo
- TextoExtraidoHash
- PromptUsado
- FechaCarga
- CargadoPorUsuarioKey

## 14. APIs esperadas

Crear endpoints o servicios para:

### Capacitacion

- `POST /api/examenes`
- `PUT /api/examenes/{id}`
- `POST /api/examenes/{id}/preguntas`
- `POST /api/examenes/{id}/publicar`
- `POST /api/examenes/{id}/asignar`
- `POST /api/examenes/generar-ia`
- `GET /api/examenes/{id}/resultados`
- `GET /api/examenes/{id}/analisis-preguntas`

### Visitador

- `GET /api/visitador/examenes-pendientes`
- `POST /api/examenes/{id}/iniciar`
- `POST /api/intentos/{id}/responder`
- `POST /api/intentos/{id}/entregar`
- `GET /api/intentos/{id}/reporte`
- `GET /api/visitador/historial-examenes`

## 15. Python esperado

Crear un backend o modulo Python que incluya:

- extraccion de texto de PDF / Word / PowerPoint
- generacion de preguntas con IA
- validacion del JSON generado
- guardado de examen y preguntas
- aleatorizacion de preguntas/opciones
- correccion automatica
- calculo de KPIs
- envio de correo

Funciones minimas:

```python
extraer_texto_fuente(path_archivo)
generar_preguntas_ia(texto, n_multi, n_casos)
validar_preguntas_generadas(preguntas)
preparar_intento(examen_id, asignacion_id, rand_preguntas, rand_opciones)
calcular_score(intento_id)
generar_reporte_intento(intento_id)
calcular_kpis_examen(examen_id)
```

## 16. Seguridad y auditoria

Requisitos:

1. Autenticacion obligatoria.
2. Autorizacion por rol.
3. El visitador solo ve sus examenes.
4. GD solo ve su equipo.
5. Capacitacion ve todos los examenes.
6. Guardar auditoria de:
   - creacion
   - publicacion
   - asignacion
   - inicio de intento
   - entrega
   - cambios de preguntas
   - generacion IA
7. Guardar user agent y dispositivo al tomar examen.
8. Evitar doble entrega del mismo intento.
9. Validar expiracion por fecha limite.
10. Validar intentos maximos.

## 17. Vista / dashboard

Crear vistas:

```text
exam.vwDashboardCapacitacion
exam.vwResultadosExamen
exam.vwAnalisisPregunta
exam.vwHistorialVisitador
```

Campos claves para dashboard:

- examen
- producto
- estado
- asignados
- completados
- completitud_pct
- promedio_score
- aprobacion_pct
- visitador
- gerente
- ultimo_score
- intentos_usados
- fecha_ultimo_intento
- pregunta
- error_pct

## 18. Entregables esperados

La respuesta debe producir:

1. Excel de estructura del modulo Examenes.
2. SQL Server DDL con schema `exam`.
3. Python loader / backend base.
4. Prompt IA para generacion de preguntas.
5. Guia tecnica y funcional.
6. Definicion de APIs.
7. Criterios de aceptacion.
8. Consideraciones responsive/mobile.

Nombrar archivos con prefijo:

```text
modelo_examenes
```

Guardar en carpeta separada:

```text
modulo_examenes
```

## 19. Criterios de aceptacion

El modulo sera correcto si:

1. Capacitacion puede crear examen manual.
2. Capacitacion puede generar examen desde IA y editar antes de guardar.
3. El examen puede publicarse solo si tiene preguntas.
4. Puede asignarse a visitadores con fecha limite e intentos maximos.
5. Visitador puede tomar examen desde iPhone, Android, iPad, tablet, laptop o desktop.
6. La interfaz es responsive y touch-friendly.
7. El sistema aleatoriza preguntas y opciones si esta configurado.
8. El sistema corrige automaticamente.
9. El visitador recibe retroalimentacion inmediata.
10. El historial conserva todos los intentos.
11. El ranking usa el ultimo intento.
12. El analisis por pregunta usa todos los intentos.
13. Capacitacion y GD pueden ver KPIs y reportes.
14. El sistema guarda auditoria y fuente IA.
15. No se mezclan tablas del modulo de Examenes con los otros modulos.
