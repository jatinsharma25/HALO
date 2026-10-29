"""Sustained-crowd heuristic: flags when the number of currently-tracked
people exceeds a threshold for a sustained period. A per-frame headcount
over the count already produced by CentroidTracker -- unlike fall/abandoned-
object/fire-smoke, this isn't inferring a fuzzy visual state, it's counting
things already reliably tracked, so it carries normal (not capped-low)
confidence.

Deliberately global (whole-frame), not per-zone: no zone-level "expected
occupancy" config exists yet. A crowd during after-hours already gets a
second, independent signal from the after-hours-presence rule -- this stays
a simple, standalone headcount rather than trying to encode that context
itself.
"""
from dataclasses import dataclass


@dataclass
class CrowdHeuristic:
    """One instance per camera."""

    count_threshold: int
    sustain_seconds: float
    cooldown_seconds: float = 30.0

    _above_since: float | None = None
    _last_emitted: float | None = None

    def evaluate(self, person_count: int, now_ts: float) -> dict | None:
        if person_count < self.count_threshold:
            self._above_since = None
            return None

        if self._above_since is None:
            self._above_since = now_ts
        dwell = now_ts - self._above_since
        if dwell < self.sustain_seconds:
            return None

        should_emit = self._last_emitted is None or (now_ts - self._last_emitted) >= self.cooldown_seconds
        if should_emit:
            self._last_emitted = now_ts

        # Returned every tick once sustained (not just on the cooldown-gated
        # emission) so the live-feed overlay can keep showing the count.
        return {
            "person_count": person_count,
            "dwell_seconds": dwell,
            "confidence": 0.9,
            "emit": should_emit,
        }
