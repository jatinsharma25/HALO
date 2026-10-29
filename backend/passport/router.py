"""
backend/passport/router.py

GET /passport — Model Passport and measured performance scorecard.

The passport content below is a factual description of what actually runs
(see backend/pipeline/detection_pipeline.py, requirements.txt) — not a
marketing claim. scorecard_runs is empty until scenario replay runs are
persisted (backend/replay/ is not yet wired to a persistence layer); the UI
is expected to show "no runs recorded yet" rather than fabricated numbers.
"""
from fastapi import APIRouter, Depends

from backend.auth.jwt import require_role

router = APIRouter(tags=["passport"])

MODEL_PASSPORT = {
    "model_name": "YOLOv8n",
    "model_version": "ultralytics 8.0.198, weights yolov8n.pt",
    "task": "Person-class object detection (COCO class 0 only) feeding anonymous, "
            "camera-local centroid tracking and deterministic zone/schedule/dwell-time heuristics. "
            "No other COCO class is acted on.",
    "training_data": "COCO 2017 (pretrained upstream weights). Not fine-tuned on any "
                      "campus-specific, identifiable, or biometric data.",
    "tracking": "Centroid-based (backend/modules/centroid_tracker.py), anonymous and "
                "camera-local: track IDs reset every pipeline session and are never "
                "linked across cameras.",
    "known_limitations": [
        "Detection accuracy degrades in low light, heavy occlusion, and oblique camera angles.",
        "Loitering, restricted-zone, and after-hours rules are deterministic thresholds, not "
        "learned classifiers — they will not adapt to scenes they weren't configured for.",
        "Camera-health checks (offline/frozen/blackout) are statistical heuristics over pixel "
        "brightness and frame-to-frame difference, not a certified hardware-fault detector.",
        "No re-identification across cameras or across a track's own session gaps.",
        "Evidence clips are captured from the live feed at request time — see README's Branches "
        "section — not from a true pre/post-event rolling buffer.",
    ],
    "excluded_capabilities": [
        "Facial recognition or identity watchlists",
        "Attendance or student identification",
        "Cross-camera biometric re-identification",
        "Emotion, aggression, or criminal-intent detection",
        "Gender, age, caste, religion, or disability inference",
        "\"Suspicious person\" or individual risk scores",
        "Automatic police calls, door locking, sirens, or lockdowns",
        "Automatic disciplinary decisions",
        "Weapon or fight detection presented as reliable",
        "Any LLM-generated decision or natural-language footage search",
        "Claims of zero false positives or court-certified evidence",
    ],
}


@router.get("/passport")
def get_passport(_user=Depends(require_role("admin", "operator", "responder"))):
    return {"passport": MODEL_PASSPORT, "scorecard_runs": []}
