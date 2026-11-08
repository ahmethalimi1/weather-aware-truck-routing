import type { MilesByLevel } from "./types";

export const LEVELS = [
  { value: 0, key: "low", label: "Low", color: "#2f9e62" },
  { value: 1, key: "moderate", label: "Moderate", color: "#e3b505" },
  { value: 2, key: "high", label: "High", color: "#f08a24" },
  { value: 3, key: "severe", label: "Severe", color: "#d63a2f" },
  { value: 4, key: "no_travel", label: "No Travel", color: "#5b1a5e" },
] as const;

export const NO_FORECAST_COLOR = "#9aa4b2";

export const levelColor = (value: number): string => (value < 0 ? NO_FORECAST_COLOR : LEVELS[Math.min(value, 4)].color);

/** MapLibre `match` expression: a feature's numeric `level` property -> colour. */
export const levelColorExpression = (property = "level"): unknown[] => [
  "match",
  ["get", property],
  ...LEVELS.flatMap((l) => [l.value, l.color]),
  NO_FORECAST_COLOR,
];

export const MAX_LOAD_LB = 80_000;

/** The load in pounds, or null if the text is empty or outside the legal range. */
export function parseLoad(text: string): number | null {
  if (text.trim() === "") return null;
  const lb = Number(text);
  return Number.isFinite(lb) && lb >= 0 && lb <= MAX_LOAD_LB ? lb : null;
}

export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}

export function formatMiles(miles: number): string {
  return `${Math.round(miles).toLocaleString("en-US")} mi`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function formatHour(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { weekday: "short", hour: "numeric" });
}

/** Share of the route (0-1) spent at each level, in LEVELS order, for the stacked bar. */
export function levelShares(miles: MilesByLevel, unknown = 0): { key: string; label: string; color: string; share: number; miles: number }[] {
  const total = Object.values(miles).reduce((a, b) => a + b, 0) + unknown || 1;
  return LEVELS.map((l) => ({ key: l.key, label: l.label, color: l.color, share: miles[l.key] / total, miles: miles[l.key] }));
}

/** Default departure for the form: the next full hour, formatted for <input type="datetime-local">. */
export function defaultDeparture(now = new Date()): string {
  const d = new Date(now);
  d.setHours(d.getHours() + 1, 0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}
