/**
 * FUENTE ÚNICA DE COLOR — Laboratorios Mallén.
 *
 * Todo color de la aplicación sale de aquí. Cambiar un valor en este archivo lo
 * cambia en TODAS las pantallas a la vez: no hay que recorrerlas una por una.
 *
 * POR QUÉ EXISTE. Hasta ago-2026 había 972 colores escritos a mano repartidos en
 * 55 archivos. El rebrand a Mallén se pudo hacer solo porque se sustituyeron con
 * un guion, literal por literal — y ese método falló dos veces: los colores en
 * `rgba()` no los veía la búsqueda de hexadecimales, y un emoji azul no era CSS
 * en absoluto. Un valor centralizado no tiene ese problema porque no hay nada
 * que buscar.
 *
 * REGLA: ningún archivo de `pages/` o `components/` debe declarar un `#rrggbb`.
 * Si hace falta un color nuevo se añade aquí, con nombre, y se importa.
 *
 * Los dos colores corporativos NO se eligieron a ojo: se extrajeron del propio
 * archivo vectorial del logotipo, así que son exactamente los que imprime la marca.
 *
 *   Pantone 405 C      → #686158   (taupe: el cuerpo del logotipo)
 *   Pantone Red 032 CP → #F63440   (rojo: el acento sobre la «E»)
 *
 * JERARQUÍA — el rojo manda en las ACCIONES (botones, estado activo, acentos); el
 * taupe ESTRUCTURA (barras, superficies, texto). Es la proporción del propio logo,
 * donde el rojo es un solo trazo sobre un logotipo entero en taupe. Invertirla
 * convertiría el color de marca en ruido y le quitaría su único trabajo: señalar
 * dónde actuar.
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

/** Rojo muy tenue: fondo de avisos y realces suaves. */
export const ROJO_TENUE = '#FDEBEC';
/** Taupe casi negro — fondo de la pantalla de entrada. */
export const TAUPE_NEGRO = '#2A2622';
/** Taupe aclarado — tramo final de degradados y bordes sobre oscuro. */
export const TAUPE_CLARO = '#7A7166';

/* ── SUPERFICIES Y TEXTO ───────────────────────────────────────────────────
 * Neutros CÁLIDOS, no grises puros: junto al taupe de Mallén un gris neutro se
 * percibe azulado por contraste simultáneo y delata que no es de la familia.
 */
export const FONDO = '#F6F4F2';        // área de contenido
export const SUPERFICIE = '#FFFFFF';   // tarjetas, tablas, diálogos
export const SUPERFICIE_2 = '#F9F8F6'; // superficie alterna (filas, paneles)
export const SUPERFICIE_3 = '#F4F1EE'; // realce tenue
export const SUPERFICIE_4 = '#EFEBE6'; // realce algo más marcado
export const BORDE = '#E4DED7';
export const BORDE_SUAVE = '#EDE9E4';
export const BORDE_FUERTE = '#D8D2CB';
export const TEXTO = '#2E2A26';
export const TEXTO_TENUE = '#57504A';

/* ── ESCALA NEUTRA CÁLIDA ──────────────────────────────────────────────────
 * Sustituye a la escala «blue grey» de Material (#37474F … #90A4AE), que seguía
 * siendo azulada. Se conservan CINCO pasos porque varias pantallas los usan para
 * distinguir categorías: colapsarlos perdería información, no solo matiz.
 */
export const NEUTRO_900 = '#3D3833';
export const NEUTRO_700 = '#4C4640';
export const NEUTRO_600 = '#5E574F';
export const NEUTRO_400 = '#8A8177';
export const NEUTRO_300 = '#A69C91';
export const NEUTRO_200 = '#C9C1B8';

/* ── ESTADO ────────────────────────────────────────────────────────────────
 * NO son colores de marca, y por eso NO se tiñen de rojo ni de taupe: el verde,
 * el ámbar y el rojo de error significan algo por convención universal. Si el
 * aviso compartiera el color de la marca, el usuario dejaría de distinguir
 * «atención» de «decoración» — que es justo lo que estos existen para evitar.
 */
export const EXITO = '#2E7D32';
export const EXITO_OSCURO = '#00695C';
export const EXITO_MEDIO = '#00897B';
export const EXITO_TENUE = '#E0F2F1';
export const AVISO = '#E65100';
export const AVISO_MEDIO = '#F57C00';
export const AVISO_OSCURO = '#EF6C00';
export const AVISO_TENUE = '#FFF3E0';
export const ERROR = '#C62828';
export const ERROR_TENUE = '#FBEAEA';

/* ── DEGRADADOS DE MARCA ───────────────────────────────────────────────────
 * Aquí y no en `navTokens` para que tengan un solo origen: los usan la barra
 * superior, la inferior y la pantalla de entrada.
 */
export const DEGRADADO_BARRA =
  `linear-gradient(130deg, ${TAUPE_PROFUNDO} 0%, ${TAUPE_MEDIO} 55%, ${TAUPE} 100%)`;
export const DEGRADADO_ENTRADA =
  `linear-gradient(135deg, ${TAUPE_NEGRO} 0%, ${TAUPE_PROFUNDO} 40%, ${TAUPE_MEDIO} 75%, ${TAUPE} 100%)`;

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
