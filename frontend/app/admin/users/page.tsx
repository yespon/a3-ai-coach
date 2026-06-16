"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createManagedUser,
  importManagedUsers,
  listCoachOptions,
  listManagedUsers,
  managedUsersTemplateUrl,
  updateManagedUser,
} from "@/lib/admin";
import type { CoachOption, ImportResult, ManagedUser, ManagedUserPayload, ManagedUserRole } from "@/types/admin";

const roleLabels: Record<ManagedUserRole, string> = {
  admin: "管理员",
  coach: "教练",
  student: "学员",
};

const emptyForm: ManagedUserPayload = {
  employee_no: "",
  name: "",
  email: "",
  department_level1: "",
  primary_role: "student",
  is_coach: false,
  coach_id: null,
  enabled: true,
};

export default function AdminUsersPage() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [coaches, setCoaches] = useState<CoachOption[]>([]);
  const [form, setForm] = useState<ManagedUserPayload>(emptyForm);
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  useEffect(() => {
    void refresh();
  }, []);

  const coachChoices = useMemo(() => {
    if (!editingUser) return coaches;
    return coaches.filter((coach) => coach.id !== editingUser.id);
  }, [coaches, editingUser]);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [managedUsers, coachOptions] = await Promise.all([listManagedUsers(), listCoachOptions()]);
      setUsers(managedUsers);
      setCoaches(coachOptions);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  function updateForm<K extends keyof ManagedUserPayload>(key: K, value: ManagedUserPayload[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function startCreate() {
    setEditingUser(null);
    setForm(emptyForm);
    setImportResult(null);
    setNotice("");
    setError("");
  }

  function startEdit(user: ManagedUser) {
    setEditingUser(user);
    setForm({
      employee_no: user.employee_no,
      name: user.name || "",
      email: user.email || "",
      department_level1: user.department_level1 || "",
      primary_role: user.primary_role,
      is_coach: user.is_coach,
      coach_id: user.coach_id,
      enabled: user.enabled,
    });
    setImportResult(null);
    setNotice("");
    setError("");
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = normalizePayload(form);
      if (editingUser) {
        await updateManagedUser(editingUser.id, payload);
        setNotice("用户信息已更新");
      } else {
        await createManagedUser(payload);
        setNotice("用户已创建");
      }
      setEditingUser(null);
      setForm(emptyForm);
      await refresh();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  async function onImport(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError("");
    setNotice("");
    setImportResult(null);
    try {
      const result = await importManagedUsers(file);
      setImportResult(result);
      await refresh();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleEnabled(user: ManagedUser, enabled: boolean) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await updateManagedUser(user.id, normalizePayload({
        employee_no: user.employee_no,
        name: user.name,
        email: user.email,
        department_level1: user.department_level1,
        primary_role: user.primary_role,
        is_coach: user.is_coach,
        coach_id: user.coach_id,
        enabled,
      }));
      await refresh();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-page-stack">
      <section className="admin-page-header">
        <div>
          <p className="admin-kicker">Managed Users</p>
          <h2>用户管理</h2>
          <p>维护工号、角色、教练关系与启用状态。系统管理员账号会显示特殊标识。</p>
        </div>
        <div className="admin-actions-row">
          <a className="admin-button admin-button-muted" href={managedUsersTemplateUrl()}>
            下载模板
          </a>
          <label className={`admin-button admin-button-primary ${busy ? "disabled" : ""}`}>
            导入 Excel
            <input
              type="file"
              accept=".xlsx,.xls"
              hidden
              disabled={busy}
              onChange={(event) => void onImport(event.target.files?.[0] || null)}
            />
          </label>
        </div>
      </section>

      {importResult ? (
        <section className="admin-result-panel">
          <strong>导入完成</strong>
          <span>新增 {importResult.created}</span>
          <span>更新 {importResult.updated}</span>
          <span>跳过 {importResult.skipped}</span>
          {importResult.errors.length > 0 ? (
            <details>
              <summary>查看错误 {importResult.errors.length} 条</summary>
              <ul>
                {importResult.errors.map((item) => (
                  <li key={`${item.row}-${item.reason}`}>第 {item.row} 行：{item.reason}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>
      ) : null}

      {notice ? <div className="admin-notice">{notice}</div> : null}
      {error ? <div className="admin-error">{error}</div> : null}

      <section className="admin-content-grid">
        <article className="admin-card admin-form-card">
          <div className="admin-section-head">
            <div>
              <p className="admin-kicker">{editingUser ? "Edit" : "Create"}</p>
              <h3>{editingUser ? "编辑用户" : "新增用户"}</h3>
            </div>
            {editingUser ? (
              <button className="admin-link-button" type="button" onClick={startCreate}>
                取消编辑
              </button>
            ) : null}
          </div>

          <form className="admin-user-form" onSubmit={onSubmit}>
            <label>
              工号
              <input
                value={form.employee_no}
                onChange={(event) => updateForm("employee_no", event.target.value)}
                placeholder="请输入工号"
                required
                disabled={busy || Boolean(editingUser?.is_system_admin)}
              />
            </label>
            <label>
              姓名
              <input value={form.name || ""} onChange={(event) => updateForm("name", event.target.value)} placeholder="姓名" disabled={busy} />
            </label>
            <label>
              邮箱
              <input value={form.email || ""} onChange={(event) => updateForm("email", event.target.value)} placeholder="name@example.com" type="email" disabled={busy} />
            </label>
            <label>
              一级部门
              <input value={form.department_level1 || ""} onChange={(event) => updateForm("department_level1", event.target.value)} placeholder="部门" disabled={busy} />
            </label>
            <label>
              角色
              <select value={form.primary_role} onChange={(event) => updateForm("primary_role", event.target.value as ManagedUserRole)} disabled={busy}>
                {Object.entries(roleLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label>
              学员教练
              <select value={form.coach_id || ""} onChange={(event) => updateForm("coach_id", event.target.value || null)} disabled={busy}>
                <option value="">未指定</option>
                {coachChoices.map((coach) => (
                  <option key={coach.id} value={coach.id}>
                    {coach.name || coach.employee_no}{coach.department_level1 ? ` · ${coach.department_level1}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <div className="admin-switch-row">
              <label className="admin-switch">
                <input type="checkbox" checked={form.is_coach} onChange={(event) => updateForm("is_coach", event.target.checked)} disabled={busy} />
                <span>管理员教练身份</span>
              </label>
              <label className="admin-switch">
                <input type="checkbox" checked={form.enabled} onChange={(event) => updateForm("enabled", event.target.checked)} disabled={busy} />
                <span>启用账号</span>
              </label>
            </div>
            {editingUser?.is_system_admin ? <div className="admin-inline-warning">系统管理员的工号不可在此修改。</div> : null}
            <button className="admin-button admin-button-primary" type="submit" disabled={busy}>
              {editingUser ? "保存修改" : "创建用户"}
            </button>
          </form>
        </article>

        <article className="admin-card admin-table-card">
          <div className="admin-section-head">
            <div>
              <p className="admin-kicker">Directory</p>
              <h3>用户列表</h3>
            </div>
            <span className="admin-count">{users.length} 人</span>
          </div>

          {loading ? (
            <div className="admin-empty-state">正在加载用户数据...</div>
          ) : users.length === 0 ? (
            <div className="admin-empty-state">暂无用户，请创建或导入 Excel。</div>
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table managed-users-table">
                <thead>
                  <tr>
                    <th>用户</th>
                    <th>角色</th>
                    <th>教练关系</th>
                    <th>来源</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <div className="admin-user-cell">
                          <strong>{user.name || user.employee_no}</strong>
                          <span>{user.employee_no}{user.email ? ` · ${user.email}` : ""}</span>
                          {user.department_level1 ? <span>{user.department_level1}</span> : null}
                        </div>
                      </td>
                      <td>
                        <span className="admin-pill">{roleLabels[user.primary_role]}</span>
                        {user.is_coach ? <span className="admin-pill admin-pill-green">教练</span> : null}
                        {user.is_system_admin ? <span className="admin-pill admin-pill-gold">系统管理员</span> : null}
                      </td>
                      <td>{user.coach_name || "未指定"}</td>
                      <td>{user.source}</td>
                      <td>
                        <label className="admin-toggle">
                          <input type="checkbox" checked={user.enabled} disabled={busy} onChange={(event) => void toggleEnabled(user, event.target.checked)} />
                          <span>{user.enabled ? "启用" : "停用"}</span>
                        </label>
                      </td>
                      <td>
                        <button className="admin-link-button" type="button" onClick={() => startEdit(user)} disabled={busy}>
                          编辑
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      </section>
    </div>
  );
}

function normalizePayload(payload: ManagedUserPayload): ManagedUserPayload {
  return {
    employee_no: payload.employee_no.trim(),
    name: emptyToNull(payload.name),
    email: emptyToNull(payload.email),
    department_level1: emptyToNull(payload.department_level1),
    primary_role: payload.primary_role,
    is_coach: payload.is_coach,
    coach_id: payload.coach_id || null,
    enabled: payload.enabled,
  };
}

function emptyToNull(value: string | null | undefined): string | null {
  const trimmed = (value || "").trim();
  return trimmed ? trimmed : null;
}

function formatError(err: unknown) {
  return err instanceof Error ? err.message : "请求失败";
}
