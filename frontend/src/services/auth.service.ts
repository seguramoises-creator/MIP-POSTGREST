import axios from 'axios';
import { TokenResponse } from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1';

export const authService = {
  async login(username: string, password: string): Promise<TokenResponse> {
    const form = new URLSearchParams();
    form.append('username', username);
    form.append('password', password);
    form.append('grant_type', 'password');

    const { data } = await axios.post<TokenResponse>(
      `${API_URL}/auth/login`,
      form,
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    );
    return data;
  },

  async logout(token: string) {
    await axios.post(
      `${API_URL}/auth/logout`,
      {},
      { headers: { Authorization: `Bearer ${token}` } }
    ).catch(() => {});
    localStorage.clear();
  },

  decodeToken(token: string) {
    try {
      const payload = token.split('.')[1];
      return JSON.parse(atob(payload));
    } catch {
      return null;
    }
  },

  // "Olvidó su contraseña" — paso 1: pide el código al correo (respuesta genérica).
  async forgotPassword(email: string): Promise<string> {
    const { data } = await axios.post<{ message: string }>(`${API_URL}/auth/forgot-password`, { email });
    return data.message;
  },

  // Paso 2: valida el código y fija la nueva contraseña.
  async resetPassword(email: string, codigo: string, password_nuevo: string): Promise<string> {
    const { data } = await axios.post<{ message: string }>(
      `${API_URL}/auth/reset-password`, { email, codigo, password_nuevo });
    return data.message;
  },

  // ── Activación de cuenta (enlace de un solo uso) ──────────────────────────
  // Endpoints públicos: quien llega todavía no tiene contraseña, así que no hay token
  // de sesión que enviar. Lo que autoriza es el token del enlace del correo.

  // Valida el enlace antes de pintar el formulario (para saludar por el nombre y avisar
  // de inmediato si venció).
  async validarActivacion(token: string): Promise<{ nombre: string; username: string; min_longitud: number }> {
    const { data } = await axios.get(`${API_URL}/auth/activacion/${encodeURIComponent(token)}`);
    return data;
  },

  // El usuario fija su propia contraseña; el token se consume en el servidor.
  async activarCuenta(token: string, password: string): Promise<string> {
    const { data } = await axios.post<{ message: string }>(
      `${API_URL}/auth/activacion`, { token, password });
    return data.message;
  },

  // Pide un enlace nuevo cuando el anterior venció. Respuesta siempre genérica.
  async reenviarActivacion(email: string): Promise<string> {
    const { data } = await axios.post<{ message: string }>(
      `${API_URL}/auth/activacion/reenviar`, { email });
    return data.message;
  },
};
