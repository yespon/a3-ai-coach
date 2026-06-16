"use client";

import { useEffect, useMemo, useState } from "react";
import { getConversationSession, listConversationSessions, listConversationUsers } from "@/lib/admin";
import { checkAuth } from "@/lib/auth";
import type { AdminConversationDetail, AdminSessionSummary, ConversationUserSummary } from "@/types/admin";
import type { UserInfo } from "@/types/auth";
import type { AttachmentMeta, ChatHistoryItem } from "@/types/chat";

type ConversationScope = "mine" | "all";

export default function AdminConversationsPage() {
  const [currentUser, setCurrentUser] = useState<UserInfo | null>(null);
  const [scope, setScope] = useState<ConversationScope>("all");
  const [users, setUsers] = useState<ConversationUserSummary[]>([]);
  const [selectedUser, setSelectedUser] = useState<ConversationUserSummary | null>(null);
  const [sessions, setSessions] = useState<AdminSessionSummary[]>([]);
  const [selectedSession, setSelectedSession] = useState<AdminSessionSummary | null>(null);
  const [detail, setDetail] = useState<AdminConversationDetail | null>(null);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function initialize() {
      setLoadingUsers(true);
      setError("");
      try {
        const user = await checkAuth();
        if (!active) return;
        const defaultScope: ConversationScope = user?.is_admin && user.is_coach ? "mine" : "all";
        setCurrentUser(user);
        setScope(defaultScope);
        const conversationUsers = await listConversationUsers(defaultScope);
        if (!active) return;
        setUsers(conversationUsers);
      } catch (err) {
        if (active) setError(formatError(err));
      } finally {
        if (active) setLoadingUsers(false);
      }
    }
    void initialize();
    return () => {
      active = false;
    };
  }, []);

  const selectedUserName = useMemo(() => formatUserName(selectedUser), [selectedUser]);

  async function changeScope(nextScope: ConversationScope) {
    if (nextScope === scope) return;
    setScope(nextScope);
    setSelectedUser(null);
    setSessions([]);
    setSelectedSession(null);
    setDetail(null);
    await refreshUsers(nextScope);
  }

  async function refreshUsers(nextScope = scope) {
    setLoadingUsers(true);
    setError("");
    try {
      const conversationUsers = await listConversationUsers(nextScope);
      setUsers(conversationUsers);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoadingUsers(false);
    }
  }

  async function selectUser(user: ConversationUserSummary) {
    setSelectedUser(user);
    setSelectedSession(null);
    setDetail(null);
    setSessions([]);
    setLoadingSessions(true);
    setError("");
    try {
      const userSessions = await listConversationSessions(user.managed_user_id);
      setSessions(userSessions);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoadingSessions(false);
    }
  }

  async function selectSession(session: AdminSessionSummary) {
    setSelectedSession(session);
    setDetail(null);
    setLoadingDetail(true);
    setError("");
    try {
      const conversationDetail = await getConversationSession(session.session_id);
      setDetail(conversationDetail);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoadingDetail(false);
    }
  }

  return (
    <div className="admin-page-stack">
      <section className="admin-page-header admin-conversation-header">
        <div>
          <p className="admin-kicker">Conversation Archive</p>
          <h2>对话历史</h2>
          <p>按权限查看学员与 AI 教练的历史会话，仅提供只读审阅。</p>
        </div>
        <div className="admin-segmented" role="group" aria-label="对话范围">
          <button className={scope === "mine" ? "active" : ""} type="button" onClick={() => void changeScope("mine")} disabled={loadingUsers}>
            我的学员
          </button>
          {currentUser?.is_admin ? (
            <button className={scope === "all" ? "active" : ""} type="button" onClick={() => void changeScope("all")} disabled={loadingUsers}>
              全部
            </button>
          ) : null}
        </div>
      </section>

      {error ? <div className="admin-error">{error}</div> : null}

      <section className="admin-conversation-grid">
        <article className="admin-card admin-table-card">
          <div className="admin-section-head">
            <div>
              <p className="admin-kicker">Students</p>
              <h3>学员概览</h3>
            </div>
            <span className="admin-count">{users.length} 人</span>
          </div>

          {loadingUsers ? (
            <div className="admin-empty-state">正在加载学员对话数据...</div>
          ) : users.length === 0 ? (
            <div className="admin-empty-state">当前范围暂无学员会话。</div>
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table admin-conversation-users-table">
                <thead>
                  <tr>
                    <th>工号</th>
                    <th>姓名</th>
                    <th>一级部门</th>
                    <th>会话数</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => {
                    const selected = selectedUser?.managed_user_id === user.managed_user_id;
                    return (
                      <tr className={selected ? "admin-selected-row" : ""} key={user.managed_user_id}>
                        <td>{user.employee_no}</td>
                        <td>{user.name || "未填写"}</td>
                        <td>{user.department_level1 || "未填写"}</td>
                        <td>{user.session_count}</td>
                        <td>
                          <button className="admin-link-button" type="button" onClick={() => void selectUser(user)}>
                            查看
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </article>

        <article className="admin-card admin-table-card">
          <div className="admin-section-head">
            <div>
              <p className="admin-kicker">Sessions</p>
              <h3>{selectedUser ? `${selectedUserName} 的会话` : "会话列表"}</h3>
            </div>
            <span className="admin-count">{sessions.length} 条</span>
          </div>

          {!selectedUser ? (
            <div className="admin-empty-state">请先选择左侧学员。</div>
          ) : loadingSessions ? (
            <div className="admin-empty-state">正在加载会话列表...</div>
          ) : sessions.length === 0 ? (
            <div className="admin-empty-state">该学员暂无会话。</div>
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table admin-conversation-sessions-table">
                <thead>
                  <tr>
                    <th>最近内容</th>
                    <th>更新时间</th>
                    <th>消息数</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((session) => {
                    const selected = selectedSession?.session_id === session.session_id;
                    return (
                      <tr className={selected ? "admin-selected-row" : ""} key={session.session_id}>
                        <td className="admin-preview-cell">{session.latest_preview || "暂无内容"}</td>
                        <td>{formatDate(session.updated_at)}</td>
                        <td>{session.message_count}</td>
                        <td>
                          <button className="admin-link-button" type="button" onClick={() => void selectSession(session)}>
                            详情
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </article>
      </section>

      <section className="admin-card admin-conversation-detail-card">
        <div className="admin-section-head">
          <div>
            <p className="admin-kicker">Read-only Detail</p>
            <h3>会话详情</h3>
          </div>
          {detail ? <span className="admin-count">{detail.history.length} 条消息</span> : null}
        </div>

        {!selectedSession ? (
          <div className="admin-empty-state">选择会话后在此查看完整历史。</div>
        ) : loadingDetail ? (
          <div className="admin-empty-state">正在加载会话详情...</div>
        ) : detail ? (
          <div className="admin-detail-stack">
            <div className="admin-detail-meta">
              <span>{formatUserName(detail.student)}</span>
              <span>创建：{formatDate(detail.created_at)}</span>
              <span>更新：{formatDate(detail.updated_at)}</span>
            </div>
            <div className="admin-message-list" aria-label="会话消息">
              {detail.history.length === 0 ? (
                <div className="admin-empty-state">该会话暂无消息内容。</div>
              ) : (
                detail.history.map((message, index) => <ConversationMessage message={message} index={index} key={`${message.role}-${index}`} />)
              )}
            </div>
          </div>
        ) : (
          <div className="admin-empty-state">暂无详情。</div>
        )}
      </section>
    </div>
  );
}

function ConversationMessage({ message, index }: { message: ChatHistoryItem; index: number }) {
  const isAssistant = message.role === "assistant";
  return (
    <article className={`admin-message ${isAssistant ? "admin-message-assistant" : "admin-message-user"}`}>
      <div className="admin-message-head">
        <span>{isAssistant ? "AI 教练" : "user"}</span>
        <time>{message.created_at ? formatDate(message.created_at) : `#${index + 1}`}</time>
      </div>
      <div className="admin-message-content">{message.content || "（空消息）"}</div>
      {message.attachments && message.attachments.length > 0 ? <AttachmentList attachments={message.attachments} /> : null}
    </article>
  );
}

function AttachmentList({ attachments }: { attachments: AttachmentMeta[] }) {
  return (
    <div className="admin-attachment-list" aria-label="附件列表">
      {attachments.map((attachment, index) => (
        <div className="admin-attachment-chip" key={`${attachment.filename}-${index}`}>
          <span>{attachment.filename}</span>
          <small>{formatSize(attachment.size)}</small>
        </div>
      ))}
    </div>
  );
}

function formatUserName(user: Pick<ConversationUserSummary, "employee_no" | "name" | "department_level1"> | null) {
  if (!user) return "未选择学员";
  const name = user.name || user.employee_no;
  return user.department_level1 ? `${name} · ${user.department_level1}` : name;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}

function formatSize(size: number | undefined) {
  if (!size) return "大小未知";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatError(err: unknown) {
  return err instanceof Error ? err.message : "请求失败";
}
