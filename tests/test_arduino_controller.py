"""
tests/test_arduino_controller.py

Unit tests for ArduinoController with mocked serial interface.
Tests:
  - Command serialization and line termination
  - Rate limiting behavior
  - Duplicate command suppression
  - Reconnection state reset (stale command prevention)
  - Handling of firmware error responses
  - Safe disconnection and error recovery
"""
import time
from unittest.mock import MagicMock, patch
import pytest

from backend.hardware.arduino_controller import ArduinoController


@pytest.fixture
def mock_serial():
    with patch("backend.hardware.arduino_controller._SERIAL_AVAILABLE", True), \
         patch("backend.hardware.arduino_controller.serial.Serial") as mock_ser_cls:
        instance = MagicMock()
        instance.in_waiting = 0
        instance.readline.return_value = b"OK\n"
        mock_ser_cls.return_value = instance
        yield instance


def test_connect_and_disconnect(mock_serial):
    ctrl = ArduinoController(port="COM_TEST", baud_rate=115200)
    assert not ctrl.connected

    assert ctrl.connect() is True
    assert ctrl.connected is True
    assert ctrl.port == "COM_TEST"

    ctrl.disconnect()
    assert not ctrl.connected
    mock_serial.close.assert_called_once()


def test_command_serialization(mock_serial):
    ctrl = ArduinoController(port="COM_TEST", min_command_interval_s=0.0)
    ctrl.connect()

    success = ctrl.send_angles(90.4, 45.1)
    assert success is True

    # Check written payload: rounded to integers, SET prefix, LF termination
    mock_serial.write.assert_called_once_with(b"SET,90,45\n")
    mock_serial.flush.assert_called_once()


def test_duplicate_command_suppression(mock_serial):
    ctrl = ArduinoController(port="COM_TEST", min_command_interval_s=0.0)
    ctrl.connect()

    # First send
    assert ctrl.send_angles(90, 90) is True
    assert mock_serial.write.call_count == 1

    # Immediate duplicate send should be suppressed
    assert ctrl.send_angles(90, 90) is False
    assert mock_serial.write.call_count == 1

    # Different angle should send
    assert ctrl.send_angles(91, 90) is True
    assert mock_serial.write.call_count == 2


def test_rate_limiting(mock_serial):
    # Set minimum interval to 100ms (10 Hz)
    ctrl = ArduinoController(port="COM_TEST", min_command_interval_s=0.1)
    ctrl.connect()

    assert ctrl.send_angles(90, 90) is True
    # Immediately sending a different angle within 100ms should be rejected
    assert ctrl.send_angles(95, 95) is False

    # After interval elapses, sending should succeed
    time.sleep(0.11)
    assert ctrl.send_angles(95, 95) is True


def test_reconnection_clears_stale_angles(mock_serial):
    ctrl = ArduinoController(port="COM_TEST", min_command_interval_s=0.0)
    ctrl.connect()
    ctrl.send_angles(90, 90)
    assert ctrl.status_dict()["last_pan"] == 90

    # Disconnect and reconnect
    ctrl.disconnect()
    ctrl.connect()

    # After reconnect, sending 90, 90 must NOT be treated as a duplicate
    # because the physical servo state might have changed or reset
    assert ctrl.send_angles(90, 90) is True


def test_send_fails_when_disconnected():
    ctrl = ArduinoController(port="COM_TEST")
    assert ctrl.send_angles(90, 90) is False


def test_firmware_error_handling(mock_serial):
    mock_serial.in_waiting = 10
    mock_serial.readline.return_value = b"ERR:angle_out_of_range\n"

    ctrl = ArduinoController(port="COM_TEST", min_command_interval_s=0.0)
    ctrl.connect()
    ctrl.send_angles(185, 90)

    status = ctrl.status_dict()
    assert status["error_count"] > 0


def test_write_exception_triggers_disconnect(mock_serial):
    mock_serial.write.side_effect = OSError("Serial write failed")

    ctrl = ArduinoController(port="COM_TEST", min_command_interval_s=0.0)
    ctrl.connect()
    assert ctrl.connected is True

    # Attempt send
    assert ctrl.send_angles(80, 80) is False
    # Controller must mark itself disconnected to prevent infinite blocking
    assert ctrl.connected is False
