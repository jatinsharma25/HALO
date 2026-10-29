"""
backend/hardware/arduino_controller.py

Thread-safe serial communication with the Arduino servo controller.

Responsibilities:
  - Open and close the serial port.
  - Send validated pan/tilt commands in the agreed protocol.
  - Enforce command rate limiting so the serial buffer never fills.
  - Report connection health.
  - Handle disconnection and stale-command prevention after reconnection.
  - Never block the caller for longer than SERIAL_TIMEOUT_S.

Thread safety:
  All public methods acquire _lock before touching the serial port.
  The controller is designed to be called from the TrackingController
  thread only; the lock prevents accidental concurrent writes from
  any future callers.

Command protocol (see hardware/arduino/eyespy_servo_controller.ino):
  Outgoing: "SET,<pan>,<tilt>\\n"   e.g. "SET,90,90\\n"
  Incoming: "OK\\n"  or  "ERR:<reason>\\n"
"""
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import — pyserial is optional at import time so the application can
# start without an Arduino connected.  ArduinoController raises a clear
# error at connect() time if pyserial is absent.
try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False


class ArduinoController:
    """
    Manages a single serial connection to the Arduino servo controller.

    Usage:
        ctrl = ArduinoController(port="COM3", baud_rate=115200)
        ctrl.connect()
        ctrl.send_angles(pan=90, tilt=90)
        ctrl.disconnect()

    Calling send_angles() before connect() raises RuntimeError.
    Calling connect() twice on the same port is safe (no-op on second call).
    """

    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        timeout_s: float = 1.0,
        min_command_interval_s: float = 0.05,   # 20 Hz hard ceiling
    ):
        self._port = port
        self._baud_rate = baud_rate
        self._timeout_s = timeout_s
        self._min_interval = min_command_interval_s

        self._serial: Optional[object] = None   # serial.Serial when connected
        self._lock = threading.Lock()
        self._connected = False
        self._last_command_ts: float = 0.0
        self._last_pan: Optional[int] = None
        self._last_tilt: Optional[int] = None

        # Track connection errors for status reporting
        self._last_error: Optional[str] = None
        self._error_count: int = 0

    # ── Connection lifecycle ─────────────────────────────────────────────────

    def connect(self) -> bool:
        """Open the serial port.  Returns True on success.

        Raises RuntimeError if pyserial is not installed.
        On connection failure, logs the error and returns False so the caller
        can decide whether to retry.
        """
        if not _SERIAL_AVAILABLE:
            raise RuntimeError(
                "pyserial is not installed.  "
                "Run: pip install pyserial>=3.5"
            )

        with self._lock:
            if self._connected:
                return True

            try:
                self._serial = serial.Serial(
                    port=self._port,
                    baudrate=self._baud_rate,
                    timeout=self._timeout_s,
                    write_timeout=self._timeout_s,
                )
                # Arduino resets on DTR; wait for it to boot before sending.
                time.sleep(2.0)
                # Discard any garbage from the reset
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()

                # Clear stale position memory — after reconnect we don't know
                # where the servos actually are, so the first command must be
                # sent even if it matches the last cached position.
                self._last_pan = None
                self._last_tilt = None
                self._error_count = 0
                self._last_error = None
                self._connected = True
                logger.info("ArduinoController: connected to %s @ %d baud", self._port, self._baud_rate)
                return True

            except Exception as exc:
                self._last_error = str(exc)
                self._connected = False
                self._serial = None
                logger.error("ArduinoController: failed to connect to %s: %s", self._port, exc)
                return False

    def disconnect(self):
        """Close the serial port gracefully."""
        with self._lock:
            self._do_disconnect()

    def _do_disconnect(self):
        """Internal disconnect — must be called with _lock held."""
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception as exc:
                logger.warning("ArduinoController: error closing port: %s", exc)
        self._serial = None
        self._connected = False
        logger.info("ArduinoController: disconnected from %s", self._port)

    # ── Command sending ──────────────────────────────────────────────────────

    def send_angles(self, pan: float, tilt: float) -> bool:
        """Send a SET,<pan>,<tilt> command to the Arduino.

        Args:
            pan:  Desired pan angle in degrees (float; rounded to nearest int).
            tilt: Desired tilt angle in degrees (float; rounded to nearest int).

        Returns:
            True if the command was sent successfully (the Arduino may still
            report ERR — check logs for that).  False if not connected or if
            the command was rate-limited / identical to the previous one.

        This method does not block for more than SERIAL_TIMEOUT_S.  Serial
        errors mark the connection as broken and return False so the tracking
        controller can surface the error rather than silently losing commands.
        """
        pan_int = int(round(pan))
        tilt_int = int(round(tilt))

        with self._lock:
            if not self._connected or self._serial is None:
                return False

            # Rate limit: never exceed the configured command frequency.
            now = time.monotonic()
            elapsed = now - self._last_command_ts
            if elapsed < self._min_interval:
                return False

            # Duplicate suppression: skip if angles have not changed.
            if pan_int == self._last_pan and tilt_int == self._last_tilt:
                return False

            command = f"SET,{pan_int},{tilt_int}\n"
            try:
                self._serial.write(command.encode("ascii"))
                self._serial.flush()
                self._last_command_ts = now
                self._last_pan = pan_int
                self._last_tilt = tilt_int

                # Attempt non-blocking read of the response.
                response = self._read_response()
                if response and response.startswith("ERR"):
                    logger.warning("ArduinoController: firmware error: %s (cmd=%r)", response.strip(), command.strip())
                    self._error_count += 1
                else:
                    logger.debug("ArduinoController: sent %r → %s", command.strip(), response.strip() if response else "(no response)")
                return True

            except Exception as exc:
                self._last_error = str(exc)
                self._error_count += 1
                logger.error("ArduinoController: write error: %s", exc)
                # Mark disconnected so next send_angles() call skips immediately
                # and the tracking controller can report the error.
                self._do_disconnect()
                return False

    def _read_response(self) -> Optional[str]:
        """Non-blocking read of a single response line.

        Returns the line string, or None if no data is available within the
        serial read timeout.  Must be called with _lock held.
        """
        try:
            if self._serial.in_waiting:
                line = self._serial.readline()
                return line.decode("ascii", errors="replace")
        except Exception as exc:
            logger.debug("ArduinoController: read error: %s", exc)
        return None

    # ── Status ───────────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def port(self) -> str:
        return self._port

    def status_dict(self) -> dict:
        return {
            "connected": self._connected,
            "port": self._port,
            "baud_rate": self._baud_rate,
            "last_pan": self._last_pan,
            "last_tilt": self._last_tilt,
            "error_count": self._error_count,
            "last_error": self._last_error,
        }

    @staticmethod
    def list_ports() -> list[str]:
        """Return available serial port names (best-effort)."""
        if not _SERIAL_AVAILABLE:
            return []
        return [p.device for p in serial.tools.list_ports.comports()]
