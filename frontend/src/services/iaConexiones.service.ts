/**
 * iaConexiones.service.ts — Panel de Conexiones de IA (§20.4).
 * Rutas exactas del router backend `/ia/conexiones` (solo ADMIN).
 * Las credenciales SIEMPRE llegan enmascaradas; el backend nunca las expone en claro.
 */
import { api } from './api';

export type CapacidadIA = 'texto' | 'voz';
export type MetodoAuthIA = 'api_key' | 'usuario_password';

export interface Conexion {
  id: number;
  nombre: string;
  capacidad: CapacidadIA;
  proveedor_tipo: string;
  endpoint_url: string | null;
  metodo_auth: string;
  modelo: string | null;
  activa: boolean;
  verificada: boolean;
  ultima_verificacion: string | null;
  ultimo_error: string | null;
  credencial_1: string | null; // enmascarada
  credencial_2: string | null; // enmascarada
}

export interface ConexionEntrada {
  nombre: string;
  capacidad: CapacidadIA;
  proveedor_tipo: string;
  endpoint_url?: string | null;
  metodo_auth: MetodoAuthIA;
  credencial_1?: string | null;
  credencial_2?: string | null;
  modelo?: string | null;
}

// Editar: todos opcionales; el backend solo aplica los presentes.
export type ConexionCambio = Partial<ConexionEntrada>;

export interface ProveedoresIA { texto: string[]; voz: string[]; }
export interface ResultadoPrueba { ok: boolean; detalle: string; }

export const listarConexionesIA = () =>
  api.get<{ conexiones: Conexion[]; cifrado_configurado: boolean }>('/ia/conexiones')
    .then((r) => r.data);

export const proveedoresIA = () =>
  api.get<ProveedoresIA>('/ia/conexiones/proveedores').then((r) => r.data);

export const crearConexionIA = (body: ConexionEntrada) =>
  api.post<Conexion>('/ia/conexiones', body).then((r) => r.data);

export const actualizarConexionIA = (id: number, body: ConexionCambio) =>
  api.put<Conexion>(`/ia/conexiones/${id}`, body).then((r) => r.data);

export const eliminarConexionIA = (id: number) =>
  api.delete(`/ia/conexiones/${id}`).then(() => undefined);

export const probarConexionIA = (id: number) =>
  api.post<ResultadoPrueba>(`/ia/conexiones/${id}/probar`).then((r) => r.data);

export const activarConexionIA = (id: number) =>
  api.post<Conexion>(`/ia/conexiones/${id}/activar`).then((r) => r.data);
