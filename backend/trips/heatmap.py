"""Heatmap data for the 0-48 hour slider: points near the routes with a risk level for each hour.

Each point has `r0` to `r48` (0-4, or -1 when there is no forecast).
"""
from datetime import datetime, timedelta

from .geo import Coord, RouteProfile, bearing_deg, offset_point
from .risk import Weather, assess

HOURS = 48  # frames 0..48 inclusive
UNKNOWN_LEVEL = -1  # no forecast for this hour
MAX_POINTS = 150  # each point needs one weather lookup
BASE_SPACING_MI = 20.0
CORRIDOR_OFFSET_MI = 15.0


def floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def corridor_points(profiles: list[RouteProfile]) -> list[Coord]:
    """Points every ~20 miles along each route, plus points 15 miles to each side."""
    spacing = BASE_SPACING_MI
    while True:
        seen: dict[tuple[float, float], Coord] = {}
        for profile in profiles:
            d = 0.0
            while d <= profile.total_miles + 1e-6:
                pos, _ = profile.locate(d)
                ahead, _ = profile.locate(min(d + 1.0, profile.total_miles))
                behind, _ = profile.locate(max(d - 1.0, 0.0))
                heading = bearing_deg(behind, ahead) if behind != ahead else 0.0
                for off in (-CORRIDOR_OFFSET_MI, 0.0, CORRIDOR_OFFSET_MI):
                    p = pos if off == 0 else offset_point(pos, (heading + 90) % 360, off)
                    seen.setdefault((round(p[1], 1), round(p[0], 1)), p)  # dedupe on a 0.1 deg grid
                d += spacing
        if len(seen) <= MAX_POINTS:
            return list(seen.values())
        spacing *= 1.25


def build_heatmap(points: list[Coord], store, departure: datetime, load_lb: float) -> dict:
    start = floor_hour(departure)
    hours = [start + timedelta(hours=h) for h in range(HOURS + 1)]
    features = []
    for lon, lat in points:
        props = {}
        for h, when in enumerate(hours):
            wx: Weather | None = store.at(lat, lon, when)
            props[f"r{h}"] = int(assess(wx, load_lb).level) if wx else UNKNOWN_LEVEL
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 4), round(lat, 4)]}, "properties": props})
    return {
        "hours": [h.isoformat() for h in hours],
        "geojson": {"type": "FeatureCollection", "features": features},
    }
