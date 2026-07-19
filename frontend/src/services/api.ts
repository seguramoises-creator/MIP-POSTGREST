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
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refresh = localStorage.getItem('refresh_token');
      if (refresh) {
        try {
          const { data } = await axios.post(`${API_URL}/auth/refresh`, {
            refresh_token: refresh,
          });
          localStorage.setItem('access_token', data.access_token);
          original.headers.Authorization = `Bearer ${data.access_token}`;
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
