/**
 * Tokens de la navegación (barra inferior + pestañas superiores).
 *
 * LEGIBILIDAD AL SOL — es el requisito que manda aquí, porque el representante
 * usa la app de pie, en la calle, con el brillo peleando contra la pantalla.
 * De ahí tres decisiones que NO son estéticas:
 *
 *  1. Fondo BLANCO SÓLIDO, nunca translúcido ni con blur. El vidrio esmerilado
 *     se ve bien en interiores y desaparece bajo el sol: el contraste efectivo
 *     cae con lo que haya detrás, que además cambia al hacer scroll.
 *  2. Gris inactivo `#4A5060` (7.4:1 sobre blanco) en lugar del gris de UI
 *     habitual (~#9AA0AE, 2.8:1). A plena luz ese gris claro simplemente no
 *     está: el usuario ve iconos flotando sin etiqueta.
 *  3. Etiquetas en peso 600. El texto fino se deshace con el reflejo mucho
 *     antes que el texto sólido, a igualdad de contraste.
 *
 * El activo es el índigo de VISTA sin retocar: 13:1 sobre blanco, y sigue
 * siendo el color de la marca.
 */
export const NAV_PAPEL = '#FFFFFF';
export const NAV_ACTIVO = '#1a237e';   // primary.main de VISTA, intacto
export const NAV_INACTIVO = '#4A5060'; // 7.4:1 sobre blanco
export const NAV_BORDE = '#E3E5EC';
export const NAV_TINTA = '#10143A';

/** Alto de la barra inferior SIN el área segura del iOS (notch/home indicator). */
export const BOTTOM_NAV_H = 60;

/**
 * Fondo de la aplicación — el mismo degradado que ya usaban las cabeceras de las
 * pantallas del módulo Visita, promovido a lienzo de toda la app.
 *
 * Se pinta en una capa FIJA detrás del contenido, no en el contenedor que hace
 * scroll: si se pintara en el contenedor, el degradado se recalcularía contra su
 * alto real y en una pantalla larga aparecería repetido o estirado, distinto en
 * cada ruta. Fijo, el lienzo es el mismo siempre.
 *
 * Las tarjetas siguen siendo claras a propósito: el degradado es el fondo, no la
 * superficie de lectura. Bajo el sol, texto oscuro sobre claro se lee mejor que
 * texto claro sobre oscuro, porque el brillo de la pantalla compite con la luz
 * ambiente en vez de sumarse a ella.
 */
export const APP_FONDO = 'linear-gradient(130deg, #0d1b4c 0%, #17307a 55%, #1f6f8f 100%)';
