# 管理后台用户管理与对话历史设计

> 日期：2026-06-16
> 范围：后端数据模型/迁移/管理 API/权限过滤 + 前端 `/admin` 管理后台
> 目标：将现有 SSO 白名单升级为系统级用户管理，并新增按角色授权的用户对话历史查看能力。

## 1. 背景

当前系统已有：

- CAS SSO 登录与 server-side session。
- `users` 登录账号表，包含 `is_admin`、`provider`、`provider_user_id` 等认证字段。
- `sso_user_whitelist` 白名单表，用于控制 SSO 工号是否可进入系统。
- `chat_sessions.user_id -> users.id` 与 `chat_messages.session_id -> chat_sessions.id` 的历史会话链路。
- `/admin/whitelist` 白名单管理页面与 `/api/v1/admin/whitelist*` 接口。

本次需求将白名单升级为独立 `/admin` 后台中的“用户管理”，同时新增对话历史查看。设计必须保留现有 `users` 数据和所有历史会话信息，不改写或删除 `chat_sessions.user_id` 这条历史链路。

## 2. 已确认需求

1. 新增独立 `/admin` 后台，包含用户管理和对话历史模块。
2. 现有白名单管理升级为“用户管理”，仅管理员可见。
3. 白名单/用户管理表仍然控制谁可使用系统。
4. `users` 表继续作为登录账号表，不承载主要业务组织关系。
5. `users` 可做轻量、可空关联改造，但不能丢失用户数据和历史会话。
6. 角色采用“主角色 + 附加能力”：主角色为管理员、教练、学员；管理员可兼任教练。
7. 管理员来源采用并行机制：`ADMIN_EMPLOYEE_NOS` 环境变量管理员 + 后台配置管理员都有效。
8. 环境变量管理员不可被后台降级或禁用到无法登录。
9. 教练归属规则：只有学员可配置所属教练；教练不配置教练归属。
10. 可选教练包含主角色为教练，以及主角色为管理员且兼任教练的人员。
11. 对话历史按“用户汇总 → 会话列表 → 会话详情”展示。
12. 教练只能查看自己负责的学员对话。
13. 管理员可查看全部；管理员兼任教练时默认查看“我的学员”，可切换“全部”。
14. 对话历史详情只读，不支持导出、删除、隐藏、备注。
15. 用户导入模板增加“一级部门”，位置在邮箱列后、主角色列前。

## 3. 数据模型

新增 `managed_users` 表，作为系统级用户管理档案和准入表。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `employee_no` | VARCHAR(100), unique, not null | 工号，SSO 准入匹配字段 |
| `name` | VARCHAR(100), nullable | 姓名 |
| `email` | VARCHAR(255), nullable | 邮箱，展示/辅助 |
| `department_level1` | VARCHAR(255), nullable | 一级部门 |
| `primary_role` | VARCHAR(20), not null | `admin` / `coach` / `student` |
| `is_coach` | BOOLEAN, default false | 是否具备教练能力 |
| `coach_id` | UUID nullable | 学员所属教练，引用 `managed_users.id` |
| `enabled` | BOOLEAN, default true | 是否允许使用系统 |
| `source` | VARCHAR(20) | `manual` / `excel` / `migrated` / `system` |
| `created_by` | UUID nullable | 创建或导入管理员 user id |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

约束和索引：

- `employee_no` 唯一。
- `enabled`、`primary_role` 建索引。
- `coach_id` 引用 `managed_users.id`。
- 应用层保证：
  - `primary_role='coach'` 时 `is_coach=true`。
  - `primary_role='student'` 时 `is_coach=false`。
  - `coach_id` 只对学员保存。
  - 学员的 `coach_id` 必须指向具备教练能力的档案。

`users` 表只新增可空字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `managed_user_id` | UUID nullable | 登录账号关联的 `managed_users.id` |

现有 `users.id`、`chat_sessions.user_id`、`chat_messages` 不变。

## 4. 迁移策略

迁移必须是增量、安全、可回退的：

1. 创建 `managed_users` 表。
2. 为 `users` 增加可空 `managed_user_id`。
3. 从旧 `sso_user_whitelist` 迁移到 `managed_users`：
   - `employee_no`、`email`、`enabled` 保留。
   - `name`、`department_level1`、`coach_id` 为空。
   - 默认 `primary_role='student'`。
   - `source='migrated'`。
4. 对 `ADMIN_EMPLOYEE_NOS` 中的工号：
   - 已迁移档案升级为 `primary_role='admin'`。
   - 若不存在档案，可创建 `source='system'` 的管理员档案。
5. 回填已有 CAS 用户关联：
   - `users.provider='cas'` 且 `users.provider_user_id = managed_users.employee_no` 时，写入 `users.managed_user_id`。
6. 不删除旧 `sso_user_whitelist` 表；实现切换后保留为兼容/备份数据。
7. 不改写 `chat_sessions.user_id`，历史会话继续通过原有 user id 访问。

## 5. 登录准入与角色判断

CAS 登录流程改为基于 `managed_users` 准入：

1. CAS ticket 校验后得到 `employee_no` 和用户属性。
2. 判断 `employee_no` 是否命中 `ADMIN_EMPLOYEE_NOS`。
3. 查询 `managed_users.employee_no = employee_no`。
4. 允许登录条件：
   - 命中环境变量管理员；或
   - 存在 `managed_users` 且 `enabled=true`。
5. 不允许登录条件：
   - 非环境变量管理员且无档案；或
   - 非环境变量管理员且档案禁用。
6. 创建或更新 `users` 登录账号，并设置 `users.managed_user_id`。
7. 环境变量管理员没有档案时自动补齐管理员档案。

有效管理员判断为任一条件成立：

- `users.is_admin=true`。
- 关联档案 `primary_role='admin'`。
- 工号命中 `ADMIN_EMPLOYEE_NOS`。

有效教练判断为任一条件成立：

- `primary_role='coach'`。
- `primary_role='admin'` 且 `is_coach=true`。

后台编辑或导入不得使环境变量管理员失去登录和后台访问能力。

## 6. 管理后台前端

新增独立 `/admin` 后台布局。

导航：

- 概览：可先展示欢迎信息和基础统计。
- 用户管理。
- 对话历史。

顶部区域：

- 当前管理员信息。
- 返回聊天首页。
- 退出登录。

访问控制：

- 非管理员不显示后台入口。
- 非管理员且非教练手动访问 `/admin/*` 时显示无权限页。
- 教练允许访问 `/admin/conversations`（及默认 `/admin` 概览），但不可访问用户管理等管理员模块。
- 后端所有 `/api/v1/admin/*` 接口继续强制权限校验，前端隐藏入口不作为安全边界。

## 7. 用户管理页面

用户管理替代原白名单管理。

列表字段：

- 工号。
- 姓名。
- 邮箱。
- 一级部门。
- 主角色。
- 兼任教练。
- 所属教练。
- 启用状态。
- 更新时间。
- 操作。

操作：

- 下载新版 Excel 模板。
- Excel 增量导入/更新。
- 手工新增用户。
- 编辑用户。
- 启用/禁用。

不提供物理删除。环境变量管理员行显示“系统管理员”标识，并禁用会导致其降级或无法登录的操作。

新增/编辑弹窗字段：

- 工号：必填。
- 姓名。
- 邮箱。
- 一级部门。
- 主角色：管理员 / 教练 / 学员。
- 兼任教练：仅管理员可选。
- 所属教练：仅学员可选。
- 启用状态：系统管理员不可禁用。

## 8. Excel 模板与导入规则

新版模板列顺序：

1. 工号
2. 姓名
3. 邮箱
4. 一级部门
5. 主角色
6. 兼任教练
7. 所属教练工号
8. 启用状态

导入规则：

- 仅接受 `.xlsx`。
- 按工号增量新增/更新。
- 工号必填。
- 主角色允许值：管理员、教练、学员；缺省为学员。
- 兼任教练允许值：是、否；仅管理员可为是。
- 启用状态允许值：启用、禁用；缺省为启用。
- 所属教练工号仅学员有效。
- 所属教练工号必须指向数据库已有或本批导入中的有效教练。
- 主角色为教练时视为具备教练能力。
- 主角色为管理员时可通过兼任教练字段获得教练能力。
- 主角色为学员时不能具备教练能力。
- 教练和管理员不保存所属教练。
- 环境变量管理员不可被导入降级或禁用。
- 返回 created、updated、skipped、errors 统计。

## 9. 管理 API

现有 `/api/v1/admin/whitelist*` 逐步由用户管理接口替代。

用户管理接口：

### `GET /api/v1/admin/users`

返回用户档案列表，支持查询参数：

- `q`：工号、姓名、邮箱关键词。
- `role`：`admin | coach | student`。
- `enabled`：`true | false`。

### `POST /api/v1/admin/users`

手工新增用户档案。

### `PATCH /api/v1/admin/users/{id}`

编辑档案、角色、教练归属、启用状态。

### `GET /api/v1/admin/users/template`

下载新版用户管理 Excel 模板。

### `POST /api/v1/admin/users/import`

导入新版用户管理 Excel。

### `GET /api/v1/admin/users/coaches`

返回可选教练列表：主角色为教练，或主角色为管理员且兼任教练。

对话历史接口：

### `GET /api/v1/admin/conversations/users?scope=mine|all`

返回按学员聚合的对话历史用户列表。

权限：

- 教练只允许 `scope=mine`。
- 管理员允许 `mine` 和 `all`。
- 管理员兼任教练前端默认请求 `mine`，可切换 `all`。

### `GET /api/v1/admin/conversations/users/{managed_user_id}/sessions`

返回某个学员的会话列表。后端再次校验当前管理员/教练是否有权查看该学员。

### `GET /api/v1/admin/conversations/sessions/{session_id}`

返回只读会话详情。后端通过 `chat_sessions.user_id -> users.managed_user_id` 校验可见性。

## 10. 对话历史页面

对话历史主页面按学员汇总展示：

- 学员姓名。
- 工号。
- 一级部门。
- 所属教练。
- 会话数。
- 最近会话时间。
- 操作：查看。

进入某个学员后展示会话列表：

- 会话创建时间。
- 会话更新时间。
- 最近消息摘要。
- 消息数。
- 操作：查看详情。

会话详情只读展示：

- 用户消息。
- AI 回复。
- 附件名称、大小等附件卡片信息。
- 消息时间顺序。

本次不做导出、删除、隐藏、备注。

## 11. 权限与安全

- 所有 `/api/v1/admin/*` 接口必须依赖管理员/教练权限校验。
- 用户管理接口只允许管理员访问。
- 对话历史接口允许管理员和教练访问，但必须按角色过滤数据。
- 教练查询时必须限制为 `managed_users.coach_id = 当前教练 managed_user_id` 的学员。
- 管理员 `scope=all` 可查看全部学员。
- 会话详情接口不能只按 session id 返回，必须反查所属学员并校验当前用户可见性。
- Excel 上传限制 `.xlsx`、文件大小和最大行数。
- 导入时不落盘，内存解析。
- 前端权限显示只作为体验优化，安全边界在后端。

## 12. 测试与验证

后端测试：

- Alembic migration 创建 `managed_users` 并给 `users` 增加可空关联。
- 旧 `sso_user_whitelist` 数据迁移为 `managed_users`。
- `ADMIN_EMPLOYEE_NOS` 命中档案迁移为管理员；缺失时自动补齐。
- 现有 CAS 用户回填 `users.managed_user_id`。
- 迁移后 `chat_sessions.user_id` 与 `chat_messages` 不丢失、不改写。
- 非环境变量管理员无档案时 SSO 登录被拒绝。
- 禁用档案的非环境变量管理员登录被拒绝。
- 环境变量管理员不受禁用/降级影响。
- 后台管理员可新增、编辑、导入用户。
- 学员只能配置有效教练归属。
- 导入模板字段、默认值、错误行统计正确。
- 教练只能查看自己学员的对话历史。
- 管理员可查看全部。
- 管理员兼任教练支持 `mine` 和 `all`。
- 会话详情接口对无权限 session 返回 403 或 404。

前端验证：

- 非管理员不显示后台入口，手动访问后台显示无权限。
- 管理员可进入 `/admin`，看到左侧导航和用户管理。
- 用户管理列表、新增、编辑、启用/禁用、模板下载、导入可用。
- 系统管理员标识和禁用降级控件生效。
- 对话历史默认范围符合角色：教练为我的学员；兼任教练管理员默认我的学员并可切换全部；普通管理员可看全部。
- 用户汇总、会话列表、会话详情三级浏览可用。
- 会话详情只读，无导出、删除、隐藏、备注入口。

## 13. 不在本次范围

- 物理删除用户档案。
- 对话导出。
- 会话删除、隐藏、备注、审计批注。
- 教练再分配的历史审计记录。
- 多级部门结构；本次只支持一级部门。
