from app.models.db_models import SsoUserWhitelistDB


def test_whitelist_model_columns():
    cols = set(SsoUserWhitelistDB.__table__.columns.keys())
    assert {"id", "employee_no", "email", "enabled", "source", "created_by", "created_at", "updated_at"} <= cols
    assert SsoUserWhitelistDB.__tablename__ == "sso_user_whitelist"
