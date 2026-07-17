# Exámenes — Notificaciones y feedback con ventana de 48h

**Fecha:** 2026-07-17 · **Estado:** aprobado por el cliente (3 bloques, uno a uno)

**Objetivo:** el representante debe (1) recibir aviso cuando le asignan un examen, (2) al
terminar, recibir un aviso de que su feedback está en la plataforma —no por correo—, (3) ver
ese feedback SOLO in-app, sin poder imprimirlo/descargarlo para reusarlo de guía, y (4) solo
durante 48 horas.

## Contexto (lo que ya existe)

- `GET /intentos/{id}/reporte` YA devuelve el feedback pregunta-por-pregunta (bien/mal). La
  pantalla `MisExamenes.tsx` lo muestra. No hay que construir el feedback.
- `notification_service.py` (smtplib best-effort, no-op si `MAIL_SERVER=""`) ya tiene
  `notificar_resultado_examen` (correo con el reporte completo) y `notificar_correcciones_examen`.
- **NO existe** ninguna `notificar_asignacion_examen` — por eso el correo de asignación nunca
  llega. `asignar_examen` recibe `notif_activa` pero no notifica.
- `IntentoExamen.fecha_entrega` ya se persiste — es el ancla de la ventana de 48h (sin migración).

## Bloque 1 — Notificación de asignación

`notification_service.notificar_asignacion_examen(destinatario, nombre, examen_nombre,
fecha_limite, link)`: correo corto, sin preguntas ni contenido, con enlace a `/mis-examenes`.
Se dispara al final de `examen_service.asignar_examen`, uno por evaluado con correo, best-effort
(un fallo de correo no rompe la asignación). Respeta `notif_activa`.

## Bloque 2 — Al entregar: aviso mínimo, no el reporte

`_finalizar_resultado` hoy llama a `notificar_resultado_examen` con score/correctas/estado. Se
cambia a un **aviso mínimo**: "Tu examen ya tiene feedback disponible, entra a revisarlo dentro
de las próximas 48 horas" + enlace a `/mis-examenes`. SIN score, correctas, estado ni PDF.
- Si el examen tiene preguntas abiertas, `_finalizar_resultado` ya solo corre cuando el resultado
  es definitivo (tras la calificación del Gerente), así que el aviso sale cuando hay algo que ver.

## Bloque 3 — Ventana de 48h + barreras anti-copia

**Guard en el backend (la barrera real):** `GET /intentos/{id}/reporte`, si el solicitante es
REPRESENTANTE_MEDICO y `now > fecha_entrega + 48h`, NO devuelve el detalle: responde solo
`nota`, `aprobado` y `feedback_vencido: true`. Gerencia (ADMIN, GERENTE_DISTRITO, CAPACITACION,
GERENTE_PRODUCTIVIDAD) lo ve completo siempre. El endpoint es la única fuente del detalle, así
que esconderlo solo en el frontend no bastaría.

**Frontend (`MisExamenes.tsx`):**
- Dentro de 48h: reporte + contador ("te quedan N h para revisarlo").
- Vencido: la tarjeta del historial queda como ahora (nota + aprobado/reprobado), sin botón de
  detalle.
- Barreras sobre la pantalla del reporte: quitar botón PDF/descarga; `@media print { display:none }`;
  clic derecho desactivado; marca de agua diagonal tenue con nombre + fecha/hora del rep.

**No cambia:** modelo de datos (sin migración), lógica de calificación, vista de gerencia.

## Constantes / valores exactos

- Ventana: `FEEDBACK_HORAS = 48`, anclada a `IntentoExamen.fecha_entrega`.
- Roles con feedback perpetuo: ADMIN, GERENTE_DISTRITO, GERENTE_PRODUCTIVIDAD, CAPACITACION.
- El rol acotado a 48h: REPRESENTANTE_MEDICO (y GERENTE si es evaluado — mismo trato que el RM).

## Pruebas

- Backend: reporte dentro de 48h como RM → detalle completo; a 48h+1min como RM → solo nota,
  sin `preguntas`; misma petición como ADMIN → completo. `notificar_asignacion_examen` respeta
  `_habilitado()` y destinatario vacío.
- E2E: FEDERICO contra la copia de producción.
