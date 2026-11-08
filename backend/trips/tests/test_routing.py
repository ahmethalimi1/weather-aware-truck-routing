import pytest

from trips.services import routing
from trips.services.routing import RawRoute, get_routes

ORIGIN, DEST = (-90.0, 40.0), (-90.0, 42.0)


def line(lon_mid=-90.0):
    # Starts and ends at the same points, bulging to lon_mid in the middle.
    pts = [(-90.0, 40.0), (lon_mid, 40.5), (lon_mid, 41.0), (lon_mid, 41.5), (-90.0, 42.0)]
    out = []
    for a, b in zip(pts, pts[1:]):
        out += [(a[0] + (b[0] - a[0]) * i / 20, a[1] + (b[1] - a[1]) * i / 20) for i in range(20)]
    return out + [pts[-1]]


def route(lon_mid=-90.0, minutes=100):
    return RawRoute(line(lon_mid), minutes * 60, None)


def fake_call(main_routes, via_routes):
    via = iter(via_routes)

    def call(waypoints, alternatives, timeout=None):
        if alternatives:
            return main_routes
        item = next(via, None)
        if item is None or isinstance(item, Exception):
            raise item or routing.RoutingError("no route")
        return [item]

    return call


def test_three_alternatives_are_used_as_is_fastest_first(monkeypatch):
    routes = [route(-89, 120), route(-90, 100), route(-91, 110)]
    monkeypatch.setattr(routing, "_call", fake_call(routes, []))
    assert [r.duration_seconds for r in get_routes(ORIGIN, DEST)] == [6000, 6600, 7200]


def test_missing_routes_are_filled_through_a_waypoint(monkeypatch):
    monkeypatch.setattr(routing, "_call", fake_call([route()], [route(-89.5, 130), route(-90.5, 140)]))
    assert len(get_routes(ORIGIN, DEST)) == 3


def test_a_waypoint_route_on_the_same_road_is_rejected(monkeypatch):
    monkeypatch.setattr(routing, "_call", fake_call([route()], [route(-90.0, 130)]))
    assert len(get_routes(ORIGIN, DEST)) == 1


def test_an_absurd_detour_is_rejected(monkeypatch):
    monkeypatch.setattr(routing, "_call", fake_call([route()], [route(-80.0, 900)]))
    assert len(get_routes(ORIGIN, DEST)) == 1


def test_a_there_and_back_trip_up_a_dead_end_is_rejected(monkeypatch):
    coords = line(-89.5)
    spur = [(coords[50][0] + i * 0.005, coords[50][1]) for i in range(1, 16)]
    dead_end = RawRoute(coords[:51] + spur + spur[-2::-1] + coords[50:], 7000, None)
    monkeypatch.setattr(routing, "_call", fake_call([route()], [dead_end]))
    assert len(get_routes(ORIGIN, DEST)) == 1


def test_failed_waypoints_do_not_lose_the_main_route(monkeypatch):
    fails = [routing.RoutingError("no route")] * 8
    monkeypatch.setattr(routing, "_call", fake_call([route()], fails))
    assert len(get_routes(ORIGIN, DEST)) == 1


def test_no_route_at_all_is_an_error(monkeypatch):
    def none(waypoints, alternatives, timeout=None):
        raise routing.RoutingError("No route found")

    monkeypatch.setattr(routing, "_call", none)
    with pytest.raises(routing.RoutingError):
        get_routes(ORIGIN, DEST)
