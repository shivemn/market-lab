import type { MarketEvent, Side } from "./market";

export interface OpenOrder {
  id: number;
  side: Side;
  quantity: number;
  remaining: number;
  limit_price: number | null;
}

export interface Portfolio {
  cash: number; // paise free to use
  reserved: number; // paise set aside for open orders
  shares: number; // free to sell
  locked: number; // set aside for open sell orders
  open_orders: OpenOrder[];
}

export interface PracticeInstrument {
  symbol: string;
  tick_size: number;
  lot_size: number;
  reference_price: number;
  band_low: number;
  band_high: number;
}

export interface PracticeStart {
  id: string;
  owner: string;
  config: { seed: number; open_seconds: number; pre_open_seconds: number; noise_traders: number; reference_price: number };
  instrument: PracticeInstrument;
  now: number;
  open_at: number;
  close_at: number;
  finished: boolean;
  events: number;
  portfolio: Portfolio;
  plan: string;
  new_events: MarketEvent[];
  new_ends: number[];
}

export interface Update {
  new_events: MarketEvent[];
  new_ends: number[];
  now: number;
  events?: number; // how many events the server has in all, to notice if we ever fall out of step
  portfolio: Portfolio;
}

export interface AdvanceReply extends Update {
  stopped_for_fill: boolean;
  finished: boolean;
}

export interface OrderReply extends Update {
  order_id: number;
}

export type PlanName = "zero" | "flat20";

export interface StartRequest {
  owner: string;
  seed: number;
  plan: PlanName;
  open_seconds?: number;
  pre_open_seconds?: number;
  noise_traders?: number;
}

/** The server turned the request down, with a reason written for a person. */
export class Refused extends Error {}

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

export const startPractice = (request: StartRequest) => call<PracticeStart>("POST", "/api/sessions", request);

export const advance = (id: string, seconds: number) =>
  call<AdvanceReply>("POST", `/api/sessions/${id}/advance`, { seconds, pause_on_fill: true });

export const placeOrder = (id: string, side: Side, quantity: number, limitPrice: number | null) =>
  call<OrderReply>("POST", `/api/sessions/${id}/orders`, { side, quantity, limit_price: limitPrice, tif: "DAY" });

export const cancelOrder = (id: string, orderId: number) => call<Update>("DELETE", `/api/sessions/${id}/orders/${orderId}`);

export const endPractice = (id: string) => call<{ ended: boolean; portfolio: Portfolio }>("DELETE", `/api/sessions/${id}`);
