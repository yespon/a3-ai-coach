"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { checkAuth } from "@/lib/auth";
import type { UserInfo } from "@/types/auth";

type OverviewModule = {
  title: string;
  description: string;
  href: string;
};

export default function AdminOverviewPage() {
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

  const modules = useMemo<OverviewModule[]>(() => {
    if (user?.is_admin) {
      return [
        {
          title: "对话历史",
          description: "查看你负责学员的历史会话与辅导轨迹。",
          href: "/admin/conversations",
        },
        {
          title: "用户管理",
          description: "维护人员身份、角色与负责人归属，支持单个创建和批量导入。",
          href: "/admin/users",
        },
        {
          title: "意见反馈",
          description: "查看用户提交的意见与建议,支持状态流转与附件预览。",
          href: "/admin/feedback",
        },
      ];
    }
    if (user?.is_coach) {
      return [
        {
          title: "对话历史",
          description: "查看你负责学员的历史会话与辅导轨迹。",
          href: "/admin/conversations",
        },
      ];
    }
    return [];
  }, [user]);

  return (
    <div className="admin-page-stack">
      <section className="admin-hero-card">
        <p className="admin-kicker">Overview</p>
        <h2>后台概览</h2>
        <p>查看你负责学员的历史会话与辅导轨迹。</p>
      </section>

      {loading ? (
        <section className="admin-card admin-empty-state">正在加载可用模块...</section>
      ) : modules.length === 0 ? (
        <section className="admin-card admin-empty-state">当前账号暂无可访问的管理模块。</section>
      ) : (
        <section className="admin-overview-grid" aria-label="后台模块">
          {modules.map((module) => (
            <article className="admin-card admin-module-card" key={module.title}>
              <p className="admin-kicker">Module</p>
              <h3>{module.title}</h3>
              <p>{module.description}</p>
              <Link href={module.href}>进入模块</Link>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
