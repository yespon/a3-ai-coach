"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { checkAuth, logout } from "@/lib/auth";
import type { UserInfo } from "@/types/auth";

function buildNavItems(user: UserInfo | null) {
  if (!user) return [];
  if (user.is_admin) {
    return [
      { href: "/admin", label: "概览" },
      { href: "/admin/conversations", label: "对话历史" },
      { href: "/admin/users", label: "用户管理" },
      { href: "/admin/feedback", label: "意见反馈" },
    ];
  }
  if (user.is_coach) {
    return [{ href: "/admin/conversations", label: "对话历史" }];
  }
  return [];
}

function canAccessPath(pathname: string, user: UserInfo | null) {
  if (!user) return false;
  if (user.is_admin) return true;
  if (user.is_coach) return pathname.startsWith("/admin/conversations") || pathname === "/admin";
  return false;
}

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

  if (!(user?.is_admin || user?.is_coach)) {
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
  const navItems = buildNavItems(user);
  const canAccess = canAccessPath(activePath, user);
  const roleLabel = user.is_admin ? "管理员" : "教练";

  if (!canAccess) {
    return (
      <main className="admin-auth-state">
        <div className="admin-card admin-center-card">
          <p className="admin-kicker">Access Control</p>
          <h1>无权限访问</h1>
          <p>当前角色无法访问该页面，请进入你有权限的模块继续查看。</p>
          <div className="admin-actions-row">
            {user.is_coach ? (
              <Link className="admin-button admin-button-primary" href="/admin/conversations">
                进入对话历史
              </Link>
            ) : null}
            <Link className="admin-button admin-button-muted" href="/">
              返回聊天首页
            </Link>
          </div>
        </div>
      </main>
    );
  }

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
        <div className="admin-user-bar">
          <Link className="admin-user-bar-return" href="/">
            ← 返回聊天首页
          </Link>
          <div className="admin-user-bar-row">
            <span className="admin-user-avatar">{displayName.charAt(0)}</span>
            <div className="admin-user-info">
              <strong>{displayName}</strong>
              {user.email ? <span>{user.email}</span> : null}
              <span className="admin-user-role">{roleLabel}</span>
            </div>
            <button className="admin-user-bar-link admin-user-bar-link--danger" type="button" onClick={() => void logout()}>
              退出
            </button>
          </div>
        </div>
      </aside>

      <section className="admin-workspace">
        <main className="admin-main">{children}</main>
      </section>
    </div>
  );
}
