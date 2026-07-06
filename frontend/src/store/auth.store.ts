import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Rol } from '../types';

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  username: string | null;
  rol: Rol | null;
  nombreCompleto: string | null;
  isAuthenticated: boolean;
  // Estado de la contraseña (política): fuerza cambio y avisa de vencimiento.
  debeCambiarPassword: boolean;
  passwordExpiraEnDias: number | null;
  passwordMotivo: string;
  setAuth: (data: {
    accessToken: string;
    refreshToken: string;
    username: string;
    rol: Rol;
    nombreCompleto: string;
    debeCambiarPassword?: boolean;
    passwordExpiraEnDias?: number | null;
    passwordMotivo?: string;
  }) => void;
  setPasswordEstado: (data: {
    debeCambiarPassword: boolean;
    passwordExpiraEnDias: number | null;
    passwordMotivo: string;
  }) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      username: null,
      rol: null,
      nombreCompleto: null,
      isAuthenticated: false,
      debeCambiarPassword: false,
      passwordExpiraEnDias: null,
      passwordMotivo: 'ok',
      setAuth: (data) =>
        set({
          accessToken: data.accessToken,
          refreshToken: data.refreshToken,
          username: data.username,
          rol: data.rol,
          nombreCompleto: data.nombreCompleto,
          isAuthenticated: true,
          debeCambiarPassword: data.debeCambiarPassword ?? false,
          passwordExpiraEnDias: data.passwordExpiraEnDias ?? null,
          passwordMotivo: data.passwordMotivo ?? 'ok',
        }),
      setPasswordEstado: (data) =>
        set({
          debeCambiarPassword: data.debeCambiarPassword,
          passwordExpiraEnDias: data.passwordExpiraEnDias,
          passwordMotivo: data.passwordMotivo,
        }),
      logout: () =>
        set({
          accessToken: null,
          refreshToken: null,
          username: null,
          rol: null,
          nombreCompleto: null,
          isAuthenticated: false,
          debeCambiarPassword: false,
          passwordExpiraEnDias: null,
          passwordMotivo: 'ok',
        }),
    }),
    {
      name: 'scgcpr-auth',
      partialize: (s) => ({
        accessToken: s.accessToken,
        refreshToken: s.refreshToken,
        username: s.username,
        rol: s.rol,
        nombreCompleto: s.nombreCompleto,
        isAuthenticated: s.isAuthenticated,
        debeCambiarPassword: s.debeCambiarPassword,
        passwordExpiraEnDias: s.passwordExpiraEnDias,
        passwordMotivo: s.passwordMotivo,
      }),
    }
  )
);
