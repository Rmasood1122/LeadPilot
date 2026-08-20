/**
 * auth-session.ts — ClientHunter Enterprise
 *
 * JWT access + refresh token management.
 *
 * M7 MIGRATION NOTE:
 * M5 stored tokens via localStorage.setItem('access_token', ...) / localStorage.setItem('refresh_token', ...).
 * All such calls must be replaced with the functions below. Search for:
 *   localStorage.setItem('access_token'
 *   localStorage.setItem('refresh_token'
 *   localStorage.getItem('access_token'
 *   localStorage.getItem('refresh_token'
 *   localStorage.removeItem('access_token'
 *   localStorage.removeItem('refresh_token'
 * and replace with the corresponding function from this module.
 *
 * On mobile: tokens are stored in OS-level secure storage (Capacitor Preferences).
 * On web: tokens are stored in sessionStorage (cleared on tab close — intentional).
 */

import { storage } from './storage';

const KEYS = {
  ACCESS: 'ch_access_token',
  REFRESH: 'ch_refresh_token',
  USER_EMAIL: 'ch_user_email',
  USER_ID: 'ch_user_id',
} as const;

// ── Setters ───────────────────────────────────────────────────────────────

export async function setAccessToken(token: string): Promise<void> {
  await storage.set(KEYS.ACCESS, token);
}

export async function setRefreshToken(token: string): Promise<void> {
  await storage.set(KEYS.REFRESH, token);
}

export async function setSession(params: {
  accessToken: string;
  refreshToken: string;
  userEmail?: string;
  userId?: string;
}): Promise<void> {
  await Promise.all([
    storage.set(KEYS.ACCESS, params.accessToken),
    storage.set(KEYS.REFRESH, params.refreshToken),
    params.userEmail ? storage.set(KEYS.USER_EMAIL, params.userEmail) : Promise.resolve(),
    params.userId ? storage.set(KEYS.USER_ID, params.userId) : Promise.resolve(),
  ]);
}

// ── Getters ───────────────────────────────────────────────────────────────

export async function getAccessToken(): Promise<string | null> {
  return storage.get(KEYS.ACCESS);
}

export async function getRefreshToken(): Promise<string | null> {
  return storage.get(KEYS.REFRESH);
}

export async function getUserEmail(): Promise<string | null> {
  return storage.get(KEYS.USER_EMAIL);
}

export async function getUserId(): Promise<string | null> {
  return storage.get(KEYS.USER_ID);
}

export async function hasSession(): Promise<boolean> {
  const token = await storage.get(KEYS.ACCESS);
  return token !== null && token.length > 0;
}

// ── Clear (logout) ────────────────────────────────────────────────────────

export async function clearSession(): Promise<void> {
  await Promise.all([
    storage.remove(KEYS.ACCESS),
    storage.remove(KEYS.REFRESH),
    storage.remove(KEYS.USER_EMAIL),
    storage.remove(KEYS.USER_ID),
  ]);
}

// ── Synchronous shim (for code that hasn't been converted to async yet) ───
// These read from sessionStorage directly on web for backwards-compat with
// M5 synchronous reads. On mobile they return null (caller must use async
// getters above). Mark each call site with TODO: convert to async.

export function getAccessTokenSync(): string | null {
  if (typeof window === 'undefined') return null;
  // On mobile this will return null — use getAccessToken() (async) instead.
  // TODO: migrate all callers of this function to the async getter above.
  return sessionStorage.getItem(KEYS.ACCESS);
}
