"use client";

interface AdminPaginationProps {
  page: number;
  pageSize: number;
  total: number;
  pageSizeOptions?: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  storageKey?: string; // localStorage key to persist page size
}

export default function AdminPagination({
  page,
  pageSize,
  total,
  pageSizeOptions = [10, 30, 50, 100],
  onPageChange,
  onPageSizeChange,
  storageKey,
}: AdminPaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const canPrev = page > 1;
  const canNext = page < totalPages;

  function handlePageSizeChange(size: number) {
    onPageSizeChange(size);
    if (storageKey && typeof window !== "undefined") {
      window.localStorage.setItem(storageKey, String(size));
    }
  }

  return (
    <div className="admin-pagination">
      <span className="admin-pagination-info">
        共 {total} 条 · 第 {page} / {totalPages} 页
      </span>
      <button
        type="button"
        className="admin-button admin-button-muted"
        onClick={() => onPageChange(page - 1)}
        disabled={!canPrev}
      >
        上一页
      </button>
      <button
        type="button"
        className="admin-button admin-button-muted"
        onClick={() => onPageChange(page + 1)}
        disabled={!canNext}
      >
        下一页
      </button>
      <label className="admin-pagination-size">
        每页
        <select
          value={pageSize}
          onChange={(event) => handlePageSizeChange(Number(event.target.value))}
        >
          {pageSizeOptions.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
