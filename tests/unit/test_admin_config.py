from app.core.config import Settings, get_admin_employee_no_set


def test_admin_employee_no_set_parses_and_trims(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "admin_employee_nos", " 1001,1002 ,, 1003 ")
    assert get_admin_employee_no_set() == {"1001", "1002", "1003"}
