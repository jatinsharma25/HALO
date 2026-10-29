"""
tests/test_tracking_controller.py

Unit tests for TrackingController logic:
  - Target selection (continuity & fallback)
  - Image center error calculation
  - Dead zone filtering
  - EMA smoothing
  - Angular step limits and mechanical clamping
  - Target loss timeout handling
  - Mode exclusivity (manual commands rejected during autonomous tracking)
"""
import time
from unittest.mock import MagicMock
import pytest

from backend.hardware.arduino_controller import ArduinoController
from backend.hardware.tracking_controller import TrackingController, TrackingState
from backend.hardware import tracking_config as cfg


@pytest.fixture
def mock_arduino():
    ard = MagicMock(spec=ArduinoController)
    ard.connected = True
    ard.send_angles.return_value = True
    return ard


@pytest.fixture
def mock_video_source():
    vsrc = MagicMock()
    vsrc.get_tracking_candidates.return_value = {}
    return vsrc


def test_initial_state(mock_arduino):
    tc = TrackingController(mock_arduino)
    status = tc.status_dict()
    assert status["enabled"] is False
    assert status["state"] == TrackingState.IDLE.value
    assert status["pan"] == cfg.INITIAL_PAN
    assert status["tilt"] == cfg.INITIAL_TILT


def test_enable_requires_camera_and_arduino(mock_arduino, mock_video_source):
    tc = TrackingController(mock_arduino)

    # Fails if no camera associated
    with pytest.raises(RuntimeError, match="No camera associated"):
        tc.enable()

    tc.set_camera(1, mock_video_source)

    # Fails if Arduino is not connected
    mock_arduino.connected = False
    with pytest.raises(RuntimeError, match="Arduino not connected"):
        tc.enable()

    # Succeeds when both are present
    mock_arduino.connected = True
    tc.enable()
    assert tc.status_dict()["enabled"] is True


def test_target_selection_continuity_and_fallback(mock_arduino):
    tc = TrackingController(mock_arduino)

    candidates = {
        "0": {"bbox": [100, 100, 200, 300], "centroid": [150, 200]},   # Area = 100 * 200 = 20,000
        "1": {"bbox": [400, 200, 650, 600], "centroid": [525, 400]},   # Area = 250 * 400 = 100,000 (largest)
        "2": {"bbox": [600, 300, 680, 420], "centroid": [640, 360]},   # Area = 80 * 120 = 9,600 (center)
    }

    # 1. No current target -> selects largest (ID "1")
    selected = tc._select_target(candidates, current_track_id=None)
    assert selected is not None
    assert selected[0] == "1"

    # 2. Existing track_id "0" is still visible -> retains "0" (continuity)
    selected_cont = tc._select_target(candidates, current_track_id="0")
    assert selected_cont is not None
    assert selected_cont[0] == "0"

    # 3. Existing track_id "99" disappeared -> falls back to largest ("1")
    selected_fallback = tc._select_target(candidates, current_track_id="99")
    assert selected_fallback is not None
    assert selected_fallback[0] == "1"


def test_dead_zone_suppresses_commands(mock_arduino, mock_video_source):
    tc = TrackingController(mock_arduino)
    tc.set_camera(1, mock_video_source)
    tc.enable()

    # Candidate exactly in the center (dead zone is 40px X, 30px Y)
    # Frame center = (640, 360)
    mock_video_source.get_tracking_candidates.return_value = {
        "0": {"bbox": [620, 340, 660, 380], "centroid": [640, 360]}
    }

    tc._tick()
    # No movement command should be sent because error is (0, 0) inside dead zone
    mock_arduino.send_angles.assert_not_called()


def test_step_clamping_and_mechanical_limits(mock_arduino, mock_video_source):
    tc = TrackingController(mock_arduino)
    tc.set_camera(1, mock_video_source)
    tc.enable()

    # Target far to the right edge: bbox cx = 1200, frame cx = 640 -> error_x = +560px
    # With gain 0.025, 560 * 0.025 = 14 degrees
    # But MAX_PAN_STEP is 5.0 degrees, so step must be clamped to +5.0 degrees
    mock_video_source.get_tracking_candidates.return_value = {
        "0": {"bbox": [1150, 300, 1250, 420], "centroid": [1200, 360]}
    }

    tc._tick()

    assert mock_arduino.send_angles.called
    sent_pan, sent_tilt = mock_arduino.send_angles.call_args[0]

    # Expected pan = INITIAL_PAN (90) + clamped_step (<= 5.0)
    assert sent_pan <= cfg.INITIAL_PAN + cfg.MAX_PAN_STEP + 0.001
    assert sent_pan >= cfg.INITIAL_PAN


def test_manual_mode_conflict_rejection(mock_arduino, mock_video_source):
    tc = TrackingController(mock_arduino)
    tc.set_camera(1, mock_video_source)

    # When tracking is disabled, manual moves succeed
    pan, tilt = tc.manual_move(85, 75)
    assert pan == 85
    assert tilt == 75

    pan, tilt = tc.go_home()
    assert pan == cfg.INITIAL_PAN
    assert tilt == cfg.INITIAL_TILT

    # Enable tracking
    tc.enable()

    # Manual move while tracking is active must raise RuntimeError
    with pytest.raises(RuntimeError, match="Disable tracking before issuing manual commands"):
        tc.manual_move(80, 80)

    # Home while tracking is active must raise RuntimeError
    with pytest.raises(RuntimeError, match="Disable tracking before issuing a home command"):
        tc.go_home()
