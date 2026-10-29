"""
tests/test_evidence_redact.py

Unit tests for privacy redaction (person bounding box blurring).
"""
import numpy as np
from backend.evidence.redact import redact_frame


def test_redact_frame_empty_boxes():
    frame = np.ones((100, 100, 3), dtype=np.uint8) * 128
    out = redact_frame(frame, [])
    assert np.array_equal(frame, out)


def test_redact_frame_blurs_region():
    # Create an image with an edge inside the box (left half 0, right half 255)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[20:50, 35:50] = 255  # Step edge at x=35 inside the box [20, 20, 50, 50]

    boxes = [[20, 20, 50, 50]]
    out = redact_frame(frame, boxes, blur_ksize=15)

    # Outside the bounding box must remain completely untouched
    assert np.all(out[0:15, 0:15] == 0)
    assert np.all(out[60:80, 60:80] == 0)

    # Inside the box, the sharp step at x=35 must now be diffused/blurred
    assert not np.array_equal(frame[20:50, 20:50], out[20:50, 20:50])


def test_redact_frame_out_of_bounds_box():
    frame = np.ones((100, 100, 3), dtype=np.uint8) * 50
    # Box exceeding image dimensions
    boxes = [[-10, -10, 150, 150]]
    out = redact_frame(frame, boxes)
    assert out.shape == frame.shape
