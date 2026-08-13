/**
 * Tokens de la navegación (barra superior + barra inferior).
 *
 * Las DOS barras van en el azul de VISTA; el área de contenido queda blanca,
 * como estaba. Así el azul enmarca la app arriba y abajo y las pantallas de
 * información no pierden legibilidad.
 *
 * LEGIBILIDAD AL SOL — es el requisito que manda aquí, porque el representante
 * usa la app de pie, en la calle, con el brillo peleando contra la pantalla.
 * De ahí tres decisiones que NO son estéticas:
 *
 *  1. Azul PLANO, no degradado ni translúcido. El vidrio esmerilado se ve bien
 *     en interiores y desaparece bajo el sol: el contraste efectivo cae con lo
 *     que haya detrás, que además cambia al hacer scroll. Y un degradado hace
 *     que el mismo texto tenga distinto contraste según dónde caiga.
 *  2. Inactivo al 78 % de blanco, no al 55-60 % habitual en barras oscuras. A
 *     plena luz ese blanco tenue simplemente no está: el usuario ve iconos
 *     flotando sin etiqueta.
 *  3. Etiquetas en peso 600. El texto fino se deshace con el reflejo mucho
 *     antes que el texto sólido, a igualdad de contraste.
 *
 * El contenido sigue siendo texto oscuro sobre superficie clara, que es lo que
 * mejor se lee al sol: el brillo de la pantalla compite con la luz ambiente en
 * vez de sumarse a ella.
 */

/** Fondo de ambas barras: el primario de VISTA, sin retocar. */
export const NAV_FONDO = '#1a237e';
/** Activo sobre el azul: blanco puro (13.2:1). */
export const NAV_ACTIVO = '#FFFFFF';
/** Inactivo sobre el azul: blanco atenuado, todavía muy por encima de AA. */
export const NAV_INACTIVO = 'rgba(255,255,255,0.78)';
/** Separador interno de las barras (sobre el azul). */
export const NAV_BORDE = 'rgba(255,255,255,0.16)';

/** Fondo del área de contenido — el gris claro de siempre. */
export const APP_FONDO = '#f5f6fa';

/**
 * Texto secundario sobre superficie CLARA (hoja de Perfil, hoja de "Más").
 * Existe aparte de `NAV_INACTIVO` justamente porque ese es blanco atenuado: sirve
 * sobre el azul de las barras y sería invisible sobre blanco. 8.05:1 sobre blanco.
 */
export const TEXTO_TENUE = '#4A5060';

/** Alto de la barra inferior SIN el área segura del iOS (notch/home indicator). */
export const BOTTOM_NAV_H = 60;
