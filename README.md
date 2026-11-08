# Weather-Aware Truck Routing

React + Django app that compares three driving routes by the **weather the truck will actually meet, at the time it gets there**, adjusted for **load weight**, and recommends the safest one.

## What it does

1. Enter origin, destination, departure date/time and load weight (lb).
2. The API fetches **3 route options**, drops a **checkpoint every 10 / 25 / 50 miles** (your choice), and estimates the **ETA at each checkpoint** from the route's per-segment durations.
3. It fetches the hourly forecast for each checkpoint and reads the hour **nearest the ETA**.
4. Each checkpoint is classified `Low / Moderate / High / Severe / No Travel` with the brief's wind, rain and snow thresholds plus the three load rules.
5. Routes are ranked and one is recommended, with a plain-English reason.
6. The map shows all routes (selected one coloured by risk), checkpoints with popups, and a **0 to 48 hour weather heatmap** driven by a slider.

## Run it

```bash
# Backend (Python 3.11+)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
DJANGO_DEBUG=1 python manage.py runserver 8000

# Frontend (Node 20+), in another terminal
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
```

No API keys are needed. Or run both with `docker compose up --build`.

```bash
cd backend && pytest        # 102 tests, no network needed
cd frontend && npm test && npm run build
```

## Architecture

```
React (Vite, TS, MapLibre GL)  --POST /api/analyze-->  Django REST API
                                                        |-- geocoding  (Photon / OSM)
                                                        |-- routing    (OSRM)
                                                        |-- weather    (Open-Meteo, batched + cached)
                                                        `-- risk engine + recommendation (pure Python)
```

```
backend/trips/
  risk.py        thresholds + load rules, pure functions (the core of the app)
  geo.py         distance, resampling, ETA interpolation, simplification
  analysis.py    route + weather source -> checkpoints, miles by level, avg risk
  recommend.py   ranking and the explanation text
  heatmap.py     corridor grid and 49 hourly frames
  service.py     orchestration: routes -> one batched weather fetch -> analysis -> heatmap
  services/      thin clients for the three external APIs
  tests/         risk boundaries, ETA logic, ranking, API contract (external calls stubbed)
frontend/src/
  components/MapView.tsx       all map layers; updated imperatively, never re-rendered per tick
  components/HeatmapControl    slider, play button, per-hour peak strip
```

### Key design decisions

* **The risk engine has no Django or network imports.** It is a table of thresholds and pure functions, so every boundary is unit-tested.
* **ETA, not departure time, picks the forecast hour.** A storm that arrives after the truck has passed does not count; a storm the truck reaches at 3 AM does. Tests assert this.
* **One batched weather fetch** covers every checkpoint and every heatmap point (50 locations per request, parallel, cached 30 min on 0.1 degree cells). A full analysis takes about 2 seconds.
* **Heatmap slider is client-side only.** The API returns all 49 hourly frames in one response (about 30 KB gzipped). Dragging the slider changes one MapLibre paint property per animation frame: no network, no React re-render. Measured: sweeping all 49 hours in 860 ms with a median frame time of 8.3 ms.
* **Heatmap colour is the true risk level**, not point density. MapLibre's built-in heatmap layer colours by how many points overlap, so a dense cluster of Moderate points would look red (Severe). A blurred, level-coloured point field cannot misreport the level.
* **Honest about missing data.** If an ETA falls outside the forecast, or the provider returns no value, that stretch is "unknown" (hatched on the bar, with a warning) and heatmap hours turn grey, "No forecast". Missing data is never shown as Low, and a route cannot win by having less of it.

## Assumptions (the brief is silent or ambiguous)

| Topic | Decision |
|---|---|
| "Every 10 / 25 / 50 miles" | A selector in the UI, default 25. |
| Threshold edges | Lower bound inclusive: 0.25 in/hr rain is High, 35 mph is High. 34.5 mph is Moderate. For rain and snow the No Travel bound is strict (`> 1.00`, `> 3.0`), so exactly 1.00 is Severe. |
| Combining wind, rain, snow | Checkpoint level is the worst of the three, then the load rules can only **raise** it. |
| Load rules | `> 30,000 lb` and `> 40,000 lb` are strict. 45-54 mph with a load at or under 30,000 lb stays Severe (the base rating). |
| Wind measure | Sustained 10 m wind. Gusts are one constant away (`WIND_VARIABLE`) and arguably safer for trucks. |
| Rain / snow units | Hourly amounts in inches, used as in/hr. Rain is Open-Meteo `rain + showers`, because `rain` alone excludes convective rain such as thunderstorms. Snow is snowfall depth, not water equivalent. |
| "Severe / High miles" | Each checkpoint owns the road from the midpoint with the previous checkpoint to the midpoint with the next; miles are summed per level. |
| Average risk | Mile-weighted average of the 0-4 level, compared at 0.1 resolution so a trivial difference does not beat a meaningfully faster route. |
| No Travel | Not listed in the brief's ranking, so it is the first sort key: a route with No Travel miles never beats one without. If all routes have it, the banner says so. |
| Ranking | Lexicographic: No Travel miles, Severe miles, High miles, miles without a forecast, average risk, travel time. |
| Heatmap time axis | Hour 0 is the departure hour; the slider covers the next 48 hours. Its risk uses the load weight too. |
| Third route | OSRM often returns 1-2 alternatives. If so, extra routes are requested through waypoints pushed sideways from the main route, kept only if clearly different (35% or more of their length), under 1.5x its length, and not a there-and-back trip up a dead end. If no such road exists (Miami to Key West), fewer than 3 routes are shown and the UI says so. |
| Departure range | From 12 hours ago to 5 days ahead (the forecast window). |

## Limitations and what I would do next

* OSRM's public demo server and Open-Meteo's free tier (600 locations/min) are fine for a demo, not production. Set `OSRM_URL` and `OPEN_METEO_API_KEY` for real use; the cache should move to Redis if the API runs more than one worker.
* The OSRM `driving` profile is a car profile: no truck restrictions (height, weight, hazmat). A truck-aware router (HERE, GraphHopper truck profile) is the obvious upgrade.
* **ETAs use car speeds and assume non-stop driving.** Trucks are slower and US drivers have an 11-hour driving limit, so on long trips the truck reaches later checkpoints later than shown, and the forecast hour shifts with it. This is the first thing I would fix for real use.
* The forecast is a point model: no road-surface conditions, visibility, ice, or alerts (NWS).
* A route is only analysed at checkpoints, so a gust front between two checkpoints can be missed; a smaller interval narrows this.
* Next: truck speeds and rest breaks in the ETA, persist/share trips, depart-later suggestions ("leaving 3 h later avoids the Severe stretch"), and a frontend test for the map layers.

## API

`POST /api/analyze/`
```json
{ "origin": "Dallas, TX", "destination": {"lat": 39.74, "lon": -104.99, "label": "Denver"},
  "departure": "2026-11-05T08:00:00Z", "load_lb": 45000, "interval_miles": 25 }
```
Returns `routes[]` (geometry, summary, checkpoints with ETA / weather / level / reasons), `recommendation`, and `heatmap` (`hours[]`, GeoJSON points with `r0..r48` levels). `GET /api/geocode/?q=` powers autocomplete. Errors are always `{ "error": "message" }`.

## Deploy

`render.yaml` is a Render blueprint (API as Docker, UI as a static site). Set `VITE_API_URL` on the UI to the API origin, and `CORS_ALLOWED_ORIGINS` on the API to the UI origin. Free tiers sleep when idle, so open the app once before sharing it.

## Data sources

[OSRM](https://project-osrm.org/) routing, [Open-Meteo](https://open-meteo.com/) forecast, [Photon](https://photon.komoot.io/) geocoding, map data (c) OpenStreetMap contributors, basemap (c) CARTO.
