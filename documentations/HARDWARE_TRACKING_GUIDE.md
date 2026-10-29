# EyeSpy Autonomous Pan-and-Tilt Tracking System
## Complete Hardware, Firmware, and Software Integration Guide (ESP-32 CP2102 Edition)

---

## 1. System Architecture

The EyeSpy autonomous tracking system integrates an **ESP-32 (CP2102 USB-C module)** controlling dual-axis MG996R metal-gear servos with the existing EyeSpy AI detection pipeline. Inference and control run on the host computer; the ESP-32 functions as a real-time, high-precision PWM motor controller.

```mermaid
flowchart TD
    subgraph Host Computer (Python 3.11)
        A["USB Webcam (Logitech C270)\n/dev/video0 or Index 0"] -->|"cv2.VideoCapture (~30fps)"| B["VideoSource (Reader Thread)"]
        B -->|"Latest Frame"| C["DetectionPipeline (Inference Thread)"]
        C -->|"YOLOv8n Person Class 0"| D["CentroidTracker (modules/)"]
        D -->|"objects_info {track_id, bbox, centroid}"| E["VideoSource.set_tracking_candidates()"]
        C -->|"Zone, Incident, Alert Evaluation"| F["SQLite DB & WebSocket Alerts"]
        
        G["TrackingController (Background Thread @ 10-20Hz)"] -->|"get_tracking_candidates()"| E
        G -->|"1. Select Target (Continuity or Largest BBox)\n2. Compute Center Error (ex, ey)\n3. Dead Zone Filter\n4. EMA Smoothing (alpha=0.4)\n5. Proportional Correction (Kp)\n6. Clamp Step & Travel Limits"| H["ArduinoController / Serial Client"]
        H -->|"SET,<pan>,<tilt>\\n @ 115200 baud"| I["USB-C Serial (CP2102 COMx / ttyUSB0)"]
    end

    subgraph Microcontroller & Actuators
        I -->|"ASCII Serial Protocol"| J["ESP-32 CP2102 (eyespy_esp32_controller.ino)"]
        J -->|"Command Validation & Watchdog (3000ms)"| K["ESP32Servo PWM Output"]
        K --> L["Pan Servo (GPIO 18, MG996R)"]
        K --> M["Tilt Servo (GPIO 19, MG996R)"]
        N["Regulated 5-6V 5A Power Supply"] -->|"Motor VCC & Common GND"| L
        N -->|"Motor VCC & Common GND"| M
        N -.->|"Common Ground"| J
    end

    subgraph Operator Dashboard (React 19 + Vite)
        O["Web Dashboard / Camera Tile"] -->|"POST /cameras/{id}/tracking/start"| G
        O -->|"POST /cameras/{id}/tracking/manual"| G
        O -->|"GET /hardware/status"| H
    end
```

---

## 2. Hardware Bill of Materials (BOM)

| Component | Part / Spec | Qty | Notes |
|---|---|:---:|---|
| Microcontroller | **ESP-32 CP2102 USB-C Dev Module** | 1 | 30-pin or 38-pin NodeMCU-32S / ESP32 DevKit V1 with USB-C |
| Pan Servo | MG996R Metal Gear High-Torque Servo | 1 | 180° rotation, stall current ~1.5–2.5 A |
| Tilt Servo | MG996R Metal Gear High-Torque Servo | 1 | 180° rotation, stall current ~1.5–2.5 A |
| Webcam | Logitech C270 (or any UVC USB camera) | 1 | 720p / 30fps default |
| Bracket | Dual-axis pan/tilt bracket kit | 1 | Aluminum / nylon bracket fitted for standard servos |
| Power Supply | Regulated 5 V – 6 V DC, ≥ 4 A – 5 A | 1 | **Crucial:** Never power servos from ESP32 pins! |
| Capacitor | 1000 µF to 2200 µF, 16 V Electrolytic | 1 | Place across servo power rails to buffer current spikes |
| Wiring | Jumper wires (M-M, M-F), breadboard/terminal | 1 set | Keep high-current leads short and secure |

---

## 3. Electrical Wiring & Schematics

### ⚠️ Critical Electrical Safety Rules for ESP-32
1. **ESP-32 is 3.3V Logic:**
   - The ESP-32 outputs 3.3V PWM signals on its GPIOs. MG996R servos comfortably detect 3.3V logic signals on their PWM input (orange/white wire).
   - **Never connect 5V or 6V back into any ESP32 GPIO pin** — ESP32 pins are not 5V tolerant!
2. **Never Power Servos from ESP32:**
   - Do NOT power servos from the ESP32 `3V3` or `VIN` pin! MG996R servos draw up to 2.5 A stall current.
   - Power the servos strictly from your external 5V–6V 4A–5A supply.
3. **Common Ground is Mandatory:**
   - The negative (-) rail of the external servo power supply MUST connect to an ESP-32 **GND** pin. Without common ground, signal reference floats and servos will jitter uncontrollably.
4. **Forbidden GPIOs on ESP-32:**
   - **Never use GPIO 6, 7, 8, 9, 10, or 11!** These are connected to the internal SPI flash memory. Using them will crash the board into a reboot loop.
   - We use **GPIO 18** (Pan) and **GPIO 19** (Tilt), which are universally safe, non-strapping, hardware-PWM-capable pins.

### Pinout Table

| ESP-32 Pin | Connected To | Wire / Signal |
|---|---|---|
| **GPIO 18** | Pan Servo Signal Wire | Orange / White (3.3V PWM) |
| **GPIO 19** | Tilt Servo Signal Wire | Orange / White (3.3V PWM) |
| **GND** | External PSU Negative (-) & Servo Ground | Brown / Black (Common GND) |
| **USB-C Port** | Host Laptop USB Port | CP2102 Serial Data & 5V Board Logic |
| **External PSU (+)** | Servo Power (VCC) Rails only | Red (5V–6V DC) |
| **External PSU (-)** | Servo Ground (GND) Rails | Brown / Black |

```
    [ External 5V-6V 5A Supply ]
          (+) ───┬───────────────────────> Servo Pan VCC (Red)
                 │                         Servo Tilt VCC (Red)
                 │  [ 1000uF Cap ]
          (-) ───┴───────┬───────────────> Servo Pan GND (Brown/Black)
                         │                 Servo Tilt GND (Brown/Black)
                         │
                         └───────────────> ESP-32 GND Pin

    [ ESP-32 CP2102 USB-C ]
          GPIO 18 ───────────────────────> Servo Pan Signal (Orange/White)
          GPIO 19 ───────────────────────> Servo Tilt Signal (Orange/White)
          USB-C   ═══════════════════════> Host PC / Laptop
```

---

## 4. Mechanical Assembly & Cable Routing

1. **Mounting Servos:** Assemble the pan base first. Align the pan horn to 90° before screwing the bracket down.
2. **Tilt Joint:** Center the tilt horn at 90° (horizontal orientation) before securing the camera tray.
3. **Mechanical Range Verification:** With power off, gently rotate both axes by hand:
   - Pan should move freely between 30° and 150° without contacting stops.
   - Tilt should pitch between 45° (slightly downward) and 135° (upward) without binding.
4. **Camera Cable Slack:** Attach the Logitech C270 to the tilt plate. Route the USB cable with an arched loop over the pivot axis. Rotate the mount to both extremes:
   - Verify the cable does not catch or wrap around the base.
   - Ensure the cable does not exert spring force on the tilt servo.

---

## 5. ESP-32 Firmware Setup

Firmware is located at:
- Dedicated ESP32 sketch: `hardware/esp32/eyespy_esp32_controller.ino`
- Dual-target sketch: `hardware/arduino/eyespy_servo_controller.ino` (auto-detects ESP32)

### Uploading with Arduino IDE:
1. **Install ESP32 Board Package (if not already installed):**
   - In Arduino IDE, go to **File > Preferences**.
   - Under *Additional Boards Manager URLs*, add:
     `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
   - Open **Tools > Board > Boards Manager...**, search for `esp32` by Espressif Systems and click **Install**.
2. **Install ESP32Servo Library:**
   - In Arduino IDE, go to **Sketch > Include Library > Manage Libraries...**
   - Search for `ESP32Servo` (by Kevin Harrington / John K. Bennett) and click **Install**.
3. **Board & Port Settings:**
   - **Tools > Board > ESP32 Arduino > ESP32 Dev Module** (or *NodeMCU-32S*).
   - **Tools > Port**: Select the COM port corresponding to `Silicon Labs CP210x USB to UART Bridge` (e.g. `COM4` or `COM5`).
   - *Note on CP2102 Driver:* If the COM port does not appear in Device Manager when the USB-C cable is connected, download and install the official Silicon Labs CP210x VCP driver.
4. **Upload:**
   - Open `hardware/esp32/eyespy_esp32_controller.ino`.
   - Click **Upload** (Ctrl + U).
5. **Verify:**
   - Open **Tools > Serial Monitor** set to **115200 baud**.
   - Press the `EN` / `RST` button on the ESP32.
   - Verify it outputs: `EYESPY_SERVO_CONTROLLER_READY`.
   - Send: `SET,90,90` — the servos will center and the ESP32 responds: `OK`.
   - Close the Serial Monitor so Python can open the port.

---

## 6. Serial Communication Protocol

- **Baud Rate:** 115200 baud, 8-N-1
- **Line Terminator:** `\n` (ASCII LF)
- **Host to ESP32:** `SET,<pan_deg>,<tilt_deg>\n` (e.g. `SET,95,85\n`)
- **ESP32 to Host:**
  - `OK\n` on valid command
  - `ERR:<reason>\n` on invalid format, out-of-bounds angle, or watchdog timeout
- **Safety Watchdog:** 3000 ms. If no `SET` command arrives within 3 seconds, the firmware freezes movement and holds the last known safe position to prevent runaway rotation.

---

## 7. Standalone Vision Tracker Testing (Phase 3)

Before running the full web platform, test the computer vision and servo response using the standalone script:

```powershell
# 1. Activate your Python environment
.venv\Scripts\activate

# 2. Test in simulation mode (webcam only, no servos)
python scripts\standalone_tracker.py --camera 0 --no-arduino

# 3. Test with live Arduino hardware
python scripts\standalone_tracker.py --camera 0 --port COM3
```

### Controls in Standalone Mode:
- **`t`**: Toggle autonomous tracking on / off
- **`h`**: Home servos to neutral (90°, 90°)
- **`r`**: Reset tracker state
- **`q`** or **ESC**: Quit cleanly

---

## 8. Full Application Operation (Phase 4 & 5)

### Running EyeSpy Backend and Frontend

```powershell
# Terminal 1: Backend
.venv\Scripts\activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
```

1. Open your browser to `http://localhost:5173` (or `http://localhost:3000`).
2. Log in with: `admin` / `admin123` (or `operator` / `op123`).
3. Navigate to **Configuration > Cameras**:
   - Add your camera with Name: "Tracking Rig", Source: `0` (or `1`).
4. Navigate to **Dashboard**:
   - Click **Start** on the camera tile to spin up the video feed and detection pipeline.
   - Click **Connect** in the Tracking Panel and enter your COM port (e.g., `COM3`).
   - Click **Follow Person** to enable autonomous tracking.
   - Walk across the camera view to observe physical panning and tilting.
   - Click **Stop Tracking** or use the manual arrow buttons when finished.

---

## 9. Tuning & Calibration Guide

All tracking parameters are configurable via environment variables in `.env` or system environment:

| Parameter | Env Variable | Default | Tuning Guide |
|---|---|:---:|---|
| Pan Gain | `EYESPY_PAN_GAIN` | `0.025` | Increase (e.g. `0.035`) if camera lags behind walking person; decrease (e.g. `0.015`) if camera oscillates/hunts. |
| Tilt Gain | `EYESPY_TILT_GAIN` | `0.025` | Adjust vertical responsiveness. Note: Tilt range is mechanically narrower than pan. |
| Max Pan Step | `EYESPY_MAX_PAN_STEP` | `5.0` | Caps degrees per update (prevents sudden jerks on new detections). |
| Dead Zone X | `EYESPY_DEAD_ZONE_X` | `40` | Width of deadband in pixels. Widen (e.g. `60`) if motor buzzes when person is standing still. |
| Dead Zone Y | `EYESPY_DEAD_ZONE_Y` | `30` | Height of deadband in pixels. |
| EMA Alpha | `EYESPY_EMA_ALPHA` | `0.4` | Error smoothing factor (0.1 = heavy filter, slow; 0.9 = raw, fast). |
| Command Rate | `EYESPY_COMMAND_RATE_HZ` | `10` | Motor update rate. 10–20 Hz matches MG996R physical response time. |
| Target Timeout | `EYESPY_TARGET_LOSS_TIMEOUT` | `2.0` | Seconds to hold target lock before declaring target lost. |

---

## 10. Troubleshooting & Failure Modes

| Symptom | Cause | Solution |
|---|---|---|
| Arduino resets repeatedly when servos move | Brownout / voltage drop | Servos are drawing current from Arduino or PSU is under-rated. Power servos from external 5V 5A supply with capacitor across rails. |
| Camera moves opposite to person | Inverted servo axis orientation | Invert the gain parameter (e.g., set `EYESPY_PAN_GAIN=-0.025`). |
| Servos chatter or buzz when target is still | Dead zone too small or noise in detection | Increase `EYESPY_DEAD_ZONE_X` to `50`–`60` px. |
| Serial connection fails (`PermissionError` / `Access Denied`) | Port held open by another program | Close Arduino Serial Monitor, Cura, or previous Python instances before connecting. |
| UI shows "Target Lost" even though person is in frame | YOLO confidence below threshold | Lower `EYESPY_CONF_THRESHOLD` to `0.4` or improve scene lighting. |
| Video feed freezes when tracking begins | Serial write blocking inference thread | Fixed by design: TrackingController runs in a separate thread from DetectionPipeline. Verify thread status. |

---

## 11. Known Limitations & Future Work

1. **Servo Type:** Hobby RC servos have open-loop position control (no position feedback from the motor shaft). Future iterations can use serial bus servos (e.g., Dynamixel or Feetech STS3215) for bidirectional angle and load telemetry.
2. **Field of View Bounds:** The camera operates within mechanical stops (30°–150° pan). It does not rotate 360° continuously due to cable wrap constraints.
3. **Multi-person Ambiguity:** In crowded scenes, the default policy follows the largest bounding box or retains the current track ID until occlusion. Facial recognition or re-identification is intentionally excluded for privacy compliance.
