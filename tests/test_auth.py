"""
tests/test_auth.py
Phase 1 tests: login, token, role guard.
Run with: pytest tests/ -v
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.db.database import Base, get_db
from backend.db.seed import seed_database

# ── In-memory test DB (isolated per test session) ────────────────────────────
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    seed_database(db)
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


_MODULE_OVERRIDES = {get_db: override_get_db}
app.dependency_overrides.update(_MODULE_OVERRIDES)
client = TestClient(app)



# ── Override isolation ────────────────────────────────────────────────────────
# app.dependency_overrides is global to the FastAPI app, and every test module
# installs its own at import time — so under `pytest tests/` the last module
# imported wins and the others silently talk to the wrong database. Re-asserting
# this module's overrides before each of its tests keeps the modules independent
# without changing how any individual test is written.
@pytest.fixture(autouse=True)
def _isolate_overrides():
    app.dependency_overrides.update(_MODULE_OVERRIDES)
    yield

# ── Health check ────────────────────────────────────────────────────────────
def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ── Login: success ──────────────────────────────────────────────────────────
def test_login_admin_success():
    response = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "admin"
    assert data["username"] == "admin"


def test_login_operator_success():
    response = client.post("/auth/login", json={"username": "operator", "password": "op123"})
    assert response.status_code == 200
    assert response.json()["role"] == "operator"


def test_login_responder_success():
    response = client.post("/auth/login", json={"username": "responder", "password": "resp123"})
    assert response.status_code == 200
    assert response.json()["role"] == "responder"


# ── Login: failure ──────────────────────────────────────────────────────────
def test_login_wrong_password():
    response = client.post("/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_login_nonexistent_user():
    response = client.post("/auth/login", json={"username": "nobody", "password": "test123"})
    assert response.status_code == 401


def test_login_empty_password():
    response = client.post("/auth/login", json={"username": "admin", "password": ""})
    assert response.status_code == 401


# ── /auth/me ────────────────────────────────────────────────────────────────
def test_me_with_valid_token():
    login = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "admin"
    assert response.json()["role"] == "admin"


def test_me_without_token():
    response = client.get("/auth/me")
    assert response.status_code == 401  # No auth header → HTTPBearer returns 401


def test_me_with_invalid_token():
    response = client.get("/auth/me", headers={"Authorization": "Bearer totally-fake-token"})
    assert response.status_code == 401


# ── Token contains role ──────────────────────────────────────────────────────
def test_token_payload_contains_role():
    """Role must be in JWT payload (not just response body)."""
    from backend.auth.jwt import decode_token
    login = client.post("/auth/login", json={"username": "operator", "password": "op123"})
    token = login.json()["access_token"]
    payload = decode_token(token)
    assert payload["role"] == "operator"
    assert "sub" in payload
    assert "exp" in payload
