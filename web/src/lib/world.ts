import type { MarketEvent, Side } from "./market";

export interface PracticeInstrument {
  symbol: string;
  tick_size: number;
  lot_size: number;
  reference_price: number;
  band_low: number;
  band_high: number;
}

/** The server turned the request down, with a reason written for a person. */
export class Refused extends Error {}


export type IndexKind = "cap" | "equal" | "price";
export const INDEX_KINDS: readonly IndexKind[] = ["cap", "equal", "price"];

export interface WorldCompany {
  symbol: string;
  name: string;
  sector: string;
  free_float_shares: number;
  instrument: PracticeInstrument;
}

export interface WorldOpenOrder {
  symbol: string;
  id: number;
  side: Side;
  quantity: number;
  remaining: number;
  limit_price: number | null;
}

export interface WorldPortfolio {
  cash: number; // paise free to use
  reserved: number; // paise set aside for open orders
  holdings: Record<string, { shares: number; locked: number }>;
  open_orders: WorldOpenOrder[];
}

export interface IndexView {
  name: string;
  level: number; // hundredths of a point
  open: number; // the level when the day began (yesterday's close)
  change: number; // level - open
  members: Record<string, { weight_bp: number; points: number }>; // points are hundredths
}

export interface SectorView {
  label: string;
  level: number;
  open: number;
  change: number;
}

export interface PositionView {
  shares: number;
  average_cost: number;
  bought: number;
  sold: number;
  charges: number;
  realised: number;
  unrealised: number;
  net: number;
  today: number;
}

export interface NewsView {
  id: number;
  at: number; // microseconds into the day
  scope: "market" | "sector" | "company";
  target: string; // "" for the market, a sector key, or a company symbol
  headline: string;
  silent: boolean; // a move with no headline; these only show up once the day is over
  impact_bp: number | null; // how far it moved the price (0: not at all); only known once the day has finished
}

export interface WorldSnapshot {
  id: string;
  owner: string;
  config: { seed: number; open_seconds: number; pre_open_seconds: number };
  index_name: string;
  news: NewsView[];
  benchmarks: { key: string; label: string; bp: number; note: string }[]; // empty until the day is over
  sectors: { key: string; label: string }[];
  companies: WorldCompany[];
  now: number;
  open_at: number;
  close_at: number;
  finished: boolean;
  portfolio: WorldPortfolio;
  prices: Record<string, number>;
  indices: Record<IndexKind, IndexView> & { sectors: Record<string, SectorView> };
  worth: number;
  starting_money: number;
  total_charges: number;
  event_counts: Record<string, number>;
  positions: Record<string, PositionView>;
}

export interface WorldStart extends WorldSnapshot {
  plan: string;
  new_events: Record<string, MarketEvent[]>;
  new_ends: Record<string, number[]>;
}

export interface WorldUpdate {
  new_events: Record<string, MarketEvent[]>;
  new_ends: Record<string, number[]>;
  now: number;
  snapshot: WorldSnapshot;
}

export interface WorldAdvance extends WorldUpdate {
  stopped_for_fill: boolean;
  finished: boolean;
}

export interface WorldStatementRow {
  at: number;
  kind: "start" | "grant" | "buy" | "sell";
  memo: string;
  symbol: string | null;
  shares_change: number;
  value: number;
  charges: Record<string, number>;
  money_change: number;
  money_after: number;
}

export interface WorldStatement {
  rows: WorldStatementRow[];
  starting_money: number;
  money: number;
  holdings: Record<string, number>;
  bought: number;
  sold: number;
  traded_value: number;
  charges_by_line: Record<string, number>;
  total_charges: number;
  charges_basis_points: number;
  worth: number;
  problems: string[];
}

export interface WorldRequest {
  owner: string;
  seed: number;
  plan: "zero" | "flat20";
  open_seconds?: number;
  pre_open_seconds?: number;
  fresh_prices?: boolean;
}

async function call<T>(method: string, url: string, body?: object): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error('Could not reach the server. Is "marketlab serve" running?');
  }
  if (response.status === 422) {
    const detail = ((await response.json()) as { detail?: unknown }).detail;
    throw new Refused(typeof detail === "string" ? detail : "That was not accepted. Check the numbers and try again.");
  }
  if (!response.ok) throw new Error(`The server could not do that (${response.status}).`);
  return (await response.json()) as T;
}

export const startWorld = (request: WorldRequest) => call<WorldStart>("POST", "/api/worlds", request);
export const advanceWorld = (id: string, seconds: number, pauseOnFill = true) =>
  call<WorldAdvance>("POST", `/api/worlds/${id}/advance`, { seconds, pause_on_fill: pauseOnFill });
export const placeWorldOrder = (id: string, symbol: string, side: Side, quantity: number, limitPrice: number | null) =>
  call<WorldUpdate & { order_id: number }>("POST", `/api/worlds/${id}/orders`, {
    symbol,
    side,
    quantity,
    limit_price: limitPrice,
    tif: "DAY",
  });
export const cancelWorldOrder = (id: string, symbol: string, orderId: number) =>
  call<WorldUpdate>("DELETE", `/api/worlds/${id}/orders/${symbol}/${orderId}`);
export const endWorld = (id: string) => call<{ ended: boolean }>("DELETE", `/api/worlds/${id}`);
export const getWorldStatement = (id: string) => call<WorldStatement>("GET", `/api/worlds/${id}/statement`);
