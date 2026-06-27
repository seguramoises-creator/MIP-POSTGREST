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
};
