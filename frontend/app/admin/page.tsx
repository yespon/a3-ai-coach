const modules = [
  {
    title: "用户管理",
    description: "维护可登录用户、岗位角色、教练关系与启用状态，支持 Excel 批量导入。",
    href: "/admin/users",
  },
  {
    title: "对话历史",
    description: "查看学员会话记录与教练辅导过程，支持后续按权限筛选。",
    href: "/admin/conversations",
  },
  {
    title: "系统治理",
    description: "统一管理后台权限、人员数据来源与运营状态，保持岗标辅导链路稳定。",
    href: "/admin/users",
  },
];

export default function AdminOverviewPage() {
  return (
    <div className="admin-page-stack">
      <section className="admin-hero-card">
        <p className="admin-kicker">Overview</p>
        <h2>后台概览</h2>
        <p>这里汇总岗标 AI 教练的管理模块。请从左侧导航进入具体功能。</p>
      </section>

      <section className="admin-overview-grid" aria-label="后台模块">
        {modules.map((module) => (
          <article className="admin-card admin-module-card" key={module.title}>
            <p className="admin-kicker">Module</p>
            <h3>{module.title}</h3>
            <p>{module.description}</p>
            <a href={module.href}>进入模块</a>
          </article>
        ))}
      </section>
    </div>
  );
}
