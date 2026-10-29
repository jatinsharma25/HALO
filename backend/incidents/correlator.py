"""
backend/incidents/correlator.py

Auto-incident creation logic.

When a high-impact Observation arrives, we:
1. Compute a dedup_hash (camera + event_type + 5-minute bucket)
2. If an open incident with that hash exists → link observation to it
3. Else → create new Incident, link observation, write audit entry

This runs synchronously when called from the incidents router or
can be triggered from the detection pipeline.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Camera, Incident, IncidentObservation, Observation, Zone
from backend.audit.chain import audit_log
from backend.incidents.scoring import compute_confidence_score, compute_impact_score
from backend.incidents.explain import build_explanation

logger = logging.getLogger(__name__)

# Observations with impact >= this threshold auto-create incidents
AUTO_INCIDENT_THRESHOLD = 0.6

# Dedup window — same camera + event_type within this window = same incident
DEDUP_WINDOW_MINUTES = 5

# Our Observation.event_type values predate scoring.py/explain.py, which use
# slightly different keys (see incidents/scoring.py, incidents/explain.py) —
# this bridges the two without renaming either the stable DB enum or the
# already-tested scoring module.
EVENT_TYPE_TO_SCORING_KEY = {
    "restricted_zone_entry": "restricted_entry",
    "after_hours_presence": "after_hours",
    "loitering": "loitering",
    "camera_offline": "camera_offline",
    "camera_frozen": "camera_frozen",
    "camera_blackout": "camera_blackout",
    "camera_blur": "camera_blur",
    "fall_warning": "fall_warning",
    "abandoned_object_warning": "abandoned_object_warning",
    "fire_smoke_warning": "fire_smoke_warning",
    "line_crossing": "line_crossing",
    "crowd_threshold": "crowd_threshold",
}


def _bucket(ts: datetime) -> str:
    """5-minute time bucket string for dedup."""
    bucket_start = ts.replace(second=0, microsecond=0)
    bucket_start = bucket_start.replace(
        minute=(ts.minute // DEDUP_WINDOW_MINUTES) * DEDUP_WINDOW_MINUTES
    )
    return bucket_start.isoformat()


def _dedup_hash(camera_id: int, event_type: str, ts: datetime) -> str:
    raw = f"{camera_id}:{event_type}:{_bucket(ts)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def maybe_create_incident(
    db: Session,
    observation: Observation,
    actor_id: Optional[int] = None,
) -> Optional[Incident]:
    """
    Called after an Observation is written.
    Creates or updates an Incident if impact_score >= threshold.
    Returns the Incident (new or existing) or None if below threshold.
    """
    if observation.impact_score < AUTO_INCIDENT_THRESHOLD:
        return None

    dhash = _dedup_hash(observation.camera_id, observation.event_type, observation.timestamp)

    # Check for open incident with same dedup hash
    existing = (
        db.query(Incident)
        .filter(
            Incident.dedup_hash == dhash,
            Incident.status.in_(["new", "acknowledged", "investigating"]),
        )
        .first()
    )

    if existing:
        # Link observation to existing incident (if not already linked)
        already_linked = (
            db.query(IncidentObservation)
            .filter(
                IncidentObservation.incident_id == existing.id,
                IncidentObservation.observation_id == observation.id,
            )
            .first()
        )
        if not already_linked:
            link = IncidentObservation(
                incident_id=existing.id,
                observation_id=observation.id,
            )
            db.add(link)
            # Extend correlation window
            existing.correlation_window_end = observation.timestamp
            db.flush()
            score_incident(db, existing)
            db.commit()
            logger.debug("Observation %d linked to existing incident %d", observation.id, existing.id)
        return existing

    # New incident
    window_start = observation.timestamp
    window_end = observation.timestamp + timedelta(minutes=DEDUP_WINDOW_MINUTES)

    incident = Incident(
        status="new",
        dedup_hash=dhash,
        correlation_window_start=window_start,
        correlation_window_end=window_end,
    )
    db.add(incident)
    db.flush()   # get incident.id

    link = IncidentObservation(
        incident_id=incident.id,
        observation_id=observation.id,
    )
    db.add(link)
    db.flush()
    score_incident(db, incident)
    db.commit()

    audit_log(
        db,
        action="incident.auto_create",
        actor_id=actor_id,
        target_type="incident",
        target_id=incident.id,
        payload={
            "trigger_observation_id": observation.id,
            "event_type": observation.event_type,
            "camera_id": observation.camera_id,
            "impact_score": observation.impact_score,
        },
    )

    logger.info(
        "Auto-incident %d created (camera=%d event=%s impact=%.2f)",
        incident.id, observation.camera_id, observation.event_type, observation.impact_score,
    )
    return incident


# Mirrors DetectionPipeline.LOITERING_SECONDS — not imported directly since
# that module pulls in torch/cv2 at import time, which this lightweight,
# frequently-called path shouldn't have to carry.
DEFAULT_LOITERING_THRESHOLD_S = 120


def score_incident(db: Session, incident: Incident) -> None:
    """
    Recompute and persist impact_score, confidence_score, and explanation for
    an incident from all of its currently-linked observations. Deterministic:
    same linked observations always produce the same scores (incidents/scoring.py,
    incidents/explain.py) — no ML/LLM involved.
    """
    observations = (
        db.query(Observation)
        .join(IncidentObservation, IncidentObservation.observation_id == Observation.id)
        .filter(IncidentObservation.incident_id == incident.id)
        .order_by(Observation.timestamp.asc())
        .all()
    )
    if not observations:
        return

    first_obs = observations[0]
    scoring_key = EVENT_TYPE_TO_SCORING_KEY.get(first_obs.event_type, first_obs.event_type)
    observation_count = len(observations)
    avg_confidence = sum(o.confidence_score for o in observations) / observation_count

    camera = db.query(Camera).filter(Camera.id == first_obs.camera_id).first()
    camera_name = camera.name if camera else f"Camera {first_obs.camera_id}"
    camera_status = camera.status if camera else "unknown"

    zone_name = None
    threshold_seconds = None
    zoned_obs = next((o for o in observations if o.zone_id is not None), None)
    if zoned_obs is not None:
        zone = db.query(Zone).filter(Zone.id == zoned_obs.zone_id).first()
        if zone:
            zone_name = zone.name
            if scoring_key == "loitering":
                threshold_seconds = zone.loitering_threshold_s or DEFAULT_LOITERING_THRESHOLD_S

    # No simulated access-event subsystem exists yet (see README/spec item 14),
    # so this never reduces impact today — kept as an explicit parameter (not
    # hardcoded away) so wiring a real one later only means changing this line.
    access_event_matched = False

    first_ts = observations[0].timestamp.isoformat()
    last_ts = observations[-1].timestamp.isoformat()

    incident.impact_score = compute_impact_score(scoring_key, observation_count, access_event_matched)
    incident.confidence_score = compute_confidence_score(scoring_key, avg_confidence, observation_count, camera_status)
    incident.explanation = json.dumps(
        build_explanation(
            scoring_key,
            camera_name,
            zone_name,
            observation_count,
            first_ts,
            last_ts,
            avg_confidence,
            camera_status,
            access_event_matched,
            threshold_seconds,
        )
    )
