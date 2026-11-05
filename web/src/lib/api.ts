import type { MarketEvent } from "./market";

export interface RunRequest {
  seed: number;
  open_seconds: number;
  pre_open_seconds: number;
  noise_traders: number;
  company?: string; // a symbol from the catalogue
}

export interface RunSummary {
  id: string;
  config: RunRequest & { reference_price: number };
  instrument: {
    symbol: string;
    tick_size: number;
    lot_size: number;
    reference_price: number;
    band_low: number;
    band_high: number;
  };
  events: number;
  commands: number;
  sha256: string;
  duration_us: number;
}

export type ServerMessage =
  | { type: "hello"; run: RunSummary }
  | { type: "batch"; events: MarketEvent[]; upto: number; sim_time: number }
  | { type: "done" };

export async function createRun(request: RunRequest): Promise<RunSummary> {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`The server refused the request (${response.status}). Is "marketlab serve" running?`);
  }
  return (await response.json()) as RunSummary;
}

export function streamUrl(id: string, speed: number): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/runs/${id}?speed=${speed}`;
}
