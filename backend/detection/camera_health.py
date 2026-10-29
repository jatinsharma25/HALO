"""Camera health signals: frozen feed, covered/blackout, severe blur.
Offline detection itself lives in ingestion/source_manager.py (it's a
function of read-failures over time, not frame content)."""
import logging
import time
from collections import deque

import cv2
import numpy as np

from backend.config import (
    BLACKOUT_BRIGHTNESS_THRESHOLD,
    BLACKOUT_STD_THRESHOLD,
    BLUR_LAPLACIAN_THRESHOLD,
    BLUR_SUSTAIN_SECONDS,
    FROZEN_DIFF_THRESHOLD,
    FROZEN_WINDOW_SECONDS,
)

MIN_SAMPLES_FOR_FROZEN_VERDICT = 5
MIN_SAMPLES_FOR_BLUR_VERDICT = 5
logger = logging.getLogger("cctv.health.debug")


class CameraHealthMonitor:
    """One instance per camera. Feed it frames as they're captured; call
    observe() to get the current health verdict. The frozen-feed check is
    time-bounded (FROZEN_WINDOW_SECONDS), not frame-count-bounded, so it
    isn't fooled by a fast capture rate feeding it many near-duplicate
    frames within a fraction of a second."""

    def __init__(self):
        # Unbounded on purpose: eviction is time-based (see the cutoff loop in
        # observe()), not count-based. A fixed maxlen here would silently
        # evict samples before that time-based prune ever runs whenever the
        # capture rate is fast enough to fill it in under FROZEN_WINDOW_SECONDS
        # (true for most local mp4/webcam sources decoding faster than 256
        # frames / (0.8 * FROZEN_WINDOW_SECONDS)), permanently preventing the
        # frozen-feed verdict from ever firing.
        self.recent_frames: deque = deque()  # (wall_time, small_gray_frame)
        # A single noisy frame (compression artifact, AF/AE hunting, a blink
        # of motion blur) shouldn't flip the whole camera to "blurred" — real
        # consumer webcams dip below most fixed sharpness thresholds on
        # individual frames constantly even when the feed is fine on average.
        # Same time-windowed-majority approach as the frozen check above.
        self.recent_blur_raw: deque = deque()  # (wall_time, bool)

    def observe(self, frame) -> dict:
        now = time.time()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (160, 90))
        self.recent_frames.append((now, small))
        cutoff = now - FROZEN_WINDOW_SECONDS
        while self.recent_frames and self.recent_frames[0][0] < cutoff:
            self.recent_frames.popleft()

        brightness = float(np.mean(small))
        stddev = float(np.std(small))
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        blackout = brightness < BLACKOUT_BRIGHTNESS_THRESHOLD or stddev < BLACKOUT_STD_THRESHOLD
        frozen = self._is_frozen()
        blurred = (not blackout) and self._is_sustained_blur(now, laplacian_var < BLUR_LAPLACIAN_THRESHOLD)

        return {
            "blackout": blackout,
            "frozen": frozen,
            "blurred": blurred,
            "brightness": brightness,
            "stddev": stddev,
            "laplacian_var": laplacian_var,
        }

    def _is_frozen(self) -> bool:
        samples = list(self.recent_frames)
        if len(samples) < MIN_SAMPLES_FOR_FROZEN_VERDICT:
            return False
        span = samples[-1][0] - samples[0][0]
        if span < FROZEN_WINDOW_SECONDS * 0.8:
            return False  # haven't actually observed a full window yet
        frames = [s[1] for s in samples]
        diffs = [float(np.mean(cv2.absdiff(frames[i], frames[i + 1]))) for i in range(len(frames) - 1)]
        result = max(diffs) < FROZEN_DIFF_THRESHOLD
        if result:
            logger.warning(
                "FROZEN verdict: %d samples span=%.2fs max_diff=%.4f diffs=%s",
                len(samples), span, max(diffs), [round(d, 3) for d in diffs],
            )
        return result

    def _is_sustained_blur(self, now: float, this_frame_is_blurry: bool) -> bool:
        self.recent_blur_raw.append((now, this_frame_is_blurry))
        cutoff = now - BLUR_SUSTAIN_SECONDS
        while self.recent_blur_raw and self.recent_blur_raw[0][0] < cutoff:
            self.recent_blur_raw.popleft()

        samples = list(self.recent_blur_raw)
        if len(samples) < MIN_SAMPLES_FOR_BLUR_VERDICT:
            return False
        span = samples[-1][0] - samples[0][0]
        if span < BLUR_SUSTAIN_SECONDS * 0.8:
            return False  # haven't actually observed a full window yet
        # Every sample in the window, not just a majority — a feed that's
        # only sometimes below threshold is exactly the noisy-frame case
        # this is meant to filter out, not a real covered/defocused lens.
        result = all(is_blurry for _, is_blurry in samples)
        if result:
            logger.warning(
                "BLUR verdict: %d samples span=%.2fs (all below threshold)",
                len(samples), span,
            )
        return result
