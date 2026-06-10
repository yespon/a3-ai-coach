# 岗位标准化 Chatbot 服务

## 功能

- 新建会话时自动加载 `岗位标准化母体.history.json` 作为默认上下文。
- 可通过开关控制是否在用户对话记录中显示这些默认上下文。
- 聊天框支持多附件上传，后端会保存附件并把可读文本摘要注入对话。
- 已支持自动提取可读文本的附件类型：`txt`、`md`、`json`、`csv`、`doc`、`docx`、`xls`、`xlsx`、`pdf`。
- 支持配置教材目录自动注入：每次新建会话时自动扫描目录并加载可读摘要（无需手工重复上传）。
- 未配置 `OPENAI_API_KEY` 时会启用本地回退回复，便于本地联调。

## 启动

1. 安装依赖

```bash
uv sync
```

2. 启动服务

```bash
uv run python main.py
```

3. 打开页面

访问 `http://127.0.0.1:8000`。

## 可选环境变量

- `OPENAI_API_KEY`: OpenAI 或兼容网关 key。
- `OPENAI_BASE_URL`: 兼容 OpenAI 协议的 base URL，默认 `https://api.openai.com/v1`。
- `OPENAI_MODEL`: 模型名，默认 `gpt-4o-mini`。
- `MATERIALS_AUTOLOAD`: 是否自动加载教材目录，默认 `true`。
- `MATERIALS_DIR`: 教材目录路径（支持相对项目根目录），如 `materials`。
- `MATERIALS_MAX_FILES`: 每次会话最多注入材料数，默认 `20`。
- `MATERIALS_MAX_EXCERPT_CHARS`: 每份材料注入的最大字符数，默认 `1200`。

服务启动时会自动读取项目根目录的 `.env` 文件，例如：

```env
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

MATERIALS_AUTOLOAD=true
MATERIALS_DIR=materials
MATERIALS_MAX_FILES=20
MATERIALS_MAX_EXCERPT_CHARS=1200
```
