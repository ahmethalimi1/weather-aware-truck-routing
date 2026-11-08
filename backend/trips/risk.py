"""Weather risk classification.

Lower bounds are inclusive: 0.25 in/hr of rain is High and 34.5 mph wind is Moderate.
For rain and snow, No Travel starts above 1.00 and 3.0, so exactly 1.00 is Severe.
"""
from dataclasses import dataclass, field
from enum import IntEnum


class Level(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


# (lower bound, level), checked from the most severe.
WIND_BANDS = ((55.0, Level.NO_TRAVEL), (45.0, Level.SEVERE), (35.0, Level.HIGH), (25.0, Level.MODERATE))
# Rain and snow above these values are No Travel.
RAIN_NO_TRAVEL_ABOVE = 1.00
RAIN_BANDS = ((0.50, Level.SEVERE), (0.25, Level.HIGH), (0.10, Level.MODERATE))
SNOW_NO_TRAVEL_ABOVE = 3.0
SNOW_BANDS = ((2.0, Level.SEVERE), (1.0, Level.HIGH), (0.5, Level.MODERATE))

# Load rules in pounds: "over 30,000" and "over 40,000".
HEAVY_LOAD_NO_TRAVEL_LB = 30_000
HEAVY_LOAD_SEVERE_LB = 40_000


def _from_bands(value: float, bands) -> Level:
    for lower, level in bands:
        if value >= lower:
            return level
    return Level.LOW


def classify_wind(mph: float) -> Level:
    return _from_bands(mph, WIND_BANDS)


def classify_rain(in_per_hr: float) -> Level:
    if in_per_hr > RAIN_NO_TRAVEL_ABOVE:
        return Level.NO_TRAVEL
    return _from_bands(in_per_hr, RAIN_BANDS)


def classify_snow(in_per_hr: float) -> Level:
    if in_per_hr > SNOW_NO_TRAVEL_ABOVE:
        return Level.NO_TRAVEL
    return _from_bands(in_per_hr, SNOW_BANDS)


def load_adjusted_wind_level(mph: float, load_lb: float) -> Level | None:
    """Minimum level forced by the load rules, or None if no rule applies."""
    if mph >= 55:
        return Level.NO_TRAVEL
    if 45 <= mph < 55 and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return Level.NO_TRAVEL
    if 35 <= mph < 45 and load_lb > HEAVY_LOAD_SEVERE_LB:
        return Level.SEVERE
    return None


@dataclass(frozen=True)
class Weather:
    wind_mph: float
    rain_in_hr: float
    snow_in_hr: float


@dataclass(frozen=True)
class Assessment:
    level: Level
    wind_level: Level
    rain_level: Level
    snow_level: Level
    reasons: list[str] = field(default_factory=list)


def assess(weather: Weather, load_lb: float) -> Assessment:
    """Final risk level for one checkpoint: worst of wind/rain/snow, then the load rules."""
    wind = classify_wind(weather.wind_mph)
    rain = classify_rain(weather.rain_in_hr)
    snow = classify_snow(weather.snow_in_hr)
    level = max(wind, rain, snow)

    reasons = []
    for name, value, unit, lvl in (
        ("Wind", weather.wind_mph, "mph", wind),
        ("Rain", weather.rain_in_hr, "in/hr", rain),
        ("Snow", weather.snow_in_hr, "in/hr", snow),
    ):
        if lvl >= Level.MODERATE:
            reasons.append(f"{name} {value:g} {unit}: {lvl.label}")

    forced = load_adjusted_wind_level(weather.wind_mph, load_lb)
    if forced is not None and forced > level:
        reasons.append(
            f"Load rule: {weather.wind_mph:g} mph wind with {load_lb:,.0f} lb raises risk to {forced.label}"
        )
        level = forced

    return Assessment(level, wind, rain, snow, reasons)
