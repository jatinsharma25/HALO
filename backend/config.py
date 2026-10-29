"""
backend/config.py

Settings for the detection heuristics and evidence signing ported from the
oli-cctv work. Kept separate from the FastAPI app so the pure detection modules
stay importable without pulling in the whole application.
"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "data"))
KEYS_DIR = DATA_DIR / "keys"
WEIGHTS_DIR = Path(os.getenv("WEIGHTS_DIR", REPO_ROOT / "weights"))

# ── Detection ────────────────────────────────────────────────────────────────
YOLO_MODEL_PATH = Path(os.getenv("YOLO_MODEL_PATH", WEIGHTS_DIR / "yolov8n.pt"))
PERSON_CLASS_ID = 0  # COCO class 0 = person; this system detects that class only.
DETECTION_CONF_THRESHOLD = float(os.getenv("DETECTION_CONF_THRESHOLD", "0.45"))
DETECTION_TARGET_FPS = int(os.getenv("DETECTION_TARGET_FPS", "5"))
ROLLING_BUFFER_SECONDS = int(os.getenv("ROLLING_BUFFER_SECONDS", "20"))
POST_EVENT_CAPTURE_SECONDS = int(os.getenv("POST_EVENT_CAPTURE_SECONDS", "10"))

# ── Evidence signing ─────────────────────────────────────────────────────────
# Ed25519 signs the manifest so a package can be verified by a third party
# holding only the public key — the HMAC in packager.py proves it was us, this
# proves it to someone who is not us.
ED25519_PRIVATE_KEY_PATH = Path(
    os.getenv("ED25519_PRIVATE_KEY_PATH", KEYS_DIR / "evidence_ed25519.key")
)
ED25519_PUBLIC_KEY_PATH = Path(
    os.getenv("ED25519_PUBLIC_KEY_PATH", KEYS_DIR / "evidence_ed25519.pub")
)
EVIDENCE_DIR = Path(os.getenv("EVIDENCE_DIR", REPO_ROOT / "evidence_clips"))

# ── Camera health ────────────────────────────────────────────────────────────
# A camera that has silently failed is worse than one that is plainly offline:
# the operator still sees a tile and assumes it is watching. These thresholds
# separate "dark scene" from "lens covered", and "static scene" from "frozen
# feed" — FROZEN_WINDOW_SECONDS is deliberately long because real CCTV of an
# empty corridor is genuinely motionless for a long time.
OFFLINE_TIMEOUT_SECONDS = int(os.getenv("OFFLINE_TIMEOUT_SECONDS", "8"))
FROZEN_WINDOW_SECONDS = int(os.getenv("FROZEN_WINDOW_SECONDS", "30"))
FROZEN_DIFF_THRESHOLD = float(os.getenv("FROZEN_DIFF_THRESHOLD", "0.8"))
BLACKOUT_BRIGHTNESS_THRESHOLD = float(os.getenv("BLACKOUT_BRIGHTNESS_THRESHOLD", "12.0"))
BLACKOUT_STD_THRESHOLD = float(os.getenv("BLACKOUT_STD_THRESHOLD", "6.0"))
# Laplacian variance (edge sharpness) below this reads as "blurred". This is
# inherently camera- and lighting-dependent — measured against a real, in-focus
# consumer webcam this session, the raw (pre-annotation) frame sat consistently
# around 13-14, not the hundreds a sharp, well-lit CCTV frame would show. 8.0
# leaves that webcam clear margin while still catching a genuinely covered or
# defocused lens (which reads far lower). Different camera hardware will want
# a different value — override via this env var per deployment rather than
# treating 8.0 as universal.
BLUR_LAPLACIAN_THRESHOLD = float(os.getenv("BLUR_LAPLACIAN_THRESHOLD", "8.0"))
# A single noisy frame dipping below BLUR_LAPLACIAN_THRESHOLD shouldn't flip
# the camera to "blurred" — real webcams do this constantly (AF/AE hunting,
# a blink of motion blur) even when the feed is fine on average. Blur must
# hold below threshold for every sample across this whole window to count.
# Short relative to FROZEN_WINDOW_SECONDS: an actually covered/defocused
# lens should still be flagged quickly, this is only smoothing out noise.
BLUR_SUSTAIN_SECONDS = float(os.getenv("BLUR_SUSTAIN_SECONDS", "3.0"))

# ── Crowd detection ──────────────────────────────────────────────────────────
# Global (whole-frame) headcount, not per-zone -- see detection/crowd_heuristic.py.
CROWD_COUNT_THRESHOLD = int(os.getenv("CROWD_COUNT_THRESHOLD", "5"))
CROWD_SUSTAIN_SECONDS = float(os.getenv("CROWD_SUSTAIN_SECONDS", "10.0"))
