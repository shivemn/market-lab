import { useEffect, useRef, useState } from "react";

/** Whether the person has asked their computer for less motion. Then animated panels show a still, finished frame. */
export function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

const FRAME_MS = 33; // about 30 frames a second is plenty for these panels and keeps the page light

/**
 * Milliseconds of motion so far, for one animated panel. It only runs while `active` is true and the tab is visible,
 * at about 30 frames a second, and it never runs under reduced motion (`still` is then true). Changing `restart`
 * sets it back to zero, so a new set of data starts from the beginning.
 */
export function useFrameClock(active: boolean, restart: unknown = null): { elapsed: number; still: boolean } {
  const [still] = useState(prefersReducedMotion);
  const [elapsed, setElapsed] = useState(0);
  const clock = useRef(0);
  useEffect(() => {
    clock.current = 0;
    setElapsed(0);
  }, [restart]);
  useEffect(() => {
    if (!active || still) return;
    let raf = 0;
    let last = 0;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (last === 0) last = now;
      const dt = now - last;
      if (dt < FRAME_MS) return;
      last = now;
      if (document.hidden) return;
      clock.current += Math.min(dt, 100);
      setElapsed(clock.current);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active, still]);
  return { elapsed, still };
}
