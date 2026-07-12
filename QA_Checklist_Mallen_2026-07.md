# Checklist de QA en vivo — Ajustes KPI Laboratorio Mallén

**Base:** documento de campo `Ajustes_Plataforma_KPI_Laboratorio_Mallen_2026-07-10.txt`
**Implementado en:** commit `8723237` + follow-ups `9c95d1e`, `128f616`, `34876b4`
**Cómo usar:** entra a la app con un usuario del rol indicado, ejecuta el "Cómo probar" y marca `[x]` OK / `[!]` falla. Los ⚠ son puntos que dependen de datos reales.

Leyenda de estado del código: ✅ hecho · ⚠ depende de datos/QA · ❓ confirmar mapeo con Mallén

---

## 1. Registro de Visita  (rol: REPRESENTANTE_MEDICO)

- [ ] ✅ **No se puede reordenar la misión del día** — no existe arrastrar/soltar en la lista de la agenda.
- [ ] ✅ **Solo aparecen los médicos programados para hoy** en la lista del día (los demás no se listan por defecto).
- [ ] ✅ **Buscar médico fuera de misión** — campo "Registrar médico fuera de agenda"; escribe un nombre y debe encontrarlo.
- [ ] ✅ **Programado no visitado → rojo "No visitado"** en "registrados en el día".
- [ ] ✅ **En "visitas anteriores" → label `NO-Visita` en rojo** para el mismo caso.
- [ ] ✅ **Bloqueo de guardado sin producto** — intenta registrar sin marcar ningún producto: debe impedirlo y mostrar "Marca al menos un producto promocionado…".
- [ ] ✅ **Se muestra el NOMBRE del producto, no el código.**

## 2. Cobertura Diaria  (rol: GERENTE / ADMIN)

- [ ] ⚠ **Actualización en vivo de visitas registradas** (caso "Carlos Moreno"). *El refetch en vivo ya está en código; requiere reproducir con visitas reales para confirmar que el dato se refleja al instante.*
- [ ] ✅ **Ruptura / Cierre con filtros representante / línea / GD**, alimentado por los registros de visita y refrescando en vivo.

## 3. Parrilla de Muestras  (rol: ADMIN / GERENTE_PRODUCTIVIDAD)

- [ ] ✅ **Línea sin productos** → aviso "Línea sin productos registrados" + botón "¿Quiere agregar producto?" que lleva a Sistema › Configuración › Productos.

## 4. Panel Médico / Agregar Médico

- [ ] ✅ **Copiar médico existente** trae todos los datos **excepto nombre y campos de ubicación/zonificación**.
- [ ] ✅ **Validación al guardar** — campo vacío obligatorio y formato inválido (email/teléfono) se sombrean en rojo con mensaje; no deja guardar.
- [ ] ✅ **Buscador autocompletado** — al escribir va trayendo coincidencias.

## 5. Categorización Médico

- [ ] ✅ **Variables/pesos/detalle solo para Producto/MKT/Dirección** (mapeados a ADMIN, GERENTE_PRODUCTIVIDAD, GERENTE_MARCA, CONSULTA).
- [ ] ✅ **RM ve solo médico + categoría** (sin detalle ni pesos).
- [ ] ✅ **Alcance de datos:** RM = su panel; GD = su equipo; MKT/Dirección = todo.
- [ ] ❓ **Confirmar mapeo de roles con Mallén** — el sistema no tiene literalmente "Gerente de Producto / MKT / Dirección General"; se usaron los roles existentes. Validar que corresponden.

## 6. Planeación de Ciclo

- [ ] ✅ **Indica si el médico ya fue visitado** este ciclo dentro del panel.
- [ ] ✅ **Frecuencia planeada vs lograda** con coherencia (columna de frecuencia plan/logrado).
- [ ] ⚠ **"Cobertura planeada" debe aparecer inmediata** al entrar al VM. *Con la paginación + payload lite ya cargado; confirmar tiempo de despliegue en la app con datos reales.*
- [ ] ✅ **Colores de categoría:** A=Verde · B=Azul · C=Amarillo · D=Rojo (mapa único `categoriaColores.ts`).

## 7. Productividad Comercial

- [ ] ✅ **El gráfico y el mapa integral se actualizan al cambiar de ciclo** (siguen el ciclo del contexto global).

## 8. Ranking General de Representante (RKT)

- [ ] ✅ **El RKT se actualiza al cambiar de ciclo.**
- [ ] ✅ **Toggle Todos / Con registro** en la vista.
- [ ] ⚠ **Vista regional (predominando el mes siguiente)** — verificar la regla del mes con datos reales.
- [ ] ⚠ **Histórico regional trae TODOS los datos** — confirmar en vivo que no falten filas.

## 9. Cobertura Predictiva

- [ ] ✅ **3 filtros:** Línea (con "todas"), GD (todos), buscador de VM por nombre/código.
- [ ] ✅ **Cobertura por RM limitada a su GD** (auto-alcance).
- [ ] ⚠ **"Todos los datos en 0" → traer datos reales.** **DIAGNÓSTICO CORREGIDO:** el módulo se calcula EN VIVO desde el módulo Visita (`PlaneacionCiclo` = programado, `FactVisita` = realizado), **no** desde el Excel de carga. Sale 0 porque para el país+ciclo elegido casi no hay planeación ni visitas registradas (en la BD local: 14 filas de Planeación, 2 de FactVisita). **Acción:** que los VM planifiquen su ciclo y registren visitas, o sembrar datos demo. **Revisar además:** hay 61 ciclos "abiertos" (debería ser ~1 por país) — el selector puede estar cayendo en un ciclo vacío.

## 10. Costo por Visita & ROI / Pool de Ventas

- [ ] ✅ **Relabels aplicados:** "PSP visitas", "Producto contacto", "Producto esperado" (ya no aparece "Retorno y visita" ni "Visitas detalladas").
- [ ] ❓ **Confirmar visualmente** que cada renombre quedó en la columna correcta (el documento marcó dos renombres partiendo de "Retorno y visita").
- [ ] ✅ **Impacto financiero no editable** — se obtiene del módulo de Cobertura, por filtro A/B/C.
- [ ] ⚠ **Slider de coeficientes recalcula en tiempo real** — confirmar en vivo que los impactos cambian al mover el slider.

## 11. Formación

- [ ] ✅ Sin ajustes en esta revisión.

---

## Resumen

- **11/11 secciones tienen el código hecho y desplegable.**
- **Bloqueante real para "verlo funcionando":** datos del módulo Visita (Planeación + Registro) casi vacíos → afecta Cobertura Predictiva (Sec 9), Cobertura Diaria (Sec 2) y parte de Planeación (Sec 6).
- **Anomalía a revisar:** 61 ciclos abiertos en `Config.DIM_Ciclo` (debería haber ~1 abierto por país).
- **A confirmar con Mallén:** mapeo de roles (Sec 5) y renombres de columnas Costo/ROI (Sec 10).
