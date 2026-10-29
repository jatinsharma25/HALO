"""
backend/hardware/router.py

HTTP endpoints for Arduino hardware control and camera tracking.

Hardware endpoints:
  GET  /hardware/status       — Arduino connection state
  POST /hardware/connect      — Open serial port
  POST /hardware/disconnect   — Close serial port

Tracking endpoints (per-camera):
  GET  /cameras/{id}/tracking         — Current tracking state
  POST /cameras/{id}/tracking/start   — Enable autonomous tracking
  POST /cameras/{id}/tracking/stop    — Disable tracking
  POST /cameras/{id}/tracking/home    — Move to neutral position
  POST /cameras/{id}/tracking/manual  — Explicit pan/tilt (tracking must be off)

Role permissions mirror the camera control pattern:
  - admin + operator: full control
  - responder: read-only (status / tracking state)
  - manual commands and tracking start/stop: admin + operator only

Security:
  - Manual angle commands are validated and clamped to configured limits.
  - Manual commands are rejected with HTTP 409 if autonomous tracking is active.
  - Serial port is never directly exposed; only validated commands pass through.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from backend.auth.jwt import require_role
from backend.db.database import get_db
from backend.db.models import Camera
from backend.hardware.tracking_controller import (
    TrackingController,
    get_arduino,
    get_tracking_controller,
)
from backend.hardware import tracking_config as cfg
from backend.pipeline.source_manager import get_source_manager, SourceManager
from backend.pipeline.pipeline_manager import get_pipeline_manager, PipelineManager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["hardware"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    port: str
    baud_rate: int = 115200


class ManualMoveRequest(BaseModel):
    pan: float
    tilt: float

    @field_validator("pan")
    @classmethod
    def validate_pan(cls, v: float) -> float:
        if not (0 <= v <= 180):
            raise ValueError("pan must be between 0 and 180 degrees")
        return v

    @field_validator("tilt")
    @classmethod
    def validate_tilt(cls, v: float) -> float:
        if not (0 <= v <= 180):
            raise ValueError("tilt must be between 0 and 180 degrees")
        return v


class HardwareStatus(BaseModel):
    connected: bool
    port: str
    baud_rate: int
    last_pan: Optional[int]
    last_tilt: Optional[int]
    error_count: int
    last_error: Optional[str]
    available_ports: list[str]


class TrackingStatus(BaseModel):
    enabled: bool
    state: str
    camera_id: Optional[int]
    target_track_id: Optional[str]
    pan: float
    tilt: float


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_camera_or_404(db: Session, camera_id: int) -> Camera:
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if cam is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    return cam


# ── Hardware endpoints ────────────────────────────────────────────────────────

@router.get("/hardware/status", response_model=HardwareStatus)
def hardware_status(
    _user=Depends(require_role("admin", "operator", "responder")),
):
    """Return the current Arduino connection status."""
    arduino = get_arduino()
    s = arduino.status_dict()
    s["available_ports"] = arduino.list_ports()
    return HardwareStatus(**s)


@router.post("/hardware/connect")
def hardware_connect(
    body: ConnectRequest,
    _user=Depends(require_role("admin", "operator")),
):
    """Open a serial connection to the Arduino."""
    arduino = get_arduino()
    # Update port if changed
    if arduino.port != body.port or arduino.connected is False:
        from backend.hardware.arduino_controller import ArduinoController
        from backend.hardware import tracking_controller as tc_module
        import threading

        # Disconnect existing connection before switching ports
        if arduino.connected:
            arduino.disconnect()

        # Replace singleton with new controller on new port
        with tc_module._singleton_lock:
            new_arduino = ArduinoController(
                port=body.port,
                baud_rate=body.baud_rate,
                timeout_s=cfg.SERIAL_TIMEOUT_S,
                min_command_interval_s=1.0 / (cfg.COMMAND_RATE_HZ * 2),
            )
            tc_module._arduino = new_arduino

        arduino = tc_module._arduino

    ok = arduino.connect()
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to {body.port}: {arduino.status_dict().get('last_error')}",
        )
    return {"connected": True, "port": body.port}


@router.post("/hardware/disconnect")
def hardware_disconnect(
    _user=Depends(require_role("admin", "operator")),
):
    """Close the Arduino serial connection."""
    tc = get_tracking_controller()
    tc.disable()
    get_arduino().disconnect()
    return {"connected": False}


# ── Per-camera tracking endpoints ─────────────────────────────────────────────

@router.get("/cameras/{camera_id}/tracking", response_model=TrackingStatus)
def get_tracking_status(
    camera_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator", "responder")),
):
    """Return the current tracking state for a camera."""
    _get_camera_or_404(db, camera_id)
    tc = get_tracking_controller()
    s = tc.status_dict()
    # If the tracking controller is associated with a different camera,
    # report idle for this camera.
    if s["camera_id"] != camera_id:
        return TrackingStatus(
            enabled=False,
            state="idle",
            camera_id=camera_id,
            target_track_id=None,
            pan=cfg.INITIAL_PAN,
            tilt=cfg.INITIAL_TILT,
        )
    return TrackingStatus(**s)


@router.post("/cameras/{camera_id}/tracking/start")
def start_tracking(
    camera_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator")),
    source_mgr: SourceManager = Depends(get_source_manager),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    """Enable autonomous tracking for a camera.

    The camera must be running (started via /cameras/{id}/start).
    The Arduino must be connected (via /hardware/connect).
    """
    _get_camera_or_404(db, camera_id)

    src = source_mgr.get(camera_id)
    if src is None:
        raise HTTPException(status_code=400, detail="Camera is not registered")

    from backend.pipeline.video_source import SourceState
    if src.state not in (SourceState.ACTIVE, SourceState.BLURRED):
        raise HTTPException(
            status_code=400,
            detail=f"Camera is not active (state={src.state.value}). Start the camera first.",
        )

    if pipeline_mgr.get(camera_id) is None:
        raise HTTPException(status_code=400, detail="Detection pipeline is not running for this camera")

    arduino = get_arduino()
    if not arduino.connected:
        raise HTTPException(
            status_code=503,
            detail="Arduino is not connected. Use POST /hardware/connect first.",
        )

    tc = get_tracking_controller()
    try:
        tc.set_camera(camera_id, src)
        tc.enable()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info("Tracking started for camera %d by user %s", camera_id, _user.username)
    return {"enabled": True, "camera_id": camera_id, "state": "target_lost"}


@router.post("/cameras/{camera_id}/tracking/stop")
def stop_tracking(
    camera_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator")),
):
    """Disable autonomous tracking for a camera."""
    _get_camera_or_404(db, camera_id)
    tc = get_tracking_controller()
    tc.disable()
    logger.info("Tracking stopped for camera %d by user %s", camera_id, _user.username)
    return {"enabled": False, "camera_id": camera_id, "state": "idle"}


@router.post("/cameras/{camera_id}/tracking/home")
def tracking_home(
    camera_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator")),
):
    """Move the camera to its configured neutral position.

    Tracking must be disabled before calling this endpoint.
    """
    _get_camera_or_404(db, camera_id)
    arduino = get_arduino()
    if not arduino.connected:
        raise HTTPException(status_code=503, detail="Arduino is not connected")

    tc = get_tracking_controller()
    try:
        pan, tilt = tc.go_home()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"pan": pan, "tilt": tilt}


@router.post("/cameras/{camera_id}/tracking/manual")
def tracking_manual(
    camera_id: int,
    body: ManualMoveRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator")),
):
    """Move the camera to an explicit pan/tilt position.

    Tracking must be disabled before calling this endpoint.
    Angles outside the configured limits are clamped, not rejected.
    """
    _get_camera_or_404(db, camera_id)
    arduino = get_arduino()
    if not arduino.connected:
        raise HTTPException(status_code=503, detail="Arduino is not connected")

    tc = get_tracking_controller()
    try:
        pan, tilt = tc.manual_move(body.pan, body.tilt)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"pan": pan, "tilt": tilt}
