"""Driving routes from OSRM (free, no key). Returns up to 3 genuinely different routes.

OSRM's `alternatives` often returns only 1-2 routes. When that happens we ask for extra routes
forced through a waypoint pushed sideways from the middle of the main route, and keep those
that are clearly different and not absurd detours.
"""
import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

from ..geo import Coord, bearing_deg, distance_to_segment_mi, haversine_mi, offset_point, simplify

log = logging.getLogger(__name__)

MAX_ROUTES = 3
MAX_DETOUR_RATIO = 1.5  # extra routes longer than 1.5x the fastest are not useful alternatives
MIN_DIFFERENCE = 0.35  # extra routes must differ from existing ones on at least 35% of their length
SAME_ROAD_MILES = 2.0
# (position along the main route, sideways offset as a share of its length)
VIA_ATTEMPTS = ((0.5, 0.18), (0.5, 0.32), (0.3, 0.25), (0.7, 0.25))
MIN_VIA_OFFSET_MI, MAX_VIA_OFFSET_MI = 8.0, 90.0
EXTRA_ROUTE_BUDGET_S = 6.0
EXTRA_ROUTE_TIMEOUT_S = 5.0
MAX_RETRACED_SHARE = 0.05


class RoutingError(Exception):
    pass


@dataclass
class RawRoute:
    coords: list[Coord]
    duration_seconds: float
    segment_seconds: list[float] | None


def _call(waypoints: list[Coord], alternatives: bool, timeout: float | None = None) -> list[RawRoute]:
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in waypoints)
    url = f"{settings.OSRM_URL}/route/v1/driving/{path}"
    params = {
        "alternatives": "3" if alternatives else "false",
        "overview": "full",
        "geometries": "geojson",
        "annotations": "duration",
        "steps": "false",
    }
    try:
        resp = requests.get(url, params=params, timeout=timeout or settings.EXTERNAL_API_TIMEOUT)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("OSRM request failed: %s", exc)
        raise RoutingError("The routing service is unavailable right now. Please try again shortly.") from exc
    if data.get("code") != "Ok":
        raise RoutingError(data.get("message") or f"No route found ({data.get('code')})")

    routes = []
    for r in data["routes"]:
        coords = [tuple(c) for c in r["geometry"]["coordinates"]]
        seg = [d for leg in r["legs"] for d in leg["annotation"]["duration"]]
        routes.append(RawRoute(coords, r["duration"], seg if len(seg) == len(coords) - 1 else None))
    return routes


def _overlap_fraction(candidate: list[Coord], existing: list[Coord]) -> float:
    """Share of the candidate that runs within SAME_ROAD_MILES of an existing route."""
    ref = simplify(existing, 0.003)
    step = max(1, len(candidate) // 60)
    sample = candidate[::step]
    segments = list(zip(ref, ref[1:]))
    near = sum(1 for p in sample if any(distance_to_segment_mi(p, a, b) <= SAME_ROAD_MILES for a, b in segments))
    return near / len(sample)


def _length_mi(coords: list[Coord]) -> float:
    return sum(haversine_mi(a, b) for a, b in zip(coords, coords[1:]))


def _retraces_itself(coords: list[Coord]) -> bool:
    """True for a there-and-back trip, which is what a waypoint on a dead-end road produces."""
    rounded = [(round(lon, 4), round(lat, 4)) for lon, lat in coords]
    return 1 - len(set(rounded)) / len(rounded) > MAX_RETRACED_SHARE


def _via_points(main: RawRoute, main_len: float):
    """Waypoints pushed sideways from the main route, nearest and most central first."""
    side = bearing_deg(main.coords[0], main.coords[-1])
    for position, scale in VIA_ATTEMPTS:
        anchor = main.coords[int((len(main.coords) - 1) * position)]
        detour = min(MAX_VIA_OFFSET_MI, max(MIN_VIA_OFFSET_MI, main_len * scale))
        for turn in (90, -90):
            yield offset_point(anchor, (side + turn) % 360, detour)


def get_routes(origin: Coord, destination: Coord) -> list[RawRoute]:
    """origin/destination are (lon, lat). Routes are returned fastest first.

    Fewer than MAX_ROUTES can be returned when no other sensible road exists (Miami to Key West)."""
    routes = sorted(_call([origin, destination], alternatives=True), key=lambda r: r.duration_seconds)[:MAX_ROUTES]
    if len(routes) >= MAX_ROUTES:
        return routes

    main = routes[0]
    main_len = _length_mi(main.coords)
    deadline = time.monotonic() + EXTRA_ROUTE_BUDGET_S
    for via in _via_points(main, main_len):
        if len(routes) >= MAX_ROUTES or time.monotonic() > deadline:
            break
        try:
            cand = _call([origin, via, destination], alternatives=False, timeout=EXTRA_ROUTE_TIMEOUT_S)[0]
        except RoutingError as exc:
            log.info("Extra route via waypoint failed: %s", exc)
            continue
        if _length_mi(cand.coords) > main_len * MAX_DETOUR_RATIO or _retraces_itself(cand.coords):
            continue
        if all(_overlap_fraction(cand.coords, r.coords) < 1 - MIN_DIFFERENCE for r in routes):
            routes.append(cand)

    return sorted(routes, key=lambda r: r.duration_seconds)
