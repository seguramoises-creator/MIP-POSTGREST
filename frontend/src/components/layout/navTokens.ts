/**
 * Tokens de la navegación (barra superior + barra inferior).
 *
 * Marca: Laboratorios Mallén. Los colores corporativos viven en `theme/marca.ts`
 * (extraídos del vectorial del logo, no aproximados de la carta Pantone). Aquí
 * solo se decide CÓMO se aplican a la navegación.
 *
 * Las DOS barras van en el taupe de Mallén; el área de contenido queda clara, así
 * que el taupe enmarca la app arriba y abajo sin restarle legibilidad a los datos.
 *
 * LEGIBILIDAD AL SOL — es el requisito que manda aquí, porque el representante
 * usa la app de pie, en la calle, con el brillo peleando contra la pantalla. De
 * ahí tres decisiones que NO son estéticas:
 *
 *  1. Etiquetas en peso 600. El texto fino se deshace con el reflejo mucho antes
 *     que el texto sólido, a igualdad de contraste.
 *  2. Inactivo al 92 % de blanco, no al 55-60 % habitual en barras oscuras. A
 *     plena luz ese blanco tenue simplemente no está: el usuario ve iconos
 *     flotando sin etiqueta.
 *  3. Nada de vidrio esmerilado ni translucidez: se ve bien en interiores y
 *     desaparece bajo el sol, porque el contraste efectivo depende de lo que
 *     haya detrás, que además cambia al hacer scroll.
 *
 * El contenido sigue siendo texto oscuro sobre superficie clara, que es lo que
 * mejor se lee al sol: el brillo de la pantalla compite con la luz ambiente en
 * vez de sumarse a ella.
 */
import { ROJO, TAUPE } from '../../theme/marca';
import { marcaViva } from '../../theme/marcaViva';

/**
 * Fondo de ambas barras: degradado del taupe Mallén, de profundo a corporativo.
 *
 * Se aplica con `background` (no `bgcolor`): un degradado no es un color y
 * `bgcolor` lo ignora.
 *
 * El tramo FINAL (`#686158`, el taupe de marca) es el que decide la legibilidad:
 * es ahí donde el blanco tiene menos contraste, así que es contra ESE punto donde
 * hay que medir. Da 6.11:1 — cómodamente sobre el 4.5:1 de AA para texto pequeño,
 * y bastante mejor que el 4.11:1 al que llegaba el degradado azul anterior.
 */
// Se lee de la paleta VIVA, no de la de fábrica: así el degradado sigue al color
// que el administrador fije desde Identidad visual.
export const NAV_FONDO = marcaViva.degradadoBarra;

/** Taupe Mallén plano — bordes, iconos y acentos sobre superficie clara. */
export const NAV_TAUPE = marcaViva.taupe;
/** Rojo Mallén — acción y acento sobre superficie CLARA (nunca sobre las barras). */
export const NAV_ROJO = marcaViva.rojo;
/** Tramo más claro del degradado: el peor caso para medir contraste. */
export const NAV_FONDO_CLARO = marcaViva.taupe;
/** Activo sobre las barras: blanco puro (6.1:1 en el peor tramo, 12.3:1 en el mejor). */
export const NAV_ACTIVO = '#FFFFFF';
/**
 * Inactivo sobre las barras.
 *
 * 0.92 y no el 0.75-0.78 habitual, por lo dicho arriba sobre el sol: contra el
 * tramo final del degradado da 5.46:1, mientras que 0.78 lo dejaría al filo.
 * El precio es que activo e inactivo se distinguen algo menos por color, así que
 * la pestaña activa se apoya además en el subrayado, que no depende del matiz.
 */
export const NAV_INACTIVO = 'rgba(255,255,255,0.92)';

/**
 * Indicador de pestaña activa: BLANCO, no el rojo de marca.
 *
 * Es la decisión menos obvia de este archivo y conviene dejarla escrita, porque
 * el impulso natural al aplicar una identidad es marcar lo activo con su color
 * principal. Medido: el rojo `#F63440` sobre el taupe `#686158` da **1.59:1**.
 * Los dos colores de Mallén tienen luminancias casi iguales, así que puestos uno
 * sobre otro se funden — el subrayado rojo sería invisible, y al sol todavía más.
 * Combinan sobre blanco, donde ambos contrastan; no entre sí.
 *
 * La marca no se pierde por esto: el degradado taupe y el logo ya identifican a
 * Mallén, y el rojo hace su trabajo donde sí se ve (botones, iconos de campo,
 * acentos sobre las superficies claras).
 */
export const NAV_INDICADOR = '#FFFFFF';

/** Separador interno de las barras (sobre el taupe). */
export const NAV_BORDE = 'rgba(255,255,255,0.16)';

/** Fondo del área de contenido — gris cálido, afín al taupe (antes era azulado). */
export const APP_FONDO = '#F6F4F2';

/**
 * Texto secundario sobre superficie CLARA (hoja de Perfil, hoja de «Más»).
 * Existe aparte de `NAV_INACTIVO` justamente porque ese es blanco atenuado: sirve
 * sobre las barras y sería invisible sobre blanco. 7.4:1 sobre blanco.
 */
export const TEXTO_TENUE = '#57504A';

/** Alto de la barra inferior SIN el área segura del iOS (notch/home indicator). */
export const BOTTOM_NAV_H = 60;
