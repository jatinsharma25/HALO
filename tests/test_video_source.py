"""
tests/test_video_source.py
Unit tests for VideoSource — no real video file needed.
Uses mocked OpenCV capture.
"""
import time
import cv2
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from backend.pipeline.video_source import VideoSource, SourceState, FRAME_WIDTH, FRAME_HEIGHT
from backend.detection.camera_health import MIN_SAMPLES_FOR_FROZEN_VERDICT
from backend.config import FROZEN_WINDOW_SECONDS


def make_frame(brightness: int = 128, noisy: bool = False, seed: int = 0) -> np.ndarray:
    """Return a BGR frame at roughly `brightness`. Real camera frames always
    carry sensor noise/texture; a perfectly flat np.full() frame has zero
    variance, which CameraHealthMonitor's blackout check (brightness < X OR
    stddev < Y) reads as covered regardless of brightness — so tests standing
    in for a normal, non-blackout frame need `noisy=True`.

    Independent per-pixel noise isn't enough: the monitor downsamples to
    160x90 before computing variance (an exact 8x8 block reduction at this
    frame size), which averages white noise down to near-zero. Instead this
    builds noise as 8x8-pixel blocks, so it survives that downsample intact."""
    if not noisy:
        return np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), brightness, dtype=np.uint8)
    rng = np.random.default_rng(seed)
    small = np.clip(brightness + rng.integers(-60, 61, size=(90, 160)), 0, 255).astype(np.uint8)
    gray = cv2.resize(small, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


@pytest.fixture
def mock_cap():
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.read.return_value = (True, make_frame(128))
    return cap


# ── Construction ─────────────────────────────────────────────────────────────

def test_initial_state():
    src = VideoSource(camera_id=42, source_uri="test.mp4")
    assert src.state == SourceState.IDLE
    assert src.camera_id == 42
    assert src.get_frame() is None


# ── start() / stop() ─────────────────────────────────────────────────────────

def test_start_success(mock_cap):
    with patch("cv2.VideoCapture", return_value=mock_cap):
        src = VideoSource(camera_id=1, source_uri="test.mp4")
        ok = src.start()
        assert ok
        assert src.state == SourceState.ACTIVE
        assert src._running
        src.stop()
        assert src.state == SourceState.STOPPED


def test_start_failure():
    bad_cap = MagicMock()
    bad_cap.isOpened.return_value = False
    with patch("cv2.VideoCapture", return_value=bad_cap):
        src = VideoSource(camera_id=2, source_uri="nonexistent.mp4")
        ok = src.start()
        assert not ok
        assert src.state == SourceState.OFFLINE


def test_double_start_noop(mock_cap):
    with patch("cv2.VideoCapture", return_value=mock_cap):
        src = VideoSource(camera_id=3, source_uri="test.mp4")
        ok1 = src.start()
        ok2 = src.start()   # should be noop
        assert ok1 and ok2
        src.stop()


# ── Reconnection ────────────────────────────────────────────────────────────
# Without this, a source whose reads start failing (dropped RTSP connection,
# some webcam drivers under sustained near-darkness) never recovers — the old
# reader loop just kept calling .read() on the same broken handle forever.

def test_resolve_uri_webcam_index_vs_path():
    assert VideoSource(camera_id=1, source_uri="0")._resolve_uri() == 0
    assert VideoSource(camera_id=2, source_uri="rtsp://cam/live")._resolve_uri() == "rtsp://cam/live"


def test_reconnect_releases_old_capture_and_opens_new_one():
    old_cap = MagicMock()
    new_cap = MagicMock()
    new_cap.isOpened.return_value = True

    src = VideoSource(camera_id=40, source_uri="0")
    src._cap = old_cap

    with patch("cv2.VideoCapture", return_value=new_cap) as mock_ctor:
        ok = src._reconnect()

    assert ok
    old_cap.release.assert_called_once()
    mock_ctor.assert_called_once_with(0)   # "0" resolved to the int webcam index
    assert src._cap is new_cap


def test_reconnect_reports_failure_without_raising():
    old_cap = MagicMock()
    still_broken_cap = MagicMock()
    still_broken_cap.isOpened.return_value = False

    src = VideoSource(camera_id=41, source_uri="0")
    src._cap = old_cap

    with patch("cv2.VideoCapture", return_value=still_broken_cap):
        ok = src._reconnect()

    assert not ok
    assert src._cap is still_broken_cap   # still swapped in, just not open — next attempt reopens fresh


# ── Health assessment ─────────────────────────────────────────────────────────

def test_assess_health_active():
    src = VideoSource(camera_id=10, source_uri="x")
    frame = make_frame(128, noisy=True)
    state = src._assess_health(frame)
    assert state == SourceState.ACTIVE


def test_assess_health_blackout():
    src = VideoSource(camera_id=11, source_uri="x")
    dark_frame = make_frame(3)   # well below brightness threshold even with no noise
    state = src._assess_health(dark_frame)
    assert state == SourceState.BLACKOUT


def test_assess_health_frozen():
    src = VideoSource(camera_id=12, source_uri="x")
    frame = make_frame(100, noisy=True)   # same frame reused every tick -> zero diff

    # The frozen verdict is time-windowed (FROZEN_WINDOW_SECONDS), not a frame
    # count, so wall-clock time is faked to advance a full window without an
    # actual multi-second sleep.
    fake_now = [1_000_000.0]
    with patch("backend.detection.camera_health.time.time", lambda: fake_now[0]):
        state = None
        for _ in range(MIN_SAMPLES_FOR_FROZEN_VERDICT + 2):
            state = src._assess_health(frame)
            fake_now[0] += FROZEN_WINDOW_SECONDS / MIN_SAMPLES_FOR_FROZEN_VERDICT

    assert state == SourceState.FROZEN


def test_assess_health_no_freeze_on_motion():
    src = VideoSource(camera_id=13, source_uri="x")
    fake_now = [2_000_000.0]
    with patch("backend.detection.camera_health.time.time", lambda: fake_now[0]):
        state = None
        for i in range(40):
            # Alternate brightness to simulate motion between frames
            frame = make_frame(100 + (i % 2) * 50, noisy=True, seed=i)
            state = src._assess_health(frame)
            fake_now[0] += FROZEN_WINDOW_SECONDS / MIN_SAMPLES_FOR_FROZEN_VERDICT
    assert state != SourceState.FROZEN


# ── Annotated frame ──────────────────────────────────────────────────────────

def test_set_and_get_annotated_frame(mock_cap):
    with patch("cv2.VideoCapture", return_value=mock_cap):
        src = VideoSource(camera_id=20, source_uri="test.mp4")
        src.start()
        time.sleep(0.1)   # let reader thread tick at least once

        annotated = make_frame(200)
        src.set_annotated_frame(annotated)
        got = src.get_annotated_frame()
        assert got is not None
        assert got.shape == annotated.shape
        src.stop()


# ── Status dict ──────────────────────────────────────────────────────────────

def test_status_dict(mock_cap):
    with patch("cv2.VideoCapture", return_value=mock_cap):
        src = VideoSource(camera_id=30, source_uri="rtsp://cam")
        src.start()
        d = src.status_dict()
        assert d["camera_id"] == 30
        assert d["source_uri"] == "rtsp://cam"
        assert "state" in d
        assert "fps" in d
        src.stop()
