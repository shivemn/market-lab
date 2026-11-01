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

export const rupees = (paise: number): string => `₹${money(paise)}`;

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
