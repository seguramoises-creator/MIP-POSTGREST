# Checklist de QA en vivo — Ajustes KPI Laboratorio Mallén

**Base:** documento de campo `Ajustes_Plataforma_KPI_Laboratorio_Mallen_2026-07-10.txt`
**Implementado en:** commit `8723237` + correcciones de la sesión jul-2026 (`9c95d1e`, `128f616`,
`34876b4`, `5b0771e`, `0081cb3`, `2a908d7`, `d2e2c61`, `adb50d0`, `f7d0199`, `05e6924`, `9691561`,
`15f70bf`, `938714b`). **Desplegado en `vista-mip.com`.**
**Actualizado:** tras sembrar datos demo, corregir la vigencia de médicos (`fix_medico_alta.py`) y
dejar 1 ciclo abierto por país — lo que resolvió los "datos en 0".

**Cómo usar:** entra con un usuario del rol indicado y marca `[x]` OK / `[!]` falla.

Leyenda: ✅ hecho y verificado · 🔎 hecho en código, falta tu confirmación visual · ❓ decisión con Mallén

---

## 1. Registro de Visita  (rol: REPRESENTANTE_MEDICO)

- [ ] ✅ **No se puede reordenar la misión del día** — no existe arrastrar/soltar en la agenda.
- [ ] ✅ **Solo aparecen los médicos programados** — la agenda sale EXCLUSIVAMENTE de Planeación del Ciclo (se quitó el fallback al panel). Sin planeación → agenda vacía.
- [ ] ✅ **Secciones "Visita/Revisita del día" y "… del ciclo"** — separadas por el día de la semana del tipo pendiente.
- [ ] ✅ **Buscar médico fuera de misión** — campo "Registrar médico fuera de agenda".
- [ ] ✅ **Programado no visitado → rojo "No visitado"** en "registrados en el día".
- [ ] ✅ **En "visitas anteriores" → `NO-Visita` en rojo.**
- [ ] ✅ **Bloqueo de guardado sin producto** — muestra "Marca al menos un producto promocionado…".
- [ ] ✅ **Se muestra el NOMBRE del producto, no el código.**
- [ ] ✅ **Formulario inline** — se despliega justo debajo del médico seleccionado (ya no abajo).
- [ ] ✅ **Toggle Vista/Revisita según lo pendiente** — Vista hecha → queda pendiente de Revisita y el toggle abre en R; sin Vista → REVISITA desactivado.

## 2. Cobertura Diaria  (rol: GERENTE / ADMIN)

- [ ] ✅ **Actualización en vivo (caso Carlos Moreno)** — resuelto: con datos sembrados y la vigencia de médicos corregida, VM-11 (Carlos Moreno) ya muestra cobertura real; se afecta en vivo al registrar.
- [ ] ✅ **Ruptura / Cierre con filtros representante / línea / GD**, alimentado por los registros de visita, en vivo.

## 3. Parrilla de Muestras  (rol: ADMIN / GERENTE_PRODUCTIVIDAD)

- [ ] ✅ **Línea sin productos** → aviso + botón "¿Quiere agregar producto?" → Sistema › Configuración › Productos.

## 4. Panel Médico / Agregar Médico

- [ ] ✅ **Copiar médico existente** trae todo **excepto nombre y ubicación/zonificación**.
- [ ] ✅ **Validación al guardar** — vacío/formato inválido en rojo con mensaje; no deja guardar.
- [ ] ✅ **Buscador autocompletado.**
- [ ] ✅ **Aprobar / Rechazar solicitudes** — funcionaba con un error 500 (regresión de `obtener_medico`), ya corregido.

## 5. Categorización Médico

- [ ] ✅ **Variables/pesos/detalle solo para Producto/MKT/Dirección** (mapeados a ADMIN, GERENTE_PRODUCTIVIDAD, GERENTE_MARCA, CONSULTA).
- [ ] ✅ **RM ve solo médico + categoría.**
- [ ] ✅ **Alcance:** RM = su panel; GD = su equipo; MKT/Dirección = todo.
- [ ] ❓ **Confirmar mapeo de roles con Mallén** — el sistema no tiene literalmente "Gerente de Producto / MKT / Dirección General".

## 6. Planeación de Ciclo

- [ ] ✅ **Indica si el médico ya fue visitado** este ciclo.
- [ ] ✅ **Frecuencia planeada vs lograda** con coherencia.
- [ ] 🔎 **"Cobertura planeada" inmediata** al entrar al VM — mejorado con paginación + payload lite; confirmar el tiempo de despliegue en vivo.
- [ ] ✅ **Colores:** A=Verde · B=Azul · C=Amarillo · D=Rojo.

## 7. Productividad Comercial

- [ ] ✅ **Gráfico + mapa integral se actualizan al cambiar de ciclo.**

## 8. Ranking General de Representante (RKT)

- [ ] ✅ **El RKT se actualiza al cambiar de ciclo.**
- [ ] ✅ **Toggle Todos / Con registro.**
- [ ] 🔎 **Vista regional (predominando el mes siguiente)** — confirmar la regla del mes en vivo.
- [ ] 🔎 **Histórico regional trae TODOS los datos** — confirmar en vivo que no falten filas.

## 9. Cobertura Predictiva

- [ ] ✅ **3 filtros:** Línea (con "todas"), GD (todos), **buscador de representante por NOMBRE** (ya no muestra el código).
- [ ] ✅ **Cobertura por RM limitada a su GD** (auto-alcance).
- [ ] ✅ **Selector de ciclo arranca en el ABIERTO** (antes caía en C12 cerrado) y ordena C01→C12.
- [ ] ✅ **"Todos los datos en 0" → RESUELTO.** El módulo se calcula EN VIVO desde el módulo Visita (`PlaneacionCiclo` = programado, `FactVisita` = realizado), **no** desde Excel. Se resolvió con: (1) datos sembrados de Planeación + Visitas; (2) corrección de la vigencia de médicos (`fix_medico_alta.py`); (3) dejar **1 ciclo abierto** por país (antes había 61). Hoy muestra semáforo Verde/Amarillo/Rojo con números reales.
- [ ] ✅ **Ya no depende de Excel** — se retiraron del Admin las cargas por Excel y los feriados (los días hábiles salen del ciclo). Solo queda la Meta de Cobertura.
- [ ] ✅ **Gráficos con nombre del RM** (no el código) y leyenda que no se solapa con las etiquetas.

## 10. Costo por Visita & ROI / Pool de Ventas

- [ ] ✅ **Relabels aplicados:** "PSP visitas", "Producto contacto", "Producto esperado".
- [ ] ❓ **Confirmar visualmente** que cada renombre quedó en la columna correcta (el documento marcó dos renombres partiendo de "Retorno y visita").
- [ ] ✅ **Impacto financiero no editable** — se obtiene de Cobertura, por filtro A/B/C.
- [ ] 🔎 **Slider de coeficientes recalcula en tiempo real** — confirmar en vivo.

## 11. Formación

- [ ] ✅ Sin ajustes en esta revisión.

---

## Resumen

- **11/11 secciones corregidas en código y desplegadas en `vista-mip.com`.**
- **"Datos en 0" (Sec 9/2/6) RESUELTO:** se sembraron datos, se corrigió la vigencia de médicos y se dejó 1 ciclo abierto por país. Cobertura Predictiva y Cobertura Visita muestran números reales.
- **Solo queda:**
  - 🔎 3 confirmaciones visuales en vivo: cobertura planeada inmediata (6), regional + histórico (8), slider (10).
  - ❓ 2 decisiones con Mallén: mapeo de roles (5) y a qué columna corresponde cada renombre "Retorno y visita" (10).
- **Sin código pendiente.**

### Otras correcciones de la sesión (fuera de las 11 secciones)
- Registro de **visita acompañada** por el Gerente de Distrito (switch + KPI en Cobertura Visita).
- Optimizaciones de rendimiento (Panel Médico/Planeación: paginación + payload lite).
- Gestión de contraseñas: reset por ADMIN + "Olvidó su contraseña" por código; config SMTP desde Admin.
