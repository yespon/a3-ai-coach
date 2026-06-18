import { getCsrfToken } from "./auth";
import type {
  AdminConversationDetail,
  AdminSessionSummary,
  CoachOption,
  ConversationSummary,
  ConversationUserSummary,
  ImportResult,
  ManagedUser,
  ManagedUserCoachFilter,
  ManagedUserFilters,
  ManagedUserHasEmail,
  ManagedUserPayload,
  Paginated,
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

export async function listManagedUsers(
  filters: ManagedUserFilters = {},
  page = 1,
  pageSize = 30,
): Promise<Paginated<ManagedUser>> {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.role) params.set("role", filters.role);
  if (filters.enabled !== null && filters.enabled !== undefined) params.set("enabled", String(filters.enabled));
  if (filters.coach_filter && filters.coach_filter !== "all") params.set("coach_filter", filters.coach_filter);
  if (filters.department_level1?.trim()) params.set("department_level1", filters.department_level1.trim());
  if (filters.has_email === true || filters.has_email === false) params.set("has_email", String(filters.has_email));
  return (await adminFetch(`/api/v1/admin/users?${params.toString()}`, { cache: "no-store" })).json();
}

export async function createManagedUser(payload: ManagedUserPayload): Promise<ManagedUser> {
  return (await adminFetch("/api/v1/admin/users", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload),
  })).json();
}

export async function updateManagedUser(id: string, payload: Partial<ManagedUserPayload>): Promise<ManagedUser> {
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

export async function summarizeConversation(sessionId: string): Promise<ConversationSummary> {
  return (await adminFetch(`/api/v1/admin/conversations/sessions/${sessionId}/summary`, {
    method: "POST",
    headers: headers(),
  })).json();
}
