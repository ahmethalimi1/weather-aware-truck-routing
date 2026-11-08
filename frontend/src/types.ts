export type Coord = [number, number]; // [lon, lat]

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface LevelInfo {
  value: number;
  label: string;
}

export interface WeatherReading {
  wind_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
}

export interface Checkpoint {
  index: number;
  distance_miles: number;
  lon: number;
  lat: number;
  eta: string;
  segment_miles: number;
  segment: Coord[];
  weather: WeatherReading | null;
  level: LevelInfo | null;
  reasons: string[];
}

export type MilesByLevel = Record<"low" | "moderate" | "high" | "severe" | "no_travel", number>;

export interface Route {
  id: string;
  name: string;
  rank: number;
  recommended: boolean;
  fastest: boolean;
  distance_miles: number;
  duration_minutes: number;
  arrival: string;
  geometry: Coord[];
  summary: { max_level: LevelInfo | null; avg_risk: number; miles_by_level: MilesByLevel; unknown_miles: number };
  warnings: string[];
  checkpoints: Checkpoint[];
}

export interface HeatmapData {
  hours: string[];
  geojson: GeoJSON.FeatureCollection<GeoJSON.Point, Record<string, number>>;
}

export interface AnalyzeResponse {
  request: { origin: Place; destination: Place; departure: string; load_lb: number; interval_miles: number };
  recommendation: { route_id: string; reasons: string[] };
  route_notice: string | null;
  routes: Route[];
  heatmap: HeatmapData;
}

export interface AnalyzeRequest {
  origin: Place | string;
  destination: Place | string;
  departure: string;
  load_lb: number;
  interval_miles: number;
}
