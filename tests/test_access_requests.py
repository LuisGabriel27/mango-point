"""Exercise inquiry intake and review with real SQL in an isolated database."""

from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.core.config import settings
from api.core.database import get_db
from api.core.security import get_current_active_user
from api.models.access_requests import AccessRequestCreate
from api.routes.access_requests import router
from db.models import AccessRequest, UserAccount, UserRoleEnum


class TestSession:
    """Run the async service's SQL against a test-only synchronous SQLite DB."""
    __test__ = False

    def __init__(self, session):
        self.session = session
        self.bind = session.bind

    def add(self, row):
        self.session.add(row)

    async def get(self, *args):
        return self.session.get(*args)

    async def execute(self, *args):
        return self.session.execute(*args)

    async def scalar(self, *args):
        return self.session.scalar(*args)

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def refresh(self, row):
        self.session.refresh(row)


def payload(**changes):
    return {
        "submission_id": str(uuid4()), "organization": "Example Cooperative",
        "sector": "cooperative", "contact_name": "Test Contact",
        "email": "contact@example.test", "phone": "", "location": "Guimaras",
        "orchard_count": 3, "interest": "demonstration",
        "message": "We would like to discuss an orchard demonstration.",
        "consent": True, "website": "", **changes,
    }


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_SECRET_KEY", "test-only-inquiry-secret")
    monkeypatch.setattr(settings, "ACCESS_REQUEST_LIMIT_PER_HOUR", 2)
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    UserAccount.__table__.create(engine)
    AccessRequest.__table__.create(engine)
    session = Session(engine, expire_on_commit=False)
    admin = UserAccount(user_id=1, full_name="Test Admin", username="test-admin",
                        email="admin@example.test", password_hash="test", role=UserRoleEnum.ADMIN, is_active=True)
    session.add(admin)
    session.commit()
    app = FastAPI()
    app.include_router(router)

    async def database():
        yield TestSession(session)

    app.dependency_overrides[get_db] = database
    yield app, session, admin
    session.close()
    engine.dispose()


@pytest.mark.asyncio
async def test_public_submission_is_durable_private_and_idempotent(setup):
    app, session, _ = setup
    body = payload(email=" Contact@Example.test ")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/access-requests", json=body)
        assert response.status_code == 201
        assert set(response.json()) == {"reference", "created_at", "message"}
        assert response.json()["created_at"].endswith("Z")
        duplicate = await client.post("/access-requests", json=body)
        assert duplicate.json() == response.json()
        changed = await client.post("/access-requests", json={**body, "organization": "Changed Org"})
        assert changed.status_code == 409
        assert (await client.get("/access-requests")).status_code == 401
    rows = session.scalars(select(AccessRequest)).all()
    assert len(rows) == 1
    assert rows[0].email == "contact@example.test"
    assert rows[0].status == "new"
    assert rows[0].client_hash != "127.0.0.1"
    assert len(session.scalars(select(UserAccount)).all()) == 1


@pytest.mark.asyncio
async def test_review_permissions_and_conflicting_changes(setup):
    app, session, admin = setup
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        body = payload()
        await client.post("/access-requests", json=body)
        url = f"/access-requests/{body['submission_id']}"
        update = {"expected_version": 1, "status": "approved", "notes": "Agreement discussed."}
        assert (await client.patch(url, json=update)).status_code == 401
        app.dependency_overrides[get_current_active_user] = lambda: admin
        admin.role = UserRoleEnum.OPERATOR
        assert (await client.get("/access-requests")).status_code == 403
        assert (await client.patch(url, json=update)).status_code == 403
        admin.role = UserRoleEnum.ANALYST
        assert (await client.get("/access-requests")).status_code == 403
        admin.role = UserRoleEnum.ADMIN
        listing = await client.get("/access-requests", params={"search": "cooperative"})
        assert listing.json()["total"] == 1
        assert listing.json()["counts"]["new"] == 1
        saved = await client.patch(url, json=update)
        assert saved.status_code == 200
        assert saved.json()["version"] == 2
        assert saved.json()["reviewed_by_user_id"] == 1
        assert (await client.patch(url, json=update)).status_code == 409
        assert session.get(AccessRequest, body["submission_id"]).notes == "Agreement discussed."
        assert len(session.scalars(select(UserAccount)).all()) == 1
        assert (await client.get("/access-requests", params={"status": "new"})).json()["total"] == 0
        assert (await client.get("/access-requests", params={"search": "%"})).json()["total"] == 0
        assert (await client.patch(f"/access-requests/{uuid4()}", json=update)).status_code == 404


@pytest.mark.asyncio
async def test_quota_survives_service_calls_and_saved_retries_are_free(setup):
    app, _, _ = setup
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = payload()
        assert (await client.post("/access-requests", json=first)).status_code == 201
        assert (await client.post("/access-requests", json=payload())).status_code == 201
        limited = await client.post("/access-requests", json=payload())
        assert limited.status_code == 429
        assert limited.headers["Retry-After"] == "3600"
        assert (await client.post("/access-requests", json=first)).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"consent": False}, {"website": "spam.example"}, {"email": "invalid"},
    {"sector": "invented"}, {"message": "short"}, {"role": "admin"},
    {"orchard_count": -1}, {"organization": " "},
])
async def test_invalid_submissions_are_never_saved(setup, changes):
    app, session, _ = setup
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/access-requests", json=payload(**changes))).status_code == 422
    assert session.scalars(select(AccessRequest)).all() == []


def test_schema_forms_match_and_backup_restore_include_requests():
    root = Path(__file__).resolve().parents[1]
    local = (root / "db/migrations/0012_organization_access_requests.sql").read_text(encoding="utf-8")
    hosted = (root / "supabase/migrations/202610120001_organization_access_requests.sql").read_text(encoding="utf-8")
    editor = (root / "supabase/MangoPoint_Supabase_SQL_Editor.sql").read_text(encoding="utf-8")
    assert local == hosted
    assert hosted.strip() in editor
    assert "enqueue_mangopoint_sync_event('request_id')" in hosted
    assert "ENABLE ROW LEVEL SECURITY" in hosted
    from scripts.restore_from_supabase import RESTORE_ORDER
    assert RESTORE_ORDER.index("access_request") > RESTORE_ORDER.index("user_account")
