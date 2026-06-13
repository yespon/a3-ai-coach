# 登录页禁用账号密码登录开关 设计

> 日期：2026-06-13
> 范围：后端 1 个端点 + 前端登录页
> 目标：通过 `auth_mode` 控制登录页两个入口的可用性，被禁用的入口按钮置灰不可点

---

## 1. 背景

后端早已有 `settings.auth_mode`（`sso` / `local` / `both`）：
- `auth_mode=sso` → `/auth/login`、`/auth/register` 返回 403（账号密码登录被拒）
- `auth_mode=local` → `/cas/login`、`/cas/exchange` 返回 403（SSO 被拒）

**缺口**：登录页在登录前无途径知道 `auth_mode`，所以两个入口按钮（「企业 SSO 登录」「使用账号密码登录」）始终可点，点了被禁用的那个才会失败 —— 体验差。

**决策**：复用 `auth_mode`（不新增独立开关，避免语义重叠），新增一个公开 config 端点把 `auth_mode` 暴露给前端，前端据此对称置灰被禁用的入口。

## 2. 后端：公开 config 端点

`app/api/v1/routes/auth.py` 新增：

```python
@router.get("/config")
async def auth_config():
    """Public auth config for the login page (pre-auth). Non-sensitive."""
    return {"auth_mode": settings.auth_mode}
```

- 路径：`GET /api/v1/auth/config`
- 公开无鉴权（登录前调用）；GET 方法天然不受 CSRF 依赖影响
- 仅返回 `auth_mode`，不暴露任何敏感配置

## 3. 前端：据 auth_mode 对称置灰

### 3.1 `lib/auth.ts`

```ts
export async function getAuthConfig(): Promise<{ auth_mode: string }> {
  const resp = await fetch(`${API_BASE}/api/v1/auth/config`);
  if (!resp.ok) throw new Error("config unavailable");
  return resp.json();
}
```

### 3.2 `app/login/page.tsx`

- 挂载时（现有 `useEffect`）拉取 config → 新增 `authMode` state（默认 `"both"`）
- 派生两个布尔：
  - `localDisabled = authMode === "sso"`
  - `ssoDisabled = authMode === "local"`
- 「企业 SSO 登录」按钮：`disabled={ssoDisabled}`
- 「使用账号密码登录」按钮：`disabled={localDisabled}`
- 被禁用按钮下方显示对应提示：
  - `localDisabled` → 「管理员已禁用账号密码登录」
  - `ssoDisabled` → 「管理员已禁用 SSO 登录」
- **降级**：config 拉取失败 → `authMode` 保持 `"both"`，两按钮都可用（后端 403 兜底，不会误伤真实可用入口）

### 3.3 边界：直接进入 local 表单态

当前点「使用账号密码登录」会 `setMode("local")` 切到表单。`localDisabled` 时按钮不可点即可阻止。无需额外处理（按钮置灰是唯一入口）。

## 4. CSS（`globals.css`）

`.auth-local-toggle:disabled`、`.auth-sso-btn:disabled` 已有部分 disabled 样式；补充统一的灰色 + `cursor: not-allowed`（`.auth-sso-btn:disabled` 已存在，确认 `.auth-local-toggle:disabled` 也有）。提示文案用现有 `.auth-error` 或新增轻量 `.auth-disabled-hint`（灰色小字）。

## 5. 不做（YAGNI）

- 不新增独立 `local_login_enabled` 开关（复用 `auth_mode`）
- 不做运行时热切换（改 `auth_mode` 需重启 backend，与现状一致）

## 6. 验证

- `npx tsc --noEmit` + `npx next build` 通过
- 手动 E2E：
  1. `AUTH_MODE=both`（默认）→ 两按钮都可用
  2. `AUTH_MODE=sso` 重建 backend → 「使用账号密码登录」置灰 + 提示；SSO 可用
  3. `AUTH_MODE=local` 重建 backend → 「企业 SSO 登录」置灰 + 提示；账号密码可用
  4. 停掉 backend / config 404 → 前端降级两按钮都可用
