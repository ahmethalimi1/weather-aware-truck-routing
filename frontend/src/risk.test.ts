import { describe, expect, it } from "vitest";
import { NO_FORECAST_COLOR, defaultDeparture, formatDuration, levelColor, levelShares, parseLoad } from "./risk";

describe("formatDuration", () => {
  it("formats hours and minutes", () => {
    expect(formatDuration(125)).toBe("2h 05m");
    expect(formatDuration(45)).toBe("45m");
  });
});

describe("levelShares", () => {
  it("returns shares that sum to 1 in level order", () => {
    const shares = levelShares({ low: 60, moderate: 20, high: 10, severe: 10, no_travel: 0 });
    expect(shares.map((s) => s.key)).toEqual(["low", "moderate", "high", "severe", "no_travel"]);
    expect(shares.reduce((a, s) => a + s.share, 0)).toBeCloseTo(1);
    expect(shares[0].share).toBeCloseTo(0.6);
  });
  it("counts unknown miles as part of the total so the bar never overstates risk", () => {
    const shares = levelShares({ low: 0, moderate: 0, high: 0, severe: 50, no_travel: 0 }, 50);
    expect(shares[3].share).toBeCloseTo(0.5);
  });
});

describe("defaultDeparture", () => {
  it("is the next full hour in datetime-local format", () => {
    expect(defaultDeparture(new Date(2026, 0, 5, 9, 30))).toBe("2026-01-05T10:00");
  });
});

describe("parseLoad", () => {
  it("rejects an empty field instead of treating it as 0 lb", () => {
    expect(parseLoad("")).toBeNull();
    expect(parseLoad("   ")).toBeNull();
  });
  it("accepts the legal range and rejects the rest", () => {
    expect(parseLoad("0")).toBe(0);
    expect(parseLoad("40000")).toBe(40000);
    expect(parseLoad("80001")).toBeNull();
    expect(parseLoad("-1")).toBeNull();
    expect(parseLoad("abc")).toBeNull();
  });
});

describe("levelColor", () => {
  it("shows unknown as grey, never as a risk colour", () => {
    expect(levelColor(-1)).toBe(NO_FORECAST_COLOR);
    expect(levelColor(0)).not.toBe(NO_FORECAST_COLOR);
  });
});
