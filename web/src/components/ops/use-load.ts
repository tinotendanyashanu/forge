"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ActionResult } from "@/lib/types";

/** Loads data through a server action whenever `key` changes. Keeps the previous data while reloading. */
export function useLoad<T>(key: string, load: () => Promise<ActionResult<T>>) {
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });
  const [state, setState] = useState<{ key: string | null; data: T | null; error: string | null }>({
    key: null,
    data: null,
    error: null,
  });
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    loadRef.current().then((r) => {
      if (!alive) return;
      setState((s) => (r.ok ? { key, data: r.data, error: null } : { key, data: s.data, error: r.error }));
    });
    return () => {
      alive = false;
    };
  }, [key, nonce]);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data: state.data, error: state.error, loading: state.key !== key, reload };
}
