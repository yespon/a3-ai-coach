import { fileTypeInfo, formatSize } from "@/lib/fileType";

interface AttachmentCardProps {
  name: string;
  size?: number;
  onRemove?: () => void; // 提供则渲染 ✕（编辑态）；省略则只读
  disabled?: boolean; // busy 时禁用移除
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
