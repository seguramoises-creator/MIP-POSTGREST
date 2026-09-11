import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1';

export const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

// ── Interceptor: adjuntar token ───────────────────────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Interceptor: refresh automático al expirar ────────────────────────
// EL SERVIDOR ROTA EL REFRESH: al renovar revoca el usado y entrega uno nuevo. Aquí se
// guardaba solo el access, así que la segunda renovación —dos horas después de entrar—
// llegaba con un refresh revocado y echaba al usuario al login. Y como cada petición que
// caducaba renovaba por su cuenta, bastaba que dos caducaran juntas para que la segunda
// gastara un refresh ya revocado: expulsión con la sesión sana. Por eso: se guarda el
// refresh nuevo y hay UNA sola renovación en vuelo, que comparten todas.
let renovando: Promise<string> | null = null;
function renovar(refresh: string): Promise<string> {
  if (!renovando) {
    renovando = axios.post(`${API_URL}/auth/refresh`, { refresh_token: refresh })
      .then(({ data }) => {
        localStorage.setItem('access_token', data.access_token);
        if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
        return data.access_token as string;
      })
      .finally(() => { renovando = null; });
  }
  return renovando;
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      // Otra petición ya renovó mientras esta viajaba con el token viejo: reintentar basta.
      const usado = String(original.headers?.Authorization ?? '').replace('Bearer ', '');
      const vigente = localStorage.getItem('access_token');
      if (vigente && vigente !== usado) {
        original.headers.Authorization = `Bearer ${vigente}`;
        return api(original);
      }
      const refresh = localStorage.getItem('refresh_token');
      if (refresh) {
        try {
          const token = await renovar(refresh);
          original.headers.Authorization = `Bearer ${token}`;
          return api(original);
        } catch {
          localStorage.clear();
          window.location.href = '/login';
        }
      }
    }
    // Aviso global para errores del SERVIDOR (500+) o de red: los que el usuario no entiende.
    // Un componente escucha este evento, busca el error en la Matriz de Errores y muestra su
    // descripción/solución. Los 4xx (400/403/409) ya traen su mensaje específico en cada pantalla.
    const status = error.response?.status as number | undefined;
    if (!error.response || (status !== undefined && status >= 500)) {
      window.dispatchEvent(new CustomEvent('app:error-servidor', {
        detail: { status: status ?? 0, detalle: error.response?.data?.detail },
      }));
    }
    return Promise.reject(error);
  }
);
