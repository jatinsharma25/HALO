"""
tests/test_tracking_api.py

API integration tests for hardware tracking endpoints:
  - GET  /hardware/status
  - POST /hardware/connect
  - POST /hardware/disconnect
  - GET  /cameras/{camera_id}/tracking
  - POST /cameras/{camera_id}/tracking/start
  - POST /cameras/{camera_id}/tracking/stop
  - POST /cameras/{camera_id}/tracking/home
  - POST /cameras/{camera_id}/tracking/manual
  - Role-based authorization (admin/operator vs responder vs unauthenticated)
"""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.db.database import Base, get_db
from backend.db.seed import seed_database
from backend.pipeline.source_manager import get_source_manager, SourceManager
from backend.pipeline.pipeline_manager import get_pipeline_manager, PipelineManager
from backend.pipeline.video_source import SourceState

# ── Test DB setup ─────────────────────────────────────────────────────────────

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


# ── Mocks ─────────────────────────────────────────────────────────────────────

mock_source_mgr = MagicMock(spec=SourceManager)
mock_pipeline_mgr = MagicMock(spec=PipelineManager)
mock_video_source = MagicMock()
mock_video_source.state = SourceState.ACTIVE
mock_source_mgr.get.return_value = mock_video_source
mock_pipeline_mgr.get.return_value = MagicMock()

mock_arduino = MagicMock()
mock_arduino.connected = True
mock_arduino.port = "COM3"
mock_arduino.status_dict.return_value = {
    "connected": True,
    "port": "COM3",
    "baud_rate": 115200,
    "last_pan": 90,
    "last_tilt": 90,
    "error_count": 0,
    "last_error": None,
}
mock_arduino.list_ports.return_value = ["COM3"]

mock_tracking_ctrl = MagicMock()
mock_tracking_ctrl.status_dict.return_value = {
    "enabled": True,
    "state": "tracking",
    "camera_id": 1,
    "target_track_id": "0",
    "pan": 92.5,
    "tilt": 88.0,
}
mock_tracking_ctrl.go_home.return_value = (90.0, 90.0)
mock_tracking_ctrl.manual_move.return_value = (85.0, 95.0)

_MODULE_OVERRIDES = {
    get_db: override_get_db,
    get_source_manager: lambda: mock_source_mgr,
    get_pipeline_manager: lambda: mock_pipeline_mgr,
}
app.dependency_overrides.update(_MODULE_OVERRIDES)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_overrides_and_hardware():
    app.dependency_overrides.update(_MODULE_OVERRIDES)
    with patch("backend.hardware.router.get_arduino", return_value=mock_arduino), \
         patch("backend.hardware.router.get_tracking_controller", return_value=mock_tracking_ctrl):
        yield


# ── Auth helpers ──────────────────────────────────────────────────────────────

def admin_token() -> str:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


def operator_token() -> str:
    r = client.post("/auth/login", json={"username": "operator", "password": "op123"})
    return r.json()["access_token"]


def responder_token() -> str:
    r = client.post("/auth/login", json={"username": "responder", "password": "resp123"})
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_hardware_status():
    resp = client.get("/hardware/status", headers=auth(admin_token()))
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["port"] == "COM3"
    assert "available_ports" in data


def test_hardware_status_responder_allowed():
    resp = client.get("/hardware/status", headers=auth(responder_token()))
    assert resp.status_code == 200


def test_hardware_connect_admin():
    mock_arduino.connect.return_value = True
    resp = client.post(
        "/hardware/connect",
        json={"port": "COM3", "baud_rate": 115200},
        headers=auth(admin_token()),
    )
    assert resp.status_code == 200
    assert resp.json()["connected"] is True


def test_hardware_connect_responder_forbidden():
    resp = client.post(
        "/hardware/connect",
        json={"port": "COM3", "baud_rate": 115200},
        headers=auth(responder_token()),
    )
    assert resp.status_code == 403


def test_camera_tracking_status():
    resp = client.get("/cameras/1/tracking", headers=auth(admin_token()))
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["state"] == "tracking"
    assert data["pan"] == 92.5


def test_start_tracking_operator_allowed():
    resp = client.post("/cameras/1/tracking/start", headers=auth(operator_token()))
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    mock_tracking_ctrl.enable.assert_called()


def test_start_tracking_responder_forbidden():
    resp = client.post("/cameras/1/tracking/start", headers=auth(responder_token()))
    assert resp.status_code == 403


def test_stop_tracking():
    resp = client.post("/cameras/1/tracking/stop", headers=auth(operator_token()))
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    mock_tracking_ctrl.disable.assert_called()


def test_manual_move():
    resp = client.post(
        "/cameras/1/tracking/manual",
        json={"pan": 85.0, "tilt": 95.0},
        headers=auth(admin_token()),
    )
    assert resp.status_code == 200
    assert resp.json() == {"pan": 85.0, "tilt": 95.0}


def test_manual_move_validation():
    # Out of range angles (e.g. 200 degrees) must fail validation with 422
    resp = client.post(
        "/cameras/1/tracking/manual",
        json={"pan": 200.0, "tilt": 95.0},
        headers=auth(admin_token()),
    )
    assert resp.status_code == 422


def test_home_command():
    resp = client.post("/cameras/1/tracking/home", headers=auth(operator_token()))
    assert resp.status_code == 200
    assert resp.json() == {"pan": 90.0, "tilt": 90.0}
