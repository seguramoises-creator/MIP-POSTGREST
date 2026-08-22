/**
 * Colores de marca EN CALIENTE — los que el administrador fija desde la pantalla
 * Administración → Identidad visual.
 *
 * `marca.ts` define los valores de FÁBRICA. Este módulo los sustituye en tiempo
 * de ejecución con lo que haya guardado el cliente, sin volver a compilar ni
 * desplegar: se leen una vez al arrancar y alimentan el tema.
 *
 * SOLO DOS COLORES SON EDITABLES, y el resto se DERIVA. Es deliberado: los ocho
 * tonos de la paleta no son independientes, son relaciones fijas —el degradado
 * de las barras son oscurecimientos del taupe; el rojo de los enlaces es el rojo
 * de marca bajado hasta cumplir contraste—. Si se pudieran fijar uno a uno, la
 * primera vez que alguien cambiara el principal sin ajustar los demás la paleta
 * quedaría descuadrada y nadie sabría cuál de los ocho campos la rompió.
 */
import * as fabrica from './marca';
import { IDENTIDAD_FABRICA, identidad, type Identidad } from './identidades';

/** Aclara u oscurece un `#rrggbb`. `f` negativo oscurece, positivo aclara. */
function mezclar(hex: string, f: number): string {
  const n = parseInt(hex.slice(1), 16);
  const canal = (desp: number) => {
    const v = (n >> desp) & 0xff;
    const r = f < 0 ? v * (1 + f) : v + (255 - v) * f;
    return Math.max(0, Math.min(255, Math.round(r)));
  };
  return '#' + [16, 8, 0].map((d) => canal(d).toString(16).padStart(2, '0')).join('').toUpperCase();
}

/** Luminancia relativa (WCAG 2.1). */
function lum(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const c = [16, 8, 0].map((d) => {
    const v = ((n >> d) & 0xff) / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

/** Contraste entre dos colores. */
export function contraste(a: string, b: string): number {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

/**
 * Oscurece un color hasta que sirva como TEXTO sobre blanco (4.5:1, AA).
 *
 * No es un capricho de accesibilidad: el rojo de Mallén da 3.83:1 como texto y no
 * llega. Si el cliente elige un color aún más claro, los enlaces de toda la
 * aplicación quedarían ilegibles — y nadie relacionaría ese problema con haber
 * cambiado un color en una pantalla de configuración. Derivarlo lo hace imposible.
 */
export function versionLegible(hex: string): string {
  let c = hex;
  for (let i = 0; i < 24 && contraste(c, '#FFFFFF') < 4.5; i++) c = mezclar(c, -0.08);
  return c;
}

export interface Marca {
  rojo: string; rojoOscuro: string; rojoTenue: string;
  taupe: string; taupeMedio: string; taupeProfundo: string;
  taupeNegro: string; taupeClaro: string;
  degradadoBarra: string; degradadoEntrada: string;
  /** Juego de logotipos vigente (ver `identidades.ts`). */
  logo: Identidad;
}

/**
 * Construye la paleta completa a partir de los dos colores editables.
 *
 * `nombreLogo` va aparte de los colores porque son decisiones independientes:
 * una instalación puede querer el logotipo de VISTA con colores propios.
 */
export function derivar(rojo: string, taupe: string, nombreLogo?: string | null): Marca {
  const ident = identidad(nombreLogo);
  // Si los colores son LOS DE LA IDENTIDAD (nadie los cambió) y esa identidad
  // trae tonos afinados a mano, se usan tal cual. En cuanto hay un color propio
  // el cálculo vuelve a mandar: no tendría sentido mezclar el taupe elegido por
  // el cliente con los oscuros de otra marca.
  const propios = rojo === ident.rojo && taupe === ident.taupe ? ident.exactos : undefined;
  const taupeMedio = propios?.taupeMedio ?? mezclar(taupe, -0.16);
  const taupeProfundo = propios?.taupeProfundo ?? mezclar(taupe, -0.44);
  const taupeNegro = propios?.taupeNegro ?? mezclar(taupe, -0.6);
  return {
    rojo,
    rojoOscuro: propios?.rojoOscuro ?? versionLegible(rojo),
    rojoTenue: propios?.rojoTenue ?? mezclar(rojo, 0.9),
    taupe, taupeMedio, taupeProfundo, taupeNegro,
    taupeClaro: propios?.taupeClaro ?? mezclar(taupe, 0.14),
    degradadoBarra: `linear-gradient(130deg, ${taupeProfundo} 0%, ${taupeMedio} 55%, ${taupe} 100%)`,
    degradadoEntrada: `linear-gradient(135deg, ${taupeNegro} 0%, ${taupeProfundo} 40%, ${taupeMedio} 75%, ${taupe} 100%)`,
    logo: identidad(nombreLogo),
  };
}

/** Paleta de fábrica: la de Mallén, tal cual sale del vectorial del logotipo. */
export const MARCA_FABRICA: Marca = {
  rojo: fabrica.ROJO, rojoOscuro: fabrica.ROJO_OSCURO, rojoTenue: fabrica.ROJO_TENUE,
  taupe: fabrica.TAUPE, taupeMedio: fabrica.TAUPE_MEDIO,
  taupeProfundo: fabrica.TAUPE_PROFUNDO, taupeNegro: fabrica.TAUPE_NEGRO,
  taupeClaro: fabrica.TAUPE_CLARO,
  degradadoBarra: fabrica.DEGRADADO_BARRA, degradadoEntrada: fabrica.DEGRADADO_ENTRADA,
  logo: identidad(IDENTIDAD_FABRICA),
};

/**
 * La paleta vigente. Arranca en la de fábrica y `cargarMarca()` la sustituye.
 *
 * Es un objeto MUTABLE y no un valor que se reasigna: los módulos que ya lo
 * importaron —`navTokens`, las pantallas— se quedarían con la copia vieja si se
 * reemplazara la referencia. Mutando el mismo objeto, todos ven el cambio.
 */
export const marcaViva: Marca = { ...MARCA_FABRICA };

/**
 * Lee los colores guardados y los aplica. Se llama UNA vez, antes de pintar.
 *
 * Nunca lanza: si el endpoint falla o el servidor está caído, la aplicación
 * arranca con los colores de fábrica en lugar de quedarse en blanco. Un problema
 * de red no debe impedir entrar.
 */
export async function cargarMarca(): Promise<void> {
  try {
    const base = (import.meta as any).env?.VITE_API_URL || '/api/v1';
    const r = await fetch(`${base}/admin/config/marca`);
    if (!r.ok) return;
    const { rojo, taupe, logo } = await r.json();
    const hex = /^#[0-9A-Fa-f]{6}$/;
    // Elegir una identidad trae SU paleta, no solo su logotipo: una instalación
    // que pide el logotipo de VISTA y se queda con los colores de Mallén se ve
    // rota, y nadie relacionaría eso con haber elegido solo el logotipo. Los
    // colores guardados, si los hay, mandan sobre esa base — así se puede tener
    // el logotipo de una marca con los colores de otra, a propósito.
    const elegida = identidad(logo);
    Object.assign(marcaViva, derivar(
      hex.test(rojo || '') ? rojo.toUpperCase() : elegida.rojo,
      hex.test(taupe || '') ? taupe.toUpperCase() : elegida.taupe,
      logo,
    ));
  } catch {
    /* sin conexión: se queda la de fábrica */
  }
}
