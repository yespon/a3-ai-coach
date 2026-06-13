"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { createSession, getSession, listSessions, sendChat, streamChat } from "@/lib/api";
import { ChatHistoryItem, SessionSummary } from "@/types/chat";
import { checkAuth, logout, hasSessionHint } from "@/lib/auth";
import type { UserInfo } from "@/types/auth";

export default function HomePage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [history, setHistory] = useState<ChatHistoryItem[]>([]);
  const [message, setMessage] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [showContextInHistory, setShowContextInHistory] = useState(false);
  const [streamMode, setStreamMode] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [streamingDraft, setStreamingDraft] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const messageListRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // Quick synchronous check — if no session hint, redirect immediately
    if (!hasSessionHint()) {
      window.location.href = "/login";
      return;
    }
    // Async verification against backend
    checkAuth().then((user) => {
      if (!user) {
        window.location.href = "/login";
      } else {
        setUserInfo(user);
      }
    });
  }, []);

  useEffect(() => {
    void bootstrapSession();
  }, []);

  useEffect(() => {
    messageListRef.current?.scrollTo({ top: messageListRef.current.scrollHeight, behavior: "smooth" });
  }, [history, streamingDraft]);

  useEffect(() => {
    syncComposerHeight();
  }, [message]);

  const renderedMessages = useMemo(() => {
    const rows = [...history];
    if (streamingDraft) {
      rows.push({ role: "assistant", content: streamingDraft });
    }
    return rows;
  }, [history, streamingDraft]);

  const selectedFileNames = useMemo(() => files.map((file) => file.name), [files]);

  async function bootstrapSession() {
    try {
      setBusy(true);
      setError("");

      const data = await listSessions();
      setSessions(data);

      if (data.length > 0) {
        const first = await getSession(data[0].session_id);
        setSessionId(first.session_id);
        setHistory(first.history || []);
      } else {
        const created = await createSession(showContextInHistory);
        setSessionId(created.session_id);
        setHistory(created.history || []);
        const latest = await listSessions();
        setSessions(latest);
      }
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  function syncComposerHeight() {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "0px";
    const next = Math.min(textarea.scrollHeight, 220);
    textarea.style.height = `${Math.max(next, 44)}px`;
    textarea.style.overflowY = textarea.scrollHeight > 220 ? "auto" : "hidden";
  }

  async function refreshSessions() {
    try {
      setError("");
      const data = await listSessions();
      setSessions(data);
    } catch (err) {
      setError(formatError(err));
    }
  }

  async function onCreateSession() {
    try {
      setBusy(true);
      setError("");
      const session = await createSession(showContextInHistory);
      setSessionId(session.session_id);
      setHistory(session.history || []);
      await refreshSessions();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  async function onSelectSession(target: string) {
    try {
      setBusy(true);
      setError("");
      const session = await getSession(target);
      setSessionId(session.session_id);
      setHistory(session.history || []);
      setStreamingDraft("");
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  async function ensureSessionId(): Promise<string> {
    if (sessionId) {
      return sessionId;
    }
    const created = await createSession(showContextInHistory);
    setSessionId(created.session_id);
    setHistory(created.history || []);
    await refreshSessions();
    return created.session_id;
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!busy && (message.trim() || files.length > 0)) {
        void onSubmit(event as unknown as FormEvent);
      }
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim() && files.length === 0) {
      return;
    }

    try {
      setBusy(true);
      setError("");
      setStreamingDraft("");
      const activeSessionId = await ensureSessionId();

      // If files attached and message is provided, add a system message immediately
      if (files.length > 0 && message.trim().length > 0) {
        setHistory((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "已获取您的岗标材料，正在解析中...",
            created_at: new Date().toISOString(),
            is_context: false,
            attachments: [],
          },
        ]);
      }

      if (!streamMode) {
        const response = await sendChat(activeSessionId, message.trim(), files);
        setHistory(response.history || []);
      } else {
        await streamChat(activeSessionId, message.trim(), files, (evt) => {
          if (evt.type === "delta") {
            setStreamingDraft((prev) => prev + evt.delta);
          } else if (evt.type === "done") {
            setHistory(evt.history || []);
            setStreamingDraft("");
          } else if (evt.type === "error") {
            setError(evt.message);
            setStreamingDraft("");
          }
        });
      }

      setMessage("");
      setFiles([]);
      await refreshSessions();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <div className={`shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
        <aside className="sidebar" aria-label="会话侧边栏">
          <div className="sidebar-head">
            <h2>会话</h2>
            <button
              className={`secondary toggle-sidebar ${sidebarCollapsed ? "is-collapsed" : ""}`}
              type="button"
              onClick={() => setSidebarCollapsed((prev) => !prev)}
              aria-label={sidebarCollapsed ? "展开侧栏" : "收起侧栏"}
            >
              <svg className="toggle-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect x="3.5" y="5" width="17" height="14" rx="3" stroke="currentColor" strokeWidth="1.7" />
                <path d="M9.5 6.5V17.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          <button className="primary" type="button" onClick={onCreateSession} disabled={busy}>
            + 新建会话
          </button>

          {/* <label className="hint option-toggle">
            <input
              type="checkbox"
              checked={showContextInHistory}
              onChange={(e) => setShowContextInHistory(e.target.checked)}
            />
            创建时在历史中显示默认上下文
          </label> */}

          <div className="session-list" aria-label="session-list">
            {sessions.map((item) => (
              <button
                key={item.session_id}
                type="button"
                className={`session-item ${item.session_id === sessionId ? "active" : ""}`}
                onClick={() => void onSelectSession(item.session_id)}
              >
                <div className="session-preview">{item.latest_preview || "(empty)"}</div>
                <div className="session-id">{item.session_id}</div>
              </button>
          ))}
          </div>
          <div className="sidebar-user-bar">
            <div className={`user-avatar ${sidebarCollapsed ? "avatar-collapsed" : ""}`} style={{ background: userInfo ? avatarColor(userInfo.nickname || userInfo.email || "U") : "#94a3b8" }}>
              {userInfo ? (userInfo.nickname || userInfo.email || "U").charAt(0).toUpperCase() : "?"}
            </div>
            {!sidebarCollapsed && (
              <div className="user-info">
                <span className="user-email-masked">{userInfo ? (userInfo.nickname || maskEmail(userInfo.email)) : "用户"}</span>
              </div>
            )}
            {!sidebarCollapsed && (
              <button className="user-menu-trigger" type="button" onClick={() => setShowUserMenu((prev) => !prev)}>
                ⋮
              </button>
            )}
            {showUserMenu && !sidebarCollapsed && (
              <div className="user-popover">
                <button type="button" onClick={() => { setShowUserMenu(false); logout(); }}>退出登录</button>
              </div>
            )}
          </div>
        </aside>

        <section className="chat">
          <header className="chat-head">
            <h1>岗标AI教练 Beta</h1>
            <div className="hint">当前会话: {sessionId || "未选择"}</div>
          </header>

          <div className="messages" ref={messageListRef}>
            {renderedMessages.length === 0 ? (
              <div className="empty-state">开始提问吧，支持文本与附件联合问答。</div>
            ) : null}
            {renderedMessages.map((item, index) => (
              <div key={`${item.role}-${index}`} className={`msg-row ${item.role}`}>
                <div className="msg-role">{item.role === "assistant" ? "Assistant" : "You"}</div>
                <div className={`msg ${item.role}`}>
                  <MessageContent content={item.content} />
                </div>
              </div>
            ))}
          </div>

          <form className="composer" onSubmit={onSubmit}>
            {selectedFileNames.length > 0 ? (
              <div className="upload-status" aria-live="polite">
                <span className="upload-status-label">附件:</span>
                <span className="upload-status-files">{selectedFileNames.join(", ")}</span>
              </div>
            ) : null}

            <div className="composer-box">
              <label className="attach-btn" htmlFor="chat-file-input" aria-label="上传附件">
                +
              </label>
              <input
                id="chat-file-input"
                type="file"
                multiple
                onChange={(e) => setFiles(Array.from(e.target.files || []))}
                disabled={busy}
              />
              <textarea
                ref={textareaRef}
                rows={1}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onInput={syncComposerHeight}
                onKeyDown={onKeyDown}
                placeholder="输入你的问题，支持结合附件进行问答"
                disabled={busy}
              />
              <button className="primary send-btn" type="submit" disabled={busy}>
                {busy ? "发送中" : "发送"}
              </button>
            </div>

            <div className="composer-tips">
              按 <kbd>Enter</kbd> 发送&nbsp;&nbsp;·&nbsp;&nbsp;<kbd>Shift</kbd> + <kbd>Enter</kbd> 换行
              {/* <span className="composer-tips-sep">|</span>
              <label className="option-toggle">
                <input
                  type="checkbox"
                  checked={streamMode}
                  onChange={(e) => setStreamMode(e.target.checked)}
                />
                使用流式回复
              </label> */}
            </div>
          </form>

          {error ? <div className="hint error-text">Error: {error}</div> : null}
        </section>
      </div>
    </main>
  );
}

function MessageContent({ content }: { content: string }) {
  return (
    <div className="markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, ...props }) => <a {...props} target="_blank" rel="noreferrer noopener" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function formatError(err: unknown): string {
  if (err instanceof Error) {
    return err.message;
  }
  return "Unknown error";
}

function maskEmail(email: string | null): string {
  if (!email) return "用户";
  const [local, domain] = email.split("@");
  if (!domain) return email;
  return `${local.charAt(0)}***@${domain}`;
}

const AVATAR_COLORS = ["#0ea5e9", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#ef4444", "#6366f1", "#14b8a6"];

function avatarColor(email: string): string {
  let hash = 0;
  for (let i = 0; i < email.length; i++) {
    hash = email.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}
