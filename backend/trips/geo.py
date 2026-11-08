"""Geometry helpers: distances, resampling along a route, ETA interpolation, simplification."""
import bisect
import math
from dataclasses import dataclass

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344

Coord = tuple[float, float]  # (lon, lat), matching GeoJSON order


def haversine_mi(a: Coord, b: Coord) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def distance_to_segment_mi(p: Coord, a: Coord, b: Coord) -> float:
    """Shortest distance in miles from p to the segment a-b."""
    scale = math.cos(math.radians(p[1]))
    ax, ay = (a[0] - p[0]) * scale, a[1] - p[1]
    bx, by = (b[0] - p[0]) * scale, b[1] - p[1]
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
    return math.radians(math.hypot(ax + t * dx, ay + t * dy)) * EARTH_RADIUS_MI


@dataclass
class RouteProfile:
    """A route polyline with cumulative distance (miles) and time (seconds) per vertex."""

    coords: list[Coord]
    cum_miles: list[float]
    cum_seconds: list[float]

    @property
    def total_miles(self) -> float:
        return self.cum_miles[-1]

    @property
    def total_seconds(self) -> float:
        return self.cum_seconds[-1]

    def locate(self, miles: float) -> tuple[Coord, float]:
        """Return (position, seconds from departure) at a given distance along the route."""
        miles = min(max(miles, 0.0), self.total_miles)
        i = bisect.bisect_right(self.cum_miles, miles) - 1
        i = min(max(i, 0), len(self.coords) - 2)
        span = self.cum_miles[i + 1] - self.cum_miles[i]
        t = 0.0 if span <= 0 else (miles - self.cum_miles[i]) / span
        a, b = self.coords[i], self.coords[i + 1]
        pos = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        secs = self.cum_seconds[i] + (self.cum_seconds[i + 1] - self.cum_seconds[i]) * t
        return pos, secs

    def slice(self, start_mi: float, end_mi: float) -> list[Coord]:
        """Polyline between two distances along the route."""
        start_mi, end_mi = max(0.0, start_mi), min(self.total_miles, end_mi)
        points = [self.locate(start_mi)[0]]
        lo = bisect.bisect_right(self.cum_miles, start_mi)
        hi = bisect.bisect_left(self.cum_miles, end_mi)
        points.extend(self.coords[lo:hi])
        points.append(self.locate(end_mi)[0])
        return points


def build_profile(
    coords: list[Coord],
    total_seconds: float,
    segment_seconds: list[float] | None = None,
) -> RouteProfile:
    """Build cumulative distance and time. Uses the segment durations when available,
    otherwise spreads total_seconds in proportion to distance."""
    cum_mi = [0.0]
    for a, b in zip(coords, coords[1:]):
        cum_mi.append(cum_mi[-1] + haversine_mi(a, b))

    if segment_seconds and len(segment_seconds) == len(coords) - 1:
        cum_s = [0.0]
        for s in segment_seconds:
            cum_s.append(cum_s[-1] + s)
        if cum_s[-1] > 0:  # match the total reported by the API
            scale = total_seconds / cum_s[-1]
            cum_s = [s * scale for s in cum_s]
    else:
        total = cum_mi[-1] or 1.0
        cum_s = [m / total * total_seconds for m in cum_mi]
    return RouteProfile(coords, cum_mi, cum_s)


def checkpoint_distances(total_miles: float, interval_miles: float) -> list[float]:
    """0, interval, 2*interval ... and always the final point at the destination."""
    if total_miles <= 0:
        return [0.0]
    n = int(total_miles // interval_miles)
    points = [i * interval_miles for i in range(n + 1)]
    if total_miles - points[-1] > 1e-6:
        points.append(total_miles)
    return points


def segment_bounds(distances: list[float]) -> list[tuple[float, float]]:
    """The stretch of road each checkpoint is responsible for: from the midpoint to the previous
    checkpoint to the midpoint to the next one (clipped to the route ends)."""
    bounds = []
    for i, d in enumerate(distances):
        start = d if i == 0 else (distances[i - 1] + d) / 2
        end = d if i == len(distances) - 1 else (d + distances[i + 1]) / 2
        bounds.append((start, end))
    return bounds


def offset_point(origin: Coord, bearing_deg: float, miles: float) -> Coord:
    """Point `miles` away from origin along a bearing (spherical approximation)."""
    lon1, lat1 = math.radians(origin[0]), math.radians(origin[1])
    brg, ang = math.radians(bearing_deg), miles / EARTH_RADIUS_MI
    lat2 = math.asin(math.sin(lat1) * math.cos(ang) + math.cos(lat1) * math.sin(ang) * math.cos(brg))
    lon2 = lon1 + math.atan2(math.sin(brg) * math.sin(ang) * math.cos(lat1), math.cos(ang) - math.sin(lat1) * math.sin(lat2))
    return (math.degrees(lon2), math.degrees(lat2))


def bearing_deg(a: Coord, b: Coord) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def simplify(coords: list[Coord], tolerance_deg: float = 0.0006) -> list[Coord]:
    """Douglas-Peucker line simplification. The default tolerance is about 65 m."""
    if len(coords) < 3:
        return list(coords)
    keep = [False] * len(coords)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]
    while stack:
        lo, hi = stack.pop()
        (x1, y1), (x2, y2) = coords[lo], coords[hi]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        worst, idx = 0.0, -1
        for i in range(lo + 1, hi):
            px, py = coords[i]
            if norm == 0:
                dist = math.hypot(px - x1, py - y1)
            else:
                dist = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm
            if dist > worst:
                worst, idx = dist, i
        if worst > tolerance_deg and idx != -1:
            keep[idx] = True
            stack.extend([(lo, idx), (idx, hi)])
    return [c for c, k in zip(coords, keep) if k]
