import { getCsrfToken } from "./auth";
import type {
  AdminConversationDetail,
  AdminSessionSummary,
  CoachOption,
  ConversationUserSummary,
  ImportResult,
  ManagedUser,
  ManagedUserPayload,
} from "@/types/admin";

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

export async function listManagedUsers(): Promise<ManagedUser[]> {
  return (await adminFetch("/api/v1/admin/users", { cache: "no-store" })).json();
}

export async function createManagedUser(payload: ManagedUserPayload): Promise<ManagedUser> {
  return (await adminFetch("/api/v1/admin/users", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload),
  })).json();
}

export async function updateManagedUser(id: string, payload: ManagedUserPayload): Promise<ManagedUser> {
  return (await adminFetch(`/api/v1/admin/users/${id}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify(payload),
  })).json();
}

export async function listCoachOptions(): Promise<CoachOption[]> {
  return (await adminFetch("/api/v1/admin/users/coaches", { cache: "no-store" })).json();
}

export async function importManagedUsers(file: File): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  return (await adminFetch("/api/v1/admin/users/import", {
    method: "POST",
    headers: headers(false),
    body: form,
  })).json();
}

export function managedUsersTemplateUrl(): string {
  return endpoint("/api/v1/admin/users/template");
}

export async function listConversationUsers(scope: "mine" | "all"): Promise<ConversationUserSummary[]> {
  return (await adminFetch(`/api/v1/admin/conversations/users?scope=${encodeURIComponent(scope)}`, {
    cache: "no-store",
  })).json();
}

export async function listConversationSessions(managedUserId: string): Promise<AdminSessionSummary[]> {
  return (await adminFetch(`/api/v1/admin/conversations/users/${managedUserId}/sessions`, {
    cache: "no-store",
  })).json();
}

export async function getConversationSession(sessionId: string): Promise<AdminConversationDetail> {
  return (await adminFetch(`/api/v1/admin/conversations/sessions/${sessionId}`, {
    cache: "no-store",
  })).json();
}
