"""
tests/test_centroid_tracker.py

Regression test for a real crash found via live multi-camera testing:
CentroidTracker.update() indexed into list(self.objects.keys())[row] using
row indices computed BEFORE the match loop, but self.deregister() (called
when a track's disappeared-count crosses max_disappeared) mutates
self.objects mid-loop -- shrinking it out from under indices still pending
for later iterations, raising IndexError: list index out of range.

This reproduces reliably: several existing tracks all go unmatched and
cross the disappearance threshold in the same update() call, so more than
one deregister() fires within a single pass over the stale row indices.
"""
from backend.modules.centroid_tracker import CentroidTracker


def test_multiple_simultaneous_dropouts_do_not_crash():
    tracker = CentroidTracker(max_disappeared=1, max_distance=50)

    # Three well-separated people, far enough apart that nothing here is
    # ambiguous about which box matches which track.
    initial_boxes = [
        [0, 0, 20, 20],
        [500, 500, 520, 520],
        [1000, 1000, 1020, 1020],
    ]
    objects = tracker.update(initial_boxes)
    assert len(objects) == 3

    # Frame 2: nobody detected anywhere near any of the three tracks --
    # all three become "unmatched", disappeared goes 0 -> 1 for each
    # (not yet over max_disappeared=1, so no deregistration yet). With
    # existing tracks (3) >= new detections (1), an unmatched new detection
    # isn't registered as a track here -- that's the tracker's existing,
    # unrelated matching behavior, not what this test is checking.
    far_away_box = [[2000, 2000, 2020, 2020]]
    objects = tracker.update(far_away_box)
    assert len(objects) == 3  # all three still within max_disappeared, just not matched

    # Frame 3: same again -- the original three tracks now cross
    # max_disappeared (1) in the SAME update() call, so all three
    # deregister() calls fire back-to-back within one pass over the
    # original row indices. This is exactly the call that crashed before
    # the fix (IndexError: list index out of range) -- the real assertion
    # here is simply that this line doesn't raise.
    objects = tracker.update(far_away_box)

    assert len(objects) == 0  # all three correctly dropped, no crash


def test_more_existing_tracks_than_new_detections_reassigns_correctly():
    """A supporting sanity check for the same code path: with fewer new
    detections than existing tracks, the ones that DO match should still
    get the right identity, not an identity shifted by the row-index bug."""
    tracker = CentroidTracker(max_disappeared=50, max_distance=50)

    boxes = [[0, 0, 20, 20], [500, 500, 520, 520], [1000, 1000, 1020, 1020]]
    objects = tracker.update(boxes)
    ids_by_position = {tuple(info["centroid"]): oid for oid, info in objects.items()}
    middle_track_id = ids_by_position[(510, 510)]

    # Only the middle person is detected this frame; the other two go
    # unmatched but stay within max_disappeared, so they're kept, not
    # dropped -- this alone (no deregistration) already needs the row
    # indices to stay valid across the update.
    objects = tracker.update([[500, 500, 520, 520]])

    assert middle_track_id in objects
    assert objects[middle_track_id]["centroid"] == [510, 510]
