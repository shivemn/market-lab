import { RefObject, useEffect, useState } from "react";

/** The current width of an element in pixels, kept up to date as the window changes. */
export function useWidth(ref: RefObject<HTMLElement>, fallback = 800): number {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const update = () => setWidth(Math.max(240, Math.floor(element.getBoundingClientRect().width)));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}
