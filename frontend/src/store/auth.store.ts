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
  setAuth: (data: {
    accessToken: string;
    refreshToken: string;
    username: string;
    rol: Rol;
    nombreCompleto: string;
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
      setAuth: (data) =>
        set({
          accessToken: data.accessToken,
          refreshToken: data.refreshToken,
          username: data.username,
          rol: data.rol,
          nombreCompleto: data.nombreCompleto,
          isAuthenticated: true,
        }),
      logout: () =>
        set({
          accessToken: null,
          refreshToken: null,
          username: null,
          rol: null,
          nombreCompleto: null,
          isAuthenticated: false,
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
      }),
    }
  )
);
