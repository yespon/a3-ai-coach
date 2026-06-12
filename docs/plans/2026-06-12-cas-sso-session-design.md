# 方案 C 落地设计：锐捷 SID（CAS）+ Postgres 服务端 Session

> **状态：方案已定（C）。** 本文只设计、不改代码。

## ✅ 已确认决策（2026-06-12 回填）

| # | 确认项 | 结论 | 对设计的影响 |
|---|---|---|---|
| 1 | 会话方案 | **走 C：Postgres 服务端 session** | SLO 视为强制，做 BACK_CHANNEL；A′/B 不再考虑 |
| 2 | 属性释放 | 员工会返回**邮箱、姓名等额外信息**（详见对接文档字段表） | `users` 可填 email/nickname/Position；但**非员工(供应商)无邮箱**，代码须容忍 `None` |
| 3 | 回调 `service` | **`https://gangbiao-ai-coach.ruijie.com.cn/login`**（注意是前端 `/login` 路由，非后端 callback 路径） | 流程见 §1；`service` 写死此串，两处校验逐字符一致 |
| 4 | 环境 | **只有生产 SID `https://sid.ruijie.com.cn`，无 UAT**；本地联调用 **hosts 把回调域名指向本机** | 见 §12 联调方案；ST 仅 10 秒，校验超时设小 |

落地后业务路由（`sessions.py` / `chat.py`）**零改动**——它们依赖 `get_current_user_id`（`app/api/deps.py:37`），接缝在 `get_current_user` 内部。

---

## 0. 现状基线（代码事实）

| 位置 | 现状 | 方案 C 的处理 |
|---|---|---|
| `app/api/deps.py:15` `get_current_user` | 验 JWT 签名 → 查 `type==access` → `db.get(User, sub)` → 查 `is_active` | **改为查 session 表**（同一处接缝） |
| `app/api/deps.py:37` `get_current_user_id` | `Depends(get_current_user)` 薄封装 | 不动 |
| `app/api/v1/routes/auth.py` register/login/refresh | 本地账密 + 签 JWT | SSO 下**停用**（见 §6） |
| `auth.py:62` `/logout` | 空 204，无副作用 | 改为删 session + 重定向 SID `/logout` |
| `app/core/security.py` | JWT 编解码 | 保留模块，SSO 下不再签发 access/refresh |
| `app/models/db_models.py` | `User` 已有 `sessions` 关系名 → 指向 **chat_sessions** | ⚠️ 新表命名避让：用 **`auth_sessions`**，关系名 `auth_sessions` |
| `app/core/config.py:59-63` | `database_url` (asyncpg)、`jwt_*` | 新增 `sid_*` / `session_*` 配置 |
| 基础设施 | 仅 Postgres，无 Redis | session 落 Postgres，**不引入 Redis** |
| `deps.py` 每请求 `db.get(User,...)` | 本来就每请求查库 | session 化边际成本≈0，且一次取回 user |
| 用户标识 | 现以 `email` 为中心（unique NOT NULL） | 改用 `provider`+`provider_user_id`（沿用本仓 `multi-user-auth-design.md` §10 既定方向），见 §2.2 |

> 命名警告：`User.sessions`（`db_models.py:33`）当前指**聊天会话** `chat_sessions`。认证会话表**必须**另起名 `auth_sessions`，避免语义与关系冲突。

---

## 1. 总体流程（CAS 3.0 + 服务端 session）

> 注意：`service` = 前端路由 **`https://gangbiao-ai-coach.ruijie.com.cn/login`**。SID 把 `ticket` 带回到**前端 `/login` 页面**，前端再把 ticket 交给后端换 session（前后端分离下的标准做法）。

```
浏览器(SPA)                后端                              SID (sid.ruijie.com.cn)
  │                          │                                  │
  │ 1. 访问受保护页,无cookie  │                                  │
  │   前端探测401 → 跳转       │                                  │
  │ 2. 302/直接 location 到                                       │
  │    SID /login?service=https%3A%2F%2Fgangbiao-ai-coach.ruijie.com.cn%2Flogin
  │──────────────────────────────────────────────────────────> │
  │ 3. 用户在 SID 登录(或已有 SOURCEID_TGC,8h 内静默)             │
  │ 4. 302 回 https://gangbiao-ai-coach.ruijie.com.cn/login?ticket=ST-xxx
  │<────────────────────────────────────────────────────────── │
  │ 5. 前端 /login 页读取 url 中的 ?ticket=,POST 给后端          │
  │    POST /api/auth/cas/exchange { ticket }                    │
  │─────────────────────────>│ 6. GET /p3/serviceValidate       │
  │                          │  ?service=<与第2步逐字符相同的/login>&ticket=ST
  │                          │─────────────────────────────────>│
  │                          │ 7. XML: <cas:user>R1116</>+属性   │
  │                          │<─────────────────────────────────│
  │                          │ 8. 按 provider_user_id=工号 upsert User
  │                          │ 9. 建 auth_sessions(存 ST↔session)│
  │ 10. Set-Cookie: sid_session=<不透明>; HttpOnly; Secure        │
  │<─────────────────────────│    200(JSON) 或 302 回首页         │
  │ 11. 前端清掉 url 上的 ?ticket,进入应用                        │
```

关键约束（来自对接文档，务必照做）：
- **`service` 两处逐字符一致**：第 2 步前端跳 `/login?service=` 与第 6 步后端 `/p3/serviceValidate?service=` 必须是**同一个 URL 编码串**，且都等于注册值 `https://gangbiao-ai-coach.ruijie.com.cn/login`。用配置常量 `sid_service_url` 写死，**不要**用 `request.url` 推断（反代下会漂移）。
- **ST 一次性、生产仅 10 秒**：第 5→7 步必须**同步、立即**完成；后端 `httpx` 超时设 ≤5s。
- **端点是 `/p3/serviceValidate`（CAS 3.0）**，返回带属性 XML，命名空间 `http://www.yale.edu/tp/cas`。
- **`<cas:user>` 是工号**（如 `R1116`），写入 `provider_user_id`，主键仍 UUID。见 §3。
- **前端 `/login` 在 SSO 模式下不再是账密表单**，而是 CAS 落地/弹板路由：无 ticket 且未登录→立即跳 SID；有 ticket→换 session。（呼应文档"禁止回应用自带登录页"。）

---

## 2. 数据库设计

### 2.1 新表 `auth_sessions`

```sql
CREATE TABLE auth_sessions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),   -- 不作为 cookie 值
    session_token TEXT NOT NULL UNIQUE,                          -- cookie 里的不透明值,见 §2.3
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    cas_ticket    VARCHAR(255),          -- 登录时的原始 ST,用于 BACK_CHANNEL SLO 反查
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),            -- 滑动过期基准
    expires_at    TIMESTAMPTZ NOT NULL,                          -- 绝对过期(对齐 SID TGC 8h)
    revoked_at    TIMESTAMPTZ,                                   -- 软删:登出/SLO 置位
    user_agent    TEXT,
    ip            INET
);
CREATE INDEX ix_auth_sessions_user_id   ON auth_sessions(user_id);
CREATE INDEX ix_auth_sessions_cas_ticket ON auth_sessions(cas_ticket);  -- SLO 反查
CREATE INDEX ix_auth_sessions_expires   ON auth_sessions(expires_at);   -- 清理扫描
```

对应 SQLAlchemy（与现有 `db_models.py` 风格一致，放同文件）：

```python
class AuthSessionDB(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    cas_ticket: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ip 可选

    user: Mapped["User"] = relationship()
```

> 注意：不要给 `User` 新增名为 `sessions` 的反向关系（已被 chat_sessions 占用）。这里单向关系即可，或起名 `auth_sessions`。

### 2.2 `users` 表的 SSO 适配

沿用本仓 `multi-user-auth-design.md` §10 既定方向：加 `provider` / `provider_user_id`，**不**新增 `employee_no`。当前 `users.email` 是 `unique NOT NULL`、`password_hash NOT NULL`；SSO 用户无密码，**且非员工(供应商)无邮箱**，需迁移：

```sql
ALTER TABLE users ADD COLUMN provider          VARCHAR(20)  NOT NULL DEFAULT 'local';  -- 'local' | 'cas'
ALTER TABLE users ADD COLUMN provider_user_id  VARCHAR(64);                            -- CAS 工号(如 R1116)
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;   -- SSO 用户无密码
ALTER TABLE users ALTER COLUMN email         DROP NOT NULL;   -- 供应商等无邮箱

-- (provider, provider_user_id) 唯一,定位 CAS 用户
CREATE UNIQUE INDEX uq_users_provider_uid ON users(provider, provider_user_id)
    WHERE provider_user_id IS NOT NULL;

-- email 唯一约束改为"仅本地用户生效"的部分唯一索引,
-- 否则多个 CAS 用户的 NULL/重复邮箱会撞旧的全局 UNIQUE
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key;
CREATE UNIQUE INDEX uq_users_email_local ON users(email)
    WHERE provider = 'local' AND email IS NOT NULL;
```

> 决策点（§6）：本地账密是否与 SSO 并存。`provider` 字段天然支持过渡期 `both`。

### 2.3 cookie 值与存储分离（安全）

- **cookie 里放 `session_token`**：≥32 字节 CSPRNG 随机串（`secrets.token_urlsafe(32)`）。
- 表里**只存其哈希更稳妥**（防 DB 泄露即等于 cookie 泄露）：存 `sha256(session_token)`，查询时哈希后比对。本设计的 `session_token` 列即存哈希值；真实随机串只下发给浏览器，不落库明文。
- `id`（UUID）仅内部用，**不要**当 cookie 值（可枚举风险低但无随机性收益）。

---

## 3. User 标识 / 工号策略

`<cas:user>` 是工号 `R1116`，不是邮箱。采用 `provider`+`provider_user_id`（与 §2.2 一致，沿用既定设计）：

| | 说明 |
|---|---|
| `provider` | `'cas'`（SSO 用户）/ `'local'`（本地用户，过渡期） |
| `provider_user_id` | CAS 工号（`<cas:user>`，如 `R1116`） |
| 主键 | 仍 UUID。业务外键(`chat_sessions.user_id`)是 UUID，**零改动** |

### 3.1 已确认的可用属性（来自对接文档字段表）

> ⚠️ **不同用户类型属性集不同**：员工返回邮箱/姓名等；**供应商返回 `GYSMC`/`SHXYDM` 等，无邮箱**。所有属性按"可能缺失"处理。

| CAS 属性 | 含义 | 落到 `users` | 备注 |
|---|---|---|---|
| `<cas:user>` / `GH` | 工号 | `provider_user_id` | 必有 |
| `RJEMAIL` | 邮箱 | `email` | 员工有；供应商**无** → 允许 NULL |
| `RJXM` | 姓名 | `nickname` | 员工有 |
| `RJTX` | 头像 | （可选，暂不存或存 URL） | — |
| `Position` | 主岗编码 | （建议存，**对岗标应用有业务价值**） | 后续可加列 |
| `HeadcountType` | 编制类型 | （可选） | — |
| `WORKINGLOCATION` | 工作城市 | （可选） | — |
| `SFLBDM` | 身份类别代码 | （可选，区分员工/供应商） | 真实报文里出现 |
| `GYSMC` / `SHXYDM` | 供应商名称 / 统一信用代码 | （供应商专属） | 员工无 |

### 3.2 upsert 逻辑（放 `user_service.py`）

```python
async def upsert_sso_user(db, employee_no: str, attrs: dict) -> User:
    result = await db.execute(
        select(User).where(User.provider == "cas",
                           User.provider_user_id == employee_no)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            provider="cas",
            provider_user_id=employee_no,
            email=attrs.get("RJEMAIL"),      # 供应商为 None,允许
            nickname=attrs.get("RJXM") or employee_no,
        )
        db.add(user)
    else:
        if attrs.get("RJXM"):   user.nickname = attrs["RJXM"]
        if attrs.get("RJEMAIL"): user.email = attrs["RJEMAIL"]
    await db.commit()
    await db.refresh(user)
    return user
```

> 代码要容忍 `RJEMAIL`/`RJXM` 为 `None`（供应商或属性未释放场景），不能用邮箱做主键或非空假设。

---

## 4. `get_current_user` 改造（唯一的鉴权接缝）

目标：把"验 JWT"换成"查 session"，**对外签名不变**（仍返回 `User`），下游 `get_current_user_id` 与所有业务路由零改动。

```python
# app/api/deps.py —— 改造后
from fastapi import Cookie, Depends, HTTPException, status
from datetime import datetime, UTC, timedelta
import hashlib

SESSION_COOKIE = "sid_session"
SLIDING_REFRESH = timedelta(minutes=30)   # last_seen 超过此值才回写,减少写放大

async def get_current_user(
    sid_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not sid_session:
        raise HTTPException(status_code=401, detail="未登录")  # 前端据此跳 CAS

    token_hash = hashlib.sha256(sid_session.encode()).hexdigest()
    result = await db.execute(
        select(AuthSessionDB).where(AuthSessionDB.session_token == token_hash)
    )
    sess = result.scalar_one_or_none()

    now = datetime.now(UTC)
    if (not sess) or sess.revoked_at is not None or sess.expires_at <= now:
        raise HTTPException(status_code=401, detail="会话已失效")

    # 滑动过期:活跃则续期(节流写)
    if now - sess.last_seen_at > SLIDING_REFRESH:
        sess.last_seen_at = now
        # 可选:同时把 expires_at 往后推(但不超过 SID TGC 8h 绝对上限)
        await db.commit()

    user = await db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user
```

要点：
- **一次 select 查 session，一次 get 查 user**——和现状"每请求查一次 User"成本相当。可用 `selectinload`/join 合成一次查询进一步优化，但非必需。
- 401 是前端"跳 CAS"的信号；前端拦截器收到 401 → `window.location = /api/auth/cas/login`。
- `Cookie(...)` 让 FastAPI 自动从 httpOnly cookie 取值，前端 JS 读不到，**天然抗 XSS**。

---

## 5. 新增端点（`auth.py` 内）

> 因 `service` = 前端 `/login`，SID 把 ticket 带回**前端页**，故后端不暴露 `cas/callback`，而是暴露一个 **ticket 交换端点** 供前端 `/login` 调用。

| 方法 路径 | 作用 |
|---|---|
| `GET /api/auth/cas/login-url` | 返回（或 302 到）SID `/login?service=<编码的 /login>`。`service` 用配置 `sid_service_url` 拼，**不靠 request 推断**。前端也可自行拼这个 URL |
| `POST /api/auth/cas/exchange` | **前端 `/login` 拿到 `?ticket=` 后调用**：校验 ST（service=同一 `/login`）→ upsert user → 建 session → Set-Cookie → 返回 200 |
| `POST /api/auth/cas/slo` | **BACK_CHANNEL 登出回调**：解析 SID POST 的 SAML LogoutRequest，取原始 ST，按 `cas_ticket` 反查 session → 置 `revoked_at`。返回 200 |
| `POST /api/auth/logout` | 主动登出：撤销当前 session → 清 cookie → 返回 SID `/logout` 跳转 URL（前端再跳，**禁止回应用自带登录页**） |
| `GET /api/auth/me` | 不变（返回当前 user） |

### 5.1 ticket 交换 + 校验（CAS 3.0 XML 解析）

```python
import httpx
from xml.etree import ElementTree as ET

CAS_NS = {"cas": "http://www.yale.edu/tp/cas"}

async def validate_ticket(ticket: str) -> tuple[str, dict]:
    # service 必须与第 2 步 /login 时逐字符一致 → 用同一个配置常量
    params = {"service": settings.sid_service_url, "ticket": ticket}
    # ST 仅 10s,超时要短,失败不重试(ST 一次性)
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(f"{settings.sid_base_url}/p3/serviceValidate", params=params)
    root = ET.fromstring(resp.text)
    success = root.find(".//cas:authenticationSuccess", CAS_NS)
    if success is None:
        raise HTTPException(status_code=401, detail="CAS 校验失败")
    employee_no = success.find("cas:user", CAS_NS).text
    attrs = {
        el.tag.split("}")[-1]: el.text
        for el in success.findall(".//cas:attributes/*", CAS_NS)
    }
    return employee_no, attrs   # 如 ("R1116", {"GH":"R1116","RJEMAIL":...,"Position":...})
```

`exchange` 端点骨架：

```python
@router.post("/cas/exchange")
async def cas_exchange(body: TicketBody, response: Response, db=Depends(get_db)):
    employee_no, attrs = await validate_ticket(body.ticket)
    user = await upsert_sso_user(db, employee_no, attrs)
    raw_token, sess = await create_session(db, user.id, cas_ticket=body.ticket)  # §2.3 存哈希
    response.set_cookie(
        settings.session_cookie_name, raw_token,
        httponly=True, secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite, max_age=settings.session_ttl_hours*3600,
        path="/",
    )
    return {"ok": True}
```

### 5.2 SLO 端点（BACK_CHANNEL，方案 C 的核心收益）

SID 后端登出时向**注册时填写的应用登出地址** POST 一个含原始 **ST** 的 SAML `LogoutRequest`。处理：

```python
@router.post("/cas/slo")
async def cas_single_logout(logoutRequest: str = Form(...), db=Depends(get_db)):
    # logoutRequest 是 SAML XML,内含 <samlp:SessionIndex>ST-xxx</..>
    st = parse_session_index(logoutRequest)        # 提取原始 ST
    result = await db.execute(
        select(AuthSessionDB).where(AuthSessionDB.cas_ticket == st)
    )
    sess = result.scalar_one_or_none()
    if sess:
        sess.revoked_at = datetime.now(UTC)
        await db.commit()
    return Response(status_code=200)
```

> 这正是 A′ 做不到、B 要靠黑名单绕的能力：**有 `ST↔session` 映射就能精确撤销**。登录时务必把回调拿到的 ST 写进 `auth_sessions.cas_ticket`。

---

## 6. 本地账密 / refresh_token 的处置

| 现有 | SSO 下处置 | 理由 |
|---|---|---|
| `auth.py:48` `/refresh`（7 天 refresh_token） | **停用** | 7 天 refresh 绕过 SID，违反"过期须经 SID 重认证"；与 SLO 语义冲突 |
| `auth.py:23/37` register/login（本地账密） | 过渡期可留作管理员后门，生产建议**关闭或加开关** | 纯 SSO 环境不应有第二套凭据入口 |
| `security.py` JWT 函数 | 保留模块但 SSO 路径不调用 | 留给本地/测试；避免误用作长效凭据 |
| `config.py:62-63` `jwt_*_expire` | refresh 失效；access 若仍用则缩到 ≤30min | — |

建议：加配置开关 `auth_mode: Literal["sso","local","both"]`，默认 `sso`，过渡期 `both`。

---

## 7. CSRF（Cookie 鉴权的代价）

切到 httpOnly cookie 后，`POST /chat`、`/sessions` 等会暴露在 CSRF 下（JWT 在 header 时天然免疫）。对策按强度递增任选：

1. **`SameSite=Lax`**（cookie 属性）：挡掉绝大多数跨站 POST，最省。
2. **`SameSite=Strict`**：更严，但从 SID 302 回来的首跳可能丢 cookie，需测。
3. **双提交 CSRF token**：下发一个非 httpOnly 的 `csrf` cookie，前端读出放进 `X-CSRF-Token` 头，后端比对。最稳，前端要改。

> `/chat/stream` 是 `POST+fetch`，可带自定义头，**配合方案 3 最顺**。建议：`SameSite=Lax` 打底 + 写操作加双提交 token。

cookie 下发参数（callback 里）：
```
Set-Cookie: sid_session=<random>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=28800
```

---

## 8. Session 过期与清理

- **绝对过期** `expires_at`：对齐 SID `SOURCEID_TGC` 的 8h，登录时 `now + 8h`。
- **滑动续期**：活跃请求把 `last_seen_at`/`expires_at` 往后推（节流，见 §4），但不超过某个硬上限（如 max 8h 不延，或允许活跃延长到 12h——按对接清单确认的策略）。
- **清理**：过期/已撤销行定期删除。无 Redis，用一个轻量定时任务（FastAPI lifespan 里起 `asyncio` 周期任务，或 cron 调 SQL）：
  ```sql
  DELETE FROM auth_sessions WHERE expires_at < now() - interval '1 day' OR revoked_at < now() - interval '1 day';
  ```

---

## 9. 验收用例映射（对接文档第 4 节）

| 验收项 | 方案 C 如何过 |
|---|---|
| 未登录→跳 SID | 401 → 前端跳 `/api/auth/cas/login` → 302 SID |
| SID 登录成功→进系统 | callback 建 session + Set-Cookie → 302 首页 |
| 应用会话过期→刷新→自动续登 | session 失效 401 → 跳 CAS；TGC 8h 内 SID 静默放行 |
| 清空所有 cookie→跳 SID | 无 `sid_session` cookie → 401 → 跳 CAS |
| 新窗口直接进入 | 浏览器带 cookie → session 有效 → 直接进 |
| **退出→应用会话 + SID 双失效** | logout 撤销 session + 跳 SID `/logout`（**真失效**） |
| **BACK_CHANNEL 单点登出** | `/cas/slo` 按 ST 反查撤销 session（**真失效**） |

---

## 10. 配置新增（`config.py`）

```python
# --- SID / CAS (new) ---
auth_mode: str = "sso"                       # sso | local | both
sid_base_url: str = "https://sid.ruijie.com.cn"            # 只有生产,无 UAT
sid_service_url: str = "https://gangbiao-ai-coach.ruijie.com.cn/login"  # 注册值,两处校验共用,逐字符一致
sid_logout_url: str = "https://sid.ruijie.com.cn/logout"   # 登出后回 SID
session_cookie_name: str = "sid_session"
session_ttl_hours: int = 8                   # 对齐 TGC
session_sliding_refresh_minutes: int = 30
session_cookie_secure: bool = True
session_cookie_samesite: str = "lax"
csrf_enabled: bool = True
```

> ⚠️ `sid_service_url` 是注册到 SID 的**精确串**，跳转与校验都用它，**不得**因本地/反代而变。本地联调靠 hosts 把这个域名指到本机（见 §12），而非改这个值。

---

## 11. 工时与落地顺序

> CAS service 本体（登录跳转 + 回调 + p3 XML 校验 + 按工号 upsert）约 **1.5–2 天**，三方案共用。
> 方案 C 的会话模型增量 **+2–3 天**。

落地顺序（每步可独立验证）：

1. **DB 迁移**：`users` 加 `provider`/`provider_user_id` + 放松 email/password 约束 + 部分唯一索引（§2.2），并建 `auth_sessions` 表。
2. **session 服务层**：`create_session` / `get_valid_session` / `revoke_session` / `revoke_by_ticket`（新 `auth_session_service.py`）。
3. **CAS 客户端**：`cas/login-url` 跳转 + `cas/exchange` 校验 + upsert（**本地 hosts 联调**，见 §12；只有生产 SID）。
4. **接缝改造**：`get_current_user` 换成查 session。业务路由不动，跑一遍现有 auth 集成测试确认零回归。
5. **前端 `/login` 改造**：SSO 模式下变为 CAS 落地路由（无 ticket 跳 SID、有 ticket 调 `exchange`），下线本地账密表单。
6. **登出 + SLO**：`/logout` + `/cas/slo`（SLO 已确认强制）。
7. **CSRF**：`SameSite=Lax` + 写操作双提交 token。
8. **清理任务** + 配置开关收尾。

---

## 12. 本地联调方案（无 UAT，只有生产 SID）

环境约束：SID 只有生产 `https://sid.ruijie.com.cn`；本应用注册的 `service` 固定为 `https://gangbiao-ai-coach.ruijie.com.cn/login`。本地开发机不能改这个注册值，**改 hosts 让该域名解析到本机**即可联调：

1. **hosts 映射**（开发机 `/etc/hosts` 或 Windows `C:\Windows\System32\drivers\etc\hosts`）：
   ```
   127.0.0.1   gangbiao-ai-coach.ruijie.com.cn
   ```
2. **本机跑 HTTPS**：`service` 是 `https://`，SID 回跳要求 TLS。本地用自签证书（mkcert/openssl）在 `gangbiao-ai-coach.ruijie.com.cn` 上起 443（或反代到应用端口）。浏览器信任自签证书即可。
3. **出网**：开发机能直连 `https://sid.ruijie.com.cn`（用户已确认网络通）。
4. **ST 仅 10 秒**：本地 `exchange` 链路别加断点/慢日志拖过 10s，否则票据失效。
5. **生产部署**：把域名 DNS 指向真实服务器、换正式证书，`service` 值不变——这正是固定 `service` 的好处。

> 风险：直连生产 SID 联调，测试登录会产生真实 SID 会话；登出测试注意清 `SOURCEID_TGC`。

---

## 待确认（剩余事项，转交对接清单）

- [x] ~~SLO 是否强制~~ → **已确认走 C（按强制处理）**
- [x] ~~需释放哪些属性~~ → **员工返回邮箱/姓名等，已确认（供应商无邮箱）**
- [x] ~~`service` 确切 URL~~ → **`https://gangbiao-ai-coach.ruijie.com.cn/login`**
- [x] ~~出网是否放通~~ → **已确认通；只有生产，hosts 联调**
- [ ] BACK_CHANNEL 登出回调**地址在注册时怎么填**、SID POST 的报文确切格式（解析 ST 用）→ 清单第 4 项
- [ ] 飞书注册审批发起与时长（应用ID/负责人等）→ 清单第 6 项
- [ ] session 滑动过期上限策略（是否允许活跃延长超过 TGC 8h）→ 实现时定
