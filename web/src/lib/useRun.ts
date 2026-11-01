import { useCallback, useEffect, useRef, useState } from "react";
import { createRun, RunRequest, RunSummary, ServerMessage, streamUrl } from "./api";
import type { MarketEvent } from "./market";

export type Status = "idle" | "starting" | "playing" | "paused" | "done" | "error";

export const SPEEDS = [1, 4, 10, 30, 100];

/** Starts a simulated day on the server and collects its events as they stream in. */
export function useRun() {
  const data = useRef({ events: [] as MarketEvent[], ends: [] as number[] });
  const [version, setVersion] = useState(0);
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [speed, setSpeedState] = useState(4);
  const [error, setError] = useState<string | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const token = useRef(0);
  const frame = useRef<number | null>(null);
  const speedRef = useRef(4);

  const bump = useCallback(() => {
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      setVersion((v) => v + 1);
    });
  }, []);

  const close = useCallback(() => {
    socket.current?.close();
    socket.current = null;
  }, []);

  const start = useCallback(
    async (request: RunRequest) => {
      const mine = ++token.current;
      close();
      data.current = { events: [], ends: [] };
      setSummary(null);
      setError(null);
      setStatus("starting");
      setVersion((v) => v + 1);
      try {
        const run = await createRun(request);
        if (mine !== token.current) return;
        setSummary(run);
        const ws = new WebSocket(streamUrl(run.id, speedRef.current));
        socket.current = ws;
        ws.onmessage = (message) => {
          if (mine !== token.current) return;
          const parsed = JSON.parse(message.data as string) as ServerMessage;
          if (parsed.type === "batch") {
            data.current.events.push(...parsed.events);
            data.current.ends.push(parsed.upto);
            setStatus((s) => (s === "starting" ? "playing" : s));
            bump();
          } else if (parsed.type === "done") {
            setStatus("done");
            bump();
          }
        };
        ws.onerror = () => {
          if (mine === token.current) {
            setError("Lost the connection to the server.");
            setStatus("error");
          }
        };
        setStatus("playing");
      } catch (problem) {
        if (mine !== token.current) return;
        setError(problem instanceof Error ? problem.message : String(problem));
        setStatus("error");
      }
    },
    [bump, close],
  );

  const send = (message: object) => {
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify(message));
  };

  const setSpeed = (value: number) => {
    speedRef.current = value;
    setSpeedState(value);
    send({ type: "speed", value });
  };

  const togglePause = () => {
    if (status === "playing") {
      send({ type: "pause" });
      setStatus("paused");
    } else if (status === "paused") {
      send({ type: "resume" });
      setStatus("playing");
    }
  };

  useEffect(
    () => () => {
      token.current += 1;
      close();
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    },
    [close],
  );

  return {
    events: data.current.events,
    ends: data.current.ends,
    version,
    summary,
    status,
    speed,
    error,
    start,
    setSpeed,
    togglePause,
  };
}
