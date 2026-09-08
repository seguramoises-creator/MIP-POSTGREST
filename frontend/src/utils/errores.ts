/**
 * El motivo REAL de un error del servidor, para mostrárselo al usuario.
 *
 * POR QUÉ EXISTE. Un `catch` que pinta un texto fijo convierte cualquier fallo
 * en la misma frase, y esa frase suele nombrar una causa que nadie comprobó. El
 * usuario entonces persigue el problema equivocado: el Simulacro de Venta decía
 * «verifica que haya una conexión de IA activa» ante CUALQUIER error —un 403,
 * un token vencido, un 500—, así que un permiso mal puesto se leía como un
 * problema de configuración de IA.
 *
 * Esto vive aparte y no dentro de una pantalla justamente para que la siguiente
 * no vuelva a inventarse su propio mensaje.
 *
 * FastAPI manda el motivo en `detail`: un string en los errores de negocio
 * (`HTTPException`) y una lista `[{loc, msg}]` en los 422 de validación. El
 * prefijo «Value error, » que Pydantic antepone se quita porque no significa
 * nada para quien está usando el sistema.
 *
 * El `fallback` sigue siendo necesario: un fallo de red no trae respuesta, y ahí
 * no hay nada que citar.
 */
export function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}
