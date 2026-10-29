"""
backend/schedules/router.py

Per-camera business-hours schedules — outside all of a camera's schedules is
"after-hours" (detection_pipeline.py._check_after_hours). A camera with no
schedules at all is never after-hours (always monitored).

GET    /cameras/{cam_id}/schedules         — list schedules for camera
POST   /cameras/{cam_id}/schedules         — create schedule (admin)
PATCH  /cameras/{cam_id}/schedules/{id}    — update schedule (admin)
DELETE /cameras/{cam_id}/schedules/{id}    — delete schedule (admin)

On create/update/delete the running DetectionPipeline is notified to
hot-reload its schedule list without restart — same pattern as zones/router.py.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from backend.auth.jwt import require_role
from backend.db.database import get_db
from backend.db.models import Camera, Schedule
from backend.pipeline.pipeline_manager import PipelineManager, get_pipeline_manager
from backend.audit.chain import audit_log

logger = logging.getLogger(__name__)
router = APIRouter(tags=["schedules"])

VALID_DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}


def _valid_time(v: str) -> str:
    parts = v.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError("time must be HH:MM")
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("time must be HH:MM, 00:00-23:59")
    return v


# ── Schemas ───────────────────────────────────────────────────────────────────

class ScheduleCreate(BaseModel):
    name: str
    start_time: str
    end_time: str
    days_of_week: list[str]

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_times(cls, v):
        return _valid_time(v)

    @field_validator("days_of_week")
    @classmethod
    def valid_days(cls, v):
        if not v or any(d not in VALID_DAYS for d in v):
            raise ValueError(f"days_of_week must be a non-empty subset of {sorted(VALID_DAYS)}")
        return v


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    days_of_week: Optional[list[str]] = None

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_times(cls, v):
        return None if v is None else _valid_time(v)

    @field_validator("days_of_week")
    @classmethod
    def valid_days(cls, v):
        if v is not None and (not v or any(d not in VALID_DAYS for d in v)):
            raise ValueError(f"days_of_week must be a non-empty subset of {sorted(VALID_DAYS)}")
        return v


class ScheduleOut(BaseModel):
    id: int
    camera_id: int
    name: str
    start_time: str
    end_time: str
    days_of_week: list[str]


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/cameras/{camera_id}/schedules", response_model=list[ScheduleOut])
def list_schedules(
    camera_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator")),
):
    _cam_or_404(db, camera_id)
    schedules = db.query(Schedule).filter(Schedule.camera_id == camera_id).all()
    return [_schedule_out(s) for s in schedules]


@router.post("/cameras/{camera_id}/schedules", response_model=ScheduleOut, status_code=201)
def create_schedule(
    camera_id: int,
    body: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    _cam_or_404(db, camera_id)
    schedule = Schedule(
        camera_id=camera_id,
        name=body.name,
        start_time=body.start_time,
        end_time=body.end_time,
        days_of_week=json.dumps(body.days_of_week),
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    _pipeline_reload_schedules(pipeline_mgr, camera_id, db)
    audit_log(db, action="schedule.create", actor_id=current_user.id,
              target_type="schedule", target_id=schedule.id,
              payload={"camera_id": camera_id, "name": schedule.name})
    return _schedule_out(schedule)


@router.patch("/cameras/{camera_id}/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    camera_id: int,
    schedule_id: int,
    body: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    schedule = _schedule_or_404(db, camera_id, schedule_id)

    if body.name is not None:
        schedule.name = body.name
    if body.start_time is not None:
        schedule.start_time = body.start_time
    if body.end_time is not None:
        schedule.end_time = body.end_time
    if body.days_of_week is not None:
        schedule.days_of_week = json.dumps(body.days_of_week)

    db.commit()
    db.refresh(schedule)

    _pipeline_reload_schedules(pipeline_mgr, camera_id, db)
    audit_log(db, action="schedule.update", actor_id=current_user.id,
              target_type="schedule", target_id=schedule.id, payload={"name": schedule.name})
    return _schedule_out(schedule)


@router.delete("/cameras/{camera_id}/schedules/{schedule_id}", status_code=204)
def delete_schedule(
    camera_id: int,
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    schedule = _schedule_or_404(db, camera_id, schedule_id)
    db.delete(schedule)
    db.commit()

    _pipeline_reload_schedules(pipeline_mgr, camera_id, db)
    audit_log(db, action="schedule.delete", actor_id=current_user.id,
              target_type="schedule", target_id=schedule_id, payload={"camera_id": camera_id})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cam_or_404(db: Session, camera_id: int) -> Camera:
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    return cam


def _schedule_or_404(db: Session, camera_id: int, schedule_id: int) -> Schedule:
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id, Schedule.camera_id == camera_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found on camera {camera_id}")
    return schedule


def _schedule_out(s: Schedule) -> dict:
    return {
        "id": s.id,
        "camera_id": s.camera_id,
        "name": s.name,
        "start_time": s.start_time,
        "end_time": s.end_time,
        "days_of_week": json.loads(s.days_of_week),
    }


def _pipeline_reload_schedules(pipeline_mgr: PipelineManager, camera_id: int, db: Session):
    """Tell the running pipeline to reload schedules from DB without restart."""
    pipeline = pipeline_mgr.get(camera_id)
    if pipeline is None:
        return
    try:
        schedules = db.query(Schedule).filter(Schedule.camera_id == camera_id).all()
        pipeline._schedules = [
            {"start_time": s.start_time, "end_time": s.end_time, "days_of_week": s.days_of_week}
            for s in schedules
        ]
        logger.info("Pipeline cam %d: hot-reloaded %d schedules", camera_id, len(schedules))
    except Exception as exc:
        logger.error("Schedule hot-reload failed cam %d: %s", camera_id, exc)
