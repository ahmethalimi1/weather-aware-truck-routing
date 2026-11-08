import { LEVELS, formatDateTime, formatDuration, formatMiles, levelColor, levelShares } from "../risk";
import type { Route } from "../types";

interface Props {
  route: Route;
  selected: boolean;
  onSelect(): void;
}

export default function RouteCard({ route, selected, onSelect }: Props) {
  const { summary } = route;
  const shares = levelShares(summary.miles_by_level, summary.unknown_miles);
  const risky = ["moderate", "high", "severe", "no_travel"] as const;

  return (
    <article className={`card route ${selected ? "selected" : ""}`}>
      <button type="button" className="route-head" onClick={onSelect} aria-pressed={selected}>
        <span className="route-title">
          {route.name}
          {route.recommended && <span className="badge good">Recommended</span>}
          {route.fastest && <span className="badge">Fastest</span>}
        </span>
        <span className="risk-pill" style={{ background: levelColor(summary.max_level?.value ?? -1) }}>
          {summary.max_level ? `Peak: ${summary.max_level.label}` : "No forecast"}
        </span>
      </button>

      <dl className="stats">
        <div><dt>Distance</dt><dd>{formatMiles(route.distance_miles)}</dd></div>
        <div><dt>Drive time</dt><dd>{formatDuration(route.duration_minutes)}</dd></div>
        <div><dt>Arrive</dt><dd>{formatDateTime(route.arrival)}</dd></div>
      </dl>

      <div className="bar" role="img" aria-label={`Miles by risk: ${shares.map((s) => `${Math.round(s.miles)} ${s.label}`).join(", ")}`}>
        {shares.filter((s) => s.share > 0).map((s) => (
          <span key={s.key} style={{ width: `${s.share * 100}%`, background: s.color }} title={`${s.label}: ${Math.round(s.miles)} mi`} />
        ))}
        {summary.unknown_miles > 0 && <span className="unknown" style={{ flex: 1 }} title="No forecast" />}
      </div>
      <p className="miles">
        {risky.map((k) => {
          const lvl = LEVELS.find((l) => l.key === k)!;
          return (
            <span key={k}>
              <i style={{ background: lvl.color }} />
              {lvl.label} {Math.round(summary.miles_by_level[k])} mi
            </span>
          );
        })}
        <span className="avg">Avg risk {summary.avg_risk.toFixed(2)} / 4</span>
      </p>

      {route.warnings.map((w) => (
        <p key={w} className="warning" role="note">⚠ {w}</p>
      ))}

      {selected && (
        <details className="checkpoints">
          <summary>{route.checkpoints.length} weather checkpoints</summary>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Mile</th><th>ETA</th><th>Wind</th><th>Rain</th><th>Snow</th><th>Risk</th></tr>
              </thead>
              <tbody>
                {route.checkpoints.map((c) => (
                  <tr key={c.index}>
                    <td>{Math.round(c.distance_miles)}</td>
                    <td>{new Date(c.eta).toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" })}</td>
                    <td>{c.weather ? `${c.weather.wind_mph} mph` : "–"}</td>
                    <td>{c.weather ? `${c.weather.rain_in_hr}` : "–"}</td>
                    <td>{c.weather ? `${c.weather.snow_in_hr}` : "–"}</td>
                    <td>
                      {c.level ? (
                        <span className="dot-label"><i style={{ background: levelColor(c.level.value) }} />{c.level.label}</span>
                      ) : "n/a"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </article>
  );
}
