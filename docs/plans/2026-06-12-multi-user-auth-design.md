# 多用户认证与会话持久化设计

> 日期: 2026-06-12
> 状态: 已确认

## 1. 目标

为岗标AI教练 Chatbot 构建多用户体系：

- 用户通过邮箱 + 密码注册/登录
- JWT 无状态认证（access_token + refresh_token）
- 聊天会话与消息持久化到 PostgreSQL
- 用户级数据隔离
- 为后续 SSO 接入预留扩展点

## 2. 技术选型

| 层 | 选型 |
|---|------|
| ORM | SQLAlchemy 2.0 async + Alembic |
| 密码 | passlib\[bcrypt\]，12 rounds |
| JWT | PyJWT |
| 配置 | Pydantic Settings（替代 load\_dotenv） |
| 数据库 | PostgreSQL 16 |
| 驱动 | asyncpg |

## 3. 数据模型

### 3.1 users

| 列 | 类型 | 约束 |
|----|------|------|
| id | UUID | PK, DEFAULT gen\_random\_uuid() |
| email | VARCHAR(255) | UNIQUE NOT NULL |
| password\_hash | VARCHAR(255) | NOT NULL |
| nickname | VARCHAR(100) | |
| is\_active | BOOLEAN | DEFAULT TRUE |
| is\_admin | BOOLEAN | DEFAULT FALSE |
| created\_at | TIMESTAMPTZ | DEFAULT now() |
| updated\_at | TIMESTAMPTZ | DEFAULT now() |

### 3.2 chat\_sessions

| 列 | 类型 | 约束 |
|----|------|------|
| id | UUID | PK, DEFAULT gen\_random\_uuid() |
| user\_id | UUID | FK → users(id) ON DELETE CASCADE |
| show\_context | BOOLEAN | DEFAULT TRUE |
| context\_file | VARCHAR(500) | |
| created\_at | TIMESTAMPTZ | DEFAULT now() |
| updated\_at | TIMESTAMPTZ | DEFAULT now() |

索引: `idx_sessions_user(user_id)`

### 3.3 chat\_messages

| 列 | 类型 | 约束 |
|----|------|------|
| id | UUID | PK, DEFAULT gen\_random\_uuid() |
| session\_id | UUID | FK → chat\_sessions(id) ON DELETE CASCADE |
| role | VARCHAR(20) | NOT NULL |
| content | TEXT | NOT NULL |
| display\_content | TEXT | |
| is\_context | BOOLEAN | DEFAULT FALSE |
| visible\_in\_history | BOOLEAN | DEFAULT TRUE |
| attachments | JSONB | DEFAULT '[]' |
| created\_at | TIMESTAMPTZ | DEFAULT now() |

索引: `idx_messages_session(session_id, created_at)`

## 4. 认证流程

### 4.1 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/register | 开放注册 |
| POST | /api/v1/auth/login | 登录 |
| POST | /api/v1/auth/refresh | 刷新 token |
| POST | /api/v1/auth/logout | 登出 |
| GET | /api/v1/auth/me | 当前用户信息 |
| POST | /api/v1/admin/users | 管理员创建用户 |

### 4.2 JWT 策略

- **access\_token**: 载荷 `{sub, email, is_admin, exp}`，有效期 30 分钟，前端存 localStorage，通过 `Authorization: Bearer` 传递。
- **refresh\_token**: 载荷 `{sub, type: "refresh", exp}`，有效期 7 天，存 httpOnly + Secure + SameSite=Lax cookie。

### 4.3 密码策略

- bcrypt hash，12 rounds
- 注册/登录时 email 转小写 + strip
- 密码最少 6 位

### 4.4 认证依赖改造

`get_current_user_id()` 废弃，替换为：

```python
async def get_current_user(token = Depends(oauth2_scheme)) -> User:
    payload = decode_access_token(token)
    user = await user_repo.get_by_id(payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(401)
    return user
```

所有路由签名的 `user_id: str` 参数改为 `user: User`，用 `user.id` 替代。

## 5. 前端设计

### 5.1 路由

| 路径 | 页面 | 认证 |
|------|------|------|
| /login | 登录页 | 无需 |
| /register | 注册页 | 无需 |
| / | 聊天主页 | 需要 |

### 5.2 登录页

居中卡片布局：邮箱输入框 + 密码输入框（带可见性切换）+ 登录按钮 + "还没有账号？立即注册"链接。

### 5.3 Sidebar 改造

整体结构不变，底部固定新增用户状态栏：

- 圆形头像（邮箱首字母 + 色块）
- 脱敏邮箱显示
- 点击弹出向上 popover 菜单：个人资料（预留）、设置（预留）、退出登录（本期实现）
- sidebar 收起时仅显示头像圆形

### 5.4 前端认证管理

```
lib/auth.ts:
  login / refresh / logout / getToken / isLoggedIn

请求层:
  X-User-ID header → Authorization: Bearer header
  401 响应 → 自动尝试 refresh → 失败跳 /login
```

## 6. 后端代码结构

### 6.1 新增

```
app/auth/           jwt.py, password.py, deps.py
app/db/             engine.py, models.py, repositories/
app/api/v1/routes/  auth.py, admin.py
alembic/            env.py, versions/001_initial_schema.py
alembic.ini
```

### 6.2 改造

| 文件 | 改动 |
|------|------|
| app/api/deps.py | 废弃 get\_current\_user\_id |
| app/models/chat.py | 保留为内部 DTO |
| app/services/session\_service.py | 删除 SESSIONS 字典，改为 async DB |
| app/api/v1/routes/sessions.py | 内部调 repository |
| app/api/v1/routes/chat.py | 同上 |
| main.py | 初始化 DB engine，注册 auth 路由 |
| app/core/config.py | 替换为 Pydantic Settings |
| pyproject.toml | 新增依赖 |
| .env.example | 新增 DATABASE\_URL, JWT\_SECRET\_KEY 等 |
| docker-compose.yml | 新增 postgres 服务 |

## 7. 配置管理

替换 `load_dotenv` 为 Pydantic Settings：

```python
class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7
    openai_api_key: str = ""
    # ...

    model_config = ConfigDict(env_file=".env")

settings = Settings()
```

开发时读 `.env`；生产时容器环境变量自动优先。类型校验 + 缺失立即报错。

## 8. 测试策略

### 8.1 分层

| 层 | 覆盖 | 方式 |
|----|------|------|
| 单元 | password hash/verify, JWT encode/decode, 邮箱脱敏 | 纯函数测试 |
| 集成 | auth 端点, session CRUD, chat 端点 | 测试 PG + 事务回滚 |
| 现有 | 全部保留并改造 | 确保无回归 |

### 8.2 测试隔离

- 每个测试一个事务，结束后回滚
- `app.dependency_overrides` 注入测试 DB session
- 提供 `auth_client` fixture（自动注册 + 登录 + 带 token）

### 8.3 CI

GitHub Actions service container 启动 PostgreSQL 16。`TEST_DATABASE_URL` 环境变量指向测试库。

## 9. Docker Compose

新增 postgres 服务：

```yaml
postgres:
  image: postgres:16-alpine
  environment:
    POSTGRES_DB: gangbiao
    POSTGRES_USER: gangbiao
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  volumes:
    - pgdata:/var/lib/postgresql/data
  ports: ["5432:5432"]
```

backend 服务新增 `depends_on: postgres`。

## 10. SSO 扩展路径

当前设计为 SSO 预留的扩展点：

1. `users` 表后续可加 `provider`, `provider_user_id` 字段（Alembic migration）
2. 新增 `/api/v1/auth/sso/callback` 端点：用 IdP 返回的 code 换本系统 JWT
3. 前端登录页可加 "SSO 登录" 按钮，跳转 IdP 授权页
4. `get_current_user()` 依赖不变，所有业务路由零改动
