from app.api.v1.routes.cas import resolve_employee_no


def test_resolve_employee_no_prefers_rjgh_over_cas_user():
    assert resolve_employee_no("GH123", {"RJGH": " R09438 "}) == "R09438"


def test_resolve_employee_no_falls_back_to_cas_user_when_rjgh_missing():
    assert resolve_employee_no(" GH123 ", {}) == "GH123"
