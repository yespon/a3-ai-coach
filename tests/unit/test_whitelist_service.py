from io import BytesIO
from openpyxl import Workbook, load_workbook

from app.services.whitelist_service import parse_whitelist_excel, build_whitelist_template


def _xlsx(rows):
    wb = Workbook(); ws = wb.active
    for row in rows: ws.append(row)
    buf = BytesIO(); wb.save(buf); buf.seek(0); return buf.getvalue()


def test_parse_whitelist_excel_valid_rows():
    data = _xlsx([["工号", "邮箱"], ["1001", "a@example.com"], ["1002", None]])
    result = parse_whitelist_excel(data)
    assert result.rows == [{"employee_no": "1001", "email": "a@example.com"}, {"employee_no": "1002", "email": None}]
    assert result.errors == []


def test_parse_whitelist_excel_reports_empty_employee_no():
    data = _xlsx([["工号", "邮箱"], [None, "a@example.com"]])
    result = parse_whitelist_excel(data)
    assert result.rows == []
    assert result.errors == [{"row": 2, "reason": "工号为空"}]


def test_template_contains_expected_headers():
    wb = load_workbook(BytesIO(build_whitelist_template()))
    assert [cell.value for cell in wb.active[1]] == ["工号", "邮箱"]
