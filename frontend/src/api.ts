import type { AnalyzeRequest, AnalyzeResponse, Place } from "./types";

const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError("Could not reach the server. Check your connection and try again.");
  }
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(body.error ?? `Request failed (${resp.status}).`);
  return body as T;
}

export const analyze = (payload: AnalyzeRequest, signal?: AbortSignal) =>
  request<AnalyzeResponse>("/api/analyze/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

export const searchPlaces = async (q: string, signal?: AbortSignal): Promise<Place[]> =>
  (await request<{ results: Place[] }>(`/api/geocode/?q=${encodeURIComponent(q)}`, { signal })).results;
