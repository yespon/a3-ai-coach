"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { submitFeedback } from "@/lib/feedback";

const MAX_IMAGES = 5;
const MAX_BYTES_PER_IMAGE = 3 * 1024 * 1024;
const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_CONTENT = 1000;

interface FeedbackDialogProps {
  open: boolean;
  onClose: () => void;
}

export default function FeedbackDialog({ open, onClose }: FeedbackDialogProps) {
  const [content, setContent] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setContent("");
      images.forEach((_, idx) => URL.revokeObjectURL(previews[idx] || ""));
      setImages([]);
      setPreviews([]);
      setError("");
      setToast("");
      setSubmitting(false);
    }
    // We deliberately only reset on open→close; the cleanup runs unconditionally.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const trimmed = content.trim();
  const canSubmit = !submitting && trimmed.length >= 1 && trimmed.length <= MAX_CONTENT && images.length <= MAX_IMAGES;

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(event.target.files || []);
    if (!picked.length) return;
    const valid: File[] = [];
    let localError = "";
    for (const file of picked) {
      if (!ALLOWED_TYPES.includes(file.type)) {
        localError = `已忽略非图片文件 ${file.name}`;
        continue;
      }
      if (file.size > MAX_BYTES_PER_IMAGE) {
        localError = `已忽略过大文件 ${file.name} (单张不能超过 3MB)`;
        continue;
      }
      valid.push(file);
    }
    setError(localError);
    setImages((prev) => {
      const next = [...prev, ...valid].slice(0, MAX_IMAGES);
      setPreviews(next.map((f) => URL.createObjectURL(f)));
      return next;
    });
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function removeImage(idx: number) {
    setImages((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      setPreviews(next.map((f) => URL.createObjectURL(f)));
      return next;
    });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError("");
    try {
      await submitFeedback(trimmed, images);
      setToast("感谢你的反馈,我们已收到");
      setTimeout(() => onClose(), 600);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="admin-dialog-backdrop" role="presentation" onClick={onClose}>
      <section
        className="admin-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="意见反馈"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="admin-dialog-head">
          <div>
            <p className="admin-kicker">Feedback</p>
            <h3>意见反馈</h3>
            <p>告诉我们你遇到的问题或建议。最多可附 5 张图(单张 3MB 内)。</p>
          </div>
          <button className="admin-dialog-close" type="button" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>

        {toast ? <div className="feedback-dialog-toast">{toast}</div> : null}
        {error ? <div className="admin-error">{error}</div> : null}

        <form className="feedback-dialog-form" onSubmit={onSubmit}>
          <textarea
            className="feedback-dialog-textarea"
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="说说你遇到的问题或建议…"
            maxLength={MAX_CONTENT}
          />
          <div className="feedback-dialog-counter">
            {trimmed.length} / {MAX_CONTENT}
          </div>

          <div className="feedback-dialog-uploader">
            <div className="feedback-dialog-uploader-row">
              <label className="feedback-dialog-file-button">
                添加图片 ({images.length} / {MAX_IMAGES})
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  hidden
                  onChange={handleFileChange}
                />
              </label>
            </div>
            {previews.length > 0 ? (
              <div className="feedback-dialog-thumbnails">
                {previews.map((src, idx) => (
                  <div className="feedback-dialog-thumb" key={src}>
                    <img src={src} alt={`附件 ${idx + 1}`} />
                    <button
                      type="button"
                      className="feedback-dialog-thumb-remove"
                      onClick={() => removeImage(idx)}
                      aria-label={`删除附件 ${idx + 1}`}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <div className="admin-dialog-actions">
            <button
              type="button"
              className="admin-button admin-button-muted"
              onClick={onClose}
              disabled={submitting}
            >
              取消
            </button>
            <button
              type="submit"
              className="admin-button admin-button-primary"
              disabled={!canSubmit}
            >
              {submitting ? "提交中…" : "提交"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
