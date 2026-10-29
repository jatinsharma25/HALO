"""
backend/hardware/tracking_config.py

All configurable parameters for the Arduino pan-and-tilt tracking system.
Every value is readable from an environment variable so no hardware constant
is hard-coded in the source.

Serial port format:
  - Windows:  "COM3", "COM4", etc.
  - Linux:    "/dev/ttyACM0", "/dev/ttyUSB0", etc.

Tuning notes
------------
Start with the conservative defaults.  Once basic movement is confirmed:

1. Pan/tilt gains (PAN_GAIN, TILT_GAIN):
   - Too low  → camera responds sluggishly; target drifts to frame edge.
   - Too high → camera oscillates around the target (hunting).
   - Typical working range: 0.01 – 0.05 degrees/pixel.

2. Dead zones (DEAD_ZONE_X_PX, DEAD_ZONE_Y_PX):
   - Prevent constant micro-movements from detection jitter.
   - Widen if servos are buzzing while target is stationary.

3. EMA alpha (EMA_ALPHA):
   - 0.0 = ignore current measurement entirely (never converges).
   - 1.0 = no smoothing (noisy).
   - 0.3 – 0.5 is a reasonable starting range.

4. Command rate (COMMAND_RATE_HZ):
   - Physical servo response time limits useful rate to ~10-20 Hz.
   - Higher rates do not improve tracking and waste serial bandwidth.

5. Angle limits (MIN/MAX_PAN, MIN/MAX_TILT):
   - Measure mechanical stops physically before enabling autonomous tracking.
   - Cable twist: on a typical bracket the cable can handle ±60° from centre
     before starting to bind.  Start tighter (30°–150° for pan).
"""
import os

# ── Serial connection ────────────────────────────────────────────────────────
SERIAL_PORT: str = os.getenv("EYESPY_SERIAL_PORT", "COM3")
BAUD_RATE: int = int(os.getenv("EYESPY_BAUD_RATE", "115200"))
SERIAL_TIMEOUT_S: float = float(os.getenv("EYESPY_SERIAL_TIMEOUT", "1.0"))

# ── Servo hardware pins (ESP32 GPIO / Arduino digital pin numbers) ───────────
# ESP32 defaults: GPIO 18 (Pan), GPIO 19 (Tilt) - safe non-strapping, non-SPI-flash pins.
# (If using legacy Arduino Uno: set EYESPY_PAN_PIN=9, EYESPY_TILT_PIN=10)
PAN_SERVO_PIN: int = int(os.getenv("EYESPY_PAN_PIN", "18"))
TILT_SERVO_PIN: int = int(os.getenv("EYESPY_TILT_PIN", "19"))

# ── Initial / neutral position (degrees) ─────────────────────────────────────
INITIAL_PAN: float = float(os.getenv("EYESPY_INITIAL_PAN", "90"))
INITIAL_TILT: float = float(os.getenv("EYESPY_INITIAL_TILT", "90"))

# ── Mechanical travel limits (degrees) ───────────────────────────────────────
# Conservative defaults.  Measure your actual bracket before widening these.
MIN_PAN: float = float(os.getenv("EYESPY_MIN_PAN", "30"))
MAX_PAN: float = float(os.getenv("EYESPY_MAX_PAN", "150"))
MIN_TILT: float = float(os.getenv("EYESPY_MIN_TILT", "45"))
MAX_TILT: float = float(os.getenv("EYESPY_MAX_TILT", "135"))

# ── Dead zone (pixels on the 1280×720 frame) ─────────────────────────────────
# No command is sent when the target centre is within this rectangle around
# the frame centre.  Prevents buzzing from detection noise.
DEAD_ZONE_X_PX: int = int(os.getenv("EYESPY_DEAD_ZONE_X", "40"))
DEAD_ZONE_Y_PX: int = int(os.getenv("EYESPY_DEAD_ZONE_Y", "30"))

# ── Proportional gains (degrees per pixel of error) ──────────────────────────
PAN_GAIN: float = float(os.getenv("EYESPY_PAN_GAIN", "0.025"))
TILT_GAIN: float = float(os.getenv("EYESPY_TILT_GAIN", "0.025"))

# ── Maximum angular step per update (degrees) ─────────────────────────────────
# Hard cap on each command's change from the last position.  Prevents a single
# large detection jump (e.g. after target loss) from slewing the camera hard.
MAX_PAN_STEP: float = float(os.getenv("EYESPY_MAX_PAN_STEP", "5.0"))
MAX_TILT_STEP: float = float(os.getenv("EYESPY_MAX_TILT_STEP", "5.0"))

# ── Exponential moving average smoothing ─────────────────────────────────────
# filtered = alpha * current + (1 - alpha) * previous
# Higher alpha = faster response, less smoothing.
EMA_ALPHA: float = float(os.getenv("EYESPY_EMA_ALPHA", "0.4"))

# ── Command rate ──────────────────────────────────────────────────────────────
COMMAND_RATE_HZ: float = float(os.getenv("EYESPY_COMMAND_RATE_HZ", "10.0"))

# ── Target selection ──────────────────────────────────────────────────────────
# Confidence threshold: detections below this are ignored for tracking
# (but still appear in the surveillance pipeline).
CONF_THRESHOLD: float = float(os.getenv("EYESPY_CONF_THRESHOLD", "0.5"))

# "largest" → track the person with the biggest bounding-box area.
# "nearest_center" → track the person closest to the frame centre.
TARGET_SELECTION_POLICY: str = os.getenv("EYESPY_TARGET_POLICY", "largest")

# Seconds without a valid detection before the tracker declares target lost.
TARGET_LOSS_TIMEOUT_S: float = float(os.getenv("EYESPY_TARGET_LOSS_TIMEOUT", "2.0"))

# ── Behaviour flags ────────────────────────────────────────────────────────────
# Tracking is off by default; the operator must explicitly enable it.
TRACKING_ENABLED_DEFAULT: bool = False

# Whether to return to the home position on target loss (True) or hold last
# position (False).  Hold is safer if the cable is short — returning home
# might twist the cable if the camera has rotated far from centre.
RETURN_HOME_ON_LOSS: bool = os.getenv("EYESPY_RETURN_HOME_ON_LOSS", "false").lower() == "true"

# ── Arduino firmware watchdog ─────────────────────────────────────────────────
# The firmware stops accepting movement commands after this many milliseconds
# without a valid SET command.  Must be >= (1000 / COMMAND_RATE_HZ) * 3 to
# avoid spurious timeouts on a healthy connection.
FIRMWARE_WATCHDOG_MS: int = int(os.getenv("EYESPY_WATCHDOG_MS", "3000"))
