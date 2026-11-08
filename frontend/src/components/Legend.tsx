import { LEVELS, NO_FORECAST_COLOR } from "../risk";

export default function Legend() {
  return (
    <div className="legend" aria-label="Risk legend">
      {LEVELS.map((l) => (
        <span key={l.key}><i style={{ background: l.color }} />{l.label}</span>
      ))}
      <span><i style={{ background: NO_FORECAST_COLOR }} />No forecast</span>
    </div>
  );
}
