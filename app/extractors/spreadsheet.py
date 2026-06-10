import re
from io import BytesIO
from typing import Any

import xlrd
from openpyxl import load_workbook


def _normalize_cell_value(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalize_gangbiao_labels(text: str) -> str:
    if not text:
        return text

    normalized_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line

        # Normalize common purpose label variants.
        line = re.sub(r"\b目的\s*[:：]", "任务目的：", line)

        # Normalize result label variants while keeping the remaining sentence.
        line = re.sub(
            r"\b成果\s*(?:（[^）]*）)?\s*[:：]",
            "任务成果（预算、交期、完成度）：",
            line,
        )

        # Keep standardized labels deterministic by trimming spaces after colon.
        line = re.sub(r"任务目的：\s*", "任务目的：", line)
        line = re.sub(r"任务成果（预算、交期、完成度）：\s*", "任务成果（预算、交期、完成度）：", line)

        normalized_lines.append(line)

    return "\n".join(normalized_lines)


def _extract_xlsx_text(raw_bytes: bytes) -> str:
    try:
        # Some files have incorrect dimension metadata (e.g. A1), which breaks
        # read_only iteration. Normal mode is more robust for these workbooks.
        wb = load_workbook(filename=BytesIO(raw_bytes), data_only=False, read_only=False)
    except Exception:
        return ""

    lines: list[str] = []
    max_rows_limit = 1000
    max_cols_limit = 80

    for sheet in wb.worksheets:
        lines.append(f"[Sheet] {sheet.title}")
        merged_values: dict[tuple[int, int], Any] = {}
        for merged in sheet.merged_cells.ranges:
            top_left = sheet.cell(row=merged.min_row, column=merged.min_col).value
            if top_left in (None, ""):
                continue
            for r in range(merged.min_row, merged.max_row + 1):
                for c in range(merged.min_col, merged.max_col + 1):
                    merged_values[(r, c)] = top_left

        max_rows = min(max(sheet.max_row, 1), max_rows_limit)
        max_cols = min(max(sheet.max_column, 1), max_cols_limit)

        for row_idx in range(1, max_rows + 1):
            cells: list[str] = []
            row_has_value = False

            for col_idx in range(1, max_cols + 1):
                value = sheet.cell(row=row_idx, column=col_idx).value
                if value in (None, ""):
                    value = merged_values.get((row_idx, col_idx))

                normalized = _normalize_cell_value(value) if value not in (None, "") else ""
                if normalized:
                    row_has_value = True
                cells.append(normalized)

            if row_has_value:
                # Trim trailing empty columns but keep interior empties for table shape.
                while cells and cells[-1] == "":
                    cells.pop()
                lines.append("\t".join(cells))

        if sheet.max_row > max_rows or sheet.max_column > max_cols:
            lines.append("...")

    return _normalize_gangbiao_labels("\n".join(lines))


def _extract_xls_text(raw_bytes: bytes) -> str:
    try:
        book = xlrd.open_workbook(file_contents=raw_bytes)
    except Exception:
        return ""

    lines: list[str] = []
    max_rows_limit = 1000
    max_cols_limit = 80

    for sheet in book.sheets():
        lines.append(f"[Sheet] {sheet.name}")
        max_rows = min(max(sheet.nrows, 1), max_rows_limit)
        max_cols = min(max(sheet.ncols, 1), max_cols_limit)

        merged_values: dict[tuple[int, int], Any] = {}
        for rlo, rhi, clo, chi in getattr(sheet, "merged_cells", []):
            top_left = sheet.cell_value(rlo, clo)
            if top_left in (None, ""):
                continue
            for r in range(rlo, rhi):
                for c in range(clo, chi):
                    merged_values[(r, c)] = top_left

        for r in range(max_rows):
            cells: list[str] = []
            row_has_value = False
            for c in range(max_cols):
                value = sheet.cell_value(r, c)
                if value in (None, ""):
                    value = merged_values.get((r, c))

                normalized = _normalize_cell_value(value) if value not in (None, "") else ""
                if normalized:
                    row_has_value = True
                cells.append(normalized)

            if row_has_value:
                while cells and cells[-1] == "":
                    cells.pop()
                lines.append("\t".join(cells))

        if sheet.nrows > max_rows or sheet.ncols > max_cols:
            lines.append("...")

    return _normalize_gangbiao_labels("\n".join(lines))
