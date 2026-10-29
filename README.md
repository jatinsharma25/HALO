# EyeSpy

_For SIH internal selection 2026._

AI-augmented campus security surveillance system. Detects behavioural events (loitering, restricted zone entry, after-hours presence) using video feeds. Generates structured incidents. Supports a human operator response workflow.

Now features autonomous person-tracking via an Arduino-driven pan-and-tilt servo camera mount, keeping detected targets centered in real time.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, SQLite, SQLAlchemy, Alembic, JWT |
| Video / Detection | OpenCV, YOLOv8n (person class 0 only) |
| Hardware Tracking | Arduino Uno R3, MG996R Servos, PySerial, PID/EMA Feedback Controller |
| Frontend | React 19 + Vite, React Router (design system in `frontend/src/components/ui`) |
| Infra | Docker + docker-compose |

## Hardware Autonomous Tracking

EyeSpy includes an autonomous pan-and-tilt tracking system:
- **Firmware:** `hardware/arduino/eyespy_servo_controller.ino`
- **Standalone test script:** `scripts/standalone_tracker.py`
- **Documentation & Assembly Guide:** [`documentations/HARDWARE_TRACKING_GUIDE.md`](documentations/HARDWARE_TRACKING_GUIDE.md)

### Standalone Test (Phase 3)
```bash
# Test tracking feedback loop directly on webcam
python scripts/standalone_tracker.py --camera 0 --port COM3
```

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

```bash
.venv/bin/python -m pytest tests/ -q     # 80 passed
```

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

> **Change all passwords before any deployment.**

## Development (without Docker)

```bash
# Create and activate virtualenv
python -m venv .venv
.venv\Scripts\activate    # Windows
source .venv/bin/activate  # Linux/Mac

# Install deps
pip install -r requirements.txt

# Run backend
uvicorn backend.main:app --reload --port 8000

# Run tests
pytest tests/ -v
```

## Project Structure

```
backend/          FastAPI app, DB models, detection engine
frontend/         React + Vite UI (5 views)
modules/          Video analysis modules (kept from original)
tests/            pytest test suite
docs/             Model passport, scoring formula
docker-compose.yml
Dockerfile.backend
Dockerfile.frontend
requirements.txt
```

## Build Phases

| Phase | Status | Description |
|---|---|---|
| 1 | ✅ Done | DB schema, FastAPI skeleton, JWT auth, Docker |
| 2 | 🔲 Next | Multi-source video pipeline (VideoSource, SourceManager) |
| 3 | 🔲 | Detection behaviours (zone entry, after-hours, loitering) |
| 4 | 🔲 | Incident engine (scoring, dedup, lifecycle state machine) |
| 5 | 🔲 | UI — 5 views (React + Tailwind) |
| 6 | 🔲 | Evidence packaging and hash-chained audit log |

## Privacy & Governance

- Detects **person class only** (COCO class 0). No face recognition, no identity matching.
- All alerts are human-reviewed. No automated enforcement.
- See `docs/model_passport.md` for full model governance documentation.
