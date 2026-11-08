from datetime import datetime, timedelta, timezone

import pytest
from django.core.cache import cache

from trips.services import weather
from trips.services.weather import Forecast, ForecastStore, _parse

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def payload(**over):
    hourly = {
        "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
        "wind_speed_10m": [10.0, 20.0],
        "rain": [0.06, 0.0],
        "showers": [0.04, 0.3],
        "snowfall": [0.0, 0.0],
    }
    hourly.update(over)
    return {"hourly": hourly}


def test_rain_includes_convective_showers():
    forecast = _parse(payload())
    assert forecast.at(START).rain_in_hr == 0.1  # exactly on the Moderate threshold, no float drift
    assert forecast.at(START + timedelta(hours=1)).rain_in_hr == 0.3  # a thunderstorm is High, not Low


def test_showers_are_requested_from_the_provider():
    assert "showers" in weather.HOURLY.split(",")


@pytest.mark.parametrize("field", ["wind_speed_10m", "rain", "showers", "snowfall"])
def test_a_missing_value_is_unknown_not_calm(field):
    forecast = _parse(payload(**{field: [None, None]}))
    assert forecast.at(START) is None


def test_lookup_uses_the_nearest_hour_and_stops_at_the_horizon():
    forecast = Forecast(START, (1.0, 2.0), (0.0, 0.0), (0.0, 0.0))
    assert forecast.at(START + timedelta(minutes=40)).wind_mph == 2.0
    assert forecast.at(START + timedelta(hours=5)) is None
    assert forecast.at(START - timedelta(hours=5)) is None


def test_prefetch_uses_the_cache_on_the_second_call(monkeypatch):
    cache.clear()
    calls = []

    def fake(keys):
        calls.append(keys)
        return {k: Forecast(START, (1.0,), (0.0,), (0.0,)) for k in keys}

    monkeypatch.setattr(weather, "_fetch_batch", fake)
    ForecastStore().prefetch([(40.01, -90.01), (40.02, -90.02)])  # same 0.1 degree cell
    store = ForecastStore()
    store.prefetch([(40.0, -90.0)])
    assert len(calls) == 1 and len(calls[0]) == 1
    assert store.at(40.0, -90.0, START).wind_mph == 1.0
