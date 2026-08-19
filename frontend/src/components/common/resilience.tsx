/* Resiliencia de carga (evita el congelamiento en móvil tras un deploy).
 *
 * lazyWithReload: si el chunk de una ruta no se puede importar (típico cuando el
 * navegador/SW tiene un index viejo que apunta a un hash que ya no existe), recarga
 * UNA vez para traer el index + chunks frescos, en vez de dejar la app colgada.
 *
 * ErrorBoundary: red de seguridad — cualquier error de render muestra una pantalla
 * de "Recargar" en lugar de un árbol React desmontado (pantalla oscura congelada).
 */
import { Component, lazy, type ComponentType, type ReactNode } from 'react';

const RELOAD_KEY = 'vista-chunk-reload';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyWithReload<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
) {
  return lazy(async () => {
    try {
      return await factory();
    } catch (err) {
      // Recarga una sola vez (guard temporal) para no entrar en bucle de recargas.
      let last = 0;
      try { last = Number(sessionStorage.getItem(RELOAD_KEY) || 0); } catch { /* noop */ }
      if (Date.now() - last > 10000) {
        try { sessionStorage.setItem(RELOAD_KEY, String(Date.now())); } catch { /* noop */ }
        window.location.reload();
        return { default: (() => null) as unknown as T };
      }
      throw err;
    }
  });
}

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false };
  static getDerivedStateFromError() { return { error: true }; }
  componentDidCatch(err: unknown) { console.error('ErrorBoundary:', err); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        minHeight: '100vh', gap: 14, padding: 24, textAlign: 'center',
        fontFamily: 'system-ui, "Inter", sans-serif',
      }}>
        <div style={{ fontSize: 42 }}>⚠️</div>
        <div style={{ fontSize: 18, fontWeight: 700 }}>Algo salió mal</div>
        <div style={{ color: '#666', maxWidth: 320 }}>
          Recarga la aplicación para continuar.
        </div>
        <button
          onClick={() => { try { sessionStorage.clear(); } catch { /* noop */ } window.location.reload(); }}
          style={{
            marginTop: 8, padding: '10px 22px', fontSize: 16, borderRadius: 8,
            border: 'none', background: '#686158', color: '#fff', fontWeight: 700, cursor: 'pointer',
          }}
        >
          Recargar
        </button>
      </div>
    );
  }
}
