# 附件上传/发送 UX 优化设计

> 日期：2026-06-13
> 范围：前端 `frontend/`，参考 ChatGPT 附件卡片 + 等待回复动效
> 目标：把「纯文本附件列表 + 无等待反馈」升级为「附件卡片 + 呼吸文字等待动效」

---

## 1. 背景与约束

当前实现（`frontend/app/page.tsx`）：
- 选中文件后以纯文本逗号拼接展示（`附件: a.xlsx, b.pdf`）
- 发送时 `busy=true`，按钮变「发送中」，并 push 一条 hacky 的假消息「已获取您的岗标材料，正在解析中…」（第 178-189 行）
- 无等待回复动效；流式直接显示原始 delta

**关键架构约束**：文件随聊天消息一起 multipart 发送（`/chat`、`/chat/stream`），**没有独立上传接口**。因此：
- 「上传」是即时的（浏览器本地持有 `File`），不存在真实网络上传进度
- 真实「解析」发生在发送后的服务端请求内（流式首字到达前）
- 后端 history 每条消息已返回 `attachments` 数组（`filename`/`content_type`/`size`/`saved_path`/`excerpt`），但前端 `ChatHistoryItem` 类型未包含该字段，数据被丢弃

## 2. 设计决策（已与用户确认）

1. **附件卡片**：ChatGPT 横向卡片 —— 彩色类型图标 + 文件名 + `类型 · 大小`副标题 + 右上角 `✕` 移除
2. **选择文件动效**：立即就绪（真实），不假装上传/解析；解析动效放在发送后的等待区
3. **等待回复动效**：呼吸文字（opacity 呼吸），分阶段文案

## 3. 组件拆分（方案 B：抽组件）

```
frontend/components/
  AttachmentCard.tsx     # 单个附件卡片，editable 态带 ✕ / 只读态无 ✕
  TypingIndicator.tsx    # 发送后等待回复的呼吸文字动效
frontend/lib/
  fileType.ts            # 扩展名 → { label, color, short } 映射 + 大小格式化
```

理由：附件卡片与等待动效是边界清晰、可独立测试的 UI 单元。抽出后 `page.tsx` 只负责编排，避免其继续膨胀（当前 398 行）。

### 3.1 `fileType.ts`

```ts
export interface FileTypeInfo { label: string; color: string; short: string }

export function fileTypeInfo(filename: string): FileTypeInfo
// 按扩展名返回：
//   xlsx/xls/csv  → { label:"电子表格", color:"#107c41", short:"XLSX" }
//   pdf           → { label:"PDF",     color:"#d93025", short:"PDF" }
//   doc/docx      → { label:"文档",     color:"#2b579a", short:"DOC" }
//   txt/md/json   → { label:"文本",     color:"#5f6368", short:"TXT" }
//   png/jpg/jpeg/gif/webp → { label:"图片", color:"#8b5cf6", short:"IMG" }
//   其他          → { label:"文件",     color:"#6b7280", short:"FILE" }

export function formatSize(bytes: number): string
// 1024→"1 KB"，1536000→"1.5 MB"；无 size 时返回 ""
```

### 3.2 `AttachmentCard.tsx`

```ts
interface AttachmentCardProps {
  name: string;
  size?: number;            // 字节；编辑态来自 File.size，只读态来自 history meta
  onRemove?: () => void;    // 提供则渲染 ✕（编辑态）；省略则只读
  disabled?: boolean;       // busy 时禁用移除
}
```

- 左侧 36×36 圆角方块，背景为类型主色的浅色调，内显 `short` 角标 + 图标
- 右侧两行：文件名（`text-overflow: ellipsis` 单行省略）+ `label · 大小`副标题
- `onRemove` 存在时右上角 `✕`

### 3.3 `TypingIndicator.tsx`

```ts
interface TypingIndicatorProps { label: string }   // "正在解析附件…" | "正在思考…"
```

- 一个呼吸圆点（`◌`/小圆）+ 呼吸文字
- CSS `@keyframes breathe`：opacity 0.4↔1，1.4s ease-in-out 无限循环

## 4. 数据流补强

### 4.1 类型扩展（`frontend/types/chat.ts`）

```ts
export interface AttachmentMeta {
  filename: string;
  content_type?: string | null;
  size?: number;
}

export interface ChatHistoryItem {
  role: ChatRole;
  content: string;
  source?: string;
  created_at?: string;
  attachments?: AttachmentMeta[];   // 新增：后端已返回，前端此前丢弃
}
```

> 后端 `db_session_history_for_client` / `_session_history_for_client` 已在每条消息附 `attachments`（含 `filename`/`content_type`/`size`）。前端补类型即可消费，无需改后端。

### 4.2 渲染逻辑（`page.tsx`）

- **composer 编辑态**：`files` state（`File[]`）→ 每个渲染 `<AttachmentCard editable onRemove>`
- **多附件追加**：再次选择文件时**追加**到现有列表（而非覆盖），按文件名去重。当前 `onChange` 是 `setFiles(Array.from(...))`（覆盖），改为 `setFiles(prev => dedupeByName([...prev, ...picked]))`；追加后清空 `input.value` 以便能重选同名文件被去重逻辑正确处理
- **移除单个**：`setFiles(files.filter((_, i) => i !== idx))`（当前只能整体重选）
- **用户历史气泡**：`item.attachments?.length` → 在气泡内顶部渲染只读 `<AttachmentCard>`（无 ✕），保证刷新/切会话后附件不丢失
- **等待占位**：删除第 178-189 行的假消息逻辑；改为发送期间用一个 `pending` 标记，在消息区末尾渲染 `assistant` 占位气泡含 `<TypingIndicator>`

## 5. 等待 → 流式衔接（`onSubmit`）

```
发送开始
  ├── files.length > 0 → TypingIndicator label="正在解析附件…"
  └── 否则             → TypingIndicator label="正在思考…"
流式首个 delta 到达
  └── 占位替换为 streamingDraft 流式文本
done
  └── setHistory(最终 history)，清空 draft 与 pending
error
  └── 占位替换为错误提示，清空 pending
```

非流式（`streamMode=false`）：发送期间显示 TypingIndicator，响应返回后一次性替换为 history。

## 6. CSS（`globals.css`）

新增：
- `.attachment-card`、`.attachment-card-icon`、`.attachment-card-body`、`.attachment-card-name`、`.attachment-card-sub`、`.attachment-card-remove`
- `.attachment-list`（flex-wrap 横向排列）
- `.typing-indicator`、`.typing-dot`
- `@keyframes breathe`

复用现有设计 token（`--brand`、`--line`、`--muted`、`--font-body` 等）。移除/精简旧 `.upload-status` 相关样式。

## 7. 不做（YAGNI）

- 不引入真实独立上传接口/进度条（架构是 inline multipart，无意义）
- 不做拖拽上传、粘贴上传（本次范围外）
- 不引入状态机库

## 8. 验证

- `npx tsc --noEmit` 零错误
- `npx next build` 成功
- 手动 E2E：选文件 → 卡片显示 → 移除单个 → 发送 → 呼吸动效（解析/思考文案）→ 流式回复 → 切会话后用户气泡仍显示已发送附件卡片
- 多附件 E2E：分多次选择文件 → 追加而非覆盖 → 同名文件去重 → 多卡片 flex-wrap 横向换行
