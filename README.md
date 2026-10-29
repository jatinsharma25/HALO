# EyeSpy — AI-Augmented Autonomous Tracking Surveillance System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19.2-61dafb.svg)](https://react.dev/)
[![Hardware: ESP--32 / Arduino](https://img.shields.io/badge/Hardware-ESP--32%20%7C%20Arduino-E7352C.svg)](hardware/esp32/eyespy_esp32_controller.ino)
[![Tests: 162 Passed](https://img.shields.io/badge/Tests-162%20Passed-success.svg)](tests/)

AI-augmented campus security surveillance system. Detects behavioural events (loitering, restricted zone entry, after-hours presence, falls, crowd thresholds) using live video feeds, correlates incidents with audit hash-chains, and autonomously steers a physical pan-and-tilt camera mount to track detected individuals in real time.

---

## ⚡ Core Capabilities

- **Autonomous Person-Tracking Mount:** Dual-axis MG996R servo pan-and-tilt tracking driven by an **ESP-32 CP2102 USB-C** microcontroller (or Arduino Uno) using a zero-overhead proportional feedback loop with exponential moving average (EMA) smoothing and deadband suppression.
- **AI Person Detection & Multi-Object Tracking:** YOLOv8n (COCO class 0) paired with an optimized centroid tracker (`backend/modules/centroid_tracker.py`).
- **Behavioral Analytics Heuristics:** Real-time evaluation of restricted zone entries, schedule-aware after-hours presence, dwell-time loitering, fall/collapse detection, abandoned object warnings, and crowd headcounts.
- **Operator Response Dashboard:** React 19 + Vite dashboard featuring live MJPEG camera streams, interactive PTZ positioning controls, incident triage, and one-click tracking toggles.
- **Cryptographic Evidence Verification:** Automated packaging of incident clips carrying HMAC service signatures and third-party verifiable Ed25519 asymmetric signatures.
- **Tamper-Evident Audit Trail:** SHA-256 hash-chained log securing all operator interventions and state transitions.

---

## 🛠️ Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11, FastAPI, SQLite, SQLAlchemy 2.0, Alembic, JWT (python-jose), PySerial |
| **Computer Vision** | OpenCV 4.9, YOLOv8n (Ultralytics), Supervision |
| **Microcontroller & Motors** | ESP-32 CP2102 (ESP32Servo LEDC PWM) / Arduino Uno R3, Dual MG996R metal-gear servos |
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS, Radix UI, TanStack Query |
| **Infrastructure** | Docker, Docker Compose, Uvicorn |

---

## 🤖 Hardware Autonomous Tracking

EyeSpy autonomously pans (horizontal) and tilts (vertical) the camera mount to center detected individuals.

- **ESP-32 Firmware (Recommended):** [`hardware/esp32/eyespy_esp32_controller.ino`](hardware/esp32/eyespy_esp32_controller.ino) (uses safe GPIO 18/19 & 50Hz LEDC PWM)
- **Arduino Firmware (Legacy):** [`hardware/arduino/eyespy_servo_controller.ino`](hardware/arduino/eyespy_servo_controller.ino)
- **Complete Hardware & Wiring Guide:** [`documentations/HARDWARE_TRACKING_GUIDE.md`](documentations/HARDWARE_TRACKING_GUIDE.md)
- **Project Handover & Runbook:** [`HANDOVER.md`](HANDOVER.md)

### Standalone Vision-Tracker Test (Phase 3)
Verify your camera, servos, and control gains without running the full web server:
```bash
# Test feedback loop with live ESP-32 / Arduino hardware
python scripts/standalone_tracker.py --camera 0 --port COM3

# Test in simulation mode (webcam only, no microcontroller connected)
python scripts/standalone_tracker.py --camera 0 --no-arduino
```
*(Interactive hotkeys: `t` toggle tracking, `h` home servos, `r` reset tracker, `q` quit).*

## Quick Start

```bash
cp .env.example .env        # then set JWT_SECRET
docker compose up --build

# Frontend:    http://localhost:3000
# Backend API: http://localhost:8000
# API docs:    http://localhost:8000/docs
```

The frontend proxies `/api` to the backend, so the browser talks to one origin
and no CORS setup is needed.

Runtime state lives in `./data` (SQLite database and packaged evidence clips),
mounted into the backend so it survives a restart. Put video files in `./media`
and reference one from a camera as `/app/media/<name>`.

### Without Docker

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn backend.main:app --reload    # :8000

cd frontend && npm install && npm run dev                 # :3000
```

The frontend reads `VITE_API_BASE_URL`, defaulting to `http://127.0.0.1:8000`
for local dev. The Docker image builds it with `/api` so nginx can proxy it
same-origin — Vite inlines env at build time, so that is set in the Dockerfile
rather than in compose.

## Screens

| Screen | What it does |
| --- | --- |
| Operations | Live camera tiles, MJPEG view, start/stop, recent observations |
| Casebook | Incident queue, status workflow, evidence packaging and integrity verification |
| Incidents | Alert feed with severity, detail and one-click acknowledgement |
| Configuration | Camera CRUD |
| Governance | Security policies, audit log with hash-chain verification, evidence signing key |
| Directory | Personnel directory |

## Branches

`main` carries every branch's work.

`oli-cctv` was a parallel rewrite with its own `backend/app/`, its own API shape
and its own frontend. Adopting it wholesale would have broken the `UI/UX-design`
frontend outright — it has no `/cameras/{id}/observations`, no `start`/`stop`,
and serves cameras under `/config` — so its **logic** was ported into this
backend instead of its structure:

| Ported from oli-cctv | Where |
| --- | --- |
| 7 detection heuristics (zone rules, schedules, falls, abandoned objects, fire/smoke, camera health, person tracking) | `backend/detection/` |
| Incident scoring and explanation | `backend/incidents/scoring.py`, `explain.py` |
| Evidence redaction and Ed25519 signing | `backend/evidence/redact.py`, `sign.py` |
| Scenario replay | `backend/replay/` |

Not ported: `evidence/capture.py` and `incident/lifecycle.py`, which are welded
to that branch's own models and ingestion — this backend already does both jobs.

## Evidence integrity

A package carries two signatures because they answer to different people.

The **HMAC** proves the package is ours to anyone holding the service secret.
The **Ed25519 signature** proves it to anyone holding only the public key, which
is the case that matters once a clip leaves the system — fetch it from
`GET /evidence/public-key`.

`GET /evidence/{id}/verify` re-hashes the file on disk and re-checks the
signature, so a tampered clip fails even if its database row is untouched.

## Tests

Run the complete automated test suite (includes camera pipeline, heuristics, ESP-32/Arduino hardware controllers, feedback loop, redaction, and API contracts):

```bash
pytest tests/ -v --tb=short
```

**Test Status:** `162 passed, 1 skipped (100% pass rate across 163 tests)`

## Default Credentials (development only)

> These are seeded into any empty database, production included. Set
> `SEED_ADMIN_PASSWORD`, `SEED_OPERATOR_PASSWORD` and `SEED_RESPONDER_PASSWORD`
> in `.env` **before the first start** for anything reachable from a network —
> the seed only runs once, on an empty database.

| Username | Password | Role |
|---|---|---|
| admin | admin123 | admin |
| operator | op123 | operator |
| responder | resp123 | responder |

> **Change all passwords before any production deployment.**

## Development (without Docker)

```bash
# Create and activate virtualenv
python -m venv .venv
.venv\Scripts\activate    # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies (includes PySerial, OpenCV, Ultralytics YOLO)
pip install -r requirements.txt

# Run backend API server (:8000)
uvicorn backend.main:app --reload --port 8000

# Run frontend dev server (:5173 / :3000)
cd frontend
npm install
npm run dev

# Run test suite
pytest tests/ -v
```

## Project Structure

```
backend/
  hardware/       ESP-32 & Arduino serial drivers, tracking controller, REST router
  cameras/        Camera CRUD, lifecycle start/stop, status endpoints
  pipeline/       VideoSource reader thread, DetectionPipeline (YOLO + Tracker)
  modules/        CentroidTracker, line counters, zone analyzers
  detection/      Heuristics (fall, crowd, loitering, after-hours, fire/smoke)
  evidence/       Ed25519 signing, display-layer privacy redaction
  incidents/      Correlator, scoring engine, explanation generator
hardware/
  esp32/          ESP-32 CP2102 firmware (eyespy_esp32_controller.ino)
  arduino/        Arduino Uno firmware (eyespy_servo_controller.ino)
scripts/
  standalone_tracker.py  Interactive standalone computer-vision tracking tool
frontend/         React 19 + TypeScript + Vite surveillance dashboard
tests/            163-item pytest suite (unit, integration, hardware mocks)
documentations/   Illustrated Hardware Assembly & ESP-32 CP2102 Wiring Guide
HANDOVER.md       Complete Engineering Handover & Runbook
```

## System Implementation Status

| Feature / Subsystem | Status | Details |
|---|:---:|---|
| Database & Auth | ✅ Complete | SQLite + Alembic migrations, RBAC (admin, operator, responder), JWT |
| Multi-Source Video Pipeline | ✅ Complete | Thread-safe `VideoSource` supporting Webcams, MP4 files, RTSP |
| YOLOv8n Detection & Tracking | ✅ Complete | COCO Class 0 person detection + `CentroidTracker` |
| Autonomous PTZ Hardware Tracking | ✅ Complete | ESP-32 CP2102 / Arduino Uno, MG996R dual servos, zero second-loop overhead |
| Surveillance Heuristics | ✅ Complete | Restricted zones, after-hours schedules, loitering, falls, crowds |
| Incident Scoring & Explainability | ✅ Complete | Impact/confidence scoring, rule explainability |
| Cryptographic Evidence Packaging | ✅ Complete | HMAC service proof + Ed25519 public verification, person redaction |
| React 19 Operator Dashboard | ✅ Complete | Live MJPEG streams, PTZ tracking panel, D-Pad manual controls, alerts WS |
| Automated Test Suite | ✅ Complete | 162 passing tests with mocked hardware and API contracts |

## Privacy & Governance

- Detects **person class only** (COCO class 0). No face recognition, biometric matching, or mass identity indexing.
- Live streams support display-layer Gaussian privacy redaction via `backend/evidence/redact.py`.
- All alerts and incidents are operator-reviewed; no automated enforcement.
- Operator actions are recorded in a SHA-256 tamper-evident audit hash-chain.

## License

This project is licensed under the [MIT License](LICENSE) — see the `LICENSE` file for details.
