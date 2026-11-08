from datetime import datetime, timedelta, timezone

import pytest

from trips.analysis import analyze_route
from trips.geo import build_profile
from trips.risk import Level, Weather

DEPARTURE = datetime(2026, 1, 10, 6, 0, tzinfo=timezone.utc)
# ~207 miles due north, 4 hours at constant speed.
PROFILE = build_profile([(0, 0), (0, 3)], total_seconds=4 * 3600)


class FakeWeather:
    """Returns weather chosen by the time we are asked about, recording each lookup."""

    def __init__(self, by_hour: dict[int, Weather]):
        self.by_hour = by_hour
        self.asked: list[datetime] = []

    def at(self, lat, lon, when):
        self.asked.append(when)
        return self.by_hour.get(when.hour, Weather(5, 0, 0))


def run(weather, load=20_000, interval=50):
    return analyze_route("r1", "Route A", PROFILE, DEPARTURE, load, interval, weather)


def test_weather_is_sampled_at_each_checkpoints_eta_not_departure_time():
    fake = FakeWeather({})
    result = run(fake)
    assert fake.asked[0] == DEPARTURE
    assert fake.asked[-1] == DEPARTURE + timedelta(hours=4)
    assert [c.eta for c in result.checkpoints] == fake.asked
    assert result.arrival == DEPARTURE + timedelta(hours=4)


def test_storm_that_arrives_later_only_hits_checkpoints_reached_then():
    # Severe wind only at 08:00 and later; checkpoints before that see calm weather.
    stormy = {h: Weather(50, 0, 0) for h in range(8, 12)}
    result = run(FakeWeather(stormy), load=10_000)
    levels = [c.level for c in result.checkpoints]
    assert levels[0] == Level.LOW
    assert levels[-1] == Level.SEVERE
    assert result.max_level == Level.SEVERE


def test_miles_by_level_sum_to_route_length():
    stormy = {9: Weather(40, 0.3, 0), 10: Weather(50, 0, 0)}
    result = run(FakeWeather(stormy))
    assert sum(result.miles_by_level.values()) + result.unknown_miles == pytest.approx(PROFILE.total_miles)


def test_average_risk_is_mile_weighted():
    result = run(FakeWeather({h: Weather(40, 0, 0) for h in range(0, 24)}), load=10_000)
    assert result.avg_risk == pytest.approx(int(Level.HIGH))


def test_heavy_load_changes_the_outcome_on_the_same_weather():
    weather = {h: Weather(40, 0, 0) for h in range(0, 24)}
    assert run(FakeWeather(weather), load=20_000).max_level == Level.HIGH
    assert run(FakeWeather(weather), load=50_000).max_level == Level.SEVERE


def test_missing_forecast_is_reported_not_treated_as_safe():
    class NoForecast:
        def at(self, *a):
            return None

    result = run(NoForecast())
    assert result.unknown_miles == pytest.approx(PROFILE.total_miles)
    assert result.miles_by_level[Level.LOW] == 0
    assert result.max_level is None  # not "Low"
    assert any("not available" in w for w in result.warnings)


def test_no_travel_adds_a_warning():
    result = run(FakeWeather({h: Weather(60, 0, 0) for h in range(24)}))
    assert result.max_level == Level.NO_TRAVEL
    assert any("No Travel" in w for w in result.warnings)
