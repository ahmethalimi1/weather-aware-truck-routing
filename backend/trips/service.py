"""Orchestrates one trip analysis: routes -> weather -> risk -> ranking -> heatmap."""
from dataclasses import dataclass
from datetime import datetime

from . import heatmap, recommend
from .analysis import RouteAnalysis, analyze_route
from .geo import Coord, build_profile, checkpoint_distances
from .services import routing
from .services.weather import ForecastStore

ROUTE_NAMES = ("Route A", "Route B", "Route C")


@dataclass
class TripResult:
    routes: list[RouteAnalysis]  # in display order (fastest first)
    ranked: list[RouteAnalysis]
    recommendation_reasons: list[str]
    heatmap: dict
    departure: datetime
    load_lb: float
    interval_miles: float


def run_trip(
    origin: Coord,
    destination: Coord,
    departure: datetime,
    load_lb: float,
    interval_miles: float,
    store: ForecastStore | None = None,
) -> TripResult:
    store = store or ForecastStore()
    raw_routes = routing.get_routes(origin, destination)
    profiles = [build_profile(r.coords, r.duration_seconds, r.segment_seconds) for r in raw_routes]

    # Load the weather for all checkpoints and heatmap points at once.
    checkpoint_positions = []
    for p in profiles:
        for d in checkpoint_distances(p.total_miles, interval_miles):
            lon, lat = p.locate(d)[0]
            checkpoint_positions.append((lat, lon))
    corridor = heatmap.corridor_points(profiles)
    store.prefetch(checkpoint_positions + [(lat, lon) for lon, lat in corridor])

    routes = [
        analyze_route(f"r{i + 1}", ROUTE_NAMES[i], profile, departure, load_lb, interval_miles, store)
        for i, profile in enumerate(profiles)
    ]
    ranked = recommend.rank_routes(routes)
    return TripResult(
        routes=routes,
        ranked=ranked,
        recommendation_reasons=recommend.explain(ranked[0], ranked),
        heatmap=heatmap.build_heatmap(corridor, store, departure, load_lb),
        departure=departure,
        load_lb=load_lb,
        interval_miles=interval_miles,
    )
