"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { checkAuth, logout } from "@/lib/auth";
import type { UserInfo } from "@/types/auth";

const navItems = [
  { href: "/admin", label: "概览" },
  { href: "/admin/users", label: "用户管理" },
  { href: "/admin/conversations", label: "对话历史" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    checkAuth()
      .then((currentUser) => {
        if (active) setUser(currentUser);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <main className="admin-auth-state">
        <div className="admin-card admin-center-card">
          <p className="admin-kicker">Admin Console</p>
          <h1>正在验证权限</h1>
          <p>请稍候，正在检查当前登录状态。</p>
        </div>
      </main>
    );
  }

  if (!user?.is_admin) {
    return (
      <main className="admin-auth-state">
        <div className="admin-card admin-center-card">
          <p className="admin-kicker">Access Control</p>
          <h1>无权限访问</h1>
          <p>当前账号没有管理后台权限，请返回聊天首页继续使用岗标 AI 教练。</p>
          <Link className="admin-button admin-button-primary" href="/">
            返回聊天首页
          </Link>
        </div>
      </main>
    );
  }

  const displayName = user.nickname || user.employee_no || user.email || "管理员";
  const activePath = pathname || "/admin";

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar" aria-label="管理后台导航">
        <div className="admin-brand-block">
          <span className="admin-brand-mark">GB</span>
          <div>
            <p className="admin-kicker">Gangbiao</p>
            <h1>管理后台</h1>
          </div>
        </div>
        <nav className="admin-nav">
          {navItems.map((item) => {
            const isActive = item.href === "/admin" ? activePath === "/admin" : activePath.startsWith(item.href);
            return (
              <Link key={item.href} className={`admin-nav-link ${isActive ? "active" : ""}`} href={item.href}>
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <section className="admin-workspace">
        <header className="admin-topbar">
          <div>
            <p className="admin-kicker">当前管理员</p>
            <div className="admin-user-line">
              <strong>{displayName}</strong>
              {user.email ? <span>{user.email}</span> : null}
            </div>
          </div>
          <div className="admin-topbar-actions">
            <Link className="admin-button admin-button-muted" href="/">
              返回聊天首页
            </Link>
            <button className="admin-button admin-button-danger" type="button" onClick={() => void logout()}>
              退出登录
            </button>
          </div>
        </header>
        <main className="admin-main">{children}</main>
      </section>
    </div>
  );
}
