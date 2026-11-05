import { useEffect, useRef, useState } from "react";

/**
 * Follows `value`, but changes at most once every `ms`. With `ms` of 0 it follows at once. Used for text that would
 * otherwise flicker too fast to read when the day is running at high speed.
 */
export function useThrottled<T>(value: T, ms: number): T {
  const [shown, setShown] = useState(value);
  const last = useRef(0);
  const latest = useRef(value);
  latest.current = value;
  useEffect(() => {
    const wait = ms - (Date.now() - last.current);
    if (wait <= 0) {
      last.current = Date.now();
      setShown(value);
      return;
    }
    const timer = window.setTimeout(() => {
      last.current = Date.now();
      setShown(latest.current);
    }, wait);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return shown;
}
