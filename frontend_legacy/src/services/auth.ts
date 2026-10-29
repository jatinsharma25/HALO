import { fetchApi } from './api';
import type { AuthTokenResponse, UserMeResponse } from '../types/api';

export const authService = {
  async login(username: string, password: string): Promise<AuthTokenResponse> {
    const data = await fetchApi<AuthTokenResponse>('/auth/login', {
      method: 'POST',
      requireAuth: false,
      body: JSON.stringify({ username, password })
    });
    return data;
  },

  async getMe(): Promise<UserMeResponse> {
    const data = await fetchApi<UserMeResponse>('/auth/me', {
      method: 'GET',
      requireAuth: true
    });
    return data;
  }
};
