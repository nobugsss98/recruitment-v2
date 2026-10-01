import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type { TokenPair } from './types';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

const ACCESS_KEY = 'tf_access_token';
const REFRESH_KEY = 'tf_refresh_token';

export const tokenStore = {
  get access(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  },
  set(pair: TokenPair) {
    localStorage.setItem(ACCESS_KEY, pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.access;
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

// Single-flight refresh: concurrent 401s share one refresh call.
let refreshPromise: Promise<string> | null = null;

function doRefresh(): Promise<string> {
  if (!refreshPromise) {
    const refreshToken = tokenStore.refresh;
    if (!refreshToken) {
      return Promise.reject(new Error('No refresh token available'));
    }
    // Plain axios instance — must NOT use the intercepted `api` client,
    // otherwise a failed refresh would recurse into this same interceptor.
    refreshPromise = axios
      .post<TokenPair>(`${API_BASE}/api/v1/auth/refresh`, {
        refresh_token: refreshToken,
      })
      .then((res) => {
        tokenStore.set(res.data);
        return res.data.access_token;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetryableConfig | undefined;
    const status = error.response?.status;

    if (status === 401 && original && !original._retried) {
      original._retried = true;
      try {
        const newToken = await doRefresh();
        original.headers.set('Authorization', `Bearer ${newToken}`);
        return api.request(original);
      } catch {
        tokenStore.clear();
        if (!window.location.pathname.startsWith('/login')) {
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  },
);

export default api;
