import { getCsrfToken } from "./auth";
import type {
  FeedbackDetail,
  FeedbackFilters,
  FeedbackStatus,
  PaginatedFeedbackList,
} from "@/types/feedback";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "";

function jsonHeaders(): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const csrf = getCsrfToken();
  if (csrf) h["X-CSRF-Token"] = csrf;
  return h;
}

async function send<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: { ...(options.headers || {}), ...jsonHeaders() },
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败: ${resp.status}`);
  }
  return resp.json();
}

export async function submitFeedback(content: string, images: File[]): Promise<{ id: string; created_at: string }> {
  const form = new FormData();
  form.append("content", content);
  for (const img of images) {
    form.append("images", img);
  }
  const csrf = getCsrfToken();
  const resp = await fetch(`${API_BASE}/api/v1/feedback`, {
    method: "POST",
    credentials: "include",
    headers: csrf ? { "X-CSRF-Token": csrf } : undefined,
    body: form,
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `提交失败: ${resp.status}`);
  }
  return resp.json();
}

export async function adminListFeedback(
  filters: FeedbackFilters = {},
  page = 1,
  pageSize = 30,
): Promise<PaginatedFeedbackList> {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  if (filters.status && filters.status !== "all") params.set("status", filters.status);
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  return send(`/api/v1/admin/feedback?${params.toString()}`);
}

export async function adminGetFeedback(id: string): Promise<FeedbackDetail> {
  return send(`/api/v1/admin/feedback/${id}`);
}

export async function adminPatchFeedbackStatus(id: string, status: FeedbackStatus): Promise<void> {
  await send(`/api/v1/admin/feedback/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}
