from datetime import datetime, timezone

from trips.analysis import RouteAnalysis
from trips.geo import build_profile
from trips.recommend import explain, rank_routes
from trips.risk import Level

PROFILE = build_profile([(0, 0), (0, 1)], 3600)


def route(rid, severe=0.0, high=0.0, avg=0.0, minutes=60, no_travel=0.0, unknown=0.0):
    miles = {lvl: 0.0 for lvl in Level}
    miles[Level.SEVERE], miles[Level.HIGH], miles[Level.NO_TRAVEL] = severe, high, no_travel
    profile = build_profile([(0, 0), (0, 1)], minutes * 60)
    return RouteAnalysis(
        rid, f"Route {rid}", profile, [], miles, unknown, avg, Level.LOW, datetime(2026, 1, 1, tzinfo=timezone.utc)
    )


def order(*routes):
    return [r.route_id for r in rank_routes(list(routes))]


def test_fewest_severe_miles_wins_over_everything_else():
    a = route("A", severe=5, high=0, avg=0.1, minutes=30)
    b = route("B", severe=0, high=90, avg=2.5, minutes=300)
    assert order(a, b) == ["B", "A"]


def test_high_miles_break_a_severe_tie():
    assert order(route("A", high=20), route("B", high=10)) == ["B", "A"]


def test_average_risk_breaks_a_high_tie():
    assert order(route("A", avg=1.2), route("B", avg=0.8)) == ["B", "A"]


def test_travel_time_is_the_last_tiebreaker():
    assert order(route("A", minutes=120), route("B", minutes=90)) == ["B", "A"]


def test_no_travel_route_is_never_preferred_over_a_drivable_one():
    blocked = route("A", no_travel=10, minutes=10)
    drivable = route("B", severe=50, minutes=500)
    assert order(blocked, drivable) == ["B", "A"]


def test_explanation_names_the_deciding_criterion_and_the_time_trade_off():
    fast_but_severe = route("A", severe=12, minutes=100)
    safe_but_slow = route("B", severe=0, minutes=130)
    ranked = rank_routes([fast_but_severe, safe_but_slow])
    reasons = explain(ranked[0], ranked)
    assert "0 Severe miles versus 12" in reasons[0]
    assert "30 min slower" in reasons[1]


def test_negligible_average_risk_difference_does_not_beat_a_faster_route():
    fast = route("A", avg=0.03, minutes=60)
    slow = route("B", avg=0.00, minutes=120)
    assert order(fast, slow) == ["A", "B"]


def test_meaningful_average_risk_difference_still_wins():
    fast = route("A", avg=0.30, minutes=60)
    slow = route("B", avg=0.00, minutes=120)
    assert order(fast, slow) == ["B", "A"]


def test_a_route_cannot_win_by_having_no_forecast():
    has_gap = route("A", unknown=40, avg=0.0, minutes=60)
    fully_known = route("B", avg=0.5, minutes=120)
    assert order(has_gap, fully_known) == ["B", "A"]
    assert "miles without a forecast" in explain(*(lambda r: (r[0], r))(rank_routes([has_gap, fully_known])))[0]


def test_known_severe_miles_still_outrank_missing_data():
    assert order(route("A", severe=10), route("B", unknown=40)) == ["B", "A"]
