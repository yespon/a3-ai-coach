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
  pptx: { label: "演示文稿", color: "#d24726", short: "PPTX" },
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
