import { useCallback, useEffect, useRef, useState } from "react";
import type { MarketEvent, Side } from "./market";
import type { Status } from "./useRun";
import {
  advanceWorld,
  cancelWorldOrder,
  endWorld,
  placeWorldOrder,
  Refused,
  startWorld,
  WorldRequest,
  WorldSnapshot,
  WorldStart,
  WorldUpdate,
} from "./world";

export { SPEEDS } from "./useRun";

const TICK_MS = 1000; // the browser asks the server to move the day on this often; the server has no clock of its own.
// Once a second, not four times: each request carries `speed` simulated seconds, so the load on the server is a quarter.

interface Stores {
  events: Record<string, MarketEvent[]>;
  ends: Record<string, number[]>;
}

const empty = (): Stores => ({ events: {}, ends: {} });

/**
 * A practice day across all twelve companies. The server only moves the day when asked, so this hook is the clock:
 * while "playing" it asks for `speed` simulated seconds per real second. Every call goes through one queue so replies
 * can never arrive out of order, and the events always add up to exactly what the server holds.
 */
export function useWorld() {
  const data = useRef<Stores>(empty());
  const touched = useRef(new Set<string>()); // companies the person has sent an order to
  const [version, setVersion] = useState(0);
  const [snapshot, setSnapshot] = useState<WorldSnapshot | null>(null);
  const [first, setFirst] = useState<WorldSnapshot | null>(null);
  const [plan, setPlan] = useState("");
  const [factors, setFactors] = useState<WorldStart["index_factors"] | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [speed, setSpeedState] = useState(10);
  const [error, setError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const chain = useRef<Promise<void>>(Promise.resolve());
  const waiting = useRef(0);
  const worldRef = useRef<WorldSnapshot | null>(null);
  const speedRef = useRef(10);
  const pauseRef = useRef(true);
  const [pauseOnFill, setPauseState] = useState(true);
  const [played, setPlayed] = useState(false); // has the day been played at all (for the first-day guide)
  const token = useRef(0);

  const enqueue = useCallback(<T,>(work: () => Promise<T>): Promise<T> => {
    waiting.current += 1;
    const result = chain.current.then(work);
    chain.current = result.then(
      () => undefined,
      () => undefined,
    );
    return result.finally(() => {
      waiting.current -= 1;
    });
  }, []);

  const take = useCallback((reply: Pick<WorldUpdate, "new_events" | "new_ends" | "snapshot">) => {
    for (const [symbol, events] of Object.entries(reply.new_events)) {
      (data.current.events[symbol] ??= []).push(...events);
      (data.current.ends[symbol] ??= []).push(...(reply.new_ends[symbol] ?? []));
    }
    for (const [symbol, count] of Object.entries(reply.snapshot.event_counts)) {
      if ((data.current.events[symbol]?.length ?? 0) !== count) {
        throw new Error("The page and the server have gone out of step. Start a new day to carry on.");
      }
    }
    setSnapshot(reply.snapshot);
    setVersion((v) => v + 1);
  }, []);

  const start = useCallback(
    async (request: WorldRequest) => {
      const mine = ++token.current;
      const old = worldRef.current;
      worldRef.current = null;
      if (old) void endWorld(old.id).catch(() => undefined);
      data.current = empty();
      touched.current = new Set();
      setPlayed(false);
      setSnapshot(null);
      setFirst(null);
      setFactors(null);
      setError(null);
      setRefusal(null);
      setNotice(null);
      setStatus("starting");
      setVersion((v) => v + 1);
      try {
        const opened = await enqueue(() => startWorld(request));
        if (mine !== token.current) return;
        worldRef.current = opened;
        take({ new_events: opened.new_events, new_ends: opened.new_ends, snapshot: opened });
        setFirst(opened);
        setPlan(opened.plan);
        setFactors(opened.index_factors);
        setStatus("paused"); // the person presses play when ready
      } catch (problem) {
        if (mine !== token.current) return;
        setError(problem instanceof Error ? problem.message : String(problem));
        setStatus("error");
      }
    },
    [enqueue, take],
  );

  // the clock
  useEffect(() => {
    if (status !== "playing") return;
    const timer = window.setInterval(() => {
      const open = worldRef.current;
      if (!open || waiting.current > 0) return; // still busy with the last request: skip this beat
      const mine = token.current;
      void enqueue(() => advanceWorld(open.id, (speedRef.current * TICK_MS) / 1000, pauseRef.current))
        .then((reply) => {
          if (mine !== token.current) return;
          take(reply);
          if (reply.finished) {
            setStatus("done");
            setNotice("The market has closed. Orders still waiting expired and their money came back.");
          } else if (reply.stopped_for_fill) {
            setStatus("paused");
            setNotice("Your order traded, so the day is paused. Press play to carry on.");
          }
        })
        .catch((problem: unknown) => {
          if (mine !== token.current) return;
          setError(problem instanceof Error ? problem.message : String(problem));
          setStatus("error");
        });
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, [status, enqueue, take]);

  const togglePause = () => {
    if (status === "playing") setStatus("paused");
    else if (status === "paused") {
      setNotice(null);
      setPlayed(true);
      setStatus("playing");
    }
  };

  const setPauseOnFill = (value: boolean) => {
    pauseRef.current = value;
    setPauseState(value);
  };

  const setSpeed = (value: number) => {
    speedRef.current = value;
    setSpeedState(value);
  };

  const run = async (work: (id: string) => Promise<WorldUpdate>): Promise<boolean> => {
    const open = worldRef.current;
    if (!open) return false;
    const mine = token.current;
    try {
      const reply = await enqueue(() => work(open.id));
      if (mine !== token.current) return false;
      take(reply);
      setRefusal(null);
      return true;
    } catch (problem) {
      if (mine !== token.current) return false;
      if (problem instanceof Refused) setRefusal(problem.message);
      else {
        setError(problem instanceof Error ? problem.message : String(problem));
        setStatus("error");
      }
      return false;
    }
  };

  const place = (symbol: string, side: Side, quantity: number, limitPrice: number | null) => {
    touched.current.add(symbol);
    return run((id) => placeWorldOrder(id, symbol, side, quantity, limitPrice));
  };
  const cancel = (symbol: string, orderId: number) => run((id) => cancelWorldOrder(id, symbol, orderId));

  useEffect(
    () => () => {
      token.current += 1;
      const old = worldRef.current;
      if (old) void endWorld(old.id).catch(() => undefined);
    },
    [],
  );

  return {
    events: data.current.events,
    ends: data.current.ends,
    touched: touched.current,
    version,
    snapshot,
    first,
    plan,
    factors,
    status,
    speed,
    error,
    refusal,
    notice,
    pauseOnFill,
    setPauseOnFill,
    played,
    clearRefusal: () => setRefusal(null),
    start,
    setSpeed,
    togglePause,
    place,
    cancel,
  };
}
