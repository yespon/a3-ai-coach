"use client";

import { FormEvent, useEffect, useState } from "react";
import { checkAuth } from "@/lib/auth";
import {
  addWhitelistEntry,
  importWhitelist,
  listWhitelist,
  setWhitelistEnabled,
  whitelistTemplateUrl,
} from "@/lib/admin";
import type { UserInfo } from "@/types/auth";
import type { ImportResult, WhitelistEntry } from "@/types/admin";

export default function WhitelistAdminPage() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [entries, setEntries] = useState<WhitelistEntry[]>([]);
  const [employeeNo, setEmployeeNo] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);

  useEffect(() => {
    checkAuth().then((u) => {
      setUser(u);
      if (u?.is_admin) refresh();
    });
  }, []);

  async function refresh() {
    try {
      setEntries(await listWhitelist());
    } catch (e) {
      setError(formatError(e));
    }
  }

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await addWhitelistEntry(employeeNo, email || undefined);
      setEmployeeNo("");
      setEmail("");
      await refresh();
    } catch (e) {
      setError(formatError(e));
    } finally {
      setBusy(false);
    }
  }

  async function onImport(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await importWhitelist(file));
      await refresh();
    } catch (e) {
      setError(formatError(e));
    } finally {
      setBusy(false);
    }
  }

  if (user && !user.is_admin) {
    return (
      <main className="admin-page">
        <div className="admin-card">
          <h1>无权限访问</h1>
          <button onClick={() => { window.location.href = "/"; }}>返回首页</button>
        </div>
      </main>
    );
  }

  return (
    <main className="admin-page">
      <div className="admin-card">
        <header className="admin-head">
          <h1>白名单管理</h1>
          <button onClick={() => { window.location.href = "/"; }}>返回首页</button>
        </header>
        <section className="admin-actions">
          <a className="secondary" href={whitelistTemplateUrl()}>下载模板</a>
          <label className="secondary">
            导入 Excel
            <input
              type="file"
              accept=".xlsx"
              hidden
              onChange={(e) => void onImport(e.target.files?.[0] || null)}
              disabled={busy}
            />
          </label>
          <form onSubmit={onAdd} className="admin-add-form">
            <input value={employeeNo} onChange={(e) => setEmployeeNo(e.target.value)} placeholder="工号" required />
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="邮箱（可选）" />
            <button type="submit" disabled={busy}>添加</button>
          </form>
        </section>
        {result ? <div className="admin-result">新增 {result.created}，更新 {result.updated}，跳过 {result.skipped}</div> : null}
        {error ? <div className="auth-error">{error}</div> : null}
        <table className="admin-table">
          <thead><tr><th>工号</th><th>邮箱</th><th>来源</th><th>更新时间</th><th>启用</th></tr></thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td>{e.employee_no}</td>
                <td>{e.email || "-"}</td>
                <td>{e.source}</td>
                <td>{e.updated_at}</td>
                <td>
                  <input
                    type="checkbox"
                    checked={e.enabled}
                    onChange={(ev) => void setWhitelistEnabled(e.id, ev.target.checked).then(refresh)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}

function formatError(err: unknown) {
  return err instanceof Error ? err.message : "请求失败";
}
