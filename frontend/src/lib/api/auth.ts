import { api, saveSession, clearSession } from "./client";
import type { TokenBundle, UserOut } from "./types";

export async function signup(email: string, password: string): Promise<UserOut> {
  const bundle = await api<TokenBundle>("/auth/signup", {
    body: { email, password },
    auth: false,
  });
  saveSession(bundle);
  return bundle.user;
}

export async function login(email: string, password: string): Promise<UserOut> {
  const bundle = await api<TokenBundle>("/auth/login", {
    body: { email, password },
    auth: false,
  });
  saveSession(bundle);
  return bundle.user;
}

export function logout() {
  clearSession();
  localStorage.removeItem("leadpilot.theme");
}

export function me(): Promise<UserOut> {
  return api<UserOut>("/auth/me");
}
