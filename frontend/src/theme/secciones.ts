/**
 * Color por SECCIÓN funcional del menú.
 *
 * Un icono a color solo informa si el color significa algo. Aquí cada familia de
 * trabajo tiene el suyo, así que el usuario aprende «lo rojo es campo, lo verde
 * es farmacia» y localiza por color antes de leer la etiqueta — que es justo lo
 * que se necesita cuando la lista de módulos ya pasa de treinta entradas.
 *
 * POR QUÉ VIVE APARTE DE `marca.ts`. Estas dos funciones necesitan `marcaViva`, y
 * `marcaViva` importa `marca` para conocer los valores de fábrica. Ponerlas allí
 * cerraba un ciclo entre los dos módulos: `marcaViva` se evalúa primero, lee los
 * colores de fábrica cuando `marca` todavía no ha corrido su cuerpo y revienta en
 * la zona muerta temporal de los `const`. Un archivo tercero rompe el ciclo, y de
 * paso deja `marca.ts` como lo que debe ser: una hoja sin dependencias.
 *
 * TODO SE CALCULA AL LLAMAR, nunca en ámbito de módulo: un mapa constante
 * copiaría los colores al cargar el archivo, que ocurre ANTES de que
 * `cargarMarca()` lea la identidad del servidor, y las secciones se quedarían con
 * la paleta de fábrica mientras el resto de la aplicación cambia — sin que nada
 * avise. Es el mismo motivo por el que `navTokens.ts` expone funciones.
 */
import { marcaViva, tinteSobre } from './marcaViva';

/**
 * DÓNDE SE USAN: solo sobre superficie CLARA (hoja de «Más», listas de sección,
 * tarjetas). Sobre las barras oscuras manda el contraste, no el color — ver la
 * nota de legibilidad al sol en `navTokens.ts`.
 *
 * Las cinco entradas escritas a mano superan 3:1 sobre blanco, el mínimo para
 * elementos gráficos (WCAG 1.4.11). Son tonos algo desaturados a propósito: junto
 * al color de estructura, una paleta de tonos puros se vería pegada encima en vez
 * de pertenecer a la misma familia. Las otras dos son colores DE IDENTIDAD y por
 * eso salen de `marcaViva`, no de un literal.
 */
export const colorSeccion = (): Record<string, string> => ({
  'Inicio':                marcaViva.rojo,  // Panel de entrada — el color de acción vigente.
  'Operación diaria':      marcaViva.rojo,  // Trabajo de campo: la actividad central del representante.
  'Maestros y planeación': '#2F7D6E',       // Verde clínico — médicos, farmacias, panel.
  'Desempeño y análisis':  '#B4661E',       // Ámbar tostado — métricas, ranking, reconocimiento.
  'Formación':             '#4E6E8E',       // Azul pizarra — exámenes, coaching, aprendizaje.
  'Datos':                 '#7A5C8E',       // Ciruela — cargas, reportes, integración.
  'Sistema':               marcaViva.taupe, // Color de estructura — configuración y administración.
});

/**
 * Color de una sección por su TÍTULO (el mismo que usan `Sidebar` y `useNavSecciones`).
 * El color de estructura si el título no está mapeado — una sección nueva se ve
 * neutra, nunca rota.
 */
export function colorDeSeccion(titulo?: string | null): string {
  return (titulo && colorSeccion()[titulo]) || marcaViva.taupe;
}

/**
 * Tinte CLARO de cada sección, para los ICONOS sobre las barras oscuras.
 *
 * El color pleno de `colorSeccion()` está pensado para superficie clara y sobre el
 * fondo de las barras se hunde (el verde clínico da 1.4:1). Estos tintes son la
 * misma familia de matiz llevada a alta luminancia: mantienen la pista de color
 * —campo, médicos, desempeño— y superan el 3:1 que WCAG 1.4.11 exige a los
 * elementos gráficos, medidos contra el PEOR tramo del degradado, que es el color
 * de estructura pleno.
 *
 * Los dos tintes de identidad se CALCULAN (`tinteSobre`) en vez de escribirse: el
 * `#FFB3B8` que había aquí era el rojo de Mallén aclarado a mano, y sobre un
 * degradado azul se veía prestado. Los cinco de función siguen escritos porque no
 * dependen de la marca.
 *
 * La ETIQUETA se queda en blanco (6.11:1), no en el tinte: como texto pequeño
 * necesitaría 4.5:1 y estos tintes no llegan. Así el icono aporta el color y el
 * texto conserva la legibilidad al sol, que es el requisito que manda en la barra.
 */
export const tinteSeccion = (): Record<string, string> => {
  const deMarca = tinteSobre(marcaViva.rojo, marcaViva.taupe);
  return {
    'Inicio':                deMarca,
    'Operación diaria':      deMarca,
    'Maestros y planeación': '#A8E0D2',
    'Desempeño y análisis':  '#F7CE9B',
    'Formación':             '#B9D4EA',
    'Datos':                 '#D9C2E8',
    'Sistema':               '#E8E3DC',
  };
};

/** Tinte claro de una sección para las barras oscuras; blanco si no está mapeada. */
export function tinteDeSeccion(titulo?: string | null): string {
  return (titulo && tinteSeccion()[titulo]) || '#FFFFFF';
}
