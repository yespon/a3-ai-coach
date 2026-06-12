# 多用户认证与会话持久化 - 实施计划

> 基于设计文档: `docs/plans/2026-06-12-multi-user-auth-design.md`
> 日期: 2026-06-12
> 预计任务数: 15 个 Task，分 5 个 Phase

---

## Phase 1: 基础设施与配置改造

### Task 1: 添加新依赖 + Pydantic Settings 改造

**目标:** 将配置从 `load_dotenv` + `os.getenv` 迁移到 Pydantic Settings，并安装所有新依赖。

**涉及文件:**
- `pyproject.toml` (编辑)
- `app/core/config.py` (重写)
- `.env.example` (编辑)
- `main.py` (调整 import)
- 所有使用 `os.getenv` 的文件 (迁移)

**步骤:**

1. 在 `pyproject.toml` 的 `dependencies` 中添加:
   ```
   "sqlalchemy[asyncio]>=2.0.30",
   "asyncpg>=0.29.0",
   "alembic>=1.13.0",
   "passlib[bcrypt]>=1.7.4",
   "pyjwt>=2.8.0",
   "pydantic-settings>=2.2.0",
   "email-validator>=2.1.0",
   ```

2. 重写 `app/core/config.py`:
   - 用 `pydantic_settings.BaseSettings` 替代 `load_dotenv` + `os.getenv`
   - 新增字段: `database_url`, `jwt_secret_key`, `jwt_algorithm`, `jwt_access_expire_minutes`, `jwt_refresh_expire_days`
   - 保留现有常量 `CONTEXT_FILE`, `STATIC_DIR`, `UPLOAD_ROOT`, `SUPPORTED_ATTACHMENT_EXTS`
   - 保留 `get_cors_allow_origins()` 和 `get_cors_allow_origin_regex()` 函数，改用 `settings` 属性
   - `model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")`

3. 更新 `.env.example`，添加:
   ```
   DATABASE_URL=postgresql+asyncpg://gangbiao:gangbiao@localhost:5432/gangbiao
   JWT_SECRET_KEY=CHANGE-ME-IN-PRODUCTION
   JWT_ALGORITHM=HS256
   JWT_ACCESS_EXPIRE_MINUTES=30
   JWT_REFRESH_EXPIRE_DAYS=7
   ```

4. 迁移所有 `os.getenv` 调用:
   - `app/services/llm_service.py`: `os.getenv("OPENAI_API_KEY")` -> `settings.openai_api_key`, `os.getenv("OPENAI_MODEL")` -> `settings.openai_model`, `os.getenv("OPENAI_BASE_URL")` -> `settings.openai_base_url`
   - `app/api/v1/routes/chat.py`: `_env_flag("LLM_PAYLOAD_DEBUG")` -> `settings.llm_payload_debug`, `os.getenv("LLM_PAYLOAD_PREVIEW_CHARS")` -> `settings.llm_payload_preview_chars`
   - `app/services/context_service.py`: `os.getenv("MATERIALS_AUTOLOAD")` -> `settings.materials_autoload`, `os.getenv("MATERIALS_DIR")` -> `settings.materials_dir`, etc.
   - `app/core/logger.py`: `os.getenv("LOG_LEVEL")` -> `settings.log_level`, etc.

5. 运行 `uv sync` 安装新依赖。

**测试:** 运行 `pytest` 确认现有测试全部通过。

**提交:** `feat(config): migrate to pydantic-settings, add auth/db dependencies`

---

### Task 2: PostgreSQL + SQLAlchemy 数据库层

**目标:** 建立 async SQLAlchemy engine/session 工厂 + Alembic 迁移基础。

**涉及文件:**
- `app/core/database.py` (新建)
- `alembic.ini` (新建)
- `alembic/env.py` (新建)
- `alembic/versions/` (目录)

**步骤:**

1. 新建 `app/core/database.py`:
   - `engine = create_async_engine(settings.database_url, echo=False)`
   - `async_session_factory = async_sessionmaker(engine, expire_on_commit=False)`
   - `async def get_db() -> AsyncSession`: FastAPI dependency, yields request-scoped session

2. 初始化 Alembic:
   ```
   cd /root/workspace/projects/chat_wwith_gb
   uv run alembic init alembic
   ```

3. 编辑 `alembic/env.py`:
   - 导入 `settings` 获取 `database_url`
   - 导入 ORM model 的 `Base.metadata` 作为 `target_metadata`
   - 配置 async migration runner

4. 编辑 `alembic.ini`: `sqlalchemy.url` 设为空（由 `env.py` 动态设置）

**测试:** `uv run alembic check` 确认配置无语法错误。

**提交:** `feat(db): add async sqlalchemy engine + alembic init`

---

### Task 3: ORM 模型 + 首次迁移

**目标:** 创建 users / chat_sessions / chat_messages 三张表的 ORM Model，生成迁移脚本。

**涉及文件:**
- `app/models/db_models.py` (新建)
- `alembic/versions/xxxx_initial_schema.py` (自动生成)

**步骤:**

1. 新建 `app/models/db_models.py`:
   - `class Base(DeclarativeBase)`: SQLAlchemy 基类
   - `class User(Base)`: `__tablename__ = "users"`，字段: `id` (UUID PK), `email` (VARCHAR 255 UNIQUE), `password_hash` (VARCHAR 255), `nickname` (VARCHAR 100 nullable), `is_active` (BOOLEAN default true), `is_admin` (BOOLEAN default false), `created_at` / `updated_at` (TIMESTAMPTZ)
   - `class ChatSessionDB(Base)`: `__tablename__ = "chat_sessions"`，字段: `id` (UUID PK), `user_id` (UUID FK -> users.id CASCADE, indexed), `show_context` (BOOLEAN default true), `context_file` (VARCHAR 500 nullable), `created_at` / `updated_at` (TIMESTAMPTZ)
   - `class ChatMessageDB(Base)`: `__tablename__ = "chat_messages"`，字段: `id` (UUID PK), `session_id` (UUID FK -> chat_sessions.id CASCADE, indexed), `seq` (int), `role` (VARCHAR 20), `content` (Text), `display_content` (Text nullable), `is_context` (BOOLEAN default false), `visible_in_history` (BOOLEAN default true), `attachments` (JSONB default '[]'), `created_at` (TIMESTAMPTZ)
   - 所有 `id` 列使用 `server_default=text("gen_random_uuid()")`
   - relationships: `User.sessions`, `ChatSessionDB.user` / `ChatSessionDB.messages`, `ChatMessageDB.session`

2. 确保 `alembic/env.py` import `app.models.db_models.Base` 作为 `target_metadata`

3. 生成迁移:
   ```
   uv run alembic revision --autogenerate -m "initial schema: users, chat_sessions, chat_messages"
   ```

4. 执行迁移（需要运行中的 PostgreSQL）:
   ```
   uv run alembic upgrade head
   ```

**测试:** 连接数据库确认三张表存在，索引正确。

**提交:** `feat(db): add user/session/message ORM models + initial migration`

---

## Phase 2: 认证模块

### Task 4: 密码工具 + JWT 工具

**目标:** 实现密码 hash/verify 和 JWT encode/decode 工具函数。

**涉及文件:**
- `app/core/security.py` (新建)
- `tests/unit/test_security.py` (新建)

**步骤:**

1. 新建 `app/core/security.py`:
   - `pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)`
   - `hash_password(plain) -> str`: hash 密码
   - `verify_password(plain, hashed) -> bool`: 验证密码
   - `create_access_token(user_id, expires_delta=None) -> str`: 生成 access JWT，payload 含 `sub`, `exp`, `type="access"`
   - `create_refresh_token(user_id) -> str`: 生成 refresh JWT，payload 含 `sub`, `exp`, `type="refresh"`
   - `decode_token(token) -> dict`: decode JWT，验证签名和过期

2. 新建 `tests/unit/test_security.py`:
   - `test_hash_and_verify_password`: hash 后 verify 成功
   - `test_verify_wrong_password`: 错误密码返回 False
   - `test_create_access_token_valid`: 生成 token 可 decode，sub 正确
   - `test_create_refresh_token_valid`: refresh token type 为 "refresh"
   - `test_expired_token_raises`: 过期 token decode 抛出 `ExpiredSignatureError`
   - `test_invalid_token_raises`: 无效 token decode 抛出 `InvalidTokenError`

**测试:** `uv run pytest tests/unit/test_security.py -v`

**提交:** `feat(auth): add password hashing + JWT utility functions`

---

### Task 5: Auth 路由 (注册 / 登录 / 刷新 / 获取当前用户)

**目标:** 实现 `/api/v1/auth/*` 端点。

**涉及文件:**
- `app/api/v1/routes/auth.py` (新建)
- `app/models/schema.py` (编辑，添加 auth schemas)
- `app/services/user_service.py` (新建)
- `app/api/v1/router.py` (编辑，注册 auth_router)

**步骤:**

1. 在 `app/models/schema.py` 添加 auth schemas:
   - `RegisterRequest(email: EmailStr, password: str min_length=6, nickname: str | None)`
   - `LoginRequest(email: EmailStr, password: str)`
   - `TokenResponse(access_token, refresh_token, token_type="bearer")`
   - `RefreshRequest(refresh_token: str)`
   - `UserResponse(id, email, nickname, is_active, created_at)`

2. 新建 `app/services/user_service.py`:
   - `create_user(db, email, password, nickname) -> User`: 检查邮箱唯一性，hash 密码，插入并返回。重复邮箱抛 `ValueError("email_already_exists")`
   - `authenticate_user(db, email, password) -> User | None`: 查询用户，verify 密码
   - `get_user_by_id(db, user_id) -> User | None`: 按 ID 查询

3. 新建 `app/api/v1/routes/auth.py`:
   - `POST /auth/register` -> 调用 `user_service.create_user`，返回 `TokenResponse`。重复邮箱返回 409
   - `POST /auth/login` -> 调用 `user_service.authenticate_user`，返回 `TokenResponse`。失败返回 401
   - `POST /auth/refresh` -> decode refresh_token，验证 `type="refresh"`，返回新 `TokenResponse`
   - `GET /auth/me` -> `Depends(get_current_user)`，返回 `UserResponse`
   - 所有端点注入 `db: AsyncSession = Depends(get_db)`

4. (本期不实现) `POST /api/v1/admin/users` -> 管理员创建用户端点，设计文档已列出但本期优先实现核心认证流程，admin 端点作为后续迭代。
5. 编辑 `app/api/v1/router.py`:
   ```
   from app.api.v1.routes.auth import router as auth_router
   api_v1_router.include_router(auth_router)
   ```

**测试:** 集成测试在 Task 7 统一编写。

**提交:** `feat(auth): add register/login/refresh/me endpoints`

---

### Task 6: 替换 get_current_user_id 依赖

**目标:** 将现有的 `X-User-ID` header 方式替换为 JWT Bearer token 认证。

**涉及文件:**
- `app/api/deps.py` (重写)

**步骤:**

1. 重写 `app/api/deps.py`:
   - `bearer_scheme = HTTPBearer(auto_error=False)`
   - `async def get_current_user(credentials, db) -> User`: 从 Bearer token decode JWT，验证 `type="access"`, 查询 DB 用户，返回 `User` 对象。无效/过期 token 返回 401
   - `def get_current_user_id(user: User = Depends(get_current_user)) -> str`: 返回 `str(user.id)`，保持与现有路由签名兼容
   - 保留 `LOGGER` 导出

2. 现有所有路由使用 `Depends(get_current_user_id)` 的地方无需改动签名。

**注意:** 此改动会立即让所有现有端点要求 JWT token。设计文档明确要求替换，所以直接切换。

**测试:** 在 Task 7 中覆盖。

**提交:** `feat(auth): replace header-based auth with JWT bearer token`

---

### Task 7: 认证集成测试

**目标:** 验证完整认证流程 + 确保现有 session/chat 端点在 JWT 保护下正常工作。

**涉及文件:**
- `tests/integration/test_auth.py` (新建)
- `tests/conftest.py` (编辑，添加 DB + auth fixture)

**步骤:**

1. 编辑 `tests/conftest.py` 添加:
   - `test_db` fixture: 创建测试数据库 session，每个测试使用事务回滚
   - `auth_client` fixture: 自动注册测试用户 + 登录 + 返回带 token 的 TestClient
   - `app.dependency_overrides[get_db]` 注入测试 session
   - 调整现有 `isolate_runtime_state` 和 `client` fixture 以适配新的 DB 依赖

2. 新建 `tests/integration/test_auth.py`:
   - `test_register_success`: 注册新用户，返回 token
   - `test_register_duplicate_email`: 重复邮箱返回 409
   - `test_login_success`: 正确凭证返回 token
   - `test_login_wrong_password`: 错误密码返回 401
   - `test_login_nonexistent_user`: 不存在用户返回 401
   - `test_refresh_token`: 用 refresh_token 获取新 access_token
   - `test_refresh_with_access_token_fails`: 用 access_token 刷新应失败
   - `test_me_endpoint`: 带有效 token 获取用户信息
   - `test_me_without_token`: 无 token 返回 401
   - `test_me_expired_token`: 过期 token 返回 401

3. 确保现有 `test_api_v1_parity.py` 和 `test_api_contract_sessions.py` 在新 fixture 下仍然通过。

**测试:** `uv run pytest tests/integration/ -v`

**提交:** `test(auth): add comprehensive auth integration tests`

---

## Phase 3: 会话与消息持久化

### Task 8: Session CRUD 持久化

**目标:** 将内存 `SESSIONS` dict 替换为 PostgreSQL 持久化。

**涉及文件:**
- `app/services/session_service.py` (重写)
- `app/api/v1/routes/sessions.py` (编辑，注入 db)
- `app/api/v1/routes/chat.py` (编辑，注入 db)

**步骤:**

1. 重写 `app/services/session_service.py`:
   - `create_session_in_db(db, user_id, show_context, context_file) -> ChatSessionDB`
   - `list_user_sessions(db, user_id) -> list[ChatSessionDB]`
   - `get_session_by_id(db, session_id, user_id) -> ChatSessionDB | None`
   - `update_session_settings(db, session, show_context) -> ChatSessionDB`
   - `db_session_history_for_client(session_db) -> list[dict]`: 转换 DB rows 为客户端格式
   - `db_session_summary_for_client(session_db) -> dict`: 转换 DB session 为摘要格式

2. 编辑 `app/api/v1/routes/sessions.py`:
   - 所有路由添加 `db: AsyncSession = Depends(get_db)` 参数
   - `create_session`: 先在 DB 创建 session，再加载 context messages，同时将 context messages 持久化到 chat_messages 表
   - `list_sessions` / `get_session` / `update_session_settings`: 从 DB 查询/更新
   - 保持返回格式不变

3. **关键设计决策:** 采用 "内存 session 作为 runtime cache + DB 作为持久层" 的双写模式:
   - 创建 session 时: DB 写入 + 内存缓存
   - 发送消息时: 内存 session 用于 LLM context + DB 持久化消息
   - 加载 session 时: 从 DB 加载 + 重建内存 session
   - 需要一个 `SessionCache` 类来管理内存中的 ChatSession 对象，key 为 session_id

**测试:** `uv run pytest tests/integration/ -v`

**提交:** `feat(session): persist sessions to PostgreSQL with hybrid runtime cache`

---

### Task 9: 聊天消息持久化

**目标:** 每条用户消息和 AI 回复写入 chat_messages 表。

**涉及文件:**
- `app/services/message_service.py` (新建)
- `app/services/chat_service.py` (编辑)
- `app/api/v1/routes/chat.py` (编辑)

**步骤:**

1. 新建 `app/services/message_service.py`:
   - `append_message(db, session_id, role, content, display_content, is_context, visible_in_history, attachments) -> ChatMessageDB`: 获取当前 max seq + 1，插入新消息
   - `get_session_messages(db, session_id) -> list[ChatMessageDB]`: 按 seq 排序查询
   - `append_context_messages(db, session_id, context_messages)`: 批量插入 context messages (is_context=True)

2. 编辑 `app/api/v1/routes/chat.py`:
   - 注入 `db: AsyncSession = Depends(get_db)` 和 `user: User = Depends(get_current_user)`
   - 在 `_append_user_message_with_attachments` 后，调用 `message_service.append_message` 持久化用户消息
   - 在 `_finalize_stream_reply` 后，调用 `message_service.append_message` 持久化 AI 回复
   - 创建 session 时，context messages 也持久化 (is_context=True)

3. 编辑 `app/services/chat_service.py`:
   - 传入 db session 参数
   - 保留内存 `session.messages` 用于 LLM context window 构建

**测试:** 手动验证 chat 流程后数据库有消息记录。单元测试在 Task 10。

**提交:** `feat(chat): persist chat messages to PostgreSQL`

---

### Task 10: 持久化集成测试

**目标:** 验证 session 和 message 的完整 CRUD 持久化。

**涉及文件:**
- `tests/integration/test_persistence.py` (新建)

**步骤:**

1. 新建 `tests/integration/test_persistence.py`:
   - `test_create_session_persists`: 创建 session 后，重新查询能找到
   - `test_list_sessions_filters_by_user`: 不同用户只能看到自己的 session
   - `test_chat_message_persisted`: 发送消息后，messages 表有对应记录
   - `test_session_history_from_db`: 从数据库加载历史，内容与发送时一致
   - `test_delete_user_cascades`: 删除用户后，关联 session 和 message 被级联删除
   - `test_context_messages_persisted`: context messages 以 is_context=True 存入 DB

**测试:** `uv run pytest tests/integration/test_persistence.py -v`

**提交:** `test(persistence): add session/message persistence tests`

---

## Phase 4: 前端认证集成

### Task 11: 前端登录/注册页面

**目标:** 新增登录、注册页面 UI。

**涉及文件:**
- `frontend/app/login/page.tsx` (新建)
- `frontend/app/register/page.tsx` (新建)
- `frontend/lib/auth.ts` (新建)
- `frontend/types/auth.ts` (新建)

**步骤:**

1. 新建 `frontend/types/auth.ts`:
   - `TokenResponse`: `{ access_token, refresh_token, token_type }`
   - `UserInfo`: `{ id, email, nickname, is_active, created_at }`

2. 新建 `frontend/lib/auth.ts`:
   - `login(email, password)`: POST `/api/v1/auth/login`，存储 tokens 到 localStorage key `gb_auth`
   - `register(email, password, nickname?)`: POST `/api/v1/auth/register`
   - `refreshToken()`: POST `/api/v1/auth/refresh`，更新 stored tokens
   - `logout()`: 清除 localStorage tokens，跳转 `/login`
   - `getAccessToken()`: 返回当前 access_token，过期时自动 refresh
   - `isAuthenticated()`: 检查是否有有效 token
   - Token 存储格式: `{ access_token, refresh_token, expires_at }`

3. 新建登录页面 `frontend/app/login/page.tsx`:
   - 邮箱 + 密码表单
   - 登录成功后跳转到主页面 `/`
   - "没有账号？去注册" 链接到 `/register`
   - 错误提示（邮箱格式、密码错误等）
   - 样式与现有页面风格一致

4. 新建注册页面 `frontend/app/register/page.tsx`:
   - 邮箱 + 密码 + 确认密码 + 昵称(可选) 表单
   - 注册成功后自动登录并跳转 `/`
   - "已有账号？去登录" 链接到 `/login`
   - 密码最少 6 字符提示

**测试:** 手动验证页面渲染和表单提交。

**提交:** `feat(frontend): add login/register pages + auth utility`

---

### Task 12: 前端 API 请求添加 JWT + 路由守卫

**目标:** 所有 API 请求附带 Authorization header；未登录时重定向到登录页。

**涉及文件:**
- `frontend/lib/api.ts` (编辑)
- `frontend/app/page.tsx` (编辑，添加 auth check)

**步骤:**

1. 编辑 `frontend/lib/api.ts`:
   - 移除 `getUserId()` 函数和 `X-User-ID` header 逻辑
   - 移除 localStorage `gb_user_id` 相关代码
   - 替换 `userHeaders()` 为 `authHeaders()`:
     ```
     import { getAccessToken } from "./auth";
     function authHeaders(): HeadersInit {
       const token = getAccessToken();
       return token ? { Authorization: `Bearer ` } : {};
     }
     ```
   - 所有 API 调用使用 `authHeaders()` 替代 `userHeaders()`
   - 添加 401 响应处理: 尝试 refresh token，refresh 失败则跳转 `/login`

2. 编辑 `frontend/app/page.tsx`:
   - 在 `bootstrapSession` 之前添加 auth check
   - 如果 `isAuthenticated()` 为 false，重定向到 `/login`
   - Sidebar 底部新增用户状态栏（设计文档 5.3 节）:
     - 圆形头像（邮箱首字母 + 色块）
     - 脱敏邮箱显示（如 ``u***@example.com``）
     - 点击弹出向上 popover 菜单: 退出登录
     - sidebar 收起时仅显示头像圆形

**测试:** 手动验证:
- 未登录访问主页 -> 跳转登录
- 登录后 API 请求带 Authorization header
- token 过期后自动 refresh
- 退出后清除 token 并跳转登录页

**提交:** `feat(frontend): add JWT auth to API requests + route guard`

---

## Phase 5: 部署与 CI

### Task 13: Docker Compose 添加 PostgreSQL

**目标:** 更新部署配置，添加 PostgreSQL 服务。

**涉及文件:**
- `docker-compose.yml` (编辑)
- `Dockerfile.backend` (可能编辑，添加 alembic 迁移步骤)
- `.env.example` (确认完整)

**步骤:**

1. 编辑 `docker-compose.yml`:
   - 新增 `postgres` service: `postgres:16-alpine`, env `POSTGRES_DB=gangbiao`, `POSTGRES_USER=gangbiao`, `POSTGRES_PASSWORD`, volume `pgdata`, healthcheck `pg_isready`
   - `backend` 新增 `depends_on: postgres (condition: service_healthy)` 和 `DATABASE_URL` 环境变量
   - 新增 `volumes: pgdata`

2. 编辑 `Dockerfile.backend` 或创建 entrypoint 脚本:
   - 在应用启动前执行 `alembic upgrade head`
   - 确保 PostgreSQL 已就绪后再执行迁移

**测试:** `docker compose up -d` -> 确认所有服务健康启动，数据库迁移成功。

**提交:** `feat(deploy): add PostgreSQL to docker-compose with healthcheck`

---

### Task 14: CI GitHub Actions 更新

**目标:** CI 中启动 PostgreSQL service container，运行完整测试。

**涉及文件:**
- `.github/workflows/ci.yml` (编辑)

**步骤:**

1. 编辑 `.github/workflows/ci.yml`:
   - 添加 PostgreSQL service container (`postgres:16-alpine`, env `POSTGRES_DB=gangbiao_test`, healthcheck)
   - 测试步骤设置环境变量: `DATABASE_URL`, `JWT_SECRET_KEY=ci-test-secret`, `OPENAI_API_KEY=""`, `MATERIALS_AUTOLOAD=false`
   - 添加迁移步骤: `alembic upgrade head`（在 run tests 之前）
   - 更新 pip install 步骤以包含新依赖

**测试:** Push 到分支，确认 CI 通过。

**提交:** `ci: add PostgreSQL service + auth env for test workflow`

---

### Task 15: 回归验证 + 清理

**目标:** 确保所有现有功能无回归，清理废弃代码。

**涉及文件:**
- `tests/` (运行全部)
- 各处废弃代码清理
- `README.md` (更新)

**步骤:**

1. 运行完整测试套件: `uv run pytest --cov -v`

2. 清理:
   - 移除 `app/services/session_service.py` 中的 `SESSIONS` 内存 dict
   - 移除 `main.py` 中对 `SESSIONS` 和 `MATERIALS_CONTEXT_CACHE` 的引用
   - 移除 `frontend/lib/api.ts` 中的 `getUserId()` 和 localStorage `gb_user_id`
   - 移除 `app/api/deps.py` 中旧的 `X-User-ID` header 逻辑
   - 移除 `app/core/config.py` 中旧的 `load_dotenv` 和 `_env_flag` 函数

3. 更新文档:
   - 更新 `README.md` 启动说明（需先启动 PostgreSQL 或使用 docker-compose）
   - 更新 `.env.example` 确认所有新变量都有说明
   - 添加认证相关的 API 文档说明

4. 端到端验证:
   - `docker compose up -d` 启动所有服务
   - 注册新用户 -> 登录 -> 创建会话 -> 发送消息 -> 重启服务 -> 消息仍在
   - 不同用户之间数据隔离
   - 前端登录/注册流程完整

**测试:** 全量 pytest + 手动 E2E 验证。

**提交:** `chore: cleanup deprecated code + update docs + final regression check`

---

## 依赖关系

```
Phase 1: Task 1 -> Task 2 -> Task 3
Phase 2: Task 4 -> Task 5 -> Task 6 -> Task 7
Phase 3: Task 8 -> Task 9 -> Task 10
Phase 4: Task 11 -> Task 12
Phase 5: Task 13 -> Task 14 -> Task 15
```

- Phase 1 完成后 Phase 2 和 Phase 3 可并行开始（Phase 3 依赖 Task 3 的 ORM 模型，Phase 2 依赖 Task 1 的依赖安装）
- Phase 4 依赖 Phase 2 完成（需要 auth endpoints 可用）
- Phase 5 可在 Phase 3 完成后开始

## 风险与注意事项

1. **现有测试兼容:** 所有现有测试依赖内存 session 和 `X-User-ID` header，迁移期间需维护 `app.dependency_overrides` 或条件分支确保测试不回归
2. **数据迁移:** 内存中的数据在切换后丢失，生产环境首次部署需告知用户历史会话不保留
3. **Token 安全:** `JWT_SECRET_KEY` 必须在生产环境中设置为强随机值，不能使用默认值
4. **密码策略:** 当前设计仅要求 6 字符最小长度，后续可加强（大小写+数字+特殊字符）
5. **并发:** asyncpg + SQLAlchemy async 天然支持并发，但需注意 session scope（request-scoped）
6. **Hybrid 模式:** 内存 session 作为 LLM runtime cache + DB 作为持久层的双写模式需要仔细处理一致性，特别是在 stream 回复中断时
7. **前端 localStorage:** 设计文档要求 refresh_token 存 httpOnly cookie，本期先用 localStorage 简化实现，后续迭代迁移到 cookie + httpOnly 以增强安全性（防 XSS）
