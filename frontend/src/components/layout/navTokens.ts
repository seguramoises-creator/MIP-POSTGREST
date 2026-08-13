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

/**
 * Fondo de ambas barras: el degradado azul de VISTA.
 *
 * Es el mismo que usaban las cabeceras del módulo Visita, así que el azul de las
 * barras y el de la marca son literalmente el mismo color. Se aplica con
 * `background` (no `bgcolor`): un degradado no es un color y `bgcolor` lo ignora.
 *
 * El tramo más claro (`#1f6f8f`) es el que decide la legibilidad: es ahí donde el
 * blanco tiene menos contraste, así que es contra ESE punto —y no contra el azul
 * oscuro del inicio— donde hay que medir si las etiquetas se leen.
 */
export const NAV_FONDO = 'linear-gradient(130deg, #0d1b4c 0%, #17307a 55%, #1f6f8f 100%)';

/** Azul de VISTA plano — bordes, iconos y acentos sobre superficie clara. */
export const NAV_AZUL = '#1a237e';
/** Tramo más claro del degradado: el peor caso para medir contraste. */
export const NAV_FONDO_CLARO = '#1f6f8f';
/** Activo sobre el azul: blanco puro (13.2:1). */
export const NAV_ACTIVO = '#FFFFFF';
/**
 * Inactivo sobre el azul.
 *
 * 0.92 y no el 0.75-0.78 habitual porque el degradado termina en un azul-teal
 * claro (`#1f6f8f`), y es en ESE tramo —la derecha de las barras— donde las
 * etiquetas tienen menos contraste. Con 0.78 caían a 4.11:1, por debajo del
 * mínimo AA para texto pequeño; a 0.92 vuelven a superarlo. El precio es que
 * activo e inactivo se distinguen algo menos por color, así que la pestaña
 * activa se apoya además en el subrayado blanco, que no depende del contraste.
 */
export const NAV_INACTIVO = 'rgba(255,255,255,0.92)';
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
