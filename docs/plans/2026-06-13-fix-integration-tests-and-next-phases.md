# 集成测试修复 + E2E 验证 + CAS SSO 准备 — 实施计划

> 基于已完成的前 5 Phase（15 个 Task，全部已提交到 feature/multi-user-auth）
> 日期: 2026-06-13
> 预计任务数: 9 个 Task，分 3 个 Phase

---

## 现状总结

**已完成:** Phase 1-5 的 15 个 Task 全部提交，包括 pydantic-settings 改造、ORM 模型、auth 端点、JWT 认证、会话/消息持久化、前端登录页、docker-compose PG、CI workflow、README。

**当前问题:**
1. `.env` 中无 `DATABASE_URL`，pydantic-settings 默认值密码为 `gangbiao`，但 docker-compose PG 密码为 `gangbiao_dev` → 本地直连 PG 失败
2. `get_db()` 依赖在 yield 后做 `commit()`，而 `user_service.create_user()` 也做 `commit()` → 双重提交导致 session 状态异常
3. `auth_client` fixture 无 DB 测试隔离（无事务回滚、无数据清理）→ 测试间数据残留引发 IntegrityError
4. 持久化集成测试 (`test_persistence.py`) 使用 `client` fixture（有 dependency_overrides），而非 `auth_client`，需要确认是否真正测试了 DB 持久化

---

## Phase 6: 修复集成测试

### Task 1: 修复 DATABASE_URL 密码不一致

**目标:** 确保 `.env` 中的 `DATABASE_URL` 与 docker-compose PG 密码一致，本地开发能直连 PG。

**涉及文件:**
- `.env` (编辑)
- `app/core/config.py` (可选调整默认值)

**步骤:**

1. 在 `.env` 中添加 `DATABASE_URL=postgresql+asyncpg://gangbiao:gangbiao_dev@localhost:5432/gangbiao`，与 docker-compose 的 `POSTGRES_PASSWORD` 默认值 `gangbiao_dev` 一致。

2. 更新 `app/core/config.py` 中 `database_url` 的默认值，改为 `postgresql+asyncpg://gangbiao:gangbiao_dev@localhost:5432/gangbiao`，确保即使 `.env` 缺少该行也能用正确密码连接本地 PG。

3. 验证连接:
   ```bash
   source .venv/bin/activate
   python3 -c "from app.core.config import settings; print(settings.database_url)"
   # 应输出: postgresql+asyncpg://gangbiao:gangbiao_dev@localhost:5432/gangbiao
   ```

**测试:** 用 asyncpg 连接验证 PG 可达。

**提交:** `fix(config): align DATABASE_URL password with docker-compose PG`

---

### Task 2: 修复 get_db() 双重提交问题

**目标:** 消除 `get_db()` 依赖与 service 函数的双重 `commit()` 冲突，改为依赖层只做 rollback-on-error，让 service 层负责 commit。

**涉及文件:**
- `app/core/database.py` (重写 `get_db()`)
- `app/services/user_service.py` (确认 commit 逻辑)
- `app/services/session_service.py` (确认 commit 逻辑)
- `app/services/message_service.py` (确认 commit 逻辑)

**根因分析:**

当前 `get_db()` 实现:
```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()  # ← 依赖层 commit
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

而 `user_service.create_user()` 也做 `await db.commit()`。当 service 先 commit 后，依赖层再次 commit 同一个 session，可能导致:
- 已 flushed/commit 的对象状态不一致
- session 在 TestClient 同步上下文中生命周期异常（RuntimeWarning: coroutine not awaited）

**修复方案:**

改为 **依赖层不 commit，只做 rollback-on-error + close**。所有 commit 由 service/route 层负责:

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**验证:** 确认所有 service 函数（`create_user`, `authenticate_user`, `create_session_in_db`, `append_message`, `append_context_messages`）都已有 `await db.commit()`，无需额外添加。

**测试:** 运行现有 43 个单元测试确保无回归:
```bash
pytest tests/unit/ tests/contract/ -v --timeout=30
```

**提交:** `fix(db): remove double-commit in get_db dependency, let service layer own commits`

---

### Task 3: 重写 auth_client fixture — 添加 DB 测试隔离

**目标:** 让 `auth_client` fixture 在每个测试前后清理测试数据，避免 IntegrityError 和数据残留。

**涉及文件:**
- `tests/conftest.py` (重写 `auth_client` fixture)

**根因分析:**

当前 `auth_client` fixture:
```python
@pytest.fixture()
def auth_client() -> Generator[TestClient, None, None]:
    if not pg_available():
        pytest.skip("PostgreSQL not available")
    with TestClient(main.app) as c:
        yield c
```

问题:
- 无数据清理 → 测试间残留用户数据
- 无事务隔离 → IntegrityError 在并发/顺序测试中出现
- `_unique_email()` 用 uuid 防碰撞，但 DB 中残留的旧测试数据可能干扰

**修复方案:**

在 `auth_client` fixture 的 setup/teardown 中清理测试数据:

```python
@pytest.fixture()
def auth_client() -> Generator[TestClient, None, None]:
    if not pg_available():
        pytest.skip("PostgreSQL not available")
    _clean_test_data()
    with TestClient(main.app) as c:
        yield c
    _clean_test_data()
```

其中 `_clean_test_data()` 用同步方式（通过 `asyncio.run`）删除所有 `auth_test_*@example.com` 用户及其关联的 sessions/messages:

```python
def _clean_test_data():
    import asyncio
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.models.db_models import User, ChatSessionDB, ChatMessageDB

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _clean():
        async with session_factory() as session:
            test_user_ids = select(User.id).where(User.email.like("auth_test_%@example.com"))
            await session.execute(
                delete(ChatMessageDB).where(
                    ChatMessageDB.session_id.in_(
                        select(ChatSessionDB.id).where(
                            ChatSessionDB.user_id.in_(test_user_ids)
                        )
                    )
                )
            )
            await session.execute(
                delete(ChatSessionDB).where(ChatSessionDB.user_id.in_(test_user_ids))
            )
            await session.execute(
                delete(User).where(User.id.in_(test_user_ids))
            )
            await session.commit()

    asyncio.run(_clean())
    engine.dispose()
```

**注意:** `_unique_email()` 生成的邮箱格式为 `auth_test_{counter}_{uuid_hex}@example.com`，所以 `like("auth_test_%@example.com")` 能精确匹配测试数据而不误删真实用户。

**测试:** 运行 auth 集成测试:
```bash
pytest tests/integration/test_auth.py -v --timeout=30
```

**提交:** `test(auth): add DB cleanup to auth_client fixture for test isolation`

---

### Task 4: 修复 test_register_duplicate_email 的 coroutine 未 await 问题

**目标:** 消除 `test_register_duplicate_email` 中的 RuntimeWarning（coroutine not awaited），确保第二次注册请求正确返回 409。

**涉及文件:**
- `app/api/v1/routes/auth.py` (添加 rollback)
- `tests/integration/test_auth.py` (可能需要调整)

**根因分析:**

`test_register_duplicate_email` 的流程:
1. 第一次 `_register_user` → `create_user()` commit → 成功 201
2. 第二次 `_register_user` → `create_user()` 查到已存在 → `raise ValueError("email_already_exists")`

但 `ValueError` 被 route 的 `try/except` 捕获并转为 `HTTPException(409)`。问题在于:
- `ValueError` 路径下，session 中可能有未 flush 的 add 操作残留
- `get_db()` 的 `except` 分支会 rollback，但在 TestClient 同步上下文中可能未被正确 await

**修复方案:**

在 `auth.py` register route 中，捕获 `ValueError` 时显式 rollback session:

```python
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await create_user(db, body.email, body.password, body.nickname)
    except ValueError as exc:
        await db.rollback()  # ← 显式 rollback，避免 session 状态残留
        if str(exc) == "email_already_exists":
            raise HTTPException(status_code=409, detail="email_already_exists")
        raise
    return TokenResponse(...)
```

**测试:** `pytest tests/integration/test_auth.py::test_register_duplicate_email -v`

**提交:** `fix(auth): rollback session on duplicate email to prevent stale state`

---

### Task 5: 运行并修复持久化集成测试

**目标:** 确保 `test_persistence.py` 的 5 个测试在 PG 可用时全部通过。

**涉及文件:**
- `tests/integration/test_persistence.py` (替换 fixture)
- `tests/conftest.py` (添加 `persistence_client` fixture)

**根因分析:**

当前 `test_persistence.py` 使用 `client` fixture（有 dependency_overrides: `get_current_user` → mock User, `get_db` → None）。这意味着:
- `get_db()` 返回 `None` → session_service 和 message_service 的 `if db is not None` 分支不会执行
- 测试实际上只验证了内存缓存模式，**没有测试 DB 持久化**

需要创建一个 `persistence_client` fixture，类似 `auth_client` 但:
- 不 override `get_db`（让真实 DB session 生效）
- override `get_current_user` 为一个已注册的真实测试用户

**修复方案:**

1. 在 `conftest.py` 中添加 `persistence_client` fixture:

```python
@pytest.fixture()
def persistence_client() -> Generator[TestClient, None, None]:
    if not pg_available():
        pytest.skip("PostgreSQL not available")
    # Register a real test user in DB, then override get_current_user
    import asyncio
    from app.core.security import hash_password
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.models.db_models import User, ChatSessionDB, ChatMessageDB
    from sqlalchemy import select, delete

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _setup():
        async with session_factory() as session:
            # Clean up previous persistence test user
            result = await session.execute(
                select(User).where(User.email == "persistence_test@example.com")
            )
            existing = result.scalar_one_or_none()
            if existing:
                await session.execute(
                    delete(ChatMessageDB).where(
                        ChatMessageDB.session_id.in_(
                            select(ChatSessionDB.id).where(
                                ChatSessionDB.user_id == existing.id
                            )
                        )
                    )
                )
                await session.execute(
                    delete(ChatSessionDB).where(ChatSessionDB.user_id == existing.id)
                )
                await session.execute(delete(User).where(User.id == existing.id))
                await session.commit()

            user = User(
                email="persistence_test@example.com",
                password_hash=hash_password("test123456"),
                nickname="PersistenceTestUser",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    _persistence_test_user = asyncio.run(_setup())

    main.app.dependency_overrides[get_current_user] = lambda: _persistence_test_user
    # Do NOT override get_db — let real DB sessions work

    with TestClient(main.app) as c:
        yield c

    async def _teardown():
        async with session_factory() as session:
            await session.execute(
                delete(ChatMessageDB).where(
                    ChatMessageDB.session_id.in_(
                        select(ChatSessionDB.id).where(
                            ChatSessionDB.user_id == _persistence_test_user.id
                        )
                    )
                )
            )
            await session.execute(
                delete(ChatSessionDB).where(ChatSessionDB.user_id == _persistence_test_user.id)
            )
            await session.execute(delete(User).where(User.id == _persistence_test_user.id))
            await session.commit()

    asyncio.run(_teardown())
    engine.dispose()
    main.app.dependency_overrides.clear()
```

2. 更新 `test_persistence.py`，将 `client` fixture 替换为 `persistence_client`。

3. 注意: chat 测试会调用 LLM，`isolate_runtime_state` autouse fixture 已清空 `OPENAI_API_KEY`，chat 路由在无 key 时走 fallback。

**测试:** `pytest tests/integration/test_persistence.py -v --timeout=30`

**提交:** `test(persistence): use real DB fixture for persistence integration tests`

---

### Task 6: 全量集成测试回归验证

**目标:** 确保所有测试（单元 + 集成）在 PG 可用时全部通过。

**步骤:**

1. 运行全量测试:
   ```bash
   pytest tests/ -v --timeout=60
   ```

2. 如果有失败，逐个修复:
   - 检查 fixture 冲突（`auth_client` vs `client` 的 dependency_overrides 残留）
   - 检查 DB 数据残留（`_clean_test_data` 未覆盖的场景）
   - 检查 async session 生命周期问题

3. 确保测试顺序无关。

**提交:** 如有修复则单独提交，否则跳过。

---

## Phase 7: E2E 验证与清理

### Task 7: Docker Compose E2E 验证

**目标:** 用 docker compose 启动完整服务栈，手动验证核心流程。

**步骤:**

1. 确保 `.env` 中 `DATABASE_URL` 正确（Task 1 已修复）。

2. 重建并启动所有服务:
   ```bash
   docker compose down
   docker compose up -d --build
   ```

3. 等待所有服务 healthy:
   ```bash
   docker compose ps
   ```

4. 验证核心流程:
   - 注册新用户 → 201 + tokens
   - 登录 → 200 + tokens
   - 创建会话 → 200 + session_id
   - 发送消息 → 200 (fallback)
   - 重启后数据持久 → 会话仍在
   - 用户隔离 → 第二个用户看不到第一个用户的会话

5. 前端验证:
   - 打开 `http://localhost:2088` → 跳转到登录页
   - 注册 → 登录 → 聊天界面 → 侧边栏显示用户信息
   - 创建会话 → 发送消息 → 刷新 → 数据仍在

6. 清理测试数据。

**提交:** 无代码变更则不提交。

---

### Task 8: 清理废弃代码 + 文档更新

**目标:** 清理 Phase 1-5 遗留的兼容性代码，更新文档反映最终状态。

**涉及文件:**
- `app/services/session_service.py` (检查 `SESSIONS` 别名)
- `app/api/deps.py` (确认 `get_current_user_id`)
- `README.md` (更新)
- `.env.example` (添加 `DATABASE_URL` 和 `JWT_SECRET_KEY`)

**步骤:**

1. 检查 `SESSIONS = SESSION_CACHE` 别名的使用情况:
   ```bash
   rg "SESSIONS" --type py
   ```

2. 检查 `get_current_user_id` 的使用情况:
   ```bash
   rg "get_current_user_id" --type py
   ```

3. 更新 `.env.example`:
   ```
   DATABASE_URL=postgresql+asyncpg://gangbiao:gangbiao_dev@localhost:5432/gangbiao
   JWT_SECRET_KEY=CHANGE-ME-IN-PRODUCTION
   JWT_ALGORITHM=HS256
   JWT_ACCESS_EXPIRE_MINUTES=30
   JWT_REFRESH_EXPIRE_DAYS=7
   ```

4. 更新 `README.md`:
   - 确认 auth/PG 设置说明准确
   - 添加 "运行集成测试" 章节
   - 添加 "DATABASE_URL 密码" 注意事项

**测试:** 全量 pytest 确保无回归。

**提交:** `chore: cleanup compat aliases + update .env.example and README`

---

## Phase 8: CAS SSO 准备（基础架构）

> 注意: CAS SSO 的完整实现依赖外部对接（飞书审批、测试工号等），本 Phase 只做代码层面的基础架构准备，不涉及 SID 联调。

### Task 9: CAS SSO 础架构 — session 表 + 配置 + 端点骨架

**目标:** 为 CAS SSO 接入创建基础代码骨架，包括服务端 session 表、CAS 配置项、exchange/slo 端点骨架。不实现完整 CAS 流程，只预留扩展点。

**涉及文件:**
- `app/models/db_models.py` (新增 `ServerSession` 模型)
- `alembic/versions/002_server_session_table.py` (新增 migration)
- `app/core/config.py` (新增 CAS 配置项)
- `app/api/v1/routes/cas.py` (新增 CAS 端点骨架)
- `app/api/v1/router.py` (注册 CAS 路由)
- `app/services/cas_service.py` (新增 CAS service 骨架)

**步骤:**

1. 新增 `ServerSession` ORM 模型:

```python
class ServerSession(Base):
    __tablename__ = "server_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    sid_session_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, comment="SID TGC session index for SLO"
    )
    original_st: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Original CAS Service Ticket for SLO back-channel"
    )
    access_token_jti: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Optional: JWT JTI for token revocation"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, comment="Absolute expiry aligned with TGC 8h"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
```

2. 新增 Alembic migration `002_server_session_table.py`:
   - 创建 `server_sessions` 表
   - 添加 `sid_session_id` unique index
   - 添加 `user_id` index

3. 在 `app/core/config.py` 新增 CAS 配置项:

```python
# --- CAS / SSO ---
sid_base_url: str = "https://sid.ruijie.com.cn"
sid_service_url: str = "https://gangbiao-ai-coach.ruijie.com.cn/login"
sid_session_absolute_expire_hours: int = 8  # aligned with TGC
```

4. 创建 `app/api/v1/routes/cas.py` 端点骨架:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/cas", tags=["cas"])

class ExchangeRequest(BaseModel):
    ticket: str

@router.post("/exchange")
async def exchange_ticket(body: ExchangeRequest):
    raise HTTPException(status_code=501, detail="CAS exchange not yet implemented")

@router.post("/slo")
async def slo_callback():
    raise HTTPException(status_code=501, detail="CAS SLO not yet implemented")
```

5. 注册 CAS 路由到 `app/api/v1/router.py`。

6. 创建 `app/services/cas_service.py` 骨架（`NotImplementedError` 占位）。

7. 运行 migration:
   ```bash
   source .venv/bin/activate && alembic upgrade head
   ```

**测试:** 确认 migration 成功，骨架端点返回 501。

**提交:** `feat(cas): add ServerSession model + CAS config + endpoint skeletons for SSO prep`

---

## 依赖关系

```
Phase 6: Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6
Phase 7: Task 7 (依赖 Task 6) → Task 8
Phase 8: Task 9 (依赖 Task 8 完成，可独立推进)
```

- Task 1 (密码修复) 是所有后续集成测试的前提
- Task 2 (get_db 修复) 是 Task 3-5 的前提
- Task 3 (auth_client fixture) 是 Task 4 的前提
- Task 4 (duplicate email rollback) 可与 Task 3 合并但分开更清晰
- Task 5 (persistence fixture) 依赖 Task 2 的 get_db 修复
- Task 6 (全量回归) 依赖 Task 1-5 全部完成
- Task 7 (E2E) 依赖 Task 6
- Task 8 (清理) 可与 Task 7 并行
- Task 9 (CAS 骨架) 独立于 Task 7-8，但建议在清理完成后做

---

## 风险与注意事项

1. **密码一致性:** docker-compose 用 `POSTGRES_PASSWORD` 默认 `gangbiao_dev`，本地 `.env` 必须显式设置 `DATABASE_URL` 使用相同密码。生产部署时通过环境变量覆盖。
2. **get_db commit 责任:** 移除依赖层 commit 后，所有 service 函数必须自行 commit。需逐一确认 `session_service.py` 和 `message_service.py` 的所有写操作都有 commit。
3. **TestClient + async:** FastAPI TestClient 在同步上下文中运行 async 代码。`auth_client` fixture 的 DB 清理用 `asyncio.run()` 是安全的（在 TestClient 上下文之外执行）。
4. **persistence_client 的 auth override:** override `get_current_user` 返回真实 DB User 对象，`get_current_user_id` 依赖 `get_current_user`，所以 override 会同时生效。
5. **CAS SSO 联调阻塞:** Task 9 只做骨架，完整 CAS 实现依赖飞书审批（应用注册）和测试工号提供。骨架代码不影响现有功能。
6. **前端登录页下线时机:** CAS SSO 上线后，本地邮箱+密码登录页需下线（设计文档要求）。但本期保留，等 CAS 联调完成后再切换。
7. **Alembic migration 顺序:** `002_server_session_table.py` 必须在 `001_initial_schema.py` 之后运行。`alembic upgrade head` 会按 revision chain 顺序执行。

---

## 执行方式

**推荐: Subagent-Driven** — 每个 Task 派一个独立 subagent 执行，主 agent 在 Task 间做 review checkpoint。

**备选: Inline Execution** — 在当前 session 中按 Task 顺序执行，每完成一个 Task 做 git commit + review。
