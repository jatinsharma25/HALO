/*
  EyeSpy Servo Controller — Arduino firmware
  hardware/arduino/eyespy_servo_controller.ino

  Controls a two-axis pan-and-tilt rig via standard hobby servos.

  ─── Protocol ────────────────────────────────────────────────────────────────
  Baud rate : 115200
  Command   : "SET,<pan>,<tilt>\n"   (ASCII integers, LF-terminated)
  Response  : "OK\n"                 (success)
              "ERR:<reason>\n"       (failure; command ignored)

  Angle ranges accepted:   0–180 degrees (firmware limits are tighter — see
                           constants below).  Python enforces its own limits
                           before sending; the firmware enforces them again
                           as a safety net.

  ─── Watchdog ────────────────────────────────────────────────────────────────
  If no valid SET command arrives within WATCHDOG_MS milliseconds, the firmware
  stops responding to movement commands and sends "ERR:watchdog\n" once.
  The servos remain at their last commanded position (safest choice for a
  camera on a bracket — returning to home could wrap a short cable).
  The watchdog resets on the next valid command.

  ─── Wiring ──────────────────────────────────────────────────────────────────
  Pan servo  signal → Arduino pin 9   (configurable: PAN_PIN)
  Tilt servo signal → Arduino pin 10  (configurable: TILT_PIN)
  Servo power → external 5–6 V supply (NOT Arduino 5V pin)
  Servo GND   → Arduino GND  (common ground required)

  ─── MG996R servo notes ──────────────────────────────────────────────────────
  Typical wire colours (verify against your specific unit's datasheet):
    Brown  = GND
    Red    = VCC (5–6 V from external supply)
    Orange = Signal (PWM from Arduino pin)
  Some manufacturers use Black/Red/White or Black/Red/Yellow instead.
  ALWAYS verify before connecting power.

  ─── Safety notes ────────────────────────────────────────────────────────────
  • Angle limits in this file must be set conservatively before first run.
  • Measure mechanical end-stops with power off before enabling tracking.
  • Do not allow the servo to stall at an end-stop — it will overheat.
  • Ensure the USB/camera cable has enough slack for the full range of motion.
  • Keep hands clear of the moving bracket during tests.
*/

#if defined(ESP32) || defined(ARDUINO_ARCH_ESP32)
  #include <ESP32Servo.h>
  const int PAN_PIN  = 18;  // ESP32 safe PWM GPIO
  const int TILT_PIN = 19;  // ESP32 safe PWM GPIO
#else
  #include <Servo.h>
  const int PAN_PIN  = 9;   // Arduino Uno PWM pin
  const int TILT_PIN = 10;  // Arduino Uno PWM pin
#endif

// ── Initial / home position ───────────────────────────────────────────────────
const int HOME_PAN  = 90;
const int HOME_TILT = 90;

// ── Firmware-enforced angle limits ────────────────────────────────────────────
// These are the ABSOLUTE hardware limits.  Tracking software enforces its own
// tighter limits on top of these.  Widen only after verifying mechanical travel.
const int MIN_PAN  = 30;
const int MAX_PAN  = 150;
const int MIN_TILT = 45;
const int MAX_TILT = 135;

// ── Watchdog ──────────────────────────────────────────────────────────────────
// Milliseconds without a valid command before the watchdog fires.
const unsigned long WATCHDOG_MS = 3000;

// ── Serial protocol constants ─────────────────────────────────────────────────
const int   BAUD_RATE   = 115200;
const int   MAX_CMD_LEN = 24;     // "SET,180,180\n" = 14 chars; keep generous
const char  CMD_PREFIX[] = "SET,";

// ── State ─────────────────────────────────────────────────────────────────────
Servo panServo;
Servo tiltServo;

char     inputBuffer[MAX_CMD_LEN];
int      bufferPos     = 0;
bool     watchdogFired = false;
unsigned long lastValidCmd = 0;   // millis() of last accepted SET command

// Current commanded positions (for status / debugging)
int currentPan  = HOME_PAN;
int currentTilt = HOME_TILT;


// ── Helpers ───────────────────────────────────────────────────────────────────

/** Clamp val to [lo, hi]. */
int clamp(int val, int lo, int hi) {
  if (val < lo) return lo;
  if (val > hi) return hi;
  return val;
}

/** Move both servos to the specified angles (pre-validated). */
void moveServos(int pan, int tilt) {
  currentPan  = pan;
  currentTilt = tilt;
  panServo.write(pan);
  tiltServo.write(tilt);
}

/** Move to home position safely. */
void goHome() {
  moveServos(HOME_PAN, HOME_TILT);
}

/** Send an OK response. */
void sendOK() {
  Serial.println("OK");
}

/** Send an ERR response with a short reason string. */
void sendErr(const char* reason) {
  Serial.print("ERR:");
  Serial.println(reason);
}


// ── Command parser ────────────────────────────────────────────────────────────

/**
 * Parse and execute a complete command line.
 *
 * Accepted format: "SET,<pan>,<tilt>"  (no trailing newline — stripped by caller)
 * On success:  moves servos, resets watchdog, sends "OK".
 * On failure:  sends "ERR:<reason>", servos are NOT moved.
 */
void processCommand(const char* line) {
  // Must start with "SET,"
  if (strncmp(line, CMD_PREFIX, 4) != 0) {
    sendErr("unknown_command");
    return;
  }

  // Parse two comma-separated integers after the prefix
  const char* afterPrefix = line + 4;
  char* endPtr;

  long pan = strtol(afterPrefix, &endPtr, 10);
  if (endPtr == afterPrefix || *endPtr != ',') {
    sendErr("parse_pan");
    return;
  }

  const char* afterComma = endPtr + 1;
  long tilt = strtol(afterComma, &endPtr, 10);
  if (endPtr == afterComma || (*endPtr != '\0' && *endPtr != '\r')) {
    sendErr("parse_tilt");
    return;
  }

  // Validate ranges (firmware limits, NOT Python's softer limits)
  if (pan < 0 || pan > 180 || tilt < 0 || tilt > 180) {
    sendErr("angle_out_of_range");
    return;
  }

  // Clamp to mechanical limits (belt-and-suspenders)
  int safePan  = clamp((int)pan,  MIN_PAN,  MAX_PAN);
  int safeTilt = clamp((int)tilt, MIN_TILT, MAX_TILT);

  // If the requested angles were outside firmware limits, still move to the
  // clamped position but send OK (the Python side should be sending in-range
  // values; clamping here prevents runaway from a bug on either side).
  moveServos(safePan, safeTilt);

  // Reset watchdog
  lastValidCmd = millis();
  watchdogFired = false;

  sendOK();
}


// ── Arduino lifecycle ─────────────────────────────────────────────────────────

void setup() {
  Serial.begin(BAUD_RATE);

#if defined(ESP32) || defined(ARDUINO_ARCH_ESP32)
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);
  panServo.setPeriodHertz(50);
  tiltServo.setPeriodHertz(50);
  panServo.attach(PAN_PIN, 500, 2400);
  tiltServo.attach(TILT_PIN, 500, 2400);
#else
  panServo.attach(PAN_PIN);
  tiltServo.attach(TILT_PIN);
#endif

  // Move to home position on startup
  goHome();

  lastValidCmd = millis();

  // Identify ourselves so the Python side can verify communication
  Serial.println("EYESPY_SERVO_CONTROLLER_READY");
}

void loop() {
  // ── Serial input handling ──────────────────────────────────────────────
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n') {
      // End of line — null-terminate and process
      inputBuffer[bufferPos] = '\0';

      // Strip trailing carriage return if present (Windows \r\n)
      if (bufferPos > 0 && inputBuffer[bufferPos - 1] == '\r') {
        inputBuffer[bufferPos - 1] = '\0';
      }

      if (bufferPos > 0) {
        processCommand(inputBuffer);
      }

      bufferPos = 0;  // Reset buffer for next command
    } else if (c != '\r') {
      // Accumulate characters; drop oversized lines to prevent buffer overflow
      if (bufferPos < MAX_CMD_LEN - 1) {
        inputBuffer[bufferPos++] = c;
      } else {
        // Line too long — discard this command
        bufferPos = 0;
        sendErr("line_too_long");
        // Drain remaining chars on this line
        while (Serial.available() && Serial.peek() != '\n') {
          Serial.read();
        }
      }
    }
  }

  // ── Watchdog check ─────────────────────────────────────────────────────
  unsigned long now = millis();
  // millis() wraps around ~every 49 days; subtraction handles rollover correctly.
  if (!watchdogFired && (now - lastValidCmd) > WATCHDOG_MS) {
    watchdogFired = true;
    // Design decision: HOLD POSITION (do not return to home).
    // Rationale: returning to home on timeout moves the camera and may wrap
    // a short cable if the rig has panned far.  Holding is safer — the
    // operator can issue a home command manually once they reconnect.
    // Change this to goHome() if your installation prefers that behaviour.
    sendErr("watchdog_timeout");
  }

  // Small delay to keep the loop from spinning uselessly when idle.
  // Does NOT introduce noticeable latency at 10–20 Hz command rates.
  delay(2);
}
