/**
 * Configuración de ESTA instalación — lo que distingue un montaje de otro.
 *
 * Hoy solo el modo de ingesta: por dónde entran los KPIs y las visitas.
 *
 *   excel        la carga manual de FACT_KPI_RM (pantalla Carga Excel — ETL)
 *   integracion  el cliente escribe en el esquema `ext` desde su propio SFA, y
 *                los datos entran por Lotes de Mallén
 *
 * En una instalación integrada la pantalla de Excel no solo sobra: **estorba**.
 * Ofrece una segunda puerta para los mismos datos, y cargar un archivo además de
 * la integración duplicaría el trabajo o lo pisaría. Por eso el menú desaparece
 * en vez de quedarse deshabilitado — un botón apagado invita a preguntar cómo
 * encenderlo.
 *
 * Se lee UNA vez al arrancar, en paralelo con la marca, y se guarda en un objeto
 * MUTABLE por el mismo motivo que `marcaViva`: quien lo importó ve el cambio.
 * Copiar `instalacion.modoIngesta` a una constante lo congelaría en el valor de
 * fábrica — ese error ya costó que el color configurado no llegara a las barras.
 */
export interface Instalacion {
  modoIngesta: 'excel' | 'integracion';
  /**
   * Disposición del menú.
   *
   * `pestanas` — barra superior + barra inferior. Pensada para el móvil y para
   *   quien usa la aplicación de pie, en la calle.
   * `lateral` — el menú lateral clásico. Aprovecha mejor una pantalla ancha y
   *   enseña todas las secciones a la vez, que es lo que se quiere al presentar
   *   el sistema en una sala.
   *
   * Vive aquí y no en una rama aparte por una razón aprendida a golpes: una
   * instalación que se queda con su disposición en su propio código deja de
   * poder actualizarse con un `git pull`, y cada mejora posterior exige rehacer
   * el trasplante a mano.
   */
  layout: 'pestanas' | 'lateral';
  /** ¿Se muestra el Monitor del día? Solo donde la fuerza de ventas registra en VISTA. */
  monitorDia: boolean;
}

/** Fábrica. Ninguna instalación existente cambia sin que alguien lo decida. */
export const instalacion: Instalacion = { modoIngesta: 'excel', layout: 'pestanas', monitorDia: false };

/** ¿Los datos entran por integración con el sistema del cliente? */
export const esIntegrada = () => instalacion.modoIngesta === 'integracion';

/** ¿Esta instalación usa el menú lateral en vez de las barras? */
export const esLayoutLateral = () => instalacion.layout === 'lateral';

/** ¿Esta instalación muestra el Monitor del día? */
export const hayMonitorDia = () => instalacion.monitorDia;

/**
 * Lee la configuración y la aplica. Nunca lanza: sin conexión se queda en
 * `excel`, que es el modo que no esconde nada — ante la duda, mejor un menú de
 * más que uno que falta.
 */
export async function cargarInstalacion(): Promise<void> {
  try {
    const base = (import.meta as any).env?.VITE_API_URL || '/api/v1';
    const r = await fetch(`${base}/admin/config/app`);
    if (!r.ok) return;
    const { modo_ingesta, layout, monitor_dia } = await r.json();
    if (modo_ingesta === 'integracion' || modo_ingesta === 'excel') {
      instalacion.modoIngesta = modo_ingesta;
    }
    if (layout === 'lateral' || layout === 'pestanas') {
      instalacion.layout = layout;
    }
    instalacion.monitorDia = monitor_dia === true;
  } catch {
    /* sin conexión: se queda en `excel` */
  }
}
