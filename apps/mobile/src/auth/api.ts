import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { readRefresh, storeRefresh } from './storage';

export type Profile = {
  user_id: string; player_id: string | null; display_name: string | null;
  photo_url: string | null; email: string | null; phone: string | null;
};
export type Verification = {
  status: 'verification_required'; challenge_token: string; masked_contact: string;
  resend_after: number; development_code?: string;
};
type Tokens = { status: 'authenticated'; access_token: string; refresh_token?: string; expires_in: number };
export type AuthResult = Verification | Tokens;

const web = Platform.OS === 'web';
const hostname = web ? window.location.hostname : Constants.expoConfig?.hostUri?.split(':')[0];
export const API_URL = (process.env.EXPO_PUBLIC_API_URL || `http://${hostname || 'localhost'}:8011`).replace(/\/$/, '');
let accessToken: string | null = null;
let onExpired: () => void = () => {};
let refreshing: Promise<boolean> | null = null;

export class ApiError extends Error {
  constructor(message: string, public status: number, public retryAfter = 0) { super(message); }
}

export function setExpiryHandler(handler: () => void) { onExpired = handler; }

async function request<T>(path: string, body?: unknown, token?: string | null, method = 'POST'): Promise<T> {
  const multipart = body instanceof FormData;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), multipart ? 60000 : 15000);
  try {
    const response = await fetch(`${API_URL}${path}`, {
      method, signal: controller.signal, credentials: web ? 'include' : 'omit',
      headers: { ...(!multipart ? { 'Content-Type': 'application/json' } : {}), 'X-Eleven-Client': web ? 'web' : 'native',
        ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(body === undefined ? {} : { body: multipart ? body : JSON.stringify(body) }),
    });
    const data = response.status === 204 ? null : await response.json();
    if (!response.ok) {
      throw new ApiError(typeof data?.detail === 'string' ? data.detail : 'Não foi possível concluir. Tente novamente.',
        response.status, Number(response.headers.get('Retry-After') || 0));
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError('Não foi possível conectar. Confira sua conexão e tente novamente.', 0);
  } finally { clearTimeout(timeout); }
}

export async function acceptTokens(tokens: Tokens) {
  // Persist the rotated native refresh before publishing the access token.
  if (!web) await storeRefresh(tokens.refresh_token || null);
  accessToken = tokens.access_token;
}

export async function clearLocalSession() {
  accessToken = null;
  await storeRefresh(null);
}

async function doRefresh(): Promise<boolean> {
  const raw = await readRefresh();
  if (!web && !raw) return false;
  try {
    const tokens = await request<Tokens>('/v1/auth/refresh', raw ? { refresh_token: raw } : {});
    await acceptTokens(tokens);
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      await clearLocalSession();
      return false;
    }
    throw error;
  }
}

export function refresh(): Promise<boolean> {
  if (refreshing) return refreshing;
  const operation = async (): Promise<boolean> => {
    // Serialize cookie rotation across browser tabs when Web Locks is available.
    if (web && typeof navigator !== 'undefined' && navigator.locks) {
      return await navigator.locks.request('eleven-refresh', doRefresh);
    }
    return doRefresh();
  };
  refreshing = operation().finally(() => { refreshing = null; });
  return refreshing;
}

export async function authenticated<T>(path: string, body?: unknown, method = 'GET'): Promise<T> {
  try { return await request<T>(path, body, accessToken, method); }
  catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    if (await refresh()) {
      try { return await request<T>(path, body, accessToken, method); }
      catch (retryError) {
        if (!(retryError instanceof ApiError) || retryError.status !== 401) throw retryError;
      }
    }
    await clearLocalSession();
    onExpired();
    throw new ApiError('Sua sessão expirou. Entre novamente.', 401);
  }
}

export const register = (name: string, contact: string, password: string, confirmation: string) =>
  request<Verification>('/v1/auth/register', { name, contact, password, password_confirmation: confirmation });
export const login = (contact: string, password: string) => request<AuthResult>('/v1/auth/login', { contact, password });
export const verify = (ticket: Verification, code: string) =>
  request<Tokens>('/v1/auth/verify', { challenge_token: ticket.challenge_token, code });
export const resend = (ticket: Verification, contact?: string) => request<Verification>(
  contact === undefined ? '/v1/auth/resend' : '/v1/auth/change-contact',
  { challenge_token: ticket.challenge_token, ...(contact === undefined ? {} : { contact }) },
);
export const getProfile = () => authenticated<Profile>('/v1/me');
export const saveProfile = (name: string) => authenticated<Profile>('/v1/me/profile', { name }, 'PUT');
export async function logout() {
  const raw = await readRefresh();
  await request<void>('/v1/auth/logout', raw ? { refresh_token: raw } : {});
  await clearLocalSession();
}
