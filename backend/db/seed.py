"""
backend/db/seed.py
Creates default users, cameras, zones, and schedules if the DB is empty.
Called on FastAPI startup.
"""
import json
import logging
import os
from datetime import datetime
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from .models import User, Camera, Zone, Schedule, SOP

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


# The seed runs on ANY empty database, production included, and these passwords
# are published in the README — so they are overridable from the environment and
# their use is announced loudly rather than assumed to be development-only.
_DEFAULT_PASSWORDS = {
    "admin": "admin123",
    "operator": "op123",
    "responder": "resp123",
}


def _seed_password(username: str) -> tuple[str, bool]:
    """Returns (password, is_default) for a seeded account."""
    env_key = f"SEED_{username.upper()}_PASSWORD"
    override = os.getenv(env_key)
    if override:
        return override, False
    return _DEFAULT_PASSWORDS[username], True


def seed_database(db: Session) -> None:
    """Idempotent seed — only runs if users table is empty."""
    if db.query(User).count() > 0:
        logger.info("Database already seeded, skipping.")
        return

    logger.info("Seeding database with default data...")

    # ── Users ──────────────────────────────────────────────────────────────
    users = []
    defaulted = []
    for username, role in (("admin", "admin"), ("operator", "operator"), ("responder", "responder")):
        password, is_default = _seed_password(username)
        if is_default:
            defaulted.append(username)
        users.append(User(username=username, password_hash=hash_password(password), role=role))

    if defaulted:
        logger.warning(
            "Seeded %s with PUBLISHED default passwords. These are in the README; "
            "anyone who has read it can sign in. Set %s before first run, or change "
            "them immediately.",
            ", ".join(defaulted),
            ", ".join(f"SEED_{u.upper()}_PASSWORD" for u in defaulted),
        )
    db.add_all(users)
    db.flush()  # Get IDs before adding cameras

    # ── Cameras (pointing to local MP4 test files under ./media) ────────────
    # "media/<name>" resolves correctly both in local dev (cwd = repo root)
    # and in Docker, where ./media is mounted at /app/media and the app's cwd
    # is /app.
    cameras = [
        Camera(name="Main Entrance",   source_uri="media/test.mp4",  status="unknown"),
        Camera(name="Parking Lot",     source_uri="media/test1.mp4", status="unknown"),
        Camera(name="Lab Corridor",    source_uri="media/test3.mp4", status="unknown"),
    ]
    db.add_all(cameras)
    db.flush()

    cam1_id = cameras[0].id

    # ── Zones on Camera 1 ─────────────────────────────────────────────────
    # Polygon points are expressed as fractions of 1280x720 frame
    # These are sample zones — operator reconfigures via UI
    zones = [
        Zone(
            camera_id=cam1_id,
            name="Server Room Door",
            polygon_points=json.dumps([[800, 100], [1100, 100], [1100, 400], [800, 400]]),
            zone_type="restricted",
            risk_level=5,
        ),
        Zone(
            camera_id=cam1_id,
            name="Reception Area",
            polygon_points=json.dumps([[100, 200], [600, 200], [600, 600], [100, 600]]),
            zone_type="monitored",
            risk_level=2,
        ),
    ]
    db.add_all(zones)

    # ── Schedule on Camera 1 (business hours Mon–Fri) ─────────────────────
    schedules = [
        Schedule(
            camera_id=cam1_id,
            name="Business Hours",
            start_time="08:00",
            end_time="18:00",
            days_of_week=json.dumps(["Mon", "Tue", "Wed", "Thu", "Fri"]),
        ),
    ]
    db.add_all(schedules)

    # ── Default SOPs (one per real detection event type) ───────────────────
    sops = [
        SOP(
            incident_type="restricted_zone_entry",
            title="Restricted Zone Entry",
            steps_text=(
                "1. Confirm the zone and camera on the incident detail view.\n"
                "2. Dispatch the nearest responder to verify in person.\n"
                "3. Check the simulated access-authorization log for a matching badge event.\n"
                "4. If unauthorized, escalate to the on-duty supervisor.\n"
                "5. Package evidence before resolving."
            ),
        ),
        SOP(
            incident_type="after_hours_presence",
            title="After-Hours Presence",
            steps_text=(
                "1. Verify the zone's configured schedule is current.\n"
                "2. Attempt radio/phone contact with any known personnel on site.\n"
                "3. Dispatch a responder if presence is unconfirmed after 5 minutes.\n"
                "4. Log the outcome and resolve with a disposition."
            ),
        ),
        SOP(
            incident_type="loitering",
            title="Loitering",
            steps_text=(
                "1. Review the live feed for context (waiting, distress, suspicious activity).\n"
                "2. If benign, acknowledge and monitor.\n"
                "3. If concerning, dispatch a responder.\n"
                "4. Resolve with a disposition once the person has left or been engaged."
            ),
        ),
        SOP(
            incident_type="camera_offline",
            title="Camera Offline",
            steps_text=(
                "1. Check physical power/network to the camera or its host device.\n"
                "2. Attempt a manual restart from Configuration.\n"
                "3. If unresolved within 15 minutes, log a maintenance ticket.\n"
                "4. Note the outage window when resolving, for audit continuity."
            ),
        ),
        SOP(
            incident_type="camera_frozen",
            title="Frozen Feed",
            steps_text=(
                "1. Compare the live tile to a known-recent frame for movement.\n"
                "2. Restart the camera source from Configuration.\n"
                "3. If frozen recurs, flag the camera for hardware inspection."
            ),
        ),
        SOP(
            incident_type="camera_blackout",
            title="Covered / Blackout Camera",
            steps_text=(
                "1. Treat as a potential tamper event — dispatch a responder immediately.\n"
                "2. Check for physical obstruction or lens covering on arrival.\n"
                "3. Restore the feed and confirm clear visibility before resolving.\n"
                "4. Escalate to admin if tampering is confirmed."
            ),
        ),
    ]
    db.add_all(sops)

    db.commit()
    logger.info(
        f"Seeded: {len(users)} users, {len(cameras)} cameras, "
        f"{len(zones)} zones, {len(schedules)} schedules, {len(sops)} SOPs."
    )
