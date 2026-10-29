"""
backend/evidence/redact.py

Display-layer privacy redaction. Blurs detected person bounding boxes
on video frames for streaming and privacy-conscious viewing.
"""
from typing import Sequence
import cv2
import numpy as np


def redact_frame(frame: np.ndarray, boxes: Sequence[Sequence[int]], blur_ksize: int = 51) -> np.ndarray:
    """
    Apply Gaussian blur to the bounding box regions in frame.

    Args:
        frame: np.ndarray image (BGR)
        boxes: Sequence of [x1, y1, x2, y2] pixel coordinates
        blur_ksize: Kernel size for Gaussian blur (must be odd)

    Returns:
        Frame with blurred person regions (copy).
    """
    if frame is None or not boxes:
        return frame

    out = frame.copy()
    h, w = out.shape[:2]

    # Ensure kernel size is odd and >= 3
    k = max(3, blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1)

    for box in boxes:
        if len(box) < 4:
            continue
        x1, y1, x2, y2 = [int(v) for v in box[:4]]
        # Clamp to frame dimensions
        x1 = max(0, min(w - 1, x1))
        y1 = max(0, min(h - 1, y1))
        x2 = max(0, min(w, x2))
        y2 = max(0, min(h, y2))

        if x2 <= x1 or y2 <= y1:
            continue

        region = out[y1:y2, x1:x2]
        if region.size > 0:
            blurred = cv2.GaussianBlur(region, (k, k), 0)
            out[y1:y2, x1:x2] = blurred

    return out
