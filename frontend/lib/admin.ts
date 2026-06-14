import { getCsrfToken } from "./auth";
import type { ImportResult, WhitelistEntry } from "@/types/admin";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "";
const endpoint = (path: string) => `${API_BASE}${path}`;

function headers(json = true): HeadersInit {
  const h: Record<string, string> = {};
  const csrf = getCsrfToken();
  if (csrf) h["X-CSRF-Token"] = csrf;
  if (json) h["Content-Type"] = "application/json";
  return h;
}

async function adminFetch(path: string, options: RequestInit = {}) {
  const resp = await fetch(endpoint(path), { ...options, credentials: "include" });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败: ${resp.status}`);
  }
  return resp;
}

export async function listWhitelist(): Promise<WhitelistEntry[]> {
  return (await adminFetch("/api/v1/admin/whitelist", { cache: "no-store" })).json();
}

export async function addWhitelistEntry(employee_no: string, email?: string): Promise<WhitelistEntry> {
  return (await adminFetch("/api/v1/admin/whitelist", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ employee_no, email: email || null }),
  })).json();
}

export async function setWhitelistEnabled(id: string, enabled: boolean): Promise<WhitelistEntry> {
  return (await adminFetch(`/api/v1/admin/whitelist/${id}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({ enabled }),
  })).json();
}

export async function importWhitelist(file: File): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  return (await adminFetch("/api/v1/admin/whitelist/import", {
    method: "POST",
    headers: headers(false),
    body: form,
  })).json();
}

export function whitelistTemplateUrl(): string {
  return endpoint("/api/v1/admin/whitelist/template");
}
