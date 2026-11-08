import { useEffect, useId, useRef, useState } from "react";
import { searchPlaces } from "../api";
import type { Place } from "../types";

interface Props {
  label: string;
  value: Place | string;
  onChange(value: Place | string): void;
  placeholder?: string;
}

export default function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const id = useId();
  const [text, setText] = useState(typeof value === "string" ? value : value.label);
  const [options, setOptions] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number>();
  const controller = useRef<AbortController>();

  // Keep the text in sync when the parent swaps origin and destination.
  useEffect(() => {
    setText(typeof value === "string" ? value : value.label);
  }, [value]);

  const search = (q: string) => {
    window.clearTimeout(timer.current);
    controller.current?.abort();
    if (q.trim().length < 3) {
      setOptions([]);
      setBusy(false);
      return;
    }
    timer.current = window.setTimeout(async () => {
      const ctl = new AbortController();
      controller.current = ctl;
      setBusy(true);
      try {
        setOptions(await searchPlaces(q, ctl.signal));
        setActive(-1);
      } catch {
        if (!ctl.signal.aborted) setOptions([]);
      } finally {
        if (!ctl.signal.aborted) setBusy(false);
      }
    }, 300);
  };

  // Stop any pending search when the field goes away.
  useEffect(
    () => () => {
      window.clearTimeout(timer.current);
      controller.current?.abort();
    },
    [],
  );

  const choose = (place: Place) => {
    window.clearTimeout(timer.current);
    controller.current?.abort();
    setBusy(false);
    setText(place.label);
    setOpen(false);
    setOptions([]);
    onChange(place);
  };

  return (
    <div className="field place">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        value={text}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={open && options.length > 0}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          onChange(e.target.value); // free text is geocoded by the server if no suggestion is chosen
          search(e.target.value);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, options.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter" && open && active >= 0 && options[active]) {
            e.preventDefault();
            choose(options[active]);
          } else if (e.key === "Enter") {
            window.clearTimeout(timer.current); // the form submits with the typed text
            controller.current?.abort();
            setBusy(false);
            setOpen(false);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {busy && <span className="spinner small" aria-label="Searching" />}
      {open && options.length > 0 && (
        <ul id={`${id}-list`} className="suggestions" role="listbox">
          {options.map((o, i) => (
            <li
              key={`${o.lat},${o.lon}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(o);
              }}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
