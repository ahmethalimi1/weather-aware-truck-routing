import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import { LEVELS, NO_FORECAST_COLOR, formatHour, levelColor } from "../risk";
import type { HeatmapData } from "../types";
import type { MapApi } from "./MapView";

interface Props {
  heatmap: HeatmapData;
  apiRef: MutableRefObject<MapApi | null>;
}

/** The slider talks to the map imperatively, so dragging never re-renders the app. */
export default function HeatmapControl({ heatmap, apiRef }: Props) {
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [visible, setVisible] = useState(true);
  const hourRef = useRef(0);

  // Peak risk anywhere in the corridor for every forecast hour (drives the strip under the slider).
  const peaks = useMemo(
    () => heatmap.hours.map((_, h) => Math.max(-1, ...heatmap.geojson.features.map((f) => f.properties[`r${h}`] ?? -1))),
    [heatmap],
  );

  const move = (h: number) => {
    hourRef.current = h;
    setHour(h);
    apiRef.current?.setHeatHour(h);
  };

  useEffect(() => {
    move(0);
    setPlaying(false);
    setVisible(true);
    apiRef.current?.setHeatVisible(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [heatmap]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => move((hourRef.current + 1) % heatmap.hours.length), 450);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, heatmap]);

  const peak = peaks[hour] < 0 ? null : LEVELS[peaks[hour]];

  return (
    <section className="heat-control" aria-label="Weather heatmap">
      <div className="heat-top">
        <strong>Weather heatmap</strong>
        <label className="toggle">
          <input
            type="checkbox"
            checked={visible}
            onChange={(e) => {
              setVisible(e.target.checked);
              apiRef.current?.setHeatVisible(e.target.checked);
            }}
          />
          Show
        </label>
      </div>
      <div className="heat-row">
        <button type="button" className="icon-btn" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="slider">
          <div className="strip" aria-hidden="true">
            {peaks.map((p, h) => (
              <span key={h} style={{ background: levelColor(p), opacity: h === hour ? 1 : 0.55 }} />
            ))}
          </div>
          <input
            type="range"
            min={0}
            max={heatmap.hours.length - 1}
            value={hour}
            aria-label="Forecast hours after departure"
            aria-valuetext={`${hour} hours after departure, ${formatHour(heatmap.hours[hour])}`}
            onChange={(e) => move(Number(e.target.value))}
          />
        </div>
      </div>
      <div className="heat-meta">
        <span>
          {hour === 0 ? "Departure hour" : `+${hour} h`} · {formatHour(heatmap.hours[hour])}
        </span>
        <span className="dot-label">
          <i style={{ background: peak?.color ?? NO_FORECAST_COLOR }} />
          {peak ? `Peak in corridor: ${peak.label}` : "No forecast for this hour"}
        </span>
      </div>
    </section>
  );
}
