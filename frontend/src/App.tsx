import { useCallback, useRef, useState } from "react";
import { ApiError, analyze } from "./api";
import HeatmapControl from "./components/HeatmapControl";
import Legend from "./components/Legend";
import MapView, { type MapApi } from "./components/MapView";
import RouteCard from "./components/RouteCard";
import TripForm from "./components/TripForm";
import type { AnalyzeRequest, AnalyzeResponse } from "./types";

export default function App() {
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mapApi = useRef<MapApi | null>(null);
  const inflight = useRef<AbortController>();

  const run = useCallback(async (request: AnalyzeRequest) => {
    inflight.current?.abort();
    const ctl = new AbortController();
    inflight.current = ctl;
    setLoading(true);
    setError(null);
    try {
      const data = await analyze(request, ctl.signal);
      setResult(data);
      setSelectedId(data.recommendation.route_id);
    } catch (e) {
      if (ctl.signal.aborted) return;
      setResult(null); // remove the previous results
      setSelectedId(null);
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      if (!ctl.signal.aborted) setLoading(false);
    }
  }, []);

  const best = result?.routes.find((r) => r.recommended);
  const ordered = result ? [...result.routes].sort((a, b) => a.rank - b.rank) : [];

  return (
    <div className="app">
      <aside className="sidebar">
        <header>
          <h1>Weather-Aware Truck Routing</h1>
          <p className="sub">Compare routes by the weather your truck will actually meet, at the time it gets there.</p>
        </header>

        <TripForm loading={loading} onSubmit={run} />

        {error && <div className="card error" role="alert">{error}</div>}

        {result && best && (
          <section aria-live="polite" className="results">
            <div className="card recommendation">
              <h2>Recommended: {best.name}</h2>
              <ul>
                {result.recommendation.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {result.route_notice && <p className="notice" role="note">{result.route_notice}</p>}
            </div>
            {ordered.map((r) => (
              <RouteCard key={r.id} route={r} selected={r.id === selectedId} onSelect={() => setSelectedId(r.id)} />
            ))}
          </section>
        )}
      </aside>

      <main className="stage">
        <MapView result={result} selectedId={selectedId} onSelect={setSelectedId} apiRef={mapApi} />
        <Legend />
        {result && <HeatmapControl heatmap={result.heatmap} apiRef={mapApi} />}
        {loading && (
          <div className="overlay" role="status">
            <span className="spinner" />
            <p>Finding routes and checking the weather along the way…</p>
          </div>
        )}
        {!result && !loading && <div className="empty">Enter a trip to see routes, weather risk and the forecast heatmap.</div>}
      </main>
    </div>
  );
}
