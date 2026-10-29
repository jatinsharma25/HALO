"""
backend/hardware/tracking_controller.py

Autonomous pan-and-tilt camera tracking controller.

Algorithm (proportional control with EMA smoothing):
  1. Poll VideoSource for the latest tracked objects (set by DetectionPipeline).
  2. Select a target person (largest bbox or continuity with existing track_id).
  3. Calculate pixel error from frame centre.
  4. Apply dead zone — skip update if error is small.
  5. Apply EMA smoothing to the error signal.
  6. Scale error to angular correction via configurable gains.
  7. Clamp to maximum step size and absolute angle limits.
  8. Send to ArduinoController (non-blocking; rate-limited inside controller).
  9. On target loss, hold position and eventually report lost state.

Sign conventions (VERIFY with your physical mount):
  - error_x > 0  → target is to the RIGHT of centre → increase pan angle.
  - error_y > 0  → target is BELOW centre           → increase tilt angle.
  If the camera moves in the wrong direction, negate the gain (negative value).

Threading:
  TrackingController runs in its own daemon thread.
  It shares _camera_id with the calling API thread — protected by _lock.
  VideoSource access is already thread-safe (VideoSource._lock).
  ArduinoController access is thread-safe (ArduinoController._lock).
"""
import logging
import threading
import time
from enum import Enum
from typing import Optional

from backend.hardware import tracking_config as cfg
from backend.hardware.arduino_controller import ArduinoController
from backend.pipeline.video_source import FRAME_WIDTH, FRAME_HEIGHT

logger = logging.getLogger(__name__)


class TrackingState(str, Enum):
    IDLE        = "idle"           # tracking disabled
    TRACKING    = "tracking"       # target found and being followed
    TARGET_LOST = "target_lost"    # was tracking, target disappeared
    ERROR       = "error"          # hardware error


class TrackingController:
    """
    Controls one pan-and-tilt rig for one camera.

    Lifecycle:
        tc = TrackingController(arduino)
        tc.set_camera(camera_id, video_source)
        tc.start()
        ...
        tc.stop()
    """

    FRAME_W = FRAME_WIDTH
    FRAME_H = FRAME_HEIGHT

    def __init__(self, arduino: ArduinoController):
        self._arduino = arduino
        self._lock = threading.Lock()

        # Camera currently being tracked (set by API)
        self._camera_id: Optional[int] = None
        self._video_source = None   # VideoSource | None

        # Current servo positions
        self._current_pan: float = cfg.INITIAL_PAN
        self._current_tilt: float = cfg.INITIAL_TILT

        # Tracking state
        self._state = TrackingState.IDLE
        self._enabled = False
        self._target_track_id: Optional[str] = None
        self._last_detection_ts: float = 0.0

        # EMA filter state for error signal
        self._filtered_error_x: float = 0.0
        self._filtered_error_y: float = 0.0

        # Thread
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        """Start the background tracking loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name="tracking-controller",
            daemon=True,
        )
        self._thread.start()
        logger.info("TrackingController: started")

    def stop(self):
        """Stop the background loop and release camera association."""
        self._running = False
        with self._lock:
            self._enabled = False
            self._state = TrackingState.IDLE
            self._camera_id = None
            self._video_source = None
            self._target_track_id = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        logger.info("TrackingController: stopped")

    # ── Camera association ────────────────────────────────────────────────────

    def set_camera(self, camera_id: int, video_source) -> None:
        """Associate a running VideoSource with this controller.

        Tracking does not start automatically — call enable() separately.
        """
        with self._lock:
            if self._camera_id != camera_id:
                # Switching cameras: clear per-camera state.
                self._target_track_id = None
                self._filtered_error_x = 0.0
                self._filtered_error_y = 0.0
            self._camera_id = camera_id
            self._video_source = video_source
        logger.info("TrackingController: associated with camera %d", camera_id)

    def clear_camera(self, camera_id: int) -> None:
        """Disassociate a specific camera (called when that camera stops)."""
        with self._lock:
            if self._camera_id == camera_id:
                self._enabled = False
                self._state = TrackingState.IDLE
                self._camera_id = None
                self._video_source = None
                self._target_track_id = None
                logger.info("TrackingController: cleared camera %d", camera_id)

    # ── Enable / disable ──────────────────────────────────────────────────────

    def enable(self) -> None:
        with self._lock:
            if self._video_source is None:
                raise RuntimeError("No camera associated — call set_camera() first")
            if not self._arduino.connected:
                raise RuntimeError("Arduino not connected — call arduino.connect() first")
            self._enabled = True
            self._state = TrackingState.TARGET_LOST
            self._target_track_id = None
            self._filtered_error_x = 0.0
            self._filtered_error_y = 0.0
            self._last_detection_ts = 0.0
        logger.info("TrackingController: enabled")

    def disable(self) -> None:
        with self._lock:
            self._enabled = False
            self._state = TrackingState.IDLE
            self._target_track_id = None
        logger.info("TrackingController: disabled")

    # ── Manual positioning ────────────────────────────────────────────────────

    def go_home(self) -> tuple[float, float]:
        """Move to the configured home position. Fails if tracking is active."""
        with self._lock:
            if self._enabled:
                raise RuntimeError("Disable tracking before issuing a home command")
        self._send(cfg.INITIAL_PAN, cfg.INITIAL_TILT, force=True)
        return (cfg.INITIAL_PAN, cfg.INITIAL_TILT)

    def manual_move(self, pan: float, tilt: float) -> tuple[float, float]:
        """Move to an explicit position. Rejected if tracking is active."""
        with self._lock:
            if self._enabled:
                raise RuntimeError("Disable tracking before issuing manual commands")
        pan_c = float(max(cfg.MIN_PAN, min(cfg.MAX_PAN, pan)))
        tilt_c = float(max(cfg.MIN_TILT, min(cfg.MAX_TILT, tilt)))
        self._send(pan_c, tilt_c, force=True)
        return (pan_c, tilt_c)

    # ── Status ───────────────────────────────────────────────────────────────

    def status_dict(self) -> dict:
        with self._lock:
            return {
                "enabled": self._enabled,
                "state": self._state.value,
                "camera_id": self._camera_id,
                "target_track_id": self._target_track_id,
                "pan": round(self._current_pan, 1),
                "tilt": round(self._current_tilt, 1),
            }

    # ── Background loop ───────────────────────────────────────────────────────

    def _loop(self):
        interval = 1.0 / max(cfg.COMMAND_RATE_HZ, 1.0)
        while self._running:
            try:
                self._tick()
            except Exception:
                logger.exception("TrackingController: unexpected error in tick")
            time.sleep(interval)

    def _tick(self):
        with self._lock:
            if not self._enabled or self._video_source is None:
                return
            video_source = self._video_source

        # Fetch latest tracking candidates (thread-safe via VideoSource._lock)
        candidates = video_source.get_tracking_candidates()
        now = time.monotonic()

        if not candidates:
            # No persons detected this cycle.
            elapsed_since_seen = now - self._last_detection_ts if self._last_detection_ts else float("inf")
            with self._lock:
                if self._state == TrackingState.TRACKING:
                    if elapsed_since_seen > cfg.TARGET_LOSS_TIMEOUT_S:
                        self._state = TrackingState.TARGET_LOST
                        self._target_track_id = None
                        logger.info("TrackingController: target lost")
            return

        # Select target from available candidates
        with self._lock:
            target_id = self._target_track_id

        target_info = self._select_target(candidates, target_id)
        if target_info is None:
            return

        selected_id, info = target_info
        self._last_detection_ts = now

        with self._lock:
            self._target_track_id = selected_id
            self._state = TrackingState.TRACKING

        # Calculate error in pixels from frame centre
        bbox = info["bbox"]
        x1, y1, x2, y2 = bbox
        target_cx = (x1 + x2) / 2.0
        target_cy = (y1 + y2) / 2.0
        frame_cx = self.FRAME_W / 2.0
        frame_cy = self.FRAME_H / 2.0

        error_x = target_cx - frame_cx  # positive → target is right of centre
        error_y = target_cy - frame_cy  # positive → target is below centre

        # Apply dead zone
        if abs(error_x) < cfg.DEAD_ZONE_X_PX and abs(error_y) < cfg.DEAD_ZONE_Y_PX:
            logger.debug("TrackingController: within dead zone (%.1f, %.1f)", error_x, error_y)
            return

        # Apply EMA smoothing
        with self._lock:
            self._filtered_error_x = (
                cfg.EMA_ALPHA * error_x + (1 - cfg.EMA_ALPHA) * self._filtered_error_x
            )
            self._filtered_error_y = (
                cfg.EMA_ALPHA * error_y + (1 - cfg.EMA_ALPHA) * self._filtered_error_y
            )
            fx = self._filtered_error_x
            fy = self._filtered_error_y
            cur_pan = self._current_pan
            cur_tilt = self._current_tilt

        # Proportional correction (degrees)
        pan_delta = cfg.PAN_GAIN * fx
        tilt_delta = cfg.TILT_GAIN * fy

        # Clamp to maximum step
        pan_delta = max(-cfg.MAX_PAN_STEP, min(cfg.MAX_PAN_STEP, pan_delta))
        tilt_delta = max(-cfg.MAX_TILT_STEP, min(cfg.MAX_TILT_STEP, tilt_delta))

        # New target angles
        new_pan = cur_pan + pan_delta
        new_tilt = cur_tilt + tilt_delta

        # Clamp to physical limits
        new_pan = max(cfg.MIN_PAN, min(cfg.MAX_PAN, new_pan))
        new_tilt = max(cfg.MIN_TILT, min(cfg.MAX_TILT, new_tilt))

        logger.debug(
            "TrackingController: err=(%.1f, %.1f) → pan=%.1f tilt=%.1f",
            fx, fy, new_pan, new_tilt,
        )

        self._send(new_pan, new_tilt)

    def _select_target(self, candidates: dict, current_track_id: Optional[str]) -> Optional[tuple[str, dict]]:
        """Select the best tracking target from the candidate dict.

        Priority:
          1. Maintain the current track_id if it is still visible.
          2. Otherwise apply the configured fallback policy.

        Args:
            candidates: objects_info dict from CentroidTracker.
            current_track_id: The track ID currently being followed (or None).

        Returns:
            (track_id, info_dict) or None if no valid target exists.
        """
        if not candidates:
            return None

        # Maintain continuity with existing target
        if current_track_id and current_track_id in candidates:
            return (current_track_id, candidates[current_track_id])

        # Fallback selection
        policy = cfg.TARGET_SELECTION_POLICY
        if policy == "nearest_center":
            cx = self.FRAME_W / 2.0
            cy = self.FRAME_H / 2.0
            best_id = min(
                candidates,
                key=lambda tid: (
                    (candidates[tid]["centroid"][0] - cx) ** 2 +
                    (candidates[tid]["centroid"][1] - cy) ** 2
                ),
            )
        else:
            # Default: largest bounding box area
            best_id = max(
                candidates,
                key=lambda tid: (
                    (candidates[tid]["bbox"][2] - candidates[tid]["bbox"][0]) *
                    (candidates[tid]["bbox"][3] - candidates[tid]["bbox"][1])
                ),
            )

        return (best_id, candidates[best_id])

    def _send(self, pan: float, tilt: float, force: bool = False) -> None:
        """Send angles to the Arduino and update current position cache."""
        if force:
            # Bypass rate-limit / duplicate check in ArduinoController by
            # temporarily clearing its last-position memory.
            self._arduino._last_pan = None
            self._arduino._last_tilt = None

        ok = self._arduino.send_angles(pan, tilt)
        if ok:
            with self._lock:
                self._current_pan = pan
                self._current_tilt = tilt
        elif not self._arduino.connected:
            with self._lock:
                self._state = TrackingState.ERROR
            logger.error("TrackingController: Arduino disconnected during tracking")


# ── Process-level singleton ──────────────────────────────────────────────────

_controller: Optional[TrackingController] = None
_arduino: Optional[ArduinoController] = None
_singleton_lock = threading.Lock()


def get_arduino() -> ArduinoController:
    """Return the process-level ArduinoController singleton (creates on first call)."""
    global _arduino
    with _singleton_lock:
        if _arduino is None:
            _arduino = ArduinoController(
                port=cfg.SERIAL_PORT,
                baud_rate=cfg.BAUD_RATE,
                timeout_s=cfg.SERIAL_TIMEOUT_S,
                min_command_interval_s=1.0 / (cfg.COMMAND_RATE_HZ * 2),
            )
        return _arduino


def get_tracking_controller() -> TrackingController:
    """Return the process-level TrackingController singleton (creates and starts on first call)."""
    global _controller
    with _singleton_lock:
        if _controller is None:
            _controller = TrackingController(get_arduino())
            _controller.start()
        return _controller


def shutdown_hardware() -> None:
    """Stop the tracking controller and disconnect the Arduino. Called at app shutdown."""
    global _controller, _arduino
    with _singleton_lock:
        if _controller is not None:
            _controller.stop()
            _controller = None
        if _arduino is not None:
            _arduino.disconnect()
            _arduino = None
    logger.info("Hardware subsystem shut down")
