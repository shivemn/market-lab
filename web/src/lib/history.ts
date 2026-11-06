export interface SavedFill {
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number; // paise
  at: number; // microseconds into the simulated day
}

export interface SavedDay {
  id: number;
  seed: number;
  played_at: string; // "2026-11-05 09:41:07", UTC
  finished: boolean;
  start_worth: number;
  end_worth: number;
  result: number;
  charges: number;
  companies: { symbol: string; name: string; today: number }[];
  index: Record<string, { open: number; level: number; change: number }>;
  fills: SavedFill[];
  news?: { at: number; scope: string; target: string; headline: string; silent?: boolean; impact_bp: number | null }[];
}

/** Every day this account has played, newest first. The server keeps them in the database file. */
export async function loadDays(owner: string): Promise<SavedDay[]> {
  const response = await fetch(`/api/accounts/${encodeURIComponent(owner)}/days`);
  if (!response.ok) throw new Error("Could not load your saved days.");
  return ((await response.json()) as { days: SavedDay[] }).days;
}
