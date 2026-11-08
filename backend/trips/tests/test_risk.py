import pytest

from trips.risk import (
    Level,
    Weather,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
    load_adjusted_wind_level,
)

L, M, H, S, N = Level.LOW, Level.MODERATE, Level.HIGH, Level.SEVERE, Level.NO_TRAVEL


@pytest.mark.parametrize(
    "mph,expected",
    [(0, L), (24.9, L), (25, M), (34.9, M), (35, H), (44.9, H), (45, S), (54.9, S), (55, N), (80, N)],
)
def test_wind_thresholds(mph, expected):
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    "rate,expected",
    [(0, L), (0.099, L), (0.10, M), (0.249, M), (0.25, H), (0.499, H), (0.50, S), (1.00, S), (1.001, N), (3, N)],
)
def test_rain_thresholds(rate, expected):
    assert classify_rain(rate) == expected


@pytest.mark.parametrize(
    "rate,expected",
    [(0, L), (0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H), (2.0, S), (3.0, S), (3.01, N)],
)
def test_snow_thresholds(rate, expected):
    assert classify_snow(rate) == expected


@pytest.mark.parametrize(
    "mph,load,expected",
    [
        (60, 1_000, N),  # >=55 is No Travel for any load
        (55, 0, N),
        (50, 30_001, N),  # 45-54 and > 30,000 lb
        (50, 30_000, None),  # exactly 30,000 is not "over"
        (45, 30_001, N),
        (40, 40_001, S),  # 35-44 and > 40,000 lb
        (40, 40_000, None),
        (35, 80_000, S),
        (30, 80_000, None),  # rules do not apply below 35 mph
    ],
)
def test_load_rules(mph, load, expected):
    assert load_adjusted_wind_level(mph, load) == expected


def test_assess_takes_worst_condition():
    result = assess(Weather(wind_mph=10, rain_in_hr=0.3, snow_in_hr=0.6), load_lb=20_000)
    assert result.level == H
    assert result.wind_level == L and result.rain_level == H and result.snow_level == M


def test_assess_load_rule_raises_level_and_explains():
    light = assess(Weather(40, 0, 0), load_lb=30_000)
    heavy = assess(Weather(40, 0, 0), load_lb=45_000)
    assert light.level == H
    assert heavy.level == S
    assert any("Load rule" in r for r in heavy.reasons)


def test_assess_heavy_load_in_severe_wind_is_no_travel_but_light_is_severe():
    assert assess(Weather(50, 0, 0), 25_000).level == S
    assert assess(Weather(50, 0, 0), 35_000).level == N


def test_assess_never_lowers_level():
    # Severe from snow must not be reduced by a rule that only forces a lower minimum.
    assert assess(Weather(40, 0, 2.5), 45_000).level == S
    assert assess(Weather(40, 0, 4.0), 45_000).level == N


def test_calm_weather_is_low():
    result = assess(Weather(5, 0, 0), 80_000)
    assert result.level == L and result.reasons == []
