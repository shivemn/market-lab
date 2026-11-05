import { useCallback, useEffect, useRef, useState } from "react";
import type { MarketEvent, Side } from "./market";
import {
  advance,
  cancelOrder,
  endPractice,
  placeOrder,
  Portfolio,
  PracticeStart,
  Refused,
  startPractice,
  StartRequest,
  Update,
} from "./practice";
import type { Status } from "./useRun";

export { SPEEDS } from "./useRun";

const TICK_MS = 250; // the browser asks the server to move the day on this often; the server has no clock of its own

/**
 * A practice day. The server only moves the day when asked, so this hook is the clock: while "playing" it asks for
 * `speed` simulated seconds per real second. Every call goes through one queue so replies can never arrive out of
 * order, and the events always add up to exactly what the server holds.
 */
export function usePractice() {
  const data = useRef({ events: [] as MarketEvent[], ends: [] as number[] });
  const [version, setVersion] = useState(0);
  const [session, setSession] = useState<PracticeStart | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [startPortfolio, setStartPortfolio] = useState<Portfolio | null>(null);
  const [now, setNow] = useState(0);
  const [status, setStatus] = useState<Status>("idle");
  const [speed, setSpeedState] = useState(10);
  const [error, setError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const chain = useRef<Promise<void>>(Promise.resolve());
  const waiting = useRef(0);
  const sessionRef = useRef<PracticeStart | null>(null);
  const speedRef = useRef(10);
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

  const take = useCallback((reply: Update) => {
    data.current.events.push(...reply.new_events);
    data.current.ends.push(...reply.new_ends);
    if (reply.events !== undefined && reply.events !== data.current.events.length) {
      throw new Error("The page and the server have gone out of step. Start a new day to carry on.");
    }
    setNow(reply.now);
    setPortfolio(reply.portfolio);
    setVersion((v) => v + 1);
  }, []);

  const start = useCallback(
    async (request: StartRequest) => {
      const mine = ++token.current;
      const old = sessionRef.current;
      sessionRef.current = null;
      if (old) void endPractice(old.id).catch(() => undefined);
      data.current = { events: [], ends: [] };
      setSession(null);
      setPortfolio(null);
      setStartPortfolio(null);
      setError(null);
      setRefusal(null);
      setNotice(null);
      setNow(0);
      setStatus("starting");
      setVersion((v) => v + 1);
      try {
        const opened = await enqueue(() => startPractice(request));
        if (mine !== token.current) return;
        data.current = { events: [...opened.new_events], ends: [...opened.new_ends] };
        sessionRef.current = opened;
        setSession(opened);
        setPortfolio(opened.portfolio);
        setStartPortfolio(opened.portfolio);
        setNow(opened.now);
        setVersion((v) => v + 1);
        setStatus("paused"); // the person presses play when ready
      } catch (problem) {
        if (mine !== token.current) return;
        setError(problem instanceof Error ? problem.message : String(problem));
        setStatus("error");
      }
    },
    [enqueue],
  );

  // the clock
  useEffect(() => {
    if (status !== "playing") return;
    const timer = window.setInterval(() => {
      const open = sessionRef.current;
      if (!open || waiting.current > 0) return; // still busy with the last request: skip this beat
      const mine = token.current;
      void enqueue(() => advance(open.id, (speedRef.current * TICK_MS) / 1000))
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
      setStatus("playing");
    }
  };

  const setSpeed = (value: number) => {
    speedRef.current = value;
    setSpeedState(value);
  };

  const run = async (work: (id: string) => Promise<Update>): Promise<boolean> => {
    const open = sessionRef.current;
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

  const place = (side: Side, quantity: number, limitPrice: number | null) =>
    run((id) => placeOrder(id, side, quantity, limitPrice));
  const cancel = (orderId: number) => run((id) => cancelOrder(id, orderId));

  useEffect(
    () => () => {
      token.current += 1;
      const old = sessionRef.current;
      if (old) void endPractice(old.id).catch(() => undefined);
    },
    [],
  );

  return {
    events: data.current.events,
    ends: data.current.ends,
    version,
    session,
    portfolio,
    startPortfolio,
    now,
    status,
    speed,
    error,
    refusal,
    notice,
    clearRefusal: () => setRefusal(null),
    start,
    setSpeed,
    togglePause,
    place,
    cancel,
  };
}
