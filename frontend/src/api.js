import { useCallback, useEffect, useRef, useState } from "react";

const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

/**
 * Loads the snapshot. A free Render server sleeps when idle, so the first
 * request can return 503 ("warming up") or time out: keep retrying for ~2 min.
 */
export function useSnapshot() {
  const [state, setState] = useState({ data: null, error: null, waking: false });
  const attempts = useRef(0);
  const timer = useRef(null);

  const load = useCallback(async () => {
    clearTimeout(timer.current);
    try {
      const res = await fetch(`${API_URL}/api/snapshot`);
      if (res.status === 503) throw new Error("warming_up");
      if (!res.ok) throw new Error(`Serverot vrati greshka ${res.status}.`);
      const data = await res.json();
      attempts.current = 0;
      setState({ data, error: null, waking: false });
    } catch (e) {
      attempts.current += 1;
      if (attempts.current <= 24) {
        setState((s) => ({ ...s, waking: true }));
        timer.current = setTimeout(load, 5000);
      } else {
        const msg = e.message === "warming_up" || e.name === "TypeError"
          ? "Serverot ne odgovara. Proveri dali e pushten na Render i probaj povtorno."
          : e.message;
        setState({ data: null, error: msg, waking: false });
      }
    }
  }, []);

  useEffect(() => {
    load();
    return () => clearTimeout(timer.current);
  }, [load]);

  const retry = useCallback(() => {
    attempts.current = 0;
    setState({ data: null, error: null, waking: true });
    load();
  }, [load]);

  return { ...state, retry };
}
