import { useState, type FormEvent } from "react";
import { MAX_LOAD_LB, defaultDeparture, parseLoad } from "../risk";
import type { AnalyzeRequest, Place } from "../types";
import PlaceInput from "./PlaceInput";

const INTERVALS = [10, 25, 50] as const;
const LOAD_PRESETS = [
  { label: "Light", lb: 20_000 },
  { label: "Typical", lb: 40_000 },
  { label: "Heavy", lb: 60_000 },
];

interface Props {
  loading: boolean;
  onSubmit(request: AnalyzeRequest): void;
}

const blank = (v: Place | string) => (typeof v === "string" ? v.trim() === "" : false);

export default function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | string>("");
  const [destination, setDestination] = useState<Place | string>("");
  const [departure, setDeparture] = useState(defaultDeparture());
  const [load, setLoad] = useState("40000");
  const [interval, setInterval] = useState<number>(25);
  const [error, setError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const lb = parseLoad(load);
    if (blank(origin) || blank(destination)) return setError("Enter both an origin and a destination.");
    if (!departure || Number.isNaN(new Date(departure).getTime())) return setError("Choose a departure date and time.");
    if (lb === null) return setError(`Enter a load weight between 0 and ${MAX_LOAD_LB.toLocaleString("en-US")} lb.`);
    setError(null);
    onSubmit({ origin, destination, departure: new Date(departure).toISOString(), load_lb: lb, interval_miles: interval });
  };

  const swap = () => {
    setOrigin(destination);
    setDestination(origin);
  };

  const lb = Number(load);
  const loadNote =
    lb > 40_000 ? "Over 40,000 lb: wind of 35 mph or more is rated Severe; 45 mph or more is No Travel."
    : lb > 30_000 ? "Over 30,000 lb: wind of 45 mph or more is No Travel."
    : "Wind of 55 mph or more is No Travel for any load.";

  return (
    <form className="card form" onSubmit={submit} noValidate>
      <div className="swap-row">
        <div className="places">
          <PlaceInput label="Origin" value={origin} onChange={setOrigin} placeholder="e.g. Chicago, IL" />
          <PlaceInput label="Destination" value={destination} onChange={setDestination} placeholder="e.g. Houston, TX" />
        </div>
        <button type="button" className="icon-btn" onClick={swap} aria-label="Swap origin and destination" title="Swap">
          ⇅
        </button>
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input id="departure" type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight (lb)</label>
          <input id="load" type="number" inputMode="numeric" min={0} max={MAX_LOAD_LB} step={1000} value={load} onChange={(e) => setLoad(e.target.value)} />
        </div>
      </div>

      <div className="chips" role="group" aria-label="Load presets">
        {LOAD_PRESETS.map((p) => (
          <button key={p.label} type="button" className={`chip ${lb === p.lb ? "on" : ""}`} onClick={() => setLoad(String(p.lb))}>
            {p.label} {p.lb.toLocaleString("en-US")}
          </button>
        ))}
      </div>
      <p className="hint">{loadNote}</p>

      <div className="field">
        <span className="label" id="interval-label">Weather checkpoint every</span>
        <div className="segmented" role="radiogroup" aria-labelledby="interval-label">
          {INTERVALS.map((n) => (
            <button key={n} type="button" role="radio" aria-checked={interval === n} className={interval === n ? "on" : ""} onClick={() => setInterval(n)}>
              {n} mi
            </button>
          ))}
        </div>
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary" type="submit" disabled={loading}>
        {loading ? "Analyzing…" : "Find safest route"}
      </button>
    </form>
  );
}
