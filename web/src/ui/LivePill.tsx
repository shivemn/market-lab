const WORDS = { CLOSED: "Closed", PRE_OPEN: "Before the open", OPEN: "Open" } as const;

export type Session = keyof typeof WORDS;

/** Whether the market is open, as a small pill. Its dot pulses while trading is live (not under reduced motion). */
export function LivePill({ session }: { session: Session }) {
  return <span className={`chip chip-${session.toLowerCase()}`}>{WORDS[session]}</span>;
}
