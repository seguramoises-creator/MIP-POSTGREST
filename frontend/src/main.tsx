import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'

/**
 * Tipografía de la plataforma — AUTOALOJADA, no desde Google Fonts.
 *
 * VISTA es una PWA que el representante usa en la calle, con la red que haya. Un
 * `<link>` a fonts.googleapis.com añade dos peticiones a un tercero antes de poder
 * pintar texto, y con mala cobertura eso se ve: la pantalla arranca con la fuente
 * del sistema y salta de golpe cuando llega la buena. Autoalojadas viajan con el
 * resto del paquete, funcionan sin conexión y no filtran la IP del usuario a Google.
 *
 * Solo los pesos que el sistema tipográfico usa de verdad — cada uno es un archivo
 * más que descargar:
 *   Inter   400/500/600 — interfaz y lectura (menús, botones, formularios, tablas)
 *   Manrope 600/700/800 — presencia visual (títulos, cifras destacadas, categorías)
 *
 * ANTES DE ESTO la app no cargaba NINGUNA fuente: el tema pedía «Inter» pero solo
 * estaba instalado `@fontsource/roboto`, y ni siquiera se importaba. Todo se venía
 * viendo en la fuente por defecto del sistema, distinta en cada equipo.
 */
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/manrope/600.css'
import '@fontsource/manrope/700.css'
import '@fontsource/manrope/800.css'

import { cargarMarca } from './theme/marcaViva'

// Se espera a la marca ANTES de pintar. Si se renderizara primero, la pantalla
// arrancaría con los colores de fábrica y saltaría a los del cliente medio segundo
// después — un parpadeo que se lee como un fallo. `cargarMarca` nunca lanza: sin
// conexión sigue con los de fábrica en vez de dejar la pantalla en blanco.
cargarMarca().finally(() =>
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
))
