import uuid
from datetime import UTC, datetime
from io import BytesIO

import main
from app.api.deps import get_current_user, get_db
from app.models.db_models import ManagedUserDB, User
from app.services.managed_user_service import ManagedUserParseResult


def _user(is_admin: bool):
    u = User()
    u.id = uuid.uuid4()
    u.email = "admin@example.com"
    u.nickname = "Admin"
    u.is_active = True
    u.is_admin = is_admin
    u.created_at = datetime.now(UTC)
    return u


class FakeScalarList:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values

    def scalar_one_or_none(self):
        return self.values[0] if self.values else None


class FakeAdminDb:
    def __init__(self):
        self.profile = ManagedUserDB(
            id=uuid.uuid4(),
            employee_no="1001",
            name="张三",
            email="a@example.com",
            department_level1="研发",
            primary_role="student",
            is_coach=False,
            enabled=True,
            source="manual",
        )
        self.added = []

    async def execute(self, stmt):
        return FakeScalarList([self.profile])

    async def get(self, model, obj_id):
        return self.profile if str(obj_id) == str(self.profile.id) else None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()


def test_admin_users_requires_admin(client):
    main.app.dependency_overrides[get_current_user] = lambda: _user(False)
    resp = client.get("/api/v1/admin/users")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "admin_required"


def test_admin_users_list_returns_managed_profiles(client):
    db = FakeAdminDb()
    main.app.dependency_overrides[get_current_user] = lambda: _user(True)
    main.app.dependency_overrides[get_db] = lambda: db
    resp = client.get("/api/v1/admin/users")
    assert resp.status_code == 200
    assert resp.json()[0]["employee_no"] == "1001"
    assert resp.json()[0]["department_level1"] == "研发"


def test_admin_users_template_download(client):
    main.app.dependency_overrides[get_current_user] = lambda: _user(True)
    resp = client.get("/api/v1/admin/users/template")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def test_admin_users_coaches_returns_only_effective_coaches(client):
    coach = ManagedUserDB(id=uuid.uuid4(), employee_no="2001", name="教练", primary_role="coach", is_coach=True, enabled=True)
    admin_coach = ManagedUserDB(id=uuid.uuid4(), employee_no="3001", name="管理员教练", primary_role="admin", is_coach=True, enabled=True)
    student = ManagedUserDB(id=uuid.uuid4(), employee_no="1001", name="学员", primary_role="student", is_coach=False, enabled=True)

    class CoachDb(FakeAdminDb):
        async def execute(self, stmt):
            return FakeScalarList([coach, admin_coach, student])

    main.app.dependency_overrides[get_current_user] = lambda: _user(True)
    main.app.dependency_overrides[get_db] = lambda: CoachDb()
    resp = client.get("/api/v1/admin/users/coaches")
    assert resp.status_code == 200
    assert [row["employee_no"] for row in resp.json()] == ["2001", "3001"]


def test_auth_me_includes_managed_profile_fields(client):
    managed = ManagedUserDB(
        id=uuid.uuid4(),
        employee_no="9001",
        name="管理员",
        primary_role="admin",
        is_coach=True,
        enabled=True,
    )
    user = _user(False)
    user.managed_user = managed
    user.managed_user_id = managed.id
    main.app.dependency_overrides[get_current_user] = lambda: user

    resp = client.get("/api/v1/auth/me")

    assert resp.status_code == 200
    data = resp.json()
    assert data["managed_user_id"] == str(managed.id)
    assert data["employee_no"] == "9001"
    assert data["primary_role"] == "admin"
    assert data["is_coach"] is True
    assert data["is_admin"] is True



def test_admin_users_import_resolves_existing_coach_id(client, monkeypatch):
    coach_id = uuid.uuid4()
    recorded_payloads = []

    class CoachLookupDb(FakeAdminDb):
        async def execute(self, stmt):
            return FakeScalarList([
                ManagedUserDB(
                    id=coach_id,
                    employee_no="2001",
                    name="教练",
                    primary_role="coach",
                    is_coach=True,
                    enabled=True,
                )
            ])

    async def fake_existing_coach_employee_nos(db):
        return {"2001"}

    async def fake_upsert_managed_user(db, payload, source, created_by, admin_employee_nos):
        recorded_payloads.append(dict(payload))
        profile = ManagedUserDB(id=uuid.uuid4(), employee_no=payload["employee_no"], primary_role=payload["primary_role"], is_coach=payload["is_coach"], enabled=payload["enabled"])
        return profile, True

    monkeypatch.setattr("app.api.v1.routes.admin.parse_managed_user_excel", lambda raw: ManagedUserParseResult(rows=[{
        "employee_no": "1001",
        "name": "张三",
        "email": "a@example.com",
        "department_level1": "研发",
        "primary_role": "student",
        "is_coach": False,
        "coach_employee_no": "2001",
        "enabled": True,
        "row": 2,
    }], errors=[]))
    monkeypatch.setattr("app.api.v1.routes.admin.existing_coach_employee_nos", fake_existing_coach_employee_nos)
    monkeypatch.setattr("app.api.v1.routes.admin.resolve_import_coach_links", lambda rows, existing: [])
    monkeypatch.setattr("app.api.v1.routes.admin.upsert_managed_user", fake_upsert_managed_user)

    main.app.dependency_overrides[get_current_user] = lambda: _user(True)
    main.app.dependency_overrides[get_db] = lambda: CoachLookupDb()
    resp = client.post(
        "/api/v1/admin/users/import",
        files={"file": ("users.xlsx", BytesIO(b"fake xlsx"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert resp.status_code == 200
    assert recorded_payloads[0]["coach_id"] == coach_id



def test_admin_users_import_strips_parser_metadata(client, monkeypatch):
    recorded_payloads = []

    async def fake_existing_coach_employee_nos(db):
        return set()

    async def fake_upsert_managed_user(db, payload, source, created_by, admin_employee_nos):
        recorded_payloads.append(dict(payload))
        profile = ManagedUserDB(id=uuid.uuid4(), employee_no=payload["employee_no"], primary_role=payload["primary_role"], is_coach=payload["is_coach"], enabled=payload["enabled"])
        return profile, True

    monkeypatch.setattr("app.api.v1.routes.admin.parse_managed_user_excel", lambda raw: ManagedUserParseResult(rows=[{
        "employee_no": "1001",
        "name": "张三",
        "email": "a@example.com",
        "department_level1": "研发",
        "primary_role": "student",
        "is_coach": False,
        "coach_employee_no": "2001",
        "enabled": True,
        "row": 2,
    }], errors=[]))
    monkeypatch.setattr("app.api.v1.routes.admin.existing_coach_employee_nos", fake_existing_coach_employee_nos)
    monkeypatch.setattr("app.api.v1.routes.admin.resolve_import_coach_links", lambda rows, existing: [])
    monkeypatch.setattr("app.api.v1.routes.admin.upsert_managed_user", fake_upsert_managed_user)

    main.app.dependency_overrides[get_current_user] = lambda: _user(True)
    main.app.dependency_overrides[get_db] = lambda: FakeAdminDb()
    resp = client.post(
        "/api/v1/admin/users/import",
        files={"file": ("users.xlsx", BytesIO(b"fake xlsx"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert resp.status_code == 200
    assert recorded_payloads
    assert "coach_employee_no" not in recorded_payloads[0]
    assert "row" not in recorded_payloads[0]
