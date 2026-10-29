"""
backend/pipeline/video_source.py

VideoSource owns one OpenCV capture (MP4 path, webcam int, or RTSP URL).
It runs a dedicated reader thread that keeps the latest frame fresh.
Thread-safe: callers use get_frame() / get_annotated_frame().
"""
import cv2
import threading
import time
import logging
from datetime import datetime
from enum import Enum
from typing import Optional
import numpy as np

from backend.detection.camera_health import CameraHealthMonitor

logger = logging.getLogger(__name__)

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720


class SourceState(str, Enum):
    IDLE = "idle"           # created, not started
    ACTIVE = "active"       # reading frames normally
    OFFLINE = "offline"     # cap.read() failed / source unreachable
    FROZEN = "frozen"       # frames arriving but pixel-identical (camera tamper)
    BLACKOUT = "blackout"   # frame is nearly all black (lens blocked)
    BLURRED = "blurred"     # frame is in focus range too low (lens smudged/defocused)
    STOPPED = "stopped"     # explicitly stopped


class VideoSource:
    """
    Manages a single video source.

    Usage:
        src = VideoSource(camera_id=1, source_uri="test.mp4")
        src.start()
        frame = src.get_frame()
        src.stop()
    """

    def __init__(self, camera_id: int, source_uri: str):
        self.camera_id = camera_id
        self.source_uri = source_uri

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._raw_frame: Optional[np.ndarray] = None          # latest decoded frame
        self._annotated_frame: Optional[np.ndarray] = None    # latest annotated frame (set by pipeline)
        # Latest YOLO person boxes, [x1,y1,x2,y2] pixel ints on the raw frame
        # (set by DetectionPipeline). Reused for privacy redaction — blurring
        # the whole detected person is far more reliable than running a
        # separate face detector on CCTV footage (oblique angles, distance,
        # low resolution all defeat Haar face cascades routinely).
        self._person_boxes: list = []

        # Latest tracking candidates: objects_info dict from CentroidTracker.
        # Set by DetectionPipeline._process_frame(); consumed by TrackingController.
        # Keys are str(int) track IDs; values are the full info dicts including bbox.
        # Thread-safe via the same _lock as _raw_frame.
        self._tracking_candidates: dict = {}

        self.state = SourceState.IDLE
        self._running = False

        self._last_frame_time: Optional[datetime] = None
        self._health_monitor = CameraHealthMonitor()

        # stats exposed to API
        self.fps_actual: float = 0.0
        self._frame_count: int = 0
        self._fps_ts: float = 0.0

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Open capture and start reader thread. Returns True on success."""
        if self._running:
            return True

        self._cap = cv2.VideoCapture(self._resolve_uri())
        if not self._cap.isOpened():
            logger.error("Camera %d: failed to open source '%s'", self.camera_id, self.source_uri)
            self.state = SourceState.OFFLINE
            return False

        self._running = True
        self.state = SourceState.ACTIVE
        self._fps_ts = time.monotonic()

        self._thread = threading.Thread(
            target=self._reader_loop,
            name=f"vsrc-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("Camera %d started (%s)", self.camera_id, self.source_uri)
        return True

    def stop(self):
        """Stop reader thread and release capture."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()
            self._cap = None
        self.state = SourceState.STOPPED
        logger.info("Camera %d stopped", self.camera_id)

    def _resolve_uri(self):
        """Integer index for a webcam, else the string path/URL as-is."""
        try:
            return int(self.source_uri)
        except (ValueError, TypeError):
            return self.source_uri

    def _reconnect(self) -> bool:
        """Release and reopen the capture. Returns True if it reopened.
        Without this, a source that starts failing reads (a dropped RTSP
        connection, or some webcam drivers under sustained near-total
        darkness during a lens-covered/blackout test) never recovers — the
        old loop just kept calling .read() on the same broken handle
        forever, even after the underlying problem cleared."""
        if self._cap:
            self._cap.release()
        self._cap = cv2.VideoCapture(self._resolve_uri())
        return self._cap.isOpened()

    # ── Frame access ─────────────────────────────────────────────────────────

    def get_frame(self) -> Optional[np.ndarray]:
        """Return latest raw frame (copy), or None if not available."""
        with self._lock:
            return self._raw_frame.copy() if self._raw_frame is not None else None

    def set_annotated_frame(self, frame: np.ndarray):
        """Called by DetectionPipeline to store the annotated frame."""
        with self._lock:
            self._annotated_frame = frame.copy()

    def get_annotated_frame(self) -> Optional[np.ndarray]:
        """Return latest annotated frame for MJPEG streaming."""
        with self._lock:
            if self._annotated_frame is not None:
                return self._annotated_frame.copy()
            # Fall back to raw if pipeline hasn't annotated yet
            return self._raw_frame.copy() if self._raw_frame is not None else None

    def set_person_boxes(self, boxes: list):
        """Called by DetectionPipeline each frame with the current YOLO person boxes."""
        with self._lock:
            self._person_boxes = list(boxes)

    def get_person_boxes(self) -> list:
        """Latest known person boxes, for redaction. May be one frame stale
        relative to get_frame() — acceptable since boxes are blurred with a
        margin and people don't move far in ~33ms."""
        with self._lock:
            return list(self._person_boxes)

    def set_tracking_candidates(self, objects_info: dict) -> None:
        """Called by DetectionPipeline after the tracker runs.

        Stores the full objects_info dict (track_id → {bbox, centroid, ...})
        so the TrackingController can read it without touching the pipeline.
        Thread-safe via _lock.
        """
        with self._lock:
            self._tracking_candidates = dict(objects_info)

    def get_tracking_candidates(self) -> dict:
        """Return the latest objects_info dict for the tracking controller.

        Returns an empty dict if detection has not run yet or the camera
        is not active.  May be up to one detection interval stale (~200ms
        at the default DETECTION_TARGET_FPS=5).
        """
        with self._lock:
            return dict(self._tracking_candidates)

    # ── Reader loop ──────────────────────────────────────────────────────────

    RECONNECT_BACKOFF_SECONDS = 5   # minimum gap between reopen attempts while failing

    def _reader_loop(self):
        last_reconnect_attempt = 0.0
        while self._running:
            ret, frame = self._cap.read()

            if not ret:
                # MP4: rewind; live source (webcam/RTSP): mark offline and
                # periodically try reopening the capture until it recovers.
                if isinstance(self.source_uri, str) and self.source_uri.endswith((".mp4", ".avi", ".mov")):
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                self.state = SourceState.OFFLINE
                now = time.monotonic()
                if now - last_reconnect_attempt >= self.RECONNECT_BACKOFF_SECONDS:
                    last_reconnect_attempt = now
                    logger.warning("Camera %d: read failed — attempting reconnect", self.camera_id)
                    if self._reconnect():
                        logger.info("Camera %d: reconnected", self.camera_id)
                    else:
                        logger.warning("Camera %d: reconnect failed, will retry", self.camera_id)
                time.sleep(0.5)
                continue

            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
            health = self._assess_health(frame)

            with self._lock:
                self._raw_frame = frame
                self.state = health
                self._last_frame_time = datetime.utcnow()

            self._update_fps()
            time.sleep(0.033)   # ~30 fps cap

    def _assess_health(self, frame: np.ndarray) -> SourceState:
        """Check for blackout, freeze, or severe blur via CameraHealthMonitor
        (time-windowed, not a single-frame snapshot — see detection/camera_health.py)."""
        verdict = self._health_monitor.observe(frame)
        if verdict["blackout"]:
            return SourceState.BLACKOUT
        if verdict["frozen"]:
            return SourceState.FROZEN
        if verdict["blurred"]:
            return SourceState.BLURRED
        return SourceState.ACTIVE

    def _update_fps(self):
        self._frame_count += 1
        now = time.monotonic()
        elapsed = now - self._fps_ts
        if elapsed >= 2.0:
            self.fps_actual = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_ts = now

    # ── Status dict ──────────────────────────────────────────────────────────

    def status_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "source_uri": self.source_uri,
            "state": self.state.value,
            "fps": round(self.fps_actual, 1),
            "last_frame": self._last_frame_time.isoformat() if self._last_frame_time else None,
        }
