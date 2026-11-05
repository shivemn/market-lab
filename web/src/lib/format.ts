/** Paise as rupees with Indian digit grouping: 10000000 -> "1,00,000.00". */
export function money(paise: number): string {
  const sign = paise < 0 ? "-" : "";
  const abs = Math.abs(paise);
  const rupees = Math.floor(abs / 100).toString();
  const rest = (abs % 100).toString().padStart(2, "0");
  const last3 = rupees.slice(-3);
  const front = rupees.slice(0, -3);
  const grouped = front ? front.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + "," + last3 : last3;
  return `${sign}${grouped}.${rest}`;
}

export const rupees = (paise: number): string => `${paise < 0 ? "-" : ""}₹${money(Math.abs(paise))}`;

/** "+₹12.30", "−₹4.00" or "₹0.00": a result that says which way it went without relying on colour. */
export const signed = (paise: number): string =>
  paise === 0 ? rupees(0) : `${paise > 0 ? "+" : "−"}₹${money(Math.abs(paise))}`;

/** Microseconds into the day as "3:45". */
export function clock(micros: number): string {
  const total = Math.max(0, Math.floor(micros / 1_000_000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** The change since the previous close, short enough for a header: "▲ ₹11.90 (0.48%)". */
export function changeShort(price: number, reference: number): { dir: "up" | "down" | "flat"; text: string } {
  const diff = price - reference;
  if (diff === 0) return { dir: "flat", text: "unchanged" };
  const percent = ((Math.abs(diff) / reference) * 100).toFixed(2);
  return { dir: diff > 0 ? "up" : "down", text: `${diff > 0 ? "▲" : "▼"} ${rupees(Math.abs(diff))} (${percent}%)` };
}

/** Microseconds since the start of the day as "6 min 33 s". */
export function dayClock(micros: number): string {
  const total = Math.floor(micros / 1_000_000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return minutes > 0 ? `${minutes} min ${seconds} s` : `${seconds} s`;
}

/** "Up ₹5.30 (0.21%)" or "Down ...", in words so it does not depend on colour. */
export function changeWords(price: number, reference: number): string {
  const diff = price - reference;
  if (diff === 0) return "Unchanged";
  const percent = ((Math.abs(diff) / reference) * 100).toFixed(2);
  return `${diff > 0 ? "Up" : "Down"} ${rupees(Math.abs(diff))} (${percent}%)`;
}

/** An index level given in hundredths of a point: 101235 -> "1,012.35". */
export const points = (hundredths: number): string => money(hundredths);

/** "+12.35", "−3.10" or "0.00" in index points. */
export const pointsSigned = (hundredths: number): string =>
  hundredths === 0 ? "0.00" : `${hundredths > 0 ? "+" : "−"}${money(Math.abs(hundredths))}`;

/** A change as a percentage with its sign: "+0.44%", "−1.20%", "0.00%". `part` and `whole` use the same unit. */
export function percentSigned(part: number, whole: number): string {
  if (whole === 0 || part === 0) return "0.00%";
  const value = (Math.abs(part) / Math.abs(whole)) * 100;
  return `${part > 0 ? "+" : "−"}${value.toFixed(2)}%`;
}
