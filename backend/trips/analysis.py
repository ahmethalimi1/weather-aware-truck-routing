"""Turns a route + a weather source into checkpoints, per-level mileage and a summary."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from .geo import Coord, RouteProfile, checkpoint_distances, segment_bounds, simplify
from .risk import Assessment, Level, Weather, assess


class WeatherSource(Protocol):
    def at(self, lat: float, lon: float, when: datetime) -> Weather | None:
        """Forecast for the hour nearest `when`, or None if outside the forecast horizon."""


@dataclass
class Checkpoint:
    index: int
    distance_miles: float
    position: Coord
    eta: datetime
    segment_miles: float
    segment_coords: list[Coord]
    weather: Weather | None
    assessment: Assessment | None

    @property
    def level(self) -> Level | None:
        return self.assessment.level if self.assessment else None


@dataclass
class RouteAnalysis:
    route_id: str
    name: str
    profile: RouteProfile
    checkpoints: list[Checkpoint]
    miles_by_level: dict[Level, float]
    unknown_miles: float
    avg_risk: float
    max_level: Level | None  # None when no checkpoint has a forecast
    arrival: datetime
    warnings: list[str] = field(default_factory=list)

    @property
    def distance_miles(self) -> float:
        return self.profile.total_miles

    @property
    def duration_seconds(self) -> float:
        return self.profile.total_seconds


def analyze_route(
    route_id: str,
    name: str,
    profile: RouteProfile,
    departure: datetime,
    load_lb: float,
    interval_miles: float,
    weather: WeatherSource,
) -> RouteAnalysis:
    distances = checkpoint_distances(profile.total_miles, interval_miles)
    bounds = segment_bounds(distances)

    checkpoints: list[Checkpoint] = []
    miles_by_level = {lvl: 0.0 for lvl in Level}
    unknown = 0.0
    risk_weighted = 0.0
    known_miles = 0.0

    for i, (dist, (seg_start, seg_end)) in enumerate(zip(distances, bounds)):
        pos, seconds = profile.locate(dist)
        eta = departure + timedelta(seconds=seconds)
        wx = weather.at(pos[1], pos[0], eta)
        result = assess(wx, load_lb) if wx else None
        seg_miles = seg_end - seg_start

        if result is None:
            unknown += seg_miles
        else:
            miles_by_level[result.level] += seg_miles
            risk_weighted += int(result.level) * seg_miles
            known_miles += seg_miles

        checkpoints.append(
            Checkpoint(
                index=i,
                distance_miles=dist,
                position=pos,
                eta=eta,
                segment_miles=seg_miles,
                segment_coords=simplify(profile.slice(seg_start, seg_end)),
                weather=wx,
                assessment=result,
            )
        )

    known_levels = [c.level for c in checkpoints if c.level is not None]
    warnings = []
    if unknown > 0.05:
        warnings.append(f"Forecast not available for {unknown:.0f} mi of this route (beyond forecast horizon).")
    if miles_by_level[Level.NO_TRAVEL] > 0:
        warnings.append(f"{miles_by_level[Level.NO_TRAVEL]:.0f} mi classified No Travel for this load.")

    return RouteAnalysis(
        route_id=route_id,
        name=name,
        profile=profile,
        checkpoints=checkpoints,
        miles_by_level=miles_by_level,
        unknown_miles=unknown,
        avg_risk=risk_weighted / known_miles if known_miles else 0.0,
        max_level=max(known_levels, default=None),
        arrival=departure + timedelta(seconds=profile.total_seconds),
        warnings=warnings,
    )
