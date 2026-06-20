# T-2: embedded \t and \n sanitization in Raw output

from io import BytesIO

from openpyxl import Workbook

from app.extractors.spreadsheet import _extract_xlsx_text, _rows_to_raw_lines


def test_rows_to_raw_lines_sanitizes_embedded_tab():
    """A cell containing a literal TAB should not break \t-delimited columns."""
    rows = [["含\t制表符", "正常值", "另一个"]]
    lines = _rows_to_raw_lines(rows)
    # The TAB inside the cell value should be replaced with a space,
    # so there are exactly 3 columns separated by 2 TABs.
    assert lines[0].count("\t") == 2, f"Expected 2 tabs, got {lines[0].count(chr(9))}: {lines[0]!r}"
    assert "含 制表符" in lines[0], f"TAB not sanitized: {lines[0]!r}"


def test_rows_to_raw_lines_sanitizes_embedded_newline():
    """A cell containing a literal NEWLINE should not break row boundaries."""
    rows = [["含\n换行", "正常值", "另一个"]]
    lines = _rows_to_raw_lines(rows)
    # Should produce exactly 1 line (the newline is sanitized to a space).
    assert len(lines) == 1, f"Expected 1 line, got {len(lines)}: {lines!r}"
    assert "含 换行" in lines[0], f"NEWLINE not sanitized: {lines[0]!r}"


def test_rows_to_raw_lines_sanitizes_carriage_return():
    """A cell containing a literal CR should be sanitized too."""
    rows = [["含\r回车", "值"]]
    lines = _rows_to_raw_lines(rows)
    assert len(lines) == 1
    assert "含 回车" in lines[0]


def test_extract_xlsx_raw_block_preserves_row_structure_with_special_chars():
    """End-to-end: uploading an xlsx with embedded \t/\n should not corrupt [Raw] block."""
    wb = Workbook()
    ws = wb.active
    ws.title = "特殊字符"
    ws.append(["岗位任务", "客户价值", "目的", "成果"])
    ws.append(["含\t制表符的任务", "含\n换行的价值", "正常目的", "正常成果"])
    ws.append(["任务2", "价值2", "目的2", "成果2"])
    buf = BytesIO()
    wb.save(buf)

    text = _extract_xlsx_text(buf.getvalue())

    # Find the [Raw] block and verify each data row has exactly 3 TAB separators
    in_raw = False
    raw_lines = []
    for line in text.splitlines():
        if line.strip() == "[Raw]":
            in_raw = True
            continue
        if in_raw and not line.startswith("\t"):
            raw_lines.append(line)

    # Should have at least the header + 2 data rows
    data_lines = [l for l in raw_lines if l and not l.startswith("[")]
    for i, line in enumerate(data_lines):
        tab_count = line.count("\t")
        assert tab_count == 3, (
            f"Row {i} has {tab_count} tabs (expected 3): {line!r}"
        )


if __name__ == "__main__":
    test_rows_to_raw_lines_sanitizes_embedded_tab()
    print("PASS: embedded TAB sanitized")

    test_rows_to_raw_lines_sanitizes_embedded_newline()
    print("PASS: embedded NEWLINE sanitized")

    test_rows_to_raw_lines_sanitizes_carriage_return()
    print("PASS: embedded CR sanitized")

    test_extract_xlsx_raw_block_preserves_row_structure_with_special_chars()
    print("PASS: end-to-end [Raw] block preserves row structure")

    print("\nAll tests passed ✓")
