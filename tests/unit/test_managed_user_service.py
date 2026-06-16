from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.services.managed_user_service import (
    MANAGED_USER_TEMPLATE_HEADERS,
    build_managed_user_template,
    is_effective_coach,
    normalize_managed_user_role,
    parse_managed_user_excel,
    protect_system_admin_patch,
    resolve_import_coach_links,
)


def test_normalize_student_role_clears_coach_fields():
    normalized = normalize_managed_user_role("学员", True, "coach-id")
    assert normalized == {"primary_role": "student", "is_coach": False, "coach_id": "coach-id"}


def test_normalize_coach_role_forces_is_coach_and_clears_coach_id():
    normalized = normalize_managed_user_role("教练", False, "coach-id")
    assert normalized == {"primary_role": "coach", "is_coach": True, "coach_id": None}


def test_normalize_admin_role_keeps_admin_coach_capability_and_clears_coach_id():
    normalized = normalize_managed_user_role("管理员", True, "coach-id")
    assert normalized == {"primary_role": "admin", "is_coach": True, "coach_id": None}


def test_effective_coach_includes_coach_and_admin_coach():
    assert is_effective_coach("coach", False) is True
    assert is_effective_coach("admin", True) is True
    assert is_effective_coach("admin", False) is False
    assert is_effective_coach("student", False) is False


def test_system_admin_patch_cannot_disable_or_downgrade():
    protected = protect_system_admin_patch(
        employee_no="1001",
        admin_employee_nos={"1001"},
        requested={"enabled": False, "primary_role": "student", "is_coach": False},
    )
    assert protected["enabled"] is True
    assert protected["primary_role"] == "admin"
    assert protected["is_coach"] is False


def test_managed_user_template_headers_are_in_confirmed_order():
    wb = load_workbook(BytesIO(build_managed_user_template()))
    assert [cell.value for cell in wb.active[1]] == MANAGED_USER_TEMPLATE_HEADERS
    assert MANAGED_USER_TEMPLATE_HEADERS == [
        "工号",
        "姓名",
        "邮箱",
        "一级部门",
        "主角色",
        "兼任教练",
        "所属教练工号",
        "启用状态",
    ]


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_managed_user_excel_defaults_student_and_enabled():
    data = _xlsx([
        ["工号", "姓名", "邮箱", "一级部门", "主角色", "兼任教练", "所属教练工号", "启用状态"],
        [" 1001 ", "张三", "a@example.com", "研发", None, None, None, None],
    ])
    result = parse_managed_user_excel(data)
    assert result.errors == []
    assert result.rows == [{
        "employee_no": "1001",
        "name": "张三",
        "email": "a@example.com",
        "department_level1": "研发",
        "primary_role": "student",
        "is_coach": False,
        "coach_employee_no": None,
        "enabled": True,
    }]


def test_parse_managed_user_excel_keeps_department_after_email():
    data = _xlsx([
        ["工号", "姓名", "邮箱", "一级部门", "主角色", "兼任教练", "所属教练工号", "启用状态"],
        ["2001", "李教练", "coach@example.com", "销售", "教练", "否", None, "启用"],
    ])
    result = parse_managed_user_excel(data)
    assert result.rows[0]["department_level1"] == "销售"
    assert result.rows[0]["primary_role"] == "coach"
    assert result.rows[0]["is_coach"] is True


def test_parse_managed_user_excel_rejects_invalid_student_coach_flag():
    data = _xlsx([
        ["工号", "姓名", "邮箱", "一级部门", "主角色", "兼任教练", "所属教练工号", "启用状态"],
        ["1001", "张三", None, None, "学员", "是", None, "启用"],
    ])
    result = parse_managed_user_excel(data)
    assert result.rows == []
    assert result.errors == [{"row": 2, "reason": "学员不能兼任教练"}]


def test_resolve_import_coach_links_accepts_same_batch_coach():
    rows = [
        {"employee_no": "2001", "primary_role": "coach", "is_coach": True, "coach_employee_no": None},
        {"employee_no": "1001", "primary_role": "student", "is_coach": False, "coach_employee_no": "2001"},
    ]
    errors = resolve_import_coach_links(rows, existing_coach_employee_nos=set())
    assert errors == []


def test_resolve_import_coach_links_rejects_missing_coach():
    rows = [
        {"employee_no": "1001", "primary_role": "student", "is_coach": False, "coach_employee_no": "9999"},
    ]
    errors = resolve_import_coach_links(rows, existing_coach_employee_nos=set())
    assert errors == [{"row": 2, "reason": "所属教练工号不存在或不是教练"}]
