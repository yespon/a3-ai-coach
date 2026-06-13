# CAS SSO 本地调试指南

> 本文档帮助开发者在本地环境调试 CAS SSO 流程，解决 ST 超时、HTTPS 要求等常见问题。

## 1. 前提条件

- SID (sid.ruijie.com.cn) 应用注册已完成
- 已获得 service URL 白名单配置
- 本地已安装 PostgreSQL 并运行

## 2. hosts 映射配置

SID 要求 service URL 必须是注册的域名。本地调试需要将域名指向 localhost。

### Windows
编辑 `C:\Windows\System32\drivers\etc\hosts`：
```
127.0.0.1  gangbiao-ai-coach.ruijie.com.cn
```

### Linux / macOS
```bash
sudo sh -c 'echo "127.0.0.1  gangbiao-ai-coach.ruijie.com.cn" >> /etc/hosts'
```

## 3. HTTPS 自签名证书（mkcert）

CAS 回调要求 HTTPS。使用 mkcert 生成本地信任的证书：

```bash
# 安装 mkcert
# macOS: brew install mkcert
# Linux: apt install mkcert 或从 GitHub 下载

# 安装本地 CA
mkcert -install

# 生成域名证书
mkcert gangbiao-ai-coach.ruijie.com.cn

# 输出文件:
#   gangbiao-ai-coach.ruijie.com.cn.pem      (证书)
#   gangbiao-ai-coach.ruijie.com.cn-key.pem   (私钥)
```

## 4. Nginx 反向代理配置

使用 nginx 做 HTTPS 终端，代理到后端 uvicorn：

```nginx
server {
    listen 443 ssl;
    server_name gangbiao-ai-coach.ruijie.com.cn;

    ssl_certificate     /path/to/gangbiao-ai-coach.ruijie.com.cn.pem;
    ssl_certificate_key /path/to/gangbiao-ai-coach.ruijie.com.cn-key.pem;

    # 后端 API
    location /api/ {
        proxy_pass http://127.0.0.1:2024;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 前端
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 5. 环境变量配置

本地调试时 `.env` 关键配置：

```bash
# auth_mode=both 保持两种认证并存
AUTH_MODE=both

# SID 配置
SID_BASE_URL=https://sid.ruijie.com.cn
SID_SERVICE_URL=https://gangbiao-ai-coach.ruijie.com.cn/login
SID_LOGOUT_URL=https://sid.ruijie.com.cn/logout

# 本地调试时关闭 Secure cookie（如果不使用 HTTPS）
SESSION_COOKIE_SECURE=false
```

## 6. ST 10 秒超时注意事项

⚠️ **CAS Service Ticket (ST) 只有 10 秒有效期，且只能使用一次。**

- httpx 超时设置为 5 秒（`CAS_VALIDATE_TIMEOUT_SECONDS=5`）
- **不要**在 exchange 链路中设置断点调试
- 如果需要调试 exchange 逻辑，使用 mock SID 响应（参考 `tests/integration/test_cas.py`）

### 调试建议

```python
# 不要这样做:
@router.post("/exchange")
async def cas_exchange(body: ExchangeRequest, ...):
    import pdb; pdb.set_trace()  # ❌ ST 会过期!
    employee_no, attrs = await validate_ticket(...)

# 这样做:
# 1. 先用 mock 测试逻辑
# 2. 生产联调时用日志排查
import logging
logging.getLogger("app.services.cas_service").setLevel(logging.DEBUG)
```

## 7. 调试检查清单

| # | 检查项 | 预期 |
|---|--------|------|
| 1 | `curl https://gangbiao-ai-coach.ruijie.com.cn/api/v1/health` | `{"status":"ok"}` |
| 2 | 浏览器访问 `https://gangbiao-ai-coach.ruijie.com.cn/api/v1/cas/login` | 302 到 SID 登录页 |
| 3 | SID 登录后回调 | URL 中带 `?ticket=ST-xxx` |
| 4 | 前端 POST `/api/v1/cas/exchange` with ticket | 200 + `sid_session` cookie |
| 5 | 带 cookie 请求 `/api/v1/auth/me` | 200 + 用户信息 |
| 6 | `SELECT * FROM auth_sessions LIMIT 5;` | 有对应 session 记录 |
| 7 | `SELECT * FROM users WHERE provider='cas';` | 有 CAS 用户记录 |

## 8. 常见问题

### Q: exchange 返回 401 "CAS validation failed"
- 检查 `SID_SERVICE_URL` 是否与 SID 注册的 service URL **完全一致**（含协议、路径、无尾斜杠）
- 检查 ST 是否已过期（10 秒内）或已被使用

### Q: cookie 没有被设置
- 确认请求来自与 cookie domain 一致的域名
- 检查 `SESSION_COOKIE_SECURE` 设置（HTTPS 环境必须为 true）
- 检查浏览器 DevTools → Application → Cookies

### Q: SLO 不生效
- SLO 是 SID 的 BACK_CHANNEL POST，不经过浏览器
- 检查 SID 是否配置了回调 URL
- 检查日志中是否收到 `/cas/slo` 请求

### Q: 生产环境不能直连 SID
- SID 可能有 IP 白名单
- 需要通过公司 VPN 或内网 nginx 代理
- 确认出口 IP 在 SID 白名单中

## 9. 风险提示

⚠️ **不要在本地直接连接生产 SID 进行调试**
- 生产 SID 有访问限制
- ST 一旦被验证就失效，影响正常用户
- 建议使用测试环境 SID 或 mock 服务
