"""Request validation and response shaping."""
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .geo import simplify
from .risk import Level
from .service import TripResult

INTERVAL_CHOICES = (10, 25, 50)
MAX_ROUTE_OPTIONS = 3
MAX_LOAD_LB = 80_000  # US federal gross vehicle weight limit
MAX_DEPARTURE_AHEAD = timedelta(days=5)  # forecast covers 7 days; leave room for a long trip
MAX_DEPARTURE_PAST = timedelta(hours=12)


class LocationField(serializers.Field):
    """Either a free-text place name or an explicit {lat, lon, label} chosen from autocomplete."""

    def to_internal_value(self, data):
        if isinstance(data, str) and data.strip():
            return {"query": data.strip()}
        if isinstance(data, dict):
            try:
                lat, lon = float(data["lat"]), float(data["lon"])
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError("Location needs numeric lat and lon.")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise serializers.ValidationError("Latitude/longitude out of range.")
            return {"lat": lat, "lon": lon, "label": str(data.get("label") or f"{lat:.4f}, {lon:.4f}")}
        raise serializers.ValidationError("Provide a place name or {lat, lon}.")

    def to_representation(self, value):
        return value


class AnalyzeRequestSerializer(serializers.Serializer):
    origin = LocationField()
    destination = LocationField()
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_miles = serializers.ChoiceField(choices=INTERVAL_CHOICES, default=25)

    def validate_departure(self, value):
        now = timezone.now()
        if value < now - MAX_DEPARTURE_PAST:
            raise serializers.ValidationError("Departure is too far in the past to use a forecast.")
        if value > now + MAX_DEPARTURE_AHEAD:
            raise serializers.ValidationError("Departure must be within the next 5 days (forecast range).")
        return value


def _weather(wx):
    if wx is None:
        return None
    return {"wind_mph": round(wx.wind_mph, 1), "rain_in_hr": round(wx.rain_in_hr, 3), "snow_in_hr": round(wx.snow_in_hr, 3)}


def _level(level):
    return None if level is None else {"value": int(level), "label": level.label}


def _route_notice(count: int) -> str | None:
    if count >= MAX_ROUTE_OPTIONS:
        return None
    routes = "route" if count == 1 else "routes"
    return f"Only {count} distinct {routes} found for this trip, because no other reasonable road alternative exists."


def to_payload(result: TripResult, origin: dict, destination: dict) -> dict:
    best = result.ranked[0]
    fastest = min(result.routes, key=lambda r: r.duration_seconds)
    rank_of = {r.route_id: i + 1 for i, r in enumerate(result.ranked)}

    routes = []
    for r in result.routes:
        routes.append(
            {
                "id": r.route_id,
                "name": r.name,
                "rank": rank_of[r.route_id],
                "recommended": r.route_id == best.route_id,
                "fastest": r.route_id == fastest.route_id,
                "distance_miles": round(r.distance_miles, 1),
                "duration_minutes": round(r.duration_seconds / 60),
                "arrival": r.arrival.isoformat(),
                "geometry": simplify(r.profile.coords),
                "summary": {
                    "max_level": _level(r.max_level),
                    "avg_risk": round(r.avg_risk, 2),
                    "miles_by_level": {lvl.name.lower(): round(r.miles_by_level[lvl], 1) for lvl in Level},
                    "unknown_miles": round(r.unknown_miles, 1),
                },
                "warnings": r.warnings,
                "checkpoints": [
                    {
                        "index": c.index,
                        "distance_miles": round(c.distance_miles, 1),
                        "lon": round(c.position[0], 5),
                        "lat": round(c.position[1], 5),
                        "eta": c.eta.isoformat(),
                        "segment_miles": round(c.segment_miles, 1),
                        "segment": c.segment_coords,
                        "weather": _weather(c.weather),
                        "level": _level(c.level),
                        "reasons": c.assessment.reasons if c.assessment else [],
                    }
                    for c in r.checkpoints
                ],
            }
        )

    return {
        "request": {
            "origin": origin,
            "destination": destination,
            "departure": result.departure.isoformat(),
            "load_lb": result.load_lb,
            "interval_miles": result.interval_miles,
        },
        "recommendation": {"route_id": best.route_id, "reasons": result.recommendation_reasons},
        "route_notice": _route_notice(len(result.routes)),
        "routes": routes,
        "heatmap": result.heatmap,
        "levels": [{"value": int(lvl), "label": lvl.label} for lvl in Level],
    }
