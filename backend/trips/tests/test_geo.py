import pytest

from trips.geo import (
    build_profile,
    checkpoint_distances,
    distance_to_segment_mi,
    haversine_mi,
    offset_point,
    segment_bounds,
    simplify,
)


def test_haversine_chicago_to_houston():
    assert haversine_mi((-87.6298, 41.8781), (-95.3698, 29.7604)) == pytest.approx(940, abs=10)


def test_checkpoint_distances_include_start_and_destination():
    assert checkpoint_distances(60, 25) == [0, 25, 50, 60]
    assert checkpoint_distances(50, 25) == [0, 25, 50]
    assert checkpoint_distances(5, 25) == [0, 5]
    assert checkpoint_distances(0, 25) == [0]


def test_segment_bounds_tile_the_whole_route_without_gaps():
    distances = checkpoint_distances(137, 25)
    bounds = segment_bounds(distances)
    assert bounds[0][0] == 0 and bounds[-1][1] == 137
    for (_, end), (start, _) in zip(bounds, bounds[1:]):
        assert end == pytest.approx(start)
    assert sum(b - a for a, b in bounds) == pytest.approx(137)


def test_profile_locate_uses_segment_durations_for_eta():
    # Straight line, ~69 mi per degree of latitude. First half is slow (3h), second fast (1h).
    coords = [(0, 0), (0, 1), (0, 2)]
    profile = build_profile(coords, total_seconds=4 * 3600, segment_seconds=[3 * 3600, 3600])
    _, secs_mid = profile.locate(profile.total_miles / 2)
    assert secs_mid == pytest.approx(3 * 3600, rel=0.01)  # linear spreading would say 2h


def test_profile_falls_back_to_proportional_time():
    profile = build_profile([(0, 0), (0, 1), (0, 2)], total_seconds=7200, segment_seconds=None)
    _, secs = profile.locate(profile.total_miles / 2)
    assert secs == pytest.approx(3600, rel=0.01)


def test_profile_locate_clamps_to_route_ends():
    profile = build_profile([(0, 0), (0, 1)], 3600)
    assert profile.locate(-5)[1] == 0
    assert profile.locate(10_000)[1] == pytest.approx(3600)


def test_slice_returns_points_between_distances():
    profile = build_profile([(0, 0), (0, 1), (0, 2), (0, 3)], 3600)
    piece = profile.slice(profile.total_miles * 0.2, profile.total_miles * 0.8)
    assert piece[0][1] == pytest.approx(0.6, abs=0.01) and piece[-1][1] == pytest.approx(2.4, abs=0.01)
    assert [round(p[1]) for p in piece[1:-1]] == [1, 2]


def test_simplify_drops_collinear_points_but_keeps_corners():
    line = [(0, 0), (1, 0.00001), (2, 0), (2, 2)]
    out = simplify(line, 0.001)
    assert out == [(0, 0), (2, 0), (2, 2)]


def test_offset_point_moves_requested_distance():
    start = (-90.0, 40.0)
    assert haversine_mi(start, offset_point(start, 90, 15)) == pytest.approx(15, abs=0.1)


def test_distance_to_segment_measures_to_the_line_not_its_ends():
    a, b = (-90.0, 40.0), (-90.0, 42.0)  # ~138 mi long
    assert distance_to_segment_mi((-90.0, 41.0), a, b) == pytest.approx(0, abs=0.01)
    side = offset_point((-90.0, 41.0), 90, 5)
    assert distance_to_segment_mi(side, a, b) == pytest.approx(5, abs=0.05)
    assert distance_to_segment_mi((-90.0, 39.0), a, b) == pytest.approx(69.1, abs=0.5)
