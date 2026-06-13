import { ChatResponse, SessionResponse, SessionSummary, StreamEvent } from "@/types/chat";
import { getAccessToken, refreshToken, logout, getCsrfToken } from "./auth";

// Default to same-origin API routes to avoid CORS/preflight issues in Docker or LAN access.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "";

function endpoint(path: string): string {
  return `${API_BASE}${path}`;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};

  // JWT token (local auth fallback for transition period)
  const token = getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // CSRF token for cookie-session auth (POST/PUT/DELETE)
  const csrf = getCsrfToken();
  if (csrf) {
    headers["X-CSRF-Token"] = csrf;
  }

  return headers;
}

async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = { ...options.headers, ...authHeaders() };
  const resp = await fetch(url, {
    ...options,
    headers,
    credentials: "include", // Always send cookies
  });

  if (resp.status === 401) {
    // Try JWT refresh if we have a token
    const newToken = await refreshToken();
    if (newToken) {
      const retryHeaders = { ...options.headers, ...authHeaders(), Authorization: `Bearer ${newToken}` };
      return fetch(url, { ...options, headers: retryHeaders, credentials: "include" });
    }
    logout();
    throw new Error("认证已过期，请重新登录");
  }
  return resp;
}

export async function createSession(showContextInHistory: boolean): Promise<SessionResponse> {
  const response = await authFetch(endpoint("/api/v1/sessions"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ show_context_in_history: showContextInHistory }),
  });
  if (!response.ok) {
    throw new Error(`Create session failed: ${response.status}`);
  }
  return response.json();
}

export async function listSessions(): Promise<SessionSummary[]> {
  const response = await authFetch(endpoint("/api/v1/sessions"), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`List sessions failed: ${response.status}`);
  }
  return response.json();
}

export async function getSession(sessionId: string): Promise<SessionResponse> {
  const response = await authFetch(endpoint(`/api/v1/sessions/${sessionId}`), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Get session failed: ${response.status}`);
  }
  return response.json();
}

export async function sendChat(
  sessionId: string,
  message: string,
  files: File[]
): Promise<ChatResponse> {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  formData.append("message", message);
  files.forEach((file) => formData.append("files", file));

  const response = await authFetch(endpoint("/api/v1/chat"), {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Send chat failed: ${response.status}`);
  }

  return response.json();
}

export async function streamChat(
  sessionId: string,
  message: string,
  files: File[],
  onEvent: (event: StreamEvent) => void
): Promise<void> {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  formData.append("message", message);
  files.forEach((file) => formData.append("files", file));

  const response = await authFetch(endpoint("/api/v1/chat/stream"), {
    method: "POST",
    body: formData,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Stream chat failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";

    for (const chunk of chunks) {
      const lines = chunk
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.startsWith("data:"));

      for (const line of lines) {
        const raw = line.slice(5).trim();
        if (!raw) {
          continue;
        }

        try {
          const event = JSON.parse(raw) as StreamEvent;
          onEvent(event);
        } catch {
          onEvent({ type: "error", message: "Malformed SSE payload." });
        }
      }
    }
  }
}
