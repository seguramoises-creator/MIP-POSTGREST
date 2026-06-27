/**
 * Constantes globales de KPIs — nombres canónicos y orden de presentación.
 * Usar en TODOS los componentes que muestren indicadores.
 */

/** Orden de aparición en tablas, gráficos y tarjetas */
export const KPI_ORDEN: Record<string, number> = {
  COB_MD_F2:          1,
  COB_MD_F1:          2,
  PROM_DIARIO:        3,
  COB_FARMACIAS:      4,
  EVO_IR:             5,
  VENTAS:             6,
  EVAL_CONOCIMIENTOS: 7,
  EVAL_COACHING:      8,
};

/** Nombre de presentación (UI) por código de indicador */
export const KPI_NOMBRE: Record<string, string> = {
  COB_MD_F2:          'Cobertura Médicos F2',
  COB_MD_F1:          'Cobertura Médicos F1',
  PROM_DIARIO:        'Promedio diario Médicos',
  COB_FARMACIAS:      'Cobertura Farmacias',
  EVO_IR:             'Evolución IR',
  VENTAS:             'Cumplimiento Venta',
  EVAL_CONOCIMIENTOS: 'Evaluación Conocimientos',
  EVAL_COACHING:      'Evaluación Coaching',
};

/** Nombres con salto de línea explícito para tarjetas de dashboard (cards angostas) */
const KPI_NOMBRE_CARD: Record<string, string> = {
  COB_MD_F2:          'Cobertura\nMédicos F2',
  COB_MD_F1:          'Cobertura\nMédicos F1',
  PROM_DIARIO:        'Promedio\nDiario Médicos',
  COB_FARMACIAS:      'Cobertura\nFarmacias',
  EVO_IR:             'Evolución\nIR',
  VENTAS:             'Cumplimiento\nVenta',
  EVAL_CONOCIMIENTOS: 'Evaluación\nConocimientos',
  EVAL_COACHING:      'Evaluación\nCoaching',
};

/** Devuelve el nombre canónico; si el código no está mapeado, usa el fallback o el propio código */
export function kpiNombre(codigo: string, fallback?: string): string {
  return KPI_NOMBRE[codigo] ?? fallback ?? codigo;
}

/** Versión con salto de línea para cards angostas (usar con whiteSpace: 'pre-line') */
export function kpiNombreCard(codigo: string, fallback?: string): string {
  return KPI_NOMBRE_CARD[codigo] ?? KPI_NOMBRE[codigo] ?? fallback ?? codigo;
}

/** Ordena un array de objetos que tengan campo `codigo` según KPI_ORDEN */
export function sortByKpiOrden<T extends { codigo: string }>(arr: T[]): T[] {
  return [...arr].sort((a, b) => (KPI_ORDEN[a.codigo] ?? 99) - (KPI_ORDEN[b.codigo] ?? 99));
}
