# 管理员 SSO 白名单设计

> 日期：2026-06-14
> 范围：后端认证/管理 API/数据库迁移 + 前端管理页
> 目标：管理员维护 SSO 用户白名单；SSO 登录时仅允许启用中的白名单用户（或管理员）进入系统。

---

## 1. 背景

当前系统已支持：
- SSO 登录：`/api/v1/cas/exchange` 校验 CAS ticket 后创建用户与 session
- 用户模型：`users.is_admin` 已存在
- session cookie 鉴权：`get_current_user`
- 文件解析依赖：`openpyxl` 已在 `pyproject.toml`

缺口：没有管理员初始化机制、无白名单表、无管理页面、SSO 登录不做准入控制。

## 2. 已确认需求

1. 管理员角色：管理员可进入白名单管理页。
2. 管理员初始化：通过环境变量 `ADMIN_EMPLOYEE_NOS=工号1,工号2`。
3. 白名单匹配：SSO 登录时**只按工号**匹配（CAS `employee_no` / `provider_user_id`）。邮箱仅展示/辅助。
4. Excel 导入：预制模板列为「工号、邮箱」；导入是**增量追加/更新**，不是覆盖。
5. 白名单记录默认启用；启用时允许登录，禁用时阻断登录。
6. 管理页面支持：下载模板、Excel 导入、手工新增、列表、启用/禁用开关。
7. 不做删除；“删除”需求等价为禁用，所以页面不提供删除按钮。
8. 空白名单时：非管理员 SSO 用户全部阻断。
9. 管理员不受白名单限制，否则空白名单时管理员无法进入系统。
10. 非管理员：隐藏「白名单管理」入口；手动访问管理页显示「无权限访问」页面。

## 3. 数据模型

新增表 `sso_user_whitelist`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `employee_no` | VARCHAR(100), unique, not null | 工号，SSO 准入匹配字段 |
| `email` | VARCHAR(255), nullable | 邮箱，展示/辅助 |
| `enabled` | BOOLEAN default true | true 才允许登录 |
| `source` | VARCHAR(20) | `manual` / `excel` |
| `created_by` | UUID nullable | 创建/导入管理员 user_id |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

索引：
- unique index: `employee_no`
- index: `enabled`

## 4. 配置

新增：

```python
admin_employee_nos: str = ""
```

辅助函数：

```python
def get_admin_employee_no_set() -> set[str]:
    return {part.strip() for part in settings.admin_employee_nos.split(",") if part.strip()}
```

`.env.example` 增加：

```bash
# Comma-separated SSO employee numbers that should become administrators.
ADMIN_EMPLOYEE_NOS=
```

## 5. 管理员赋权

在 SSO 登录流程中，`validate_ticket` 得到 `employee_no` 后：
- 如果 `employee_no in ADMIN_EMPLOYEE_NOS`，则该用户应为管理员。
- `upsert_sso_user` 增加参数 `is_admin: bool = False`，创建或更新用户时同步 `user.is_admin = True`（只升不降，避免临时配置错误导致管理员被降级）。

本地账号管理员（若 DB 手工设 `is_admin=true`）仍可访问管理 API。

## 6. SSO 白名单校验

在 `/api/v1/cas/exchange` 中：

1. 校验 CAS ticket，得到 `employee_no` 和 attrs。
2. 计算 `is_admin_employee_no`。
3. 如果是管理员工号：跳过白名单校验。
4. 否则查询 `sso_user_whitelist`：`employee_no == employee_no AND enabled == true`。
5. 不命中：返回 403。

错误文案：

```json
{"detail":"当前账号未开通岗标 AI 教练访问权限，请联系管理员开通。"}
```

前端 `casExchange()` 会展示后端 `detail`，无需额外接口。

## 7. 管理 API

新增 `app/api/v1/routes/admin.py`，路由前缀 `/admin`。

管理员依赖：

```python
async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin_required")
    return user
```

接口：

### `GET /api/v1/admin/whitelist`
返回列表（按 `updated_at desc`）：

```json
[
  {"id":"...","employee_no":"10001","email":"a@x.com","enabled":true,"source":"excel","created_at":"...","updated_at":"..."}
]
```

### `POST /api/v1/admin/whitelist`
手工新增/更新：

```json
{"employee_no":"10001","email":"a@x.com"}
```

行为：
- 工号必填，去首尾空格。
- 邮箱可空。
- 已存在：更新 email，`enabled=true`，`source="manual"`。
- 不存在：创建，`enabled=true`。

### `PATCH /api/v1/admin/whitelist/{id}`
更新启用状态和邮箱：

```json
{"enabled": false, "email": "a@x.com"}
```

### `GET /api/v1/admin/whitelist/template`
返回 xlsx 模板，两列表头：
- 工号
- 邮箱

### `POST /api/v1/admin/whitelist/import`
上传 xlsx，增量导入/更新，默认启用。

导入规则：
- 仅接受 `.xlsx`。
- 第一行必须包含「工号」「邮箱」。
- 工号必填；邮箱可空。
- 同一文件内重复工号：后出现的行覆盖前行。
- 数据库内已有工号：更新 email，设置 `enabled=true`，`source="excel"`。
- 新工号：创建 `enabled=true`。
- 返回统计与错误行。

返回示例：

```json
{
  "created": 10,
  "updated": 3,
  "skipped": 2,
  "errors": [{"row": 5, "reason": "工号为空"}]
}
```

## 8. 前端管理页

新增 `/admin/whitelist`。

入口：
- `HomePage` 当前已有用户菜单（退出登录）。
- 当 `userInfo.is_admin === true` 时，在菜单里显示「白名单管理」。
- 非管理员不显示入口。

类型：
- `frontend/types/auth.ts` 的 `UserInfo` 增加 `is_admin: boolean`。
- 后端 `UserResponse` 增加 `is_admin`，`/auth/me` 返回它。

页面功能：
1. 顶部：标题「白名单管理」、返回首页。
2. 操作区：
   - 下载模板按钮。
   - 上传 Excel 导入。
   - 手工新增表单：工号、邮箱、添加按钮。
3. 列表区：
   - 工号、邮箱、来源、更新时间、启用开关。
   - 开关调用 PATCH 更新 enabled。
4. 非管理员手动访问：显示「无权限访问」并提供返回首页按钮。

## 9. 安全与权限

- 所有 `/admin/*` 接口必须依赖 `require_admin`。
- 导入接口接受文件上传，应限制 `.xlsx`，不接受其它类型。
- 白名单导入只读取第一张 sheet。
- 不把上传文件落盘；直接内存解析。
- 不提供删除，避免误删；禁用即可阻断登录。
- 管理员工号不受白名单限制。
- Excel 中的邮箱只用于展示/辅助，不作为登录匹配条件。

## 10. 验证

后端：
- Alembic migration 创建 `sso_user_whitelist`。
- `ADMIN_EMPLOYEE_NOS` 命中时 SSO 用户 `is_admin=true`。
- 非管理员未在白名单：`/cas/exchange` 返回 403 + 指定文案。
- 非管理员在 enabled 白名单：放行。
- 白名单 disabled：阻断。
- 管理员访问 `/admin/whitelist` 成功；普通用户 403。
- Excel 导入 created/updated/errors 统计正确。

前端：
- admin 用户菜单显示「白名单管理」，普通用户不显示。
- 管理页可下载模板、上传 Excel、手工新增、开关启禁用。
- 普通用户手动访问 `/admin/whitelist` 显示无权限或返回首页。
- SSO 被白名单阻断时登录页显示后端文案。
