# Weather-Aware Truck Routing

A React and Django app that compares three driving routes using the weather at the truck's estimated arrival time at each checkpoint, together with the load weight, and recommends one route.

Live demo: https://truck-routing-web-kt4i.onrender.com

The demo runs on a free plan. If it has been idle, the first request can take about a minute.

## Features

- Inputs: origin, destination, departure time, load weight (lb) and checkpoint interval (10, 25 or 50 miles).
- Three route options, with an ETA at every checkpoint.
- Weather risk per checkpoint: Low, Moderate, High, Severe or No Travel.
- A recommended route with a short reason.
- A map with all routes, checkpoints and risk colours.
- A weather heatmap along the routes with a 0 to 48 hour slider.

## Run locally

Backend (Python 3.11+):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
DJANGO_DEBUG=1 python manage.py runserver 8000
```

Frontend (Node 20+), in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to the backend on port 8000. No API keys are needed.

Docker alternative: `docker compose up --build`.

Tests:

```bash
cd backend && pytest
cd frontend && npm test
```

## How it works

1. The API gets up to three routes from OSRM.
2. Checkpoints are placed every N miles and the ETA at each one is calculated from the route's segment durations.
3. The hourly forecast from Open-Meteo is read for each checkpoint, using the hour nearest to the ETA.
4. The risk level comes from the wind, rain and snow thresholds, then the load weight rules.
5. Routes are ranked by No Travel miles, Severe miles, High miles, miles without a forecast, average risk and travel time, in that order.
6. The response also contains 49 hourly heatmap frames, so moving the slider needs no extra requests.

## Project structure

```
backend/
  config/            Django settings and URLs
  trips/
    risk.py          thresholds and load rules
    geo.py           distances, ETA interpolation, route slicing
    analysis.py      checkpoints, ETAs and miles per risk level
    recommend.py     route ranking and the reason text
    heatmap.py       corridor points and hourly frames
    service.py       runs the whole analysis
    serializers.py   request validation and response format
    views.py         API endpoints
    services/        routing, weather and geocoding clients
    tests/
frontend/src/
  components/        map, form, route cards, heatmap slider
  api.ts, types.ts, risk.ts
```

## Assumptions

The brief leaves some details open. These are the choices made:

| Topic | Choice |
|---|---|
| Checkpoint interval | Selectable in the UI, default 25 miles. |
| Threshold edges | Lower bound inclusive (0.25 in/hr rain is High, 35 mph wind is High). For rain and snow, No Travel starts above 1.00 and 3.0, so exactly 1.00 is Severe. |
| Combining conditions | A checkpoint takes the worst of wind, rain and snow. The load rules can only raise it. |
| Load rules | "Over 30,000 lb" and "over 40,000 lb" are strict comparisons. |
| Wind | Sustained wind at 10 m. |
| Rain and snow | Hourly amounts in inches, used as inches per hour. Rain is `rain + showers`. Snow is snowfall depth. |
| Miles per risk level | Each checkpoint covers the road halfway to the previous and next checkpoint. |
| Average risk | Mile-weighted average of the level (0 to 4), compared to one decimal place. |
| No Travel | Used as the first ranking criterion, so a route with No Travel miles does not beat one without. |
| Heatmap hours | Hour 0 is the departure hour, then 48 more hours. |
| Third route | If OSRM returns fewer than three, extra routes are tried through waypoints beside the main route. If none is clearly different, fewer routes are shown. |
| Departure range | From 12 hours ago to 5 days ahead, which is the forecast window. |

## Limitations

- The public OSRM server and the free Open-Meteo tier have rate limits. Set `OSRM_URL` and `OPEN_METEO_API_KEY` for heavier use. The cache is in memory, so use Redis if running more than one worker.
- OSRM uses a car profile, so truck restrictions such as height and weight are not considered.
- ETAs use car speeds and do not include rest breaks, so on long trips later checkpoints are reached later than shown.
- Only the forecast is used, not road surface, visibility or weather alerts.
- Weather is checked at the checkpoints only. A smaller interval gives more coverage.

## API

`POST /api/analyze/`

```json
{
  "origin": "Dallas, TX",
  "destination": { "lat": 39.74, "lon": -104.99, "label": "Denver" },
  "departure": "2026-11-05T08:00:00Z",
  "load_lb": 45000,
  "interval_miles": 25
}
```

The response contains `routes` (geometry, summary and checkpoints with ETA, weather, level and reasons), `recommendation` and `heatmap`. `GET /api/geocode/?q=` returns place suggestions. Errors are returned as `{ "error": "message" }`.

## Deploy

`render.yaml` describes the API as a Docker service and the UI as a static site on Render, both on the free plan.

1. In Render, choose New, then Blueprint, and select this repository.
2. Create the services. Render asks for two values, which can be left empty for now.
3. Set `VITE_API_URL` on the UI service to the API address (for example `https://truck-routing-api.onrender.com`) and redeploy the UI. This value is read when the UI is built.
4. Set `CORS_ALLOWED_ORIGINS` on the API service to the UI address.

Addresses have no trailing slash. Free services sleep after 15 minutes without requests, so the first request after a pause takes about a minute.

## Data sources

[OSRM](https://project-osrm.org/) for routes, [Open-Meteo](https://open-meteo.com/) for the forecast, [Photon](https://photon.komoot.io/) for place search. Map data from OpenStreetMap contributors, basemap by CARTO.
