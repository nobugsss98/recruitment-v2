import api from './client';
import type { TokenPair, User } from './types';

export async function login(email: string, password: string): Promise<TokenPair> {
  const { data } = await api.post<TokenPair>('/api/v1/auth/login', { email, password });
  return data;
}

export async function refresh(refreshToken: string): Promise<TokenPair> {
  const { data } = await api.post<TokenPair>('/api/v1/auth/refresh', {
    refresh_token: refreshToken,
  });
  return data;
}

export async function me(): Promise<User> {
  const { data } = await api.get<User>('/api/v1/auth/me');
  return data;
}
