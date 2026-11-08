import maplibregl, { type GeoJSONSource, type MapMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, type MutableRefObject } from "react";
import { formatDateTime, levelColorExpression } from "../risk";
import type { AnalyzeResponse, Checkpoint, Route } from "../types";

export interface MapApi {
  setHeatHour(hour: number): void;
  setHeatVisible(visible: boolean): void;
}

interface Props {
  result: AnalyzeResponse | null;
  selectedId: string | null;
  onSelect(routeId: string): void;
  apiRef: MutableRefObject<MapApi | null>;
}

const STYLE_URL = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

// The heatmap is a field of blurred points coloured by their true risk level (not by point density,
// which would turn any dense cluster red), so a Moderate area can never look Severe.
const heatColor = (hour: number) => levelColorExpression(`r${hour}`);
const heatOpacity = (hour: number) => ["case", [">=", ["coalesce", ["get", `r${hour}`], 0], 1], 0.62, 0.2];
const heatSort = (hour: number) => ["coalesce", ["get", `r${hour}`], 0]; // riskier points draw on top

function paintHeat(map: maplibregl.Map, hour: number) {
  map.setPaintProperty("heat", "circle-color", heatColor(hour) as never);
  map.setPaintProperty("heat", "circle-opacity", heatOpacity(hour) as never);
  map.setLayoutProperty("heat", "circle-sort-key", heatSort(hour) as never);
}

function routeFeatures(routes: Route[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: routes.map((r) => ({
      type: "Feature",
      properties: { id: r.id },
      geometry: { type: "LineString", coordinates: r.geometry },
    })),
  };
}

function segmentFeatures(routes: Route[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: routes.flatMap((r) =>
      r.checkpoints.map((c) => ({
        type: "Feature" as const,
        properties: { routeId: r.id, level: c.level?.value ?? -1 },
        geometry: { type: "LineString" as const, coordinates: c.segment },
      })),
    ),
  };
}

function checkpointFeatures(routes: Route[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: routes.flatMap((r) =>
      r.checkpoints.map((c) => ({
        type: "Feature" as const,
        properties: { routeId: r.id, index: c.index, level: c.level?.value ?? -1 },
        geometry: { type: "Point" as const, coordinates: [c.lon, c.lat] },
      })),
    ),
  };
}

function popupContent(route: Route, c: Checkpoint): HTMLElement {
  const el = document.createElement("div");
  el.className = "popup";
  const add = (tag: string, text: string, cls?: string) => {
    const n = document.createElement(tag);
    n.textContent = text;
    if (cls) n.className = cls;
    el.appendChild(n);
  };
  add("strong", `${route.name}: mile ${Math.round(c.distance_miles)}`);
  add("div", `ETA ${formatDateTime(c.eta)}`, "muted");
  if (c.weather) {
    add("div", `Wind ${c.weather.wind_mph} mph | Rain ${c.weather.rain_in_hr} in/hr | Snow ${c.weather.snow_in_hr} in/hr`);
    add("div", `Risk: ${c.level?.label}`, "risk");
    c.reasons.forEach((r) => add("div", r, "reason"));
  } else {
    add("div", "No forecast available for this time.", "muted");
  }
  return el;
}

export default function MapView({ result, selectedId, onSelect, apiRef }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const readyRef = useRef(false);
  const markers = useRef<maplibregl.Marker[]>([]);
  const resultRef = useRef(result);
  const onSelectRef = useRef(onSelect);
  const pendingFrame = useRef<number | null>(null);
  resultRef.current = result;
  onSelectRef.current = onSelect;

  // One-time map and layer setup.
  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current!,
      style: STYLE_URL,
      center: [-96, 38.5],
      zoom: 3.4,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    map.on("load", () => {
      map.addSource("heat", { type: "geojson", data: EMPTY });
      map.addSource("routes", { type: "geojson", data: EMPTY });
      map.addSource("segments", { type: "geojson", data: EMPTY });
      map.addSource("checkpoints", { type: "geojson", data: EMPTY });

      map.addLayer({
        id: "heat",
        type: "circle",
        source: "heat",
        layout: { "circle-sort-key": heatSort(0) as never },
        paint: {
          // Radius grows with zoom so each point always covers about 2.5x the corridor sampling spacing.
          "circle-radius": ["interpolate", ["exponential", 2], ["zoom"], 3, 11, 5, 42, 8, 300],
          "circle-blur": 1,
          "circle-color": heatColor(0) as never,
          "circle-opacity": heatOpacity(0) as never,
        },
      });
      map.addLayer({
        id: "routes-hit", type: "line", source: "routes",
        paint: { "line-width": 18, "line-opacity": 0 },
      });
      map.addLayer({
        id: "routes-other", type: "line", source: "routes",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#7b8794", "line-width": 4, "line-opacity": 0.75 },
      });
      map.addLayer({
        id: "route-casing", type: "line", source: "routes",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-width": 10 },
      });
      map.addLayer({
        id: "segments", type: "line", source: "segments",
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: { "line-color": levelColorExpression("level") as never, "line-width": 6 },
      });
      map.addLayer({
        id: "checkpoints", type: "circle", source: "checkpoints",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 1.8, 6, 3.5, 9, 6],
          "circle-color": levelColorExpression("level") as never,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });

      for (const id of ["routes-hit", "checkpoints"]) {
        map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
      }
      map.on("click", "routes-hit", (e: MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
        // Routes share roads: a click on the selected route (or its checkpoints) must not switch to one beneath it.
        if (map.queryRenderedFeatures(e.point, { layers: ["checkpoints", "segments"] }).length) return;
        const id = e.features?.[0]?.properties?.id;
        if (id) onSelectRef.current(id);
      });
      map.on("click", "checkpoints", (e: MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
        const props = e.features?.[0]?.properties;
        const res = resultRef.current;
        if (!props || !res) return;
        const route = res.routes.find((r) => r.id === props.routeId);
        const cp = route?.checkpoints[props.index as number];
        if (!route || !cp) return;
        new maplibregl.Popup({ offset: 10, maxWidth: "280px" })
          .setLngLat([cp.lon, cp.lat])
          .setDOMContent(popupContent(route, cp))
          .addTo(map);
      });

      readyRef.current = true;
      map.fire("cv-ready");
    });

    apiRef.current = {
      setHeatHour(hour) {
        // Coalesce rapid slider events into one paint update per frame.
        if (pendingFrame.current !== null) cancelAnimationFrame(pendingFrame.current);
        pendingFrame.current = requestAnimationFrame(() => {
          pendingFrame.current = null;
          if (readyRef.current) paintHeat(map, hour);
        });
      },
      setHeatVisible(visible) {
        if (readyRef.current) map.setLayoutProperty("heat", "visibility", visible ? "visible" : "none");
      },
    };

    return () => {
      if (pendingFrame.current !== null) cancelAnimationFrame(pendingFrame.current);
      markers.current.forEach((m) => m.remove());
      map.remove();
      mapRef.current = null;
      readyRef.current = false;
      apiRef.current = null;
    };
  }, [apiRef]);

  // Push new results into the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const set = (id: string, data: GeoJSON.FeatureCollection) => (map.getSource(id) as GeoJSONSource).setData(data);
      markers.current.forEach((m) => m.remove());
      markers.current = [];
      if (!result) {
        set("heat", EMPTY); set("routes", EMPTY); set("segments", EMPTY); set("checkpoints", EMPTY);
        return;
      }
      set("heat", result.heatmap.geojson);
      set("routes", routeFeatures(result.routes));
      set("segments", segmentFeatures(result.routes));
      set("checkpoints", checkpointFeatures(result.routes));
      paintHeat(map, 0);

      const pin = (text: string, lngLat: [number, number], cls: string) => {
        const el = document.createElement("div");
        el.className = `pin ${cls}`;
        el.textContent = text;
        markers.current.push(new maplibregl.Marker({ element: el }).setLngLat(lngLat).addTo(map));
      };
      const { origin, destination } = result.request;
      pin("A", [origin.lon, origin.lat], "pin-a");
      pin("B", [destination.lon, destination.lat], "pin-b");

      const bounds = new maplibregl.LngLatBounds();
      result.routes.forEach((r) => r.geometry.forEach((c) => bounds.extend(c)));
      // Keep the whole trip clear of the heatmap panel, whatever the map size.
      const { clientWidth: w, clientHeight: h } = map.getContainer();
      map.fitBounds(bounds, {
        padding: { top: Math.min(90, h * 0.18), bottom: Math.min(190, h * 0.4), left: Math.min(60, w * 0.1), right: Math.min(60, w * 0.1) },
        duration: 900,
      });
    };
    if (readyRef.current) apply();
    else map.once("cv-ready" as never, apply);
  }, [result]);

  // Selecting a route only changes layer filters, so it is instant.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const id = selectedId ?? "";
      map.setFilter("routes-other", ["!=", ["get", "id"], id]);
      map.setFilter("routes-hit", ["!=", ["get", "id"], id]);
      map.setFilter("route-casing", ["==", ["get", "id"], id]);
      map.setFilter("segments", ["==", ["get", "routeId"], id]);
      map.setFilter("checkpoints", ["==", ["get", "routeId"], id]);
    };
    if (readyRef.current) apply();
    else map.once("cv-ready" as never, apply);
  }, [selectedId]);

  return <div ref={container} className="map" role="region" aria-label="Route map" />;
}
