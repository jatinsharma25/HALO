"""
backend/db/models.py
SQLAlchemy ORM models — mirrors the schema in context.md exactly.
All constraints are enforced at column level with CheckConstraint.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Boolean,
    ForeignKey, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(
        String,
        nullable=False,
        # Enforced at DB level — FastAPI layer also validates
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'operator', 'responder')", name="ck_users_role"),
    )

    incidents_assigned = relationship("Incident", back_populates="assigned_user")
    audit_entries = relationship("AuditLog", back_populates="actor")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    source_uri = Column(String, nullable=False)  # MP4 path, webcam index, or RTSP URL
    status = Column(String, default="unknown")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'offline', 'frozen', 'blackout', 'blurred', 'unknown')",
            name="ck_cameras_status",
        ),
    )

    zones = relationship("Zone", back_populates="camera", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="camera", cascade="all, delete-orphan")
    # Without delete-orphan, deleting a Camera left SQLAlchemy trying to NULL
    # out observations.camera_id (NOT NULL) instead of deleting the rows,
    # which crashed every camera deletion once it had logged anything.
    observations = relationship("Observation", back_populates="camera", cascade="all, delete-orphan")


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    name = Column(String, nullable=False)
    polygon_points = Column(Text, nullable=False)  # JSON: [[x1,y1],[x2,y2],...]
    zone_type = Column(String, nullable=False)
    risk_level = Column(Integer, default=1)
    # Null = use the global LOITERING_SECONDS default (backend/config.py).
    loitering_threshold_s = Column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "zone_type IN ('restricted', 'monitored', 'safe')",
            name="ck_zones_zone_type",
        ),
        CheckConstraint(
            "risk_level BETWEEN 1 AND 5",
            name="ck_zones_risk_level",
        ),
    )

    camera = relationship("Camera", back_populates="zones")
    observations = relationship("Observation", back_populates="zone")


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    name = Column(String, nullable=False)
    start_time = Column(String, nullable=False)  # "HH:MM" 24h
    end_time = Column(String, nullable=False)    # "HH:MM" 24h
    days_of_week = Column(Text, nullable=False)  # JSON: ["Mon","Tue",...]

    camera = relationship("Camera", back_populates="schedules")


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    schema_version = Column(String, default="v1")
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    track_id = Column(String, nullable=False)   # anonymous, camera-local only
    event_type = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=True)
    confidence_score = Column(Float, nullable=False)
    impact_score = Column(Float, nullable=False)
    explanation = Column(Text, nullable=False)  # human-readable, no PII
    raw_metadata = Column(Text, nullable=True)  # JSON: bbox, frame_number, dwell_seconds. NO face data.

    # Operator acknowledgement (alembic 002).
    acknowledged = Column(Boolean, default=False, nullable=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'restricted_zone_entry', 'after_hours_presence', 'loitering', "
            "'camera_offline', 'camera_frozen', 'camera_blackout', "
            "'camera_blur', 'fall_warning', 'abandoned_object_warning', "
            "'fire_smoke_warning', 'line_crossing', 'crowd_threshold')",
            name="ck_observations_event_type",
        ),
        CheckConstraint(
            "confidence_score BETWEEN 0 AND 1",
            name="ck_observations_confidence",
        ),
        CheckConstraint(
            "impact_score BETWEEN 0 AND 1",
            name="ck_observations_impact",
        ),
    )

    camera = relationship("Camera", back_populates="observations")
    zone = relationship("Zone", back_populates="observations")
    # Same reasoning as Camera.observations above: deleting an Observation
    # needs to take its incident_observations link rows with it, not try to
    # null out a NOT NULL composite-key column.
    incident_links = relationship("IncidentObservation", back_populates="observation", cascade="all, delete-orphan")
    acknowledged_user = relationship("User", foreign_keys=[acknowledged_by])


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String, default="new")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Not globally unique: it's only meant to merge OPEN incidents of the same
    # camera+event_type+5-minute window (see incidents/correlator.py, which
    # already scopes its own duplicate check to open statuses). The same hash
    # legitimately recurs once an earlier incident for that window is closed
    # and the same event type fires again — a DB-level unique constraint here
    # was wrong and crashed the correlator on exactly that common case.
    dedup_hash = Column(String, nullable=True)
    correlation_window_start = Column(DateTime, nullable=True)
    correlation_window_end = Column(DateTime, nullable=True)
    # Computed by the correlator from incidents/scoring.py + explain.py when the
    # incident is created/updated. Nullable: briefly absent between creation and
    # first scoring pass, and absent on rows predating this column.
    impact_score = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    explanation = Column(Text, nullable=True)  # JSON — see incidents/explain.py build_explanation()
    # Human-set only when resolving, never inferred automatically.
    disposition = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'acknowledged', 'investigating', 'escalated', 'resolved')",
            name="ck_incidents_status",
        ),
        CheckConstraint(
            "disposition IN ('true_positive', 'false_positive', 'uncertain')",
            name="ck_incidents_disposition",
        ),
    )

    assigned_user = relationship("User", back_populates="incidents_assigned")
    observation_links = relationship("IncidentObservation", back_populates="incident", cascade="all, delete-orphan")
    evidence_packages = relationship("EvidencePackage", back_populates="incident")


class IncidentObservation(Base):
    __tablename__ = "incident_observations"

    incident_id = Column(Integer, ForeignKey("incidents.id"), primary_key=True)
    observation_id = Column(Integer, ForeignKey("observations.id"), primary_key=True)

    incident = relationship("Incident", back_populates="observation_links")
    observation = relationship("Observation", back_populates="incident_links")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_hash = Column(String, nullable=False)  # sha256(prev_hash + timestamp + action + actor_id + payload)
    prev_hash = Column(String, nullable=False)   # genesis row uses "0"
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)      # e.g. "incident.acknowledge"
    target_type = Column(String, nullable=True)  # "incident", "zone", "camera"
    target_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, nullable=False)
    payload = Column(Text, nullable=True)        # JSON of what changed

    actor = relationship("User", back_populates="audit_entries")


class EvidencePackage(Base):
    __tablename__ = "evidence_packages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    clip_path = Column(String, nullable=False)   # redacted preview MP4 — sha256/signatures below are over this file
    manifest_hash = Column(String, nullable=False)  # sha256 of clip file
    signature = Column(String, nullable=False)   # HMAC-SHA256 of manifest
    # Ed25519 over the clip digest (alembic 003). Nullable: packages predating
    # the migration genuinely have none, and a blank must not read as verified.
    ed25519_signature = Column(String, nullable=True)
    # Unredacted clip (alembic 004). Nullable: packages predating the migration
    # have none. Role-protected — see evidence/router.py.
    original_clip_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    incident = relationship("Incident", back_populates="evidence_packages")


class SOP(Base):
    """Standard Operating Procedure shown alongside an incident of a matching type."""
    __tablename__ = "sops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_type = Column(String, nullable=False, unique=True)
    title = Column(String, nullable=False)
    steps_text = Column(Text, nullable=False)
