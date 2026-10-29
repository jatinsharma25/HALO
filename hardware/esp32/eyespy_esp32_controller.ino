/*
  EyeSpy Servo Controller — ESP-32 CP2102 USB-C Edition
  hardware/esp32/eyespy_esp32_controller.ino

  Controls a dual-axis pan-and-tilt rig via MG996R metal-gear servos
  connected to an ESP32 (CP2102 USB-C Dev Module).

  ─── Prerequisites ────────────────────────────────────────────────────────────
  1. Arduino IDE Board Package:
     File > Preferences > Additional Board Manager URLs:
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
     Tools > Board > Boards Manager > Search "esp32" by Espressif > Install.
  2. Servo Library:
     Sketch > Include Library > Manage Libraries... > Search "ESP32Servo" > Install.
  3. Board Selection:
     Tools > Board > ESP32 Arduino > "ESP32 Dev Module" (or "NodeMCU-32S")
     Tools > Port > Select the Silicon Labs CP210x COM port.

  ─── ESP-32 Pin Allocation ───────────────────────────────────────────────────
  Pan Servo PWM Signal  → GPIO 18   (safe, hardware PWM)
  Tilt Servo PWM Signal → GPIO 19   (safe, hardware PWM)

  ⚠️ WARNING: Never use GPIO 6 through 11 on ESP32!
  Those pins are connected directly to the internal SPI flash chip.
  Using them will cause an immediate boot loop / crash.

  ─── 3.3V Logic & 5V-6V Power Safety ──────────────────────────────────────────
  • The ESP32 logic level is 3.3V. MG996R servos comfortably detect 3.3V PWM
    signals on their orange/white signal wire.
  • NEVER power the MG996R servos from the ESP32 3.3V pin or the VIN pin!
  • Power the servos from an external, regulated 5V–6V 4A–5A DC power supply.
  • Connect External Power Supply Ground (-) to ESP32 GND pin (Common Ground).

  ─── Protocol (Identical to EyeSpy specification) ────────────────────────────
  Baud Rate : 115200
  Command   : "SET,<pan>,<tilt>\n"
  Response  : "OK\n" or "ERR:<reason>\n"
  Watchdog  : 3000ms (holds position on serial signal loss)
*/

#include <ESP32Servo.h>

// ── Pin Configuration (ESP32 safe PWM GPIOs) ─────────────────────────────────
const int PAN_PIN  = 18;
const int TILT_PIN = 19;

// ── Initial / Home Position ───────────────────────────────────────────────────
const int HOME_PAN  = 90;
const int HOME_TILT = 90;

// ── Firmware Mechanical Limits ────────────────────────────────────────────────
const int MIN_PAN  = 30;
const int MAX_PAN  = 150;
const int MIN_TILT = 45;
const int MAX_TILT = 135;

// ── Watchdog Timeout (milliseconds) ──────────────────────────────────────────
const unsigned long WATCHDOG_MS = 3000;

// ── Serial Protocol Constants ─────────────────────────────────────────────────
const int   BAUD_RATE   = 115200;
const int   MAX_CMD_LEN = 24;
const char  CMD_PREFIX[] = "SET,";

// ── Servo & State Objects ─────────────────────────────────────────────────────
Servo panServo;
Servo tiltServo;

char          inputBuffer[MAX_CMD_LEN];
int           bufferPos     = 0;
bool          watchdogFired = false;
unsigned long lastValidCmd  = 0;

int currentPan  = HOME_PAN;
int currentTilt = HOME_TILT;


int clampVal(int val, int lo, int hi) {
  if (val < lo) return lo;
  if (val > hi) return hi;
  return val;
}

void moveServos(int pan, int tilt) {
  currentPan  = pan;
  currentTilt = tilt;
  panServo.write(pan);
  tiltServo.write(tilt);
}

void goHome() {
  moveServos(HOME_PAN, HOME_TILT);
}

void sendOK() {
  Serial.println("OK");
}

void sendErr(const char* reason) {
  Serial.print("ERR:");
  Serial.println(reason);
}

void processCommand(const char* line) {
  if (strncmp(line, CMD_PREFIX, 4) != 0) {
    sendErr("unknown_command");
    return;
  }

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

  if (pan < 0 || pan > 180 || tilt < 0 || tilt > 180) {
    sendErr("angle_out_of_range");
    return;
  }

  int safePan  = clampVal((int)pan,  MIN_PAN,  MAX_PAN);
  int safeTilt = clampVal((int)tilt, MIN_TILT, MAX_TILT);

  moveServos(safePan, safeTilt);

  lastValidCmd = millis();
  watchdogFired = false;
  sendOK();
}

void setup() {
  Serial.begin(BAUD_RATE);

  // Allow allocation of all timers for ESP32 PWM
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  // Standard 50Hz hobby servo frequency
  panServo.setPeriodHertz(50);
  tiltServo.setPeriodHertz(50);

  // Attach servos with standard pulse bounds for MG996R (500us - 2400us)
  panServo.attach(PAN_PIN, 500, 2400);
  tiltServo.attach(TILT_PIN, 500, 2400);

  goHome();
  lastValidCmd = millis();

  // Python controller identifies this handshake message
  Serial.println("EYESPY_SERVO_CONTROLLER_READY");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n') {
      inputBuffer[bufferPos] = '\0';
      if (bufferPos > 0 && inputBuffer[bufferPos - 1] == '\r') {
        inputBuffer[bufferPos - 1] = '\0';
      }

      if (bufferPos > 0) {
        processCommand(inputBuffer);
      }
      bufferPos = 0;
    } else if (c != '\r') {
      if (bufferPos < MAX_CMD_LEN - 1) {
        inputBuffer[bufferPos++] = c;
      } else {
        bufferPos = 0;
        sendErr("line_too_long");
        while (Serial.available() && Serial.peek() != '\n') {
          Serial.read();
        }
      }
    }
  }

  // Safety Watchdog
  unsigned long now = millis();
  if (!watchdogFired && (now - lastValidCmd) > WATCHDOG_MS) {
    watchdogFired = true;
    sendErr("watchdog_timeout");
  }

  delay(2);
}
