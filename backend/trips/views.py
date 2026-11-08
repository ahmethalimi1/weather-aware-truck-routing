from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .geo import haversine_mi
from .serializers import AnalyzeRequestSerializer, to_payload
from .service import run_trip
from .services import geocoding, routing
from .services.weather import WeatherUnavailable


MIN_TRIP_MILES = 0.5


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
def geocode(request):
    try:
        return Response({"results": geocoding.search(request.query_params.get("q", ""))})
    except geocoding.GeocodingError as exc:
        return _error(str(exc), status.HTTP_502_BAD_GATEWAY)


@api_view(["POST"])
def analyze(request):
    serializer = AnalyzeRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        origin = data["origin"] if "lat" in data["origin"] else geocoding.resolve(data["origin"]["query"])
        destination = data["destination"] if "lat" in data["destination"] else geocoding.resolve(data["destination"]["query"])
        if haversine_mi((origin["lon"], origin["lat"]), (destination["lon"], destination["lat"])) < MIN_TRIP_MILES:
            return _error("Origin and destination are the same place.", status.HTTP_400_BAD_REQUEST)
        result = run_trip(
            (origin["lon"], origin["lat"]),
            (destination["lon"], destination["lat"]),
            data["departure"],
            data["load_lb"],
            data["interval_miles"],
        )
    except geocoding.GeocodingError as exc:
        return _error(str(exc), status.HTTP_400_BAD_REQUEST)
    except routing.RoutingError as exc:
        return _error(str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
    except WeatherUnavailable as exc:
        return _error(str(exc), status.HTTP_502_BAD_GATEWAY)

    return Response(to_payload(result, origin, destination))
