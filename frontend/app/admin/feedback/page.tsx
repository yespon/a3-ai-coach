"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import AdminPagination from "@/components/admin/AdminPagination";
import { adminListFeedback } from "@/lib/feedback";
import { checkAuth } from "@/lib/auth";
import type { UserInfo } from "@/types/auth";
import type { FeedbackListItem, FeedbackStatus } from "@/types/feedback";

const PAGE_SIZE_STORAGE = "admin.feedback.pageSize";
const PAGE_SIZE_OPTIONS = [10, 30, 50, 100] as const;
type StatusFilter = "all" | FeedbackStatus;

function readPageSize(): number {
  if (typeof window === "undefined") return 30;
  const raw = window.localStorage.getItem(PAGE_SIZE_STORAGE);
  if (!raw) return 30;
  const n = Number(raw);
  return PAGE_SIZE_OPTIONS.includes(n as (typeof PAGE_SIZE_OPTIONS)[number]) ? n : 30;
}

const STATUS_LABELS: Record<StatusFilter, string> = {
  all: "全部",
  open: "未读",
  read: "已读",
  resolved: "已处理",
};

export default function AdminFeedbackPage() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [items, setItems] = useState<FeedbackListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void checkAuth().then(setUser);
    setPageSize(readPageSize());
  }, []);

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, q, page, pageSize]);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const data = await adminListFeedback({ status, q: q.trim() || null }, page, pageSize);
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  const counts = useMemo(() => {
    const acc: Record<StatusFilter, number> = { all: total, open: 0, read: 0, resolved: 0 };
    for (const item of items) {
      acc[item.status] += 1;
    }
    return acc;
  }, [items, total]);

  if (user && !user.is_admin) {
    return (
      <div className="admin-page-stack">
        <div className="admin-error">仅管理员可访问意见反馈模块。</div>
      </div>
    );
  }

  return (
    <div className="admin-page-stack">
      <section className="admin-page-header">
        <div>
          <p className="admin-kicker">Feedback Inbox</p>
          <h2>意见反馈</h2>
          <p>查看用户提交的意见与建议,支持状态流转与附件预览。</p>
        </div>
      </section>

      <section className="admin-stat-grid" aria-label="反馈统计">
        {(["all", "open", "read", "resolved"] as StatusFilter[]).map((key) => (
          <article className="admin-card admin-stat-card" key={key}>
            <p className="admin-kicker">{STATUS_LABELS[key]}</p>
            <h3>{counts[key]}</h3>
            <p>{key === "all" ? "总数" : "本页"}</p>
          </article>
        ))}
      </section>

      <section className="admin-user-toolbar" aria-label="过滤">
        <label>
          关键词
          <input
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
            placeholder="按内容搜索"
          />
        </label>
      </section>

      {error ? <div className="admin-error">{error}</div> : null}

      <section className="admin-card admin-table-card">
        <div className="admin-section-head">
          <div className="admin-segmented" role="group" aria-label="状态过滤">
            {(["all", "open", "read", "resolved"] as StatusFilter[]).map((key) => (
              <button
                key={key}
                type="button"
                className={status === key ? "active" : ""}
                onClick={() => {
                  setStatus(key);
                  setPage(1);
                }}
              >
                {STATUS_LABELS[key]}
              </button>
            ))}
          </div>
          <span className="admin-count">{items.length} 条</span>
        </div>

        {loading ? (
          <div className="admin-empty-state">正在加载反馈数据…</div>
        ) : items.length === 0 ? (
          <div className="admin-empty-state">没有匹配的反馈。</div>
        ) : (
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>提交时间</th>
                  <th>提交人</th>
                  <th>摘要</th>
                  <th>附件</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{formatDate(item.created_at)}</td>
                    <td>
                      {item.submitter.name || "未填写"}
                      <br />
                      <small style={{ color: "#94a3b8" }}>{item.submitter.employee_no || "—"}</small>
                    </td>
                    <td>{item.content_excerpt}</td>
                    <td>{item.attachment_count}</td>
                    <td>
                      <span className={statusBadgeClass(item.status)}>{STATUS_LABELS[item.status]}</span>
                    </td>
                    <td>
                      <Link className="admin-link-button" href={`/admin/feedback/${item.id}`}>
                        查看
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <AdminPagination
          page={page}
          pageSize={pageSize}
          total={total}
          pageSizeOptions={[...PAGE_SIZE_OPTIONS]}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
            if (typeof window !== "undefined") {
              window.localStorage.setItem(PAGE_SIZE_STORAGE, String(size));
            }
          }}
          storageKey={PAGE_SIZE_STORAGE}
        />
      </section>
    </div>
  );
}

function statusBadgeClass(status: FeedbackStatus) {
  if (status === "open") return "admin-pill admin-pill-gold";
  if (status === "resolved") return "admin-pill admin-pill-green";
  return "admin-pill";
}

function formatDate(value: string | null | undefined) {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}
