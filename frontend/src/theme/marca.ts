/**
 * Identidad de marca — Laboratorios Mallén.
 *
 * Los dos colores corporativos NO están escritos a ojo: se extrajeron del propio
 * archivo vectorial del logo (`LABORATORIOS MALLEN.pdf`), así que son exactamente
 * los que imprime la marca, no una aproximación de la carta Pantone.
 *
 *   Pantone 405 C      → #686158   (taupe: el cuerpo del logotipo)
 *   Pantone Red 032 CP → #F63440   (rojo: el acento sobre la «E»)
 *
 * JERARQUÍA — el rojo es el principal, y eso significa algo concreto: manda en
 * las ACCIONES (botones, estado activo, acentos, lo que el usuario puede tocar).
 * El taupe ESTRUCTURA (barras, superficies, texto). Es la misma proporción que
 * usa el logo, donde el rojo es un solo trazo sobre un logotipo entero en taupe.
 * Invertirla —bañar la app de rojo— convertiría el color de marca en ruido y le
 * quitaría el único trabajo que hace bien: señalar dónde actuar.
 */

/** Rojo Mallén (Pantone Red 032 CP). Acción, estado activo, acento de marca. */
export const ROJO = '#F63440';
/** Rojo oscurecido para hover/pulsado y para texto rojo sobre blanco (5.1:1). */
export const ROJO_OSCURO = '#C81E2A';
/** Taupe Mallén (Pantone 405 C). Estructura: barras, superficies, texto fuerte. */
export const TAUPE = '#686158';
/** Taupe profundo — arranque del degradado de las barras. */
export const TAUPE_PROFUNDO = '#3A342F';
/** Taupe intermedio — tramo central del degradado. */
export const TAUPE_MEDIO = '#584F46';

/**
 * Color por SECCIÓN funcional del menú.
 *
 * Un icono a color solo informa si el color significa algo. Aquí cada familia de
 * trabajo tiene el suyo, así que el usuario aprende «lo rojo es campo, lo verde
 * es farmacia» y localiza por color antes de leer la etiqueta — que es justo lo
 * que se necesita cuando la lista de módulos ya pasa de treinta entradas.
 *
 * DÓNDE SE USAN: solo sobre superficie CLARA (hoja de «Más», listas de sección,
 * tarjetas). Sobre las barras oscuras manda el contraste, no el color — ver la
 * nota de legibilidad al sol en `navTokens.ts`.
 *
 * Todos superan 3:1 sobre blanco, el mínimo para elementos gráficos (WCAG
 * 1.4.11). Son tonos terrosos y algo desaturados a propósito: junto al taupe
 * cálido de Mallén, una paleta saturada de tonos puros se vería pegada encima
 * en vez de pertenecer a la misma familia.
 */
export const COLOR_SECCION: Record<string, string> = {
  'Inicio':                ROJO,      // Panel de entrada — el color principal de la marca.
  'Operación diaria':      ROJO,      // Trabajo de campo: la actividad central del representante.
  'Maestros y planeación': '#2F7D6E', // Verde clínico — médicos, farmacias, panel.
  'Desempeño y análisis':  '#B4661E', // Ámbar tostado — métricas, ranking, reconocimiento.
  'Formación':             '#4E6E8E', // Azul pizarra — exámenes, coaching, aprendizaje.
  'Datos':                 '#7A5C8E', // Ciruela — cargas, reportes, integración.
  'Sistema':               TAUPE,     // Taupe corporativo — configuración y administración.
};

/**
 * Color de una sección por su TÍTULO (el mismo que usan `Sidebar` y `useNavSecciones`).
 * Taupe si el título no está mapeado — una sección nueva se ve neutra, nunca rota.
 */
export function colorDeSeccion(titulo?: string | null): string {
  return (titulo && COLOR_SECCION[titulo]) || TAUPE;
}

/**
 * Tinte CLARO de cada sección, para los ICONOS sobre las barras oscuras.
 *
 * El color pleno de `COLOR_SECCION` está pensado para superficie clara y sobre el
 * taupe de las barras se hunde (el verde clínico da 1.4:1). Estos tintes son la
 * misma familia de matiz llevada a alta luminancia: mantienen la pista de color
 * —rojizo=campo, verdoso=médicos, ámbar=desempeño— y superan el 3:1 que WCAG
 * 1.4.11 exige a los elementos gráficos, medidos contra el PEOR tramo del
 * degradado (#686158): entre 3.60:1 y 4.78:1.
 *
 * La ETIQUETA se queda en blanco (6.11:1), no en el tinte: como texto pequeño
 * necesitaría 4.5:1 y estos tintes no llegan. Así el icono aporta el color y el
 * texto conserva la legibilidad al sol, que es el requisito que manda en la barra.
 */
export const TINTE_SECCION: Record<string, string> = {
  'Inicio':                '#FFB3B8',
  'Operación diaria':      '#FFB3B8',
  'Maestros y planeación': '#A8E0D2',
  'Desempeño y análisis':  '#F7CE9B',
  'Formación':             '#B9D4EA',
  'Datos':                 '#D9C2E8',
  'Sistema':               '#E8E3DC',
};

/** Tinte claro de una sección para las barras oscuras; blanco si no está mapeada. */
export function tinteDeSeccion(titulo?: string | null): string {
  return (titulo && TINTE_SECCION[titulo]) || '#FFFFFF';
}
