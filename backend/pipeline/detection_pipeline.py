"""
backend/pipeline/detection_pipeline.py

DetectionPipeline attaches to one VideoSource and runs the full
detection stack in a background thread:

  YOLO → CentroidTracker → ZoneAnalyzer → LineCounter
                                         ↓
                               write Observation rows
                                         ↓
                               push annotated frame → VideoSource

Privacy contract:
  - Redaction (blurring) is a display/evidence-layer concern, not done here —
    this only publishes person boxes (set_person_boxes) for the stream
    endpoint and evidence packager to blur against. No face data, detected or
    otherwise, ever touches the DB.
  - track_id is camera-local and rotates each session (no cross-camera linkage).
"""
import json
import logging
import threading
import time
import hashlib
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from backend.db.database import SessionLocal
from backend.db.models import Camera, Observation, Zone
from backend.modules.centroid_tracker import CentroidTracker
from backend.modules.zone_analyzer import ZoneAnalyzer
from backend.modules.line_counter import LineCounter
from backend.detection.fall_heuristic import FallHeuristic
from backend.detection.abandoned_object import AbandonedObjectHeuristic
from backend.detection.fire_smoke_heuristic import FireSmokeHeuristic
from backend.detection.crowd_heuristic import CrowdHeuristic
from backend.config import CROWD_COUNT_THRESHOLD, CROWD_SUSTAIN_SECONDS, DETECTION_TARGET_FPS
from .video_source import VideoSource, SourceState, FRAME_WIDTH, FRAME_HEIGHT

logger = logging.getLogger(__name__)

# Lazy YOLO import — avoids loading torch at module import time
_yolo_model = None
_yolo_lock = threading.Lock()


def _get_yolo():
    global _yolo_model
    with _yolo_lock:
        if _yolo_model is None:
            try:
                import torch
                from ultralytics import YOLO
                _yolo_model = YOLO("yolov8n.pt")
                if torch.cuda.is_available():
                    _yolo_model.to("cuda")
                    logger.info("YOLO loaded on CUDA")
                else:
                    logger.info("YOLO loaded on CPU")
            except Exception as exc:
                logger.error("Failed to load YOLO: %s", exc)
        return _yolo_model


class DetectionPipeline:
    """
    Runs detection for one camera in a daemon thread.

    Instantiate → call start() → call stop() when done.
    """

    CONFIDENCE_THRESHOLD = 0.5
    LOITERING_SECONDS = 120          # stationary this long = loitering event
    RESTRICTED_IMPACT = 0.9
    AFTER_HOURS_IMPACT = 0.7
    LOITERING_IMPACT = 0.5
    # Matches incidents/scoring.py's BASE_IMPACT/100 for these types — both are
    # classical-CV heuristics, not validated classifiers (see detection/fall_heuristic.py,
    # detection/abandoned_object.py), so confidence comes from the heuristic itself
    # (already capped low), not a fixed constant like the types above.
    FALL_IMPACT = 0.65
    ABANDONED_OBJECT_IMPACT = 0.35
    FIRE_SMOKE_IMPACT = 0.75
    # Deliberately low: a monitored line sees routine foot traffic constantly,
    # and there's no "wrong direction" policy config yet (no per-line
    # allowed-direction setting exists) — so crossings are logged for
    # analytics/audit rather than auto-creating an incident every time someone
    # walks through. Raise this (or add real directionality) if/when that
    # policy concept gets built.
    LINE_CROSSING_IMPACT = 0.2
    CROWD_IMPACT = 0.45

    def __init__(self, source: VideoSource, camera_db_id: int):
        self.source = source
        self.camera_db_id = camera_db_id

        # max_disappeared is counted in detection CALLS, not wall-clock time --
        # the original 50 was tuned assuming detection ran on every captured
        # frame (~15-18fps), i.e. a ~3s real-world dropout window. Now that
        # detection is throttled to DETECTION_TARGET_FPS, using 50 unscaled
        # would let a stale track linger ~3x longer in real time (fewer,
        # slower calls to reach the same count), which lets more simultaneous
        # tracks accumulate and makes the tracker's own O(tracks x detections)
        # distance-matrix step progressively more expensive the longer a
        # camera runs. Scaling keeps the same ~3s real dropout window
        # regardless of the throttle rate.
        _TRACK_DROPOUT_SECONDS = 3.0
        _max_disappeared = max(1, round(DETECTION_TARGET_FPS * _TRACK_DROPOUT_SECONDS))
        self._tracker = CentroidTracker(max_disappeared=_max_disappeared, max_distance=120)
        self._zone_analyzer = ZoneAnalyzer(FRAME_WIDTH, FRAME_HEIGHT)
        self._fall_heuristic = FallHeuristic()
        self._abandoned_object = AbandonedObjectHeuristic()
        self._fire_smoke = FireSmokeHeuristic()
        self._crowd = CrowdHeuristic(count_threshold=CROWD_COUNT_THRESHOLD, sustain_seconds=CROWD_SUSTAIN_SECONDS)

        line_y = FRAME_HEIGHT // 2
        self._line_counter = LineCounter(
            (100, line_y), (FRAME_WIDTH - 100, line_y)
        )

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Last Camera.status value written to the DB, so live health changes
        # (frozen/blackout/blurred/recovered) update the row the UI actually
        # reads without writing on every single frame.
        self._last_synced_status: Optional[str] = None
        self._last_blur_observation_ts: float = 0.0

        # Throttles the expensive full detection pass (YOLO + all heuristics)
        # to DETECTION_TARGET_FPS instead of running it on every captured
        # frame (previously every ~13-15fps frame from the reader thread) --
        # this was the single largest CPU cost in the pipeline. Frames in
        # between just pass the raw feed straight through, so the live view
        # stays fluid even though detection itself samples less often.
        self._last_detection_ts: float = 0.0
        self._detection_interval: float = (1.0 / DETECTION_TARGET_FPS) if DETECTION_TARGET_FPS > 0 else 0.0

        # DB-loaded zone polygons: list of (Zone.id, np.array of points, zone_type)
        self._zones: list = []
        # zone_id -> per-zone loitering threshold override (seconds); zones with
        # none set are absent here, so callers fall back to LOITERING_SECONDS.
        self._zone_loitering_threshold: dict = {}
        self._load_zones()

        # Schedules (after-hours detection)
        self._schedules: list = []
        self._load_schedules()

        # Dedup: track which (track_id, event_type) we already filed this session
        self._filed_events: set = set()

    # ── Startup / shutdown ───────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name=f"pipeline-{self.camera_db_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("DetectionPipeline started for camera %d", self.camera_db_id)

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("DetectionPipeline stopped for camera %d", self.camera_db_id)

    # ── Main loop ────────────────────────────────────────────────────────────

    def _loop(self):
        yolo = _get_yolo()
        consecutive_errors = 0

        while self._running:
            if self.source.state == SourceState.STOPPED:
                break

            # Hard anomalies: no usable frame to detect anything in, so
            # normal processing is skipped entirely.
            if self.source.state in (SourceState.OFFLINE, SourceState.FROZEN, SourceState.BLACKOUT):
                event_map = {
                    SourceState.OFFLINE: "camera_offline",
                    SourceState.FROZEN: "camera_frozen",
                    SourceState.BLACKOUT: "camera_blackout",
                }
                self._sync_camera_status(self.source.state.value)
                self._write_observation(
                    track_id="system",
                    event_type=event_map[self.source.state],
                    zone_id=None,
                    confidence=1.0,
                    impact=1.0,
                    explanation=f"Camera health anomaly: {self.source.state.value}",
                    metadata={},
                )
                time.sleep(10)   # don't spam DB on sustained anomaly
                continue

            # Blur is a quality *warning*, not a "nothing to see" state like
            # the anomalies above — a blurry frame can still contain a
            # detectable person, so detection keeps running through it.
            if self.source.state == SourceState.BLURRED:
                self._sync_camera_status("blurred")
                self._maybe_write_blur_observation()
            else:
                self._sync_camera_status("active")

            frame = self.source.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            now = time.time()
            if now - self._last_detection_ts < self._detection_interval:
                # Below the target detection rate -- pass the raw frame
                # straight through instead of paying for YOLO + every
                # heuristic again this tick. The tracker/heuristics only
                # ever see genuinely-elapsed-time-apart samples this way,
                # so their own sustain/cooldown timers (measured in wall
                # time, not frame count) stay correct regardless.
                self.source.set_annotated_frame(frame)
                time.sleep(0.01)
                continue

            try:
                logger.warning("TEMP_DEBUG_DETECTION_TICK cam=%d", self.camera_db_id)
                annotated = self._process_frame(frame, yolo)
                self.source.set_annotated_frame(annotated)
                self._last_detection_ts = now
                consecutive_errors = 0
            except Exception:
                consecutive_errors += 1
                logger.exception("Pipeline error cam %d", self.camera_db_id)
                if consecutive_errors > 10:
                    logger.critical("Pipeline cam %d: too many errors, stopping", self.camera_db_id)
                    # Without this, the camera keeps showing whatever status
                    # it last had (often "active") forever, even though
                    # detection has silently died -- indistinguishable from
                    # a healthy camera until someone notices no new
                    # incidents are coming from it.
                    self._sync_camera_status("offline")
                    break
                time.sleep(1)

    # ── Frame processing ─────────────────────────────────────────────────────

    def _process_frame(self, frame: np.ndarray, yolo) -> np.ndarray:
        annotated = frame.copy()
        timestamp = datetime.utcnow()
        is_after_hours = self._check_after_hours(timestamp)

        # ── YOLO detection ───────────────────────────────────────────────────
        person_boxes = []
        if yolo is not None:
            try:
                import supervision as sv
                results = yolo(frame, verbose=False)[0]
                detections = sv.Detections.from_ultralytics(results)
                mask = (detections.class_id == 0) & (detections.confidence > self.CONFIDENCE_THRESHOLD)
                person_detections = detections[mask]
                person_boxes = person_detections.xyxy.astype(int).tolist()
            except Exception as exc:
                logger.debug("YOLO inference error: %s", exc)

        # Published for redaction (stream display-layer blur + evidence
        # clips) — blurring the whole detected person, not a separately
        # detected face, since that's what we can actually detect reliably.
        self.source.set_person_boxes(person_boxes)

        # ── Tracker update ───────────────────────────────────────────────────
        objects_info = self._tracker.update(person_boxes)

        # Publish tracking candidates for the hardware tracking controller.
        # This is a thread-safe write to VideoSource and adds no meaningful
        # latency.  The tracking controller reads this independently.
        self.source.set_tracking_candidates(objects_info)

        # ── Per-person analysis ───────────────────────────────────────────────
        for track_id_str, info in objects_info.items():
            centroid = info["centroid"]
            bbox = info["bbox"]
            x1, y1, x2, y2 = bbox

            # Draw bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(annotated, (int(centroid[0]), int(centroid[1])), 5, (0, 255, 0), -1)
            cv2.putText(annotated, f"ID:{track_id_str}", (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            # Zone checks
            hit_zone_id, hit_zone_type = self._zone_hit(centroid)

            if hit_zone_type == "restricted":
                self._maybe_file(
                    track_id=track_id_str,
                    event_type="restricted_zone_entry",
                    zone_id=hit_zone_id,
                    confidence=0.85,
                    impact=self.RESTRICTED_IMPACT,
                    explanation=f"Person entered restricted zone (zone_id={hit_zone_id})",
                    metadata={"centroid": centroid, "bbox": bbox, "frame_w": FRAME_WIDTH, "frame_h": FRAME_HEIGHT},
                )
                cv2.putText(annotated, "RESTRICTED ZONE", (x1, y1 - 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)

            if is_after_hours and len(objects_info) > 0:
                self._maybe_file(
                    track_id=track_id_str,
                    event_type="after_hours_presence",
                    zone_id=hit_zone_id,
                    confidence=0.9,
                    impact=self.AFTER_HOURS_IMPACT,
                    explanation="Person detected outside scheduled hours",
                    metadata={"centroid": centroid},
                )

            # Loitering — per-zone threshold overrides the global default.
            if info.get("is_stationary"):
                last_seen = datetime.fromisoformat(info["last_seen"])
                dwell = (timestamp - last_seen).total_seconds()
                loitering_threshold = self._zone_loitering_threshold.get(hit_zone_id, self.LOITERING_SECONDS)
                if dwell >= loitering_threshold:
                    self._maybe_file(
                        track_id=track_id_str,
                        event_type="loitering",
                        zone_id=hit_zone_id,
                        confidence=0.75,
                        impact=self.LOITERING_IMPACT,
                        explanation=f"Person stationary for {int(dwell)}s",
                        metadata={"dwell_seconds": int(dwell), "centroid": centroid},
                    )
                    cv2.putText(annotated, f"LOITER {int(dwell)}s",
                                (int(centroid[0]) - 40, int(centroid[1]) + 35),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)

        # ── Fall/collapse heuristic (low-confidence, human verification required) ──
        now_ts = time.time()
        for event in self._fall_heuristic.evaluate(objects_info, now_ts):
            x1, y1, x2, y2 = event["bbox"]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 100, 255), 3)
            cv2.putText(annotated, f"POSSIBLE FALL {int(event['dwell_seconds'])}s", (x1, max(0, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 100, 255), 2)
            if event["emit"]:
                track_info = objects_info.get(event["track_id"], {})
                zone_id, _ = self._zone_hit(track_info["centroid"]) if track_info.get("centroid") else (None, None)
                self._write_observation(
                    track_id=str(event["track_id"]),
                    event_type="fall_warning",
                    zone_id=zone_id,
                    confidence=event["confidence"],
                    impact=self.FALL_IMPACT,
                    explanation=f"Possible fall/collapse — bounding box flat for {int(event['dwell_seconds'])}s",
                    metadata={"bbox": event["bbox"], "dwell_seconds": event["dwell_seconds"]},
                )

        # ── Abandoned-object heuristic (low-confidence, human verification required) ──
        person_boxes_frac = [
            [x1 / FRAME_WIDTH, y1 / FRAME_HEIGHT, x2 / FRAME_WIDTH, y2 / FRAME_HEIGHT]
            for x1, y1, x2, y2 in person_boxes
        ]
        for event in self._abandoned_object.evaluate(frame, person_boxes_frac, now_ts):
            bx1, by1, bx2, by2 = event["bbox"]
            px1, py1, px2, py2 = int(bx1 * FRAME_WIDTH), int(by1 * FRAME_HEIGHT), int(bx2 * FRAME_WIDTH), int(by2 * FRAME_HEIGHT)
            cv2.rectangle(annotated, (px1, py1), (px2, py2), (0, 200, 255), 2)
            cv2.putText(annotated, f"STATIC OBJECT {int(event['dwell_seconds'])}s", (px1, max(0, py1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 2)
            if event["emit"]:
                zone_id, _ = self._zone_hit(((px1 + px2) / 2, (py1 + py2) / 2))
                self._write_observation(
                    track_id="system",
                    event_type="abandoned_object_warning",
                    zone_id=zone_id,
                    confidence=event["confidence"],
                    impact=self.ABANDONED_OBJECT_IMPACT,
                    explanation=f"Static object left in place for {int(event['dwell_seconds'])}s, not overlapping any tracked person",
                    metadata={"bbox": [px1, py1, px2, py2], "dwell_seconds": event["dwell_seconds"]},
                )

        # ── Fire/smoke heuristic (least reliable in the system — HSV color-range
        # + sustained-area only, never a standalone automatic alarm) ──────────────
        for event in self._fire_smoke.evaluate(frame, now_ts):
            bx1, by1, bx2, by2 = event["bbox"]
            px1, py1, px2, py2 = int(bx1 * FRAME_WIDTH), int(by1 * FRAME_HEIGHT), int(bx2 * FRAME_WIDTH), int(by2 * FRAME_HEIGHT)
            cv2.rectangle(annotated, (px1, py1), (px2, py2), (0, 140, 255), 2)
            cv2.putText(annotated, f"POSSIBLE FIRE/SMOKE {int(event['dwell_seconds'])}s", (px1, max(0, py1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 2)
            if event["emit"]:
                zone_id, _ = self._zone_hit(((px1 + px2) / 2, (py1 + py2) / 2))
                self._write_observation(
                    track_id="system",
                    event_type="fire_smoke_warning",
                    zone_id=zone_id,
                    confidence=event["confidence"],
                    impact=self.FIRE_SMOKE_IMPACT,
                    explanation=f"Sustained flame-like color region detected for {int(event['dwell_seconds'])}s",
                    metadata={"bbox": [px1, py1, px2, py2], "dwell_seconds": event["dwell_seconds"]},
                )

        # ── Line counter ──────────────────────────────────────────────────────
        # Detection still runs every frame — only the on-screen line was removed,
        # since it's a persistent visual overlay across the camera view rather
        # than a rare/temporary alert marker like the other heuristics above.
        crossing_events = self._line_counter.update(objects_info)
        for ev in crossing_events:
            track_info = objects_info.get(str(ev["object_id"]), {})
            centroid = track_info.get("centroid")
            zone_id, _ = self._zone_hit(centroid) if centroid else (None, None)
            self._write_observation(
                track_id=str(ev["object_id"]),
                event_type="line_crossing",
                zone_id=zone_id,
                confidence=0.85,
                impact=self.LINE_CROSSING_IMPACT,
                explanation=f"Person crossed the monitored line ({ev['direction']})",
                metadata={"direction": ev["direction"]},
            )

        # ── Crowd heuristic (reliable headcount, not a fuzzy CV inference) ──────
        crowd_event = self._crowd.evaluate(len(objects_info), now_ts)
        if crowd_event:
            cv2.putText(annotated, f"CROWD: {crowd_event['person_count']} people ({int(crowd_event['dwell_seconds'])}s)",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            if crowd_event["emit"]:
                self._write_observation(
                    track_id="system",
                    event_type="crowd_threshold",
                    zone_id=None,
                    confidence=crowd_event["confidence"],
                    impact=self.CROWD_IMPACT,
                    explanation=f"Person count reached {crowd_event['person_count']}, sustained for {int(crowd_event['dwell_seconds'])}s",
                    metadata={"person_count": crowd_event["person_count"], "dwell_seconds": crowd_event["dwell_seconds"]},
                )

        # ── Zone overlay ──────────────────────────────────────────────────────
        for zone_id, pts, zone_type in self._zones:
            color = (0, 0, 200) if zone_type == "restricted" else (0, 200, 100)
            cv2.polylines(annotated, [pts], isClosed=True, color=color, thickness=2)

        # ── HUD ───────────────────────────────────────────────────────────────
        self._draw_hud(annotated, timestamp, len(objects_info), is_after_hours)

        return annotated

    # ── Zone / schedule helpers ───────────────────────────────────────────────

    def _zone_hit(self, centroid) -> tuple[Optional[int], Optional[str]]:
        """Return (zone_id, zone_type) if centroid is inside any loaded zone, else (None, None)."""
        pt = (float(centroid[0]), float(centroid[1]))
        for zone_id, pts, zone_type in self._zones:
            if cv2.pointPolygonTest(pts, pt, measureDist=False) >= 0:
                return zone_id, zone_type
        return None, None

    def _check_after_hours(self, ts: datetime) -> bool:
        """True if current time falls outside all schedules for this camera."""
        if not self._schedules:
            return False  # no schedule = always monitored, never after-hours
        current_day = ts.strftime("%a")  # Mon, Tue, …
        current_time = ts.strftime("%H:%M")
        for sched in self._schedules:
            days = json.loads(sched["days_of_week"])
            if current_day in days:
                if sched["start_time"] <= current_time <= sched["end_time"]:
                    return False  # inside a valid schedule window
        return True  # outside all windows

    def _load_zones(self):
        """Load polygon zones from DB for this camera."""
        try:
            db = SessionLocal()
            zones = db.query(Zone).filter(Zone.camera_id == self.camera_db_id).all()
            self._zones = [
                (
                    z.id,
                    np.array(json.loads(z.polygon_points), dtype=np.int32),
                    z.zone_type,
                )
                for z in zones
            ]
            self._zone_loitering_threshold = {
                z.id: z.loitering_threshold_s for z in zones if z.loitering_threshold_s is not None
            }
            db.close()
            logger.info("Camera %d: loaded %d zones", self.camera_db_id, len(self._zones))
        except Exception as exc:
            logger.error("Camera %d: failed to load zones: %s", self.camera_db_id, exc)

    def _load_schedules(self):
        """Load schedules from DB for this camera."""
        try:
            from backend.db.models import Schedule
            db = SessionLocal()
            scheds = db.query(Schedule).filter(Schedule.camera_id == self.camera_db_id).all()
            self._schedules = [
                {
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "days_of_week": s.days_of_week,
                }
                for s in scheds
            ]
            db.close()
        except Exception as exc:
            logger.error("Camera %d: failed to load schedules: %s", self.camera_db_id, exc)

    # ── DB write helpers ─────────────────────────────────────────────────────

    def _maybe_file(self, track_id: str, event_type: str, **kwargs):
        """
        Write an Observation only once per (track_id, event_type) per session.
        Loitering is re-filed every 60s after the first filing.
        """
        key = f"{track_id}:{event_type}"
        if event_type == "loitering":
            # Re-file every 60 s
            ts_key = f"{key}:ts"
            last_filed = self._filed_events_ts().get(ts_key, 0)
            if time.monotonic() - last_filed < 60:
                return
            self._loiter_ts[ts_key] = time.monotonic()
        else:
            if key in self._filed_events:
                return
            self._filed_events.add(key)
        self._write_observation(track_id=track_id, event_type=event_type, **kwargs)

    # ugly but avoids extra class attr
    _loiter_ts: dict = {}

    def _filed_events_ts(self):
        return self._loiter_ts

    def _write_observation(
        self,
        track_id: str,
        event_type: str,
        zone_id: Optional[int],
        confidence: float,
        impact: float,
        explanation: str,
        metadata: dict,
    ):
        try:
            db = SessionLocal()
            obs = Observation(
                camera_id=self.camera_db_id,
                track_id=track_id,
                event_type=event_type,
                timestamp=datetime.utcnow(),
                zone_id=zone_id,
                confidence_score=round(min(max(confidence, 0.0), 1.0), 4),
                impact_score=round(min(max(impact, 0.0), 1.0), 4),
                explanation=explanation,
                raw_metadata=json.dumps(metadata) if metadata else None,
            )
            db.add(obs)
            db.commit()
            db.refresh(obs)
            logger.debug(
                "Observation written: cam=%d track=%s event=%s",
                self.camera_db_id, track_id, event_type,
            )
            # Auto-create incident if impact is high enough (Phase 3)
            incident = None
            try:
                from backend.incidents.correlator import maybe_create_incident
                incident = maybe_create_incident(db, obs)
            except Exception as corr_exc:
                logger.error("Correlator error: %s", corr_exc)

            try:
                from backend.alerts.alert_manager import get_alert_manager
                get_alert_manager().publish_alert({
                    "observation_id": obs.id,
                    "camera_id": obs.camera_id,
                    "event_type": obs.event_type,
                    "confidence_score": obs.confidence_score,
                    "impact_score": obs.impact_score,
                    "timestamp": obs.timestamp.isoformat(),
                    "incident_id": incident.id if incident else None,
                })
            except Exception as ws_exc:
                logger.error("Alert broadcast error: %s", ws_exc)
        except Exception as exc:
            logger.error("Failed to write observation: %s", exc)
        finally:
            db.close()

    def _sync_camera_status(self, new_status: str):
        """Write the live health state to Camera.status — without this, the
        DB row (what the UI's camera list actually reads) only ever changed
        on manual start/stop and never reflected a live frozen/blackout/blur
        condition."""
        if new_status == self._last_synced_status:
            return
        try:
            db = SessionLocal()
            cam = db.query(Camera).filter(Camera.id == self.camera_db_id).first()
            if cam is not None:
                cam.status = new_status
                db.commit()
                self._last_synced_status = new_status
        except Exception as exc:
            logger.error("Camera %d: status sync failed: %s", self.camera_db_id, exc)
        finally:
            db.close()

    def _maybe_write_blur_observation(self):
        """File a camera_blur observation at most once per 10s while the
        health check keeps reporting blur — detection itself is not gated on
        this (see _loop), so it just needs to not spam the DB every frame."""
        now = time.time()
        if now - self._last_blur_observation_ts < 10:
            return
        self._last_blur_observation_ts = now
        self._write_observation(
            track_id="system",
            event_type="camera_blur",
            zone_id=None,
            confidence=1.0,
            impact=1.0,
            explanation="Camera health anomaly: blurred",
            metadata={},
        )

    # ── HUD overlay ──────────────────────────────────────────────────────────

    def _draw_hud(self, frame, ts: datetime, count: int, after_hours: bool):
        h, w = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (8, h - 90), (360, h - 8), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

        lines = [
            ts.strftime("%Y-%m-%d  %H:%M:%S UTC"),
            f"People: {count}   In:{self._line_counter.entry_count} Out:{self._line_counter.exit_count}",
            ("AFTER HOURS" if after_hours else "In-schedule"),
        ]
        colors = [(255, 255, 255), (255, 255, 255), (0, 80, 255) if after_hours else (100, 255, 100)]
        for i, (txt, col) in enumerate(zip(lines, colors)):
            cv2.putText(frame, txt, (14, h - 70 + i * 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
