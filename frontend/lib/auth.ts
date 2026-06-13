import { TokenResponse, UserInfo, CASExchangeResponse } from "@/types/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "";
const AUTH_KEY = "gb_auth";

// ---------- CSRF helper ----------

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

// ---------- Legacy JWT storage (auth_mode=both transition) ----------

interface StoredAuth {
  access_token: string;
  refresh_token: string;
  expires_at: number;
}

function getStoredAuth(): StoredAuth | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(AUTH_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

function setStoredAuth(auth: StoredAuth): void {
  localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
}

function clearStoredAuth(): void {
  localStorage.removeItem(AUTH_KEY);
}

export function getAccessToken(): string | null {
  const auth = getStoredAuth();
  if (!auth) return null;
  if (Date.now() >= auth.expires_at) return null;
  return auth.access_token;
}

// ---------- Auth state check ----------

/**
 * Check if user is authenticated.
 * Tries session cookie first (via /auth/me), falls back to JWT token.
 */
export async function checkAuth(): Promise<UserInfo | null> {
  // First try cookie-based session (SSO)
  try {
    const resp = await fetch(`${API_BASE}/api/v1/auth/me`, {
      credentials: "include",
    });
    if (resp.ok) {
      return await resp.json();
    }
  } catch {
    // Network error, fall through
  }

  // Fallback: JWT token (local auth in transition mode)
  const token = getAccessToken();
  if (token) {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.ok) return await resp.json();
    } catch { /* fall through */ }
  }

  return null;
}

/** Synchronous quick check — only tests JWT localStorage (for initial redirect guard). */
export function hasLocalToken(): boolean {
  return getAccessToken() !== null;
}

/** Check if a session cookie exists (not httpOnly, but session cookie is — check CSRF instead). */
export function hasSessionHint(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.includes("csrf_token=");
}

// ---------- CAS SSO ----------

/**
 * Exchange CAS ticket for server-side session.
 * Cookie is set by the response automatically.
 */
export async function casExchange(ticket: string): Promise<CASExchangeResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/cas/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ ticket }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({ detail: "SSO 登录失败" }));
    throw new Error(data.detail || "SSO 登录失败");
  }
  return resp.json();
}

/** Get CAS login redirect URL. */
export function getCasLoginUrl(): string {
  return `${API_BASE}/api/v1/cas/login`;
}

// ---------- Local auth (legacy) ----------

export async function login(email: string, password: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    const data = await resp.json();
    throw new Error(data.detail || "登录失败");
  }
  const tokens: TokenResponse = await resp.json();
  setStoredAuth({
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
    expires_at: Date.now() + 30 * 60 * 1000,
  });
  return tokens;
}

export async function register(email: string, password: string, nickname?: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, nickname }),
  });
  if (!resp.ok) {
    const data = await resp.json();
    throw new Error(data.detail || "注册失败");
  }
  const tokens: TokenResponse = await resp.json();
  setStoredAuth({
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
    expires_at: Date.now() + 30 * 60 * 1000,
  });
  return tokens;
}

export async function refreshToken(): Promise<string | null> {
  const auth = getStoredAuth();
  if (!auth) return null;
  try {
    const resp = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: auth.refresh_token }),
    });
    if (!resp.ok) {
      clearStoredAuth();
      return null;
    }
    const tokens: TokenResponse = await resp.json();
    setStoredAuth({
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      expires_at: Date.now() + 30 * 60 * 1000,
    });
    return tokens.access_token;
  } catch {
    clearStoredAuth();
    return null;
  }
}

// ---------- Logout ----------

export async function logout(): Promise<void> {
  // Call backend to revoke session + get SID redirect
  try {
    const resp = await fetch(`${API_BASE}/api/v1/auth/logout`, {
      method: "POST",
      credentials: "include",
      redirect: "manual", // Don't follow SID redirect automatically
    });
    // If we get a redirect (302), navigate to it
    if (resp.type === "opaqueredirect" || resp.status === 302) {
      const location = resp.headers.get("location");
      if (location) {
        clearStoredAuth();
        window.location.href = location;
        return;
      }
    }
  } catch {
    // Network error, just clear local state
  }
  clearStoredAuth();
  window.location.href = "/login";
}

// ---------- User info ----------

export async function getUserInfo(): Promise<UserInfo | null> {
  // Try cookie session first
  try {
    const resp = await fetch(`${API_BASE}/api/v1/auth/me`, {
      credentials: "include",
    });
    if (resp.ok) return resp.json();
  } catch { /* fall through */ }

  // Fallback to JWT
  const token = getAccessToken();
  if (!token) return null;
  try {
    const resp = await fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return null;
    return resp.json();
  } catch {
    return null;
  }
}

// Re-export for api.ts
export { getCsrfToken };
