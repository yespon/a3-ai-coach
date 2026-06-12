import { TokenResponse, UserInfo } from "@/types/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "";
const AUTH_KEY = "gb_auth";

interface StoredAuth {
  access_token: string;
  refresh_token: string;
  expires_at: number; // Unix timestamp in ms
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

export function isAuthenticated(): boolean {
  const auth = getStoredAuth();
  if (!auth) return false;
  return Date.now() < auth.expires_at;
}

export function getAccessToken(): string | null {
  const auth = getStoredAuth();
  if (!auth) return null;
  if (Date.now() >= auth.expires_at) {
    return null;
  }
  return auth.access_token;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    const data = await resp.json();
    throw new Error(data.detail || "\u767b\u5f55\u5931\u8d1d");
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
    throw new Error(data.detail || "\u767b\u5f55\u5931\u8d1d");
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

export function logout(): void {
  clearStoredAuth();
  window.location.href = "/login";
}

export async function getUserInfo(): Promise<UserInfo | null> {
  const token = getAccessToken();
  if (!token) return null;
  const resp = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) return null;
  return resp.json();
}
