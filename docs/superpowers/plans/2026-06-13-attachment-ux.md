# 附件上传/发送 UX 优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把附件展示从纯文本列表升级为 ChatGPT 风格横向卡片，并在发送后加入呼吸文字等待动效。

**Architecture:** 抽出 3 个独立单元（`fileType` 工具、`AttachmentCard`、`TypingIndicator`），`page.tsx` 仅负责编排。文件随消息 multipart 发送（无独立上传接口），故「解析」动效位于发送后等待区。

**Tech Stack:** Next.js 15 (App Router) + React 18 + TypeScript，纯 CSS（globals.css，复用现有设计 token）。

**测试说明（重要）：** 前端项目**无单元测试框架**（仅后端用 pytest），且本次为 UI 优化。按 spec 第 8 节，每个 task 的验证采用 `npx tsc --noEmit`（类型正确）+ 最终 `npx next build`（构建通过）+ 手动 E2E。不引入 vitest/jest（YAGNI，scope 外）。

**基准：** 所有命令在 `frontend/` 目录下执行。spec 见 `docs/superpowers/specs/2026-06-13-attachment-ux-design.md`。

---

## File Structure

| 文件 | 责任 | 动作 |
|------|------|------|
| `frontend/lib/fileType.ts` | 扩展名→图标信息映射 + 大小格式化 | Create |
| `frontend/components/AttachmentCard.tsx` | 单个附件卡片（编辑态/只读态） | Create |
| `frontend/components/TypingIndicator.tsx` | 等待回复呼吸动效 | Create |
| `frontend/app/globals.css` | 卡片 + 动效样式 + `@keyframes breathe` | Modify |
| `frontend/types/chat.ts` | `AttachmentMeta` + `ChatHistoryItem.attachments` | Modify |
| `frontend/app/page.tsx` | 集成：附件追加/移除/卡片渲染、等待动效、历史回显 | Modify |

---

## Task 1: fileType 工具

**Files:**
- Create: `frontend/lib/fileType.ts`

- [ ] **Step 1: 创建 `frontend/lib/fileType.ts`**

```ts
export interface FileTypeInfo {
  label: string;
  color: string;
  short: string;
}

const EXT_MAP: Record<string, FileTypeInfo> = {
  xlsx: { label: "电子表格", color: "#107c41", short: "XLSX" },
  xls: { label: "电子表格", color: "#107c41", short: "XLS" },
  csv: { label: "电子表格", color: "#107c41", short: "CSV" },
  pdf: { label: "PDF", color: "#d93025", short: "PDF" },
  doc: { label: "文档", color: "#2b579a", short: "DOC" },
  docx: { label: "文档", color: "#2b579a", short: "DOCX" },
  txt: { label: "文本", color: "#5f6368", short: "TXT" },
  md: { label: "文本", color: "#5f6368", short: "MD" },
  json: { label: "文本", color: "#5f6368", short: "JSON" },
  png: { label: "图片", color: "#8b5cf6", short: "PNG" },
  jpg: { label: "图片", color: "#8b5cf6", short: "JPG" },
  jpeg: { label: "图片", color: "#8b5cf6", short: "JPG" },
  gif: { label: "图片", color: "#8b5cf6", short: "GIF" },
  webp: { label: "图片", color: "#8b5cf6", short: "WEBP" },
};

const FALLBACK: FileTypeInfo = { label: "文件", color: "#6b7280", short: "FILE" };

export function fileTypeInfo(filename: string): FileTypeInfo {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return EXT_MAP[ext] ?? FALLBACK;
}

export function formatSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误（新文件自洽，无外部依赖）

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/fileType.ts
git commit -m "feat(ui): add fileType util for attachment icon mapping"
```

---

## Task 2: AttachmentCard 组件

**Files:**
- Create: `frontend/components/AttachmentCard.tsx`

- [ ] **Step 1: 创建 `frontend/components/AttachmentCard.tsx`**

```tsx
import { fileTypeInfo, formatSize } from "@/lib/fileType";

interface AttachmentCardProps {
  name: string;
  size?: number;
  onRemove?: () => void;   // 提供则渲染 ✕（编辑态）；省略则只读
  disabled?: boolean;      // busy 时禁用移除
}

export default function AttachmentCard({ name, size, onRemove, disabled }: AttachmentCardProps) {
  const info = fileTypeInfo(name);
  const sub = [info.label, formatSize(size)].filter(Boolean).join(" · ");

  return (
    <div className="attachment-card">
      <div
        className="attachment-card-icon"
        style={{ background: `${info.color}1a`, color: info.color }}
      >
        {info.short}
      </div>
      <div className="attachment-card-body">
        <div className="attachment-card-name" title={name}>
          {name}
        </div>
        <div className="attachment-card-sub">{sub}</div>
      </div>
      {onRemove ? (
        <button
          type="button"
          className="attachment-card-remove"
          onClick={onRemove}
          disabled={disabled}
          aria-label={`移除 ${name}`}
        >
          ✕
        </button>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误（依赖 Task 1 的 fileType）

- [ ] **Step 3: Commit**

```bash
git add frontend/components/AttachmentCard.tsx
git commit -m "feat(ui): add AttachmentCard component"
```

---

## Task 3: TypingIndicator 组件

**Files:**
- Create: `frontend/components/TypingIndicator.tsx`

- [ ] **Step 1: 创建 `frontend/components/TypingIndicator.tsx`**

```tsx
interface TypingIndicatorProps {
  label: string;   // "正在解析附件…" | "正在思考…"
}

export default function TypingIndicator({ label }: TypingIndicatorProps) {
  return (
    <div className="typing-indicator" aria-live="polite">
      <span className="typing-dot" />
      <span className="typing-label">{label}</span>
    </div>
  );
}
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add frontend/components/TypingIndicator.tsx
git commit -m "feat(ui): add TypingIndicator breathing animation component"
```

---

## Task 4: CSS 样式 + 呼吸动画

**Files:**
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: 在 `globals.css` 末尾追加附件卡片与动效样式**

在文件末尾（最后一个 `}` 之后）追加：

```css
/* ===== Attachment cards ===== */
.attachment-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.attachment-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: 260px;
  padding: 8px 10px;
  border: 1px solid var(--line-strong);
  border-radius: 12px;
  background: #fff;
}

.attachment-card-icon {
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.attachment-card-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.attachment-card-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attachment-card-sub {
  font-size: 11px;
  color: var(--muted);
}

.attachment-card-remove {
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: none;
  background: #eef2f7;
  color: var(--muted);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  display: grid;
  place-items: center;
}
.attachment-card-remove:hover:not(:disabled) {
  background: #e0e6ee;
  color: var(--ink);
}
.attachment-card-remove:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Attachments shown inside a sent user bubble */
.msg-attachments {
  margin-bottom: 8px;
}

/* ===== Typing / waiting indicator ===== */
.typing-indicator {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: 14px;
}
.typing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--brand);
  animation: breathe 1.4s ease-in-out infinite;
}
.typing-label {
  animation: breathe 1.4s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
```

- [ ] **Step 2: 构建检查**

Run: `cd frontend && npx next build`
Expected: 构建成功（CSS 仅追加，不影响现有类）

- [ ] **Step 3: Commit**

```bash
git add frontend/app/globals.css
git commit -m "feat(ui): add attachment card + breathing animation styles"
```

---

## Task 5: 类型扩展（ChatHistoryItem.attachments）

**Files:**
- Modify: `frontend/types/chat.ts`

- [ ] **Step 1: 在 `types/chat.ts` 顶部加 `AttachmentMeta`，并给 `ChatHistoryItem` 加 `attachments`**

将文件开头的类型定义：

```ts
export type ChatRole = "user" | "assistant" | "system";

export interface ChatHistoryItem {
  role: ChatRole;
  content: string;
  source?: string;
  created_at?: string;
}
```

替换为：

```ts
export type ChatRole = "user" | "assistant" | "system";

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
  attachments?: AttachmentMeta[];   // 后端 history 已返回；前端此前丢弃
}
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误（`attachments` 为可选，不破坏现有用法）

- [ ] **Step 3: Commit**

```bash
git add frontend/types/chat.ts
git commit -m "feat(ui): add attachments field to ChatHistoryItem type"
```

---

## Task 6: page.tsx — 附件追加/去重/移除 + composer 卡片渲染

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: 加 import（顶部 import 区）**

在 `frontend/app/page.tsx` 第 7 行（`import { createSession ... }` 之后）加：

```tsx
import AttachmentCard from "@/components/AttachmentCard";
import TypingIndicator from "@/components/TypingIndicator";
```

- [ ] **Step 2: 加多附件合并去重工具函数**

在文件底部、`function formatError` 之前加：

```tsx
function mergeFiles(prev: File[], picked: File[]): File[] {
  const seen = new Set(prev.map((f) => f.name));
  const merged = [...prev];
  for (const f of picked) {
    if (!seen.has(f.name)) {
      merged.push(f);
      seen.add(f.name);
    }
  }
  return merged;
}
```

- [ ] **Step 3: 文件 input 改为追加并清空 value（允许重选）**

把当前（约第 317-323 行）：

```tsx
              <input
                id="chat-file-input"
                type="file"
                multiple
                onChange={(e) => setFiles(Array.from(e.target.files || []))}
                disabled={busy}
              />
```

替换为：

```tsx
              <input
                id="chat-file-input"
                type="file"
                multiple
                onChange={(e) => {
                  const picked = Array.from(e.target.files || []);
                  setFiles((prev) => mergeFiles(prev, picked));
                  e.target.value = "";
                }}
                disabled={busy}
              />
```

> 注意：必须先在同步阶段把 `e.target.files` 提取到闭包变量 `picked`，再 `setFiles`。若写成 `setFiles((prev) => mergeFiles(prev, Array.from(e.target.files || [])))`，则 updater 延迟执行时 `e.target.value=""` 已清空 `files`，导致附件加不进去（竞态）。

- [ ] **Step 4: composer 内附件展示从纯文本改为卡片列表**

把当前（约第 306-311 行）：

```tsx
            {selectedFileNames.length > 0 ? (
              <div className="upload-status" aria-live="polite">
                <span className="upload-status-label">附件:</span>
                <span className="upload-status-files">{selectedFileNames.join(", ")}</span>
              </div>
            ) : null}
```

替换为：

```tsx
            {files.length > 0 ? (
              <div className="attachment-list" aria-live="polite">
                {files.map((f, idx) => (
                  <AttachmentCard
                    key={`${f.name}-${idx}`}
                    name={f.name}
                    size={f.size}
                    disabled={busy}
                    onRemove={() => setFiles((prev) => prev.filter((_, i) => i !== idx))}
                  />
                ))}
              </div>
            ) : null}
```

- [ ] **Step 5: 删除已无用的 `selectedFileNames`**

删除当前第 65 行：

```tsx
  const selectedFileNames = useMemo(() => files.map((file) => file.name), [files]);
```

- [ ] **Step 6: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误（`TypingIndicator` import 暂未用，Task 7 会用到——若 tsc 报 unused 仅是 lint 非 error；Next/tsc 默认不因 unused import 失败）

- [ ] **Step 7: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(ui): render attachments as cards with append/dedupe/remove"
```

---

## Task 7: page.tsx — 等待动效占位（删假消息）+ pendingLabel

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: 加 `pendingLabel` state**

在 `const [streamingDraft, setStreamingDraft] = useState("");`（约第 22 行）之后加：

```tsx
  const [pendingLabel, setPendingLabel] = useState("");
```

- [ ] **Step 2: `onSubmit` 删除假消息、设置 pendingLabel**

把当前 `onSubmit` 中这段（约第 172-189 行）：

```tsx
      setBusy(true);
      setError("");
      setStreamingDraft("");
      const activeSessionId = await ensureSessionId();

      // If files attached and message is provided, add a system message immediately
      if (files.length > 0 && message.trim().length > 0) {
        setHistory((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "已获取您的岗标材料，正在解析中...",
            created_at: new Date().toISOString(),
            is_context: false,
            attachments: [],
          },
        ]);
      }
```

替换为：

```tsx
      setBusy(true);
      setError("");
      setStreamingDraft("");
      setPendingLabel(files.length > 0 ? "正在解析附件…" : "正在思考…");
      const activeSessionId = await ensureSessionId();
```

- [ ] **Step 3: `onSubmit` 结束时清空 pendingLabel**

把当前 `onSubmit` 末尾的 `finally` 块（约第 213-215 行）：

```tsx
    } finally {
      setBusy(false);
    }
```

替换为：

```tsx
    } finally {
      setBusy(false);
      setPendingLabel("");
    }
```

- [ ] **Step 4: 消息区渲染等待占位（busy 且无流式草稿时）**

把当前消息区渲染（约第 295-303 行）：

```tsx
            {renderedMessages.map((item, index) => (
              <div key={`${item.role}-${index}`} className={`msg-row ${item.role}`}>
                <div className="msg-role">{item.role === "assistant" ? "Assistant" : "You"}</div>
                <div className={`msg ${item.role}`}>
                  <MessageContent content={item.content} />
                </div>
              </div>
            ))}
```

替换为：

```tsx
            {renderedMessages.map((item, index) => (
              <div key={`${item.role}-${index}`} className={`msg-row ${item.role}`}>
                <div className="msg-role">{item.role === "assistant" ? "Assistant" : "You"}</div>
                <div className={`msg ${item.role}`}>
                  <MessageContent content={item.content} />
                </div>
              </div>
            ))}
            {busy && !streamingDraft ? (
              <div className="msg-row assistant">
                <div className="msg-role">Assistant</div>
                <div className="msg assistant">
                  <TypingIndicator label={pendingLabel || "正在思考…"} />
                </div>
              </div>
            ) : null}
```

- [ ] **Step 5: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误（`TypingIndicator` 现已使用）

- [ ] **Step 6: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(ui): waiting animation placeholder, drop hacky parse message"
```

---

## Task 8: page.tsx — 历史用户气泡回显已发送附件

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: 在消息气泡内渲染只读附件卡片**

把 Task 7 Step 4 替换后的消息渲染块中的单条消息渲染：

```tsx
                <div className={`msg ${item.role}`}>
                  <MessageContent content={item.content} />
                </div>
```

替换为：

```tsx
                <div className={`msg ${item.role}`}>
                  {item.attachments && item.attachments.length > 0 ? (
                    <div className="attachment-list msg-attachments">
                      {item.attachments.map((a, i) => (
                        <AttachmentCard key={`${a.filename}-${i}`} name={a.filename} size={a.size} />
                      ))}
                    </div>
                  ) : null}
                  <MessageContent content={item.content} />
                </div>
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误（`item.attachments` 来自 Task 5 的类型扩展；流式 draft row 无 attachments，可选链保护）

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(ui): echo sent attachments as read-only cards in user bubble"
```

---

## Task 9: 最终验证 + 清理

**Files:**
- Modify: `frontend/app/globals.css`（可选：移除旧 upload-status 样式）

- [ ] **Step 1: 移除已无引用的旧 upload-status 样式**

在 `globals.css` 中删除以下三块（约第 465-484 行，`.upload-status` / `.upload-status-label` / `.upload-status-files`）：

```css
.upload-status {
  border: 1px solid #d1ecff;
  border-radius: 10px;
  background: #eff8ff;
  color: #0b4f73;
  font-size: 12px;
  padding: 8px 10px;
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.upload-status-label {
  font-weight: 700;
  flex: 0 0 auto;
}

.upload-status-files {
  line-height: 1.45;
}
```

> 先 `grep -rn "upload-status" frontend/app frontend/components` 确认已无引用再删。

- [ ] **Step 2: 类型检查 + 构建**

Run: `cd frontend && npx tsc --noEmit && npx next build`
Expected: tsc 无错误；build 成功，路由表显示 `/` 正常

- [ ] **Step 3: 手动 E2E（在运行的 Docker 或 dev server 上）**

逐项确认：
1. 点 `+` 选 1 个 xlsx → 显示绿色 XLSX 卡片（名 + `电子表格 · 大小`）
2. 再点 `+` 选 1 个 pdf → **追加**为第二张红色 PDF 卡片（不覆盖）
3. 再选同名 xlsx → 被去重，不重复
4. 点某卡片 `✕` → 仅移除该卡片
5. 发送（带附件）→ 消息区出现「正在解析附件…」呼吸动效
6. 流式首字到达 → 动效替换为流式文本
7. 不带附件发送 → 显示「正在思考…」
8. 切到其它会话再切回 → 用户气泡顶部仍显示已发送的只读附件卡片（无 ✕）

- [ ] **Step 4: 最终 Commit**

```bash
git add frontend/app/globals.css
git commit -m "chore(ui): remove unused upload-status styles"
```

---

## Self-Review 结果

- **Spec 覆盖：** 卡片样式(T2/T4)、立即就绪(T6 无解析动效)、呼吸等待(T3/T7)、文件类型映射(T1)、数据流 attachments(T5/T8)、移除单个(T6)、多附件追加去重(T6)、删假消息(T7)、历史回显(T8) — 全覆盖。
- **占位符扫描：** 无 TBD/TODO；每个代码步骤含完整代码。
- **类型一致性：** `fileTypeInfo`/`formatSize`(T1) → `AttachmentCard`(T2) 一致；`AttachmentMeta.filename/size`(T5) → T8 渲染 `a.filename`/`a.size` 一致；`pendingLabel` state(T7) 全程一致。
- **测试偏离说明：** 前端无测试框架，按 spec 用 tsc + build + 手动 E2E（已在 header 声明）。
