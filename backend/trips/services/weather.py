"""Hourly forecast from Open-Meteo (free, no API key), batched and cached."""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.core.cache import cache

from ..risk import Weather

log = logging.getLogger(__name__)

FREE_URL = "https://api.open-meteo.com/v1/forecast"
PAID_URL = "https://customer-api.open-meteo.com/v1/forecast"  # used when OPEN_METEO_API_KEY is set
# Sustained 10 m wind. Switch to "wind_gusts_10m" for a more conservative (gust-based) classification.
WIND_VARIABLE = "wind_speed_10m"
# Open-Meteo's `rain` only covers large-scale systems; convective rain (thunderstorms) is in `showers`.
HOURLY = f"{WIND_VARIABLE},rain,showers,snowfall"
BATCH_SIZE = 50
MAX_ATTEMPTS = 2
CACHE_TTL = 30 * 60
COORD_DECIMALS = 1  # 0.1 deg cells (~7 mi): finer than the forecast model grid, and nearby checkpoints share one request


class WeatherUnavailable(Exception):
    pass


class RateLimited(WeatherUnavailable):
    def __init__(self) -> None:
        super().__init__("The weather provider's request limit was reached. Please try again in about a minute.")


@dataclass(frozen=True)
class Forecast:
    start: datetime  # first hourly timestamp (UTC)
    wind: tuple[float | None, ...]
    rain: tuple[float | None, ...]
    snow: tuple[float | None, ...]

    def at(self, when: datetime) -> Weather | None:
        hours = (when - self.start).total_seconds() / 3600
        i = round(hours)
        if i < 0 or i >= len(self.wind):
            return None
        values = (self.wind[i], self.rain[i], self.snow[i])
        if any(v is None for v in values):  # the provider has no value: unknown, not calm
            return None
        return Weather(*values)


def _key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, COORD_DECIMALS), round(lon, COORD_DECIMALS))


def _cache_key(k: tuple[float, float]) -> str:
    return f"wx:{k[0]:.1f}:{k[1]:.1f}"


def _parse(payload: dict) -> Forecast:
    h = payload["hourly"]
    start = datetime.fromisoformat(h["time"][0]).replace(tzinfo=timezone.utc)
    total_rain = tuple(
        None if rain is None or showers is None else round(rain + showers, 3)
        for rain, showers in zip(h["rain"], h["showers"])
    )
    return Forecast(start, tuple(h[WIND_VARIABLE]), total_rain, tuple(h["snowfall"]))


def _fetch_batch(keys: list[tuple[float, float]]) -> dict[tuple[float, float], Forecast]:
    params = {
        "latitude": ",".join(str(k[0]) for k in keys),
        "longitude": ",".join(str(k[1]) for k in keys),
        "hourly": HOURLY,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "UTC",
        "forecast_days": 7,
        "past_days": 1,
    }
    url = FREE_URL
    if settings.OPEN_METEO_API_KEY:
        url, params["apikey"] = PAID_URL, settings.OPEN_METEO_API_KEY
    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = requests.get(url, params=params, timeout=settings.EXTERNAL_API_TIMEOUT)
            if resp.status_code == 429:  # the free tier allows 600 locations/minute
                last_error = RateLimited()
                time.sleep(2)
                continue
            resp.raise_for_status()
            data = resp.json()
            payloads = data if isinstance(data, list) else [data]  # single location returns an object
            return {k: _parse(p) for k, p in zip(keys, payloads)}
        except (requests.RequestException, KeyError, ValueError) as exc:
            last_error = exc
            log.warning("Open-Meteo batch failed (attempt %d): %s", attempt + 1, exc)
    if isinstance(last_error, RateLimited):
        raise last_error
    raise WeatherUnavailable("The weather service is unavailable right now. Please try again shortly.")


class ForecastStore:
    """Prefetches forecasts for many points in a few parallel requests, then serves lookups from memory."""

    def __init__(self) -> None:
        self._forecasts: dict[tuple[float, float], Forecast] = {}

    def prefetch(self, points: list[tuple[float, float]]) -> None:
        """`points` are (lat, lon)."""
        wanted = list({_key(lat, lon) for lat, lon in points})
        missing = []
        for k in wanted:
            cached = cache.get(_cache_key(k))
            if cached is not None:
                self._forecasts[k] = cached
            else:
                missing.append(k)
        if not missing:
            return

        batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=min(4, len(batches))) as pool:
            for result in pool.map(_fetch_batch, batches):
                for k, forecast in result.items():
                    self._forecasts[k] = forecast
                    cache.set(_cache_key(k), forecast, CACHE_TTL)

    def at(self, lat: float, lon: float, when: datetime) -> Weather | None:
        forecast = self._forecasts.get(_key(lat, lon))
        return forecast.at(when) if forecast else None
