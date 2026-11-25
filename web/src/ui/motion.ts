import { useEffect, useRef, useState, type RefObject } from "react";

/** Whether the person has asked their computer for less motion. Then animated panels show a still, finished frame. */
export function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/** Whether an element is on screen (true until it can be measured, and wherever IntersectionObserver is missing). */
export function useOnScreen(ref: RefObject<Element>): boolean {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: "80px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, ref.current]); // eslint-disable-line react-hooks/exhaustive-deps -- re-attach once the element appears
  return visible;
}

/**
 * Milliseconds of motion so far, for one animated panel. It only runs while `active` is true, the tab is visible and
 * (when `box` is given) the panel is on screen, at `fps` frames a second at most; it never runs under reduced motion
 * (`still` is then true). Changing `restart` sets it back to zero, so a new set of data starts from the beginning. With
 * `until`, the clock stops by itself at that many milliseconds (a finished animation stops asking for frames).
 */
export function useFrameClock(
  active: boolean,
  restart: unknown = null,
  box?: RefObject<Element>,
  fps = 30,
  until = Number.POSITIVE_INFINITY,
): { elapsed: number; still: boolean } {
  const [still] = useState(prefersReducedMotion);
  const [elapsed, setElapsed] = useState(0);
  const clock = useRef(0);
  const fallback = useRef<Element>(null);
  const onScreen = useOnScreen(box ?? fallback);
  useEffect(() => {
    clock.current = 0;
    setElapsed(0);
  }, [restart]);
  const running = active && !still && onScreen;
  useEffect(() => {
    if (!running || clock.current >= until) return;
    const frame = 1000 / fps;
    let raf = 0;
    let last = 0;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (last === 0) last = now;
      const dt = now - last;
      if (dt < frame) return;
      last = now;
      if (document.hidden) return;
      clock.current = Math.min(until, clock.current + Math.min(dt, 100));
      setElapsed(clock.current);
      if (clock.current >= until) cancelAnimationFrame(raf);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [running, fps, until, restart]);
  return { elapsed, still };
}
