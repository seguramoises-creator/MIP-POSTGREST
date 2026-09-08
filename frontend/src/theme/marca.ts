/**
 * Tokens de color para esta instalación — identidad VISTA (azul).
 *
 * POR QUÉ EXISTE ESTE FICHERO AQUÍ. Las pantallas del módulo de Formación se
 * escribieron después de que el proyecto centralizara sus colores, así que
 * importan sus tonos de `theme/marca` en vez de escribirlos a mano. Al traer
 * ese módulo a esta instalación había que traer también el fichero del que
 * dependen — pero con LOS COLORES DE ESTA INSTALACIÓN, no con los de la rama
 * principal, cuya identidad es la de otro cliente.
 *
 * Es exactamente el trabajo que hace la centralización: el mismo código de
 * pantalla se ve azul aquí y de otra marca allá, sin tocar ni una línea de las
 * pantallas.
 *
 * Los valores azules salen del `navTokens.ts` de esta misma instalación, así
 * que el módulo nuevo se ve como el resto de la aplicación y no como un injerto.
 */

/* ── MARCA (VISTA) ─────────────────────────────────────────────────────────
 * Del degradado original de las barras: #0d1b4c → #17307a → #1f6f8f.
 */
/** Azul marino intermedio — el tramo central del degradado de VISTA. */
export const TAUPE_MEDIO = '#17307a';

/* ── SUPERFICIES ───────────────────────────────────────────────────────────
 * Neutros FRÍOS, a juego con el azul: el `#f5f6fa` del área de contenido.
 */
/** Realce tenue sobre el fondo de la aplicación. */
export const SUPERFICIE_3 = '#eef0f6';
/** Borde suave entre bloques. */
export const BORDE_SUAVE = '#e2e5ee';

/* ── ESTADO ────────────────────────────────────────────────────────────────
 * NO son colores de marca y por eso NO se tiñen de azul: el verde, el ámbar y
 * el rojo significan algo por convención universal. Si el aviso compartiera el
 * color de la marca, el usuario dejaría de distinguir «atención» de
 * «decoración» — que es justo lo que estos existen para evitar. Son los mismos
 * valores que usa la rama principal, a propósito.
 */
export const EXITO = '#2E7D32';
export const AVISO = '#E65100';
export const AVISO_TENUE = '#FFF3E0';
export const ERROR = '#C62828';
