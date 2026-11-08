"""Place search via Photon (OpenStreetMap data, free, no key)."""
import logging

import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)

PHOTON_URL = "https://photon.komoot.io/api/"
USER_AGENT = "spotter-truck-routing/0.1"


class GeocodingError(Exception):
    pass


def _label(props: dict) -> str:
    parts = []
    for key in ("name", "street", "city", "state", "country"):
        value = props.get(key)
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


def search(query: str, limit: int = 5) -> list[dict]:
    query = query.strip()
    if len(query) < 2:
        return []
    cache_key = f"geo:{limit}:{query.lower()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        resp = requests.get(
            PHOTON_URL,
            params={"q": query, "limit": limit, "lang": "en"},
            headers={"User-Agent": USER_AGENT},
            timeout=settings.EXTERNAL_API_TIMEOUT,
        )
        resp.raise_for_status()
        features = resp.json()["features"]
    except (requests.RequestException, KeyError, ValueError) as exc:
        log.warning("Photon request failed: %s", exc)
        raise GeocodingError("The place search service is unavailable right now. Please try again shortly.") from exc

    results, seen = [], set()
    for f in features:
        label = _label(f["properties"])
        if label in seen:  # Photon returns the city and its county/district as identical labels
            continue
        seen.add(label)
        results.append({"label": label, "lat": f["geometry"]["coordinates"][1], "lon": f["geometry"]["coordinates"][0]})
    cache.set(cache_key, results, 24 * 3600)
    return results


def resolve(query: str) -> dict:
    results = search(query, limit=1)
    if not results:
        raise GeocodingError(f'Could not find a location for "{query}".')
    return results[0]
