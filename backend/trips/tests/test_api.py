from datetime import datetime, timedelta, timezone

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from trips.services import routing
from trips.services import weather as weather_service
from trips.services.weather import Forecast


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


def straight_route(offset_lon=0.0, minutes=240):
    coords = [(-90 + offset_lon, 40 + i * 0.05) for i in range(61)]  # ~207 mi north
    return routing.RawRoute(coords, minutes * 60, None)


def calm_forecast(wind=5.0):
    start = (datetime.now(timezone.utc) - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    n = 8 * 24
    return Forecast(start, (wind,) * n, (0.0,) * n, (0.0,) * n)


@pytest.fixture
def stub_services(monkeypatch):
    state = {"wind": 5.0}
    monkeypatch.setattr(
        routing, "get_routes", lambda o, d: [straight_route(0, 240), straight_route(1, 260), straight_route(-1, 300)]
    )

    def fake_fetch(keys):
        # The middle route (lon -89) sits under a storm; the others are calm.
        out = {}
        for k in keys:
            wind = 50.0 if abs(k[1] - (-89.0)) < 0.5 else 5.0
            out[k] = calm_forecast(wind)
        return out

    monkeypatch.setattr(weather_service, "_fetch_batch", fake_fetch)
    return state


def payload(**over):
    body = {
        "origin": {"lat": 40.0, "lon": -90.0, "label": "A"},
        "destination": {"lat": 43.0, "lon": -90.0, "label": "B"},
        "departure": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "load_lb": 35_000,
        "interval_miles": 25,
    }
    body.update(over)
    return body


def test_analyze_returns_three_routes_with_checkpoints_and_recommendation(client, stub_services):
    resp = client.post("/api/analyze/", payload(), format="json")
    assert resp.status_code == 200, resp.content
    data = resp.json()
    assert len(data["routes"]) == 3
    recommended = [r for r in data["routes"] if r["recommended"]]
    assert len(recommended) == 1 and recommended[0]["id"] == data["recommendation"]["route_id"]
    assert data["recommendation"]["reasons"]

    route = data["routes"][0]
    assert route["checkpoints"][0]["distance_miles"] == 0
    assert route["checkpoints"][-1]["distance_miles"] == pytest.approx(route["distance_miles"], abs=0.2)
    cp = route["checkpoints"][1]
    assert {"eta", "weather", "level", "lat", "lon", "segment"} <= cp.keys()
    assert set(route["summary"]["miles_by_level"]) == {"low", "moderate", "high", "severe", "no_travel"}


def test_storm_route_is_penalised_and_calm_route_recommended(client, stub_services):
    data = client.post("/api/analyze/", payload(), format="json").json()
    by_id = {r["id"]: r for r in data["routes"]}
    # Route r1 is the first stubbed route (lon -90, calm). Wind 50 mph + 35,000 lb => No Travel on r2.
    assert by_id["r2"]["summary"]["miles_by_level"]["no_travel"] > 0
    assert data["recommendation"]["route_id"] != "r2"
    assert by_id["r2"]["recommended"] is False


def test_heatmap_has_49_hourly_frames_per_point(client, stub_services):
    data = client.post("/api/analyze/", payload(), format="json").json()
    hm = data["heatmap"]
    assert len(hm["hours"]) == 49
    feature = hm["geojson"]["features"][0]
    assert all(f"r{h}" in feature["properties"] for h in range(49))
    assert len(hm["geojson"]["features"]) <= 150


@pytest.mark.parametrize(
    "override,fragment",
    [
        ({"load_lb": -5}, "load_lb"),
        ({"load_lb": 200_000}, "load_lb"),
        ({"interval_miles": 15}, "interval_miles"),
        ({"departure": "not-a-date"}, "departure"),
        ({"departure": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()}, "departure"),
        ({"departure": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()}, "departure"),
        ({"origin": {"lat": 999, "lon": 0}}, "origin"),
    ],
)
def test_invalid_input_returns_readable_error(client, stub_services, override, fragment):
    resp = client.post("/api/analyze/", payload(**override), format="json")
    assert resp.status_code == 400
    assert fragment in resp.json()["error"]


def test_weather_outage_is_a_502_with_a_message(client, monkeypatch):
    monkeypatch.setattr(routing, "get_routes", lambda o, d: [straight_route()])

    def boom(keys):
        raise weather_service.WeatherUnavailable("Weather service unavailable: timeout")

    monkeypatch.setattr(weather_service, "_fetch_batch", boom)
    resp = client.post("/api/analyze/", payload(), format="json")
    assert resp.status_code == 502
    assert "Weather service unavailable" in resp.json()["error"]


def test_no_route_found_is_a_422(client, monkeypatch):
    def none(o, d):
        raise routing.RoutingError("No route found")

    monkeypatch.setattr(routing, "get_routes", none)
    resp = client.post("/api/analyze/", payload(), format="json")
    assert resp.status_code == 422


def test_weather_rate_limit_gives_a_clear_message(client, monkeypatch):
    monkeypatch.setattr(routing, "get_routes", lambda o, d: [straight_route()])

    def limited(keys):
        raise weather_service.RateLimited()

    monkeypatch.setattr(weather_service, "_fetch_batch", limited)
    resp = client.post("/api/analyze/", payload(), format="json")
    assert resp.status_code == 502
    assert "try again in about a minute" in resp.json()["error"]


def test_same_origin_and_destination_is_rejected(client, stub_services):
    place = {"lat": 40.0, "lon": -90.0, "label": "A"}
    resp = client.post("/api/analyze/", payload(origin=place, destination=place), format="json")
    assert resp.status_code == 400
    assert "same place" in resp.json()["error"]


def test_fewer_than_three_routes_is_reported(client, monkeypatch, stub_services):
    monkeypatch.setattr(routing, "get_routes", lambda o, d: [straight_route()])
    data = client.post("/api/analyze/", payload(), format="json").json()
    assert len(data["routes"]) == 1
    assert "Only 1 distinct route" in data["route_notice"]


def test_three_routes_have_no_notice(client, stub_services):
    assert client.post("/api/analyze/", payload(), format="json").json()["route_notice"] is None


def test_hours_beyond_the_forecast_are_unknown_not_low(client, monkeypatch):
    monkeypatch.setattr(routing, "get_routes", lambda o, d: [straight_route()])
    start = (datetime.now(timezone.utc) - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)

    def short_forecast(keys):  # ends a few hours after departure
        return {k: Forecast(start, (5.0,) * 30, (0.0,) * 30, (0.0,) * 30) for k in keys}

    monkeypatch.setattr(weather_service, "_fetch_batch", short_forecast)
    data = client.post("/api/analyze/", payload(), format="json").json()
    props = data["heatmap"]["geojson"]["features"][0]["properties"]
    assert props["r0"] == 0
    assert props["r48"] == -1
