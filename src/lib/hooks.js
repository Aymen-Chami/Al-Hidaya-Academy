import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Loads data and keeps it fresh by polling while the tab is visible (the backend is the
 * source of truth; seat counts and statuses change as other families sign up).
 *
 *   const { data, error, loading, reload } = useResource(fetcher, { interval: 7000, enabled })
 *
 * - `loading` is true only until the first response; later polls refresh silently.
 * - A failed poll keeps the last good data; `error` is only surfaced when there is no data yet.
 * - `fetcher` should be stable (module function or useCallback). When it changes (e.g. a new
 *   filter), the old data is treated as stale and `loading` is true again until the new
 *   response arrives — so a filtered list never flashes the previous filter's results.
 */
export function useResource(fetcher, { interval = 7000, enabled = true } = {}) {
  const [state, setState] = useState({ data: null, error: null, source: null });
  const seq = useRef(0);

  const reload = useCallback(async () => {
    if (!enabled) return;
    const mine = ++seq.current;
    try {
      const data = await fetcher();
      if (mine === seq.current) setState({ data, error: null, source: fetcher });
    } catch (error) {
      if (mine === seq.current) {
        setState((s) => (s.source === fetcher ? { ...s, error } : { data: null, error, source: fetcher }));
      }
    }
  }, [fetcher, enabled]);

  useEffect(() => {
    if (!enabled) return undefined;
    // reload() only sets state after its fetch resolves, so this isn't a synchronous update.
    // oxlint-disable-next-line react/set-state-in-effect
    reload();
    if (!interval) return undefined;
    let timer = null;
    const start = () => {
      if (!timer) timer = setInterval(() => !document.hidden && reload(), interval);
    };
    const stop = () => {
      clearInterval(timer);
      timer = null;
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else {
        reload();
        start();
      }
    };
    start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [reload, interval, enabled]);

  const fresh = enabled && state.source === fetcher;
  return {
    data: fresh ? state.data : null,
    error: fresh ? state.error : null,
    loading: enabled && !fresh,
    reload,
  };
}

/**
 * Runs an API action with a busy flag, a success message, and a refresh afterwards.
 *
 *   const { run, busy } = useAction(notify)
 *   run("drop-12", () => familyApi.drop(12), { success: "Removed.", after: reload })
 *
 * `busy` holds the key of the action in flight so only that button shows a spinner, and
 * a second click can't fire the same request twice. Errors become an error toast with the
 * server's own message; the refresh runs either way so the screen matches the server.
 */
export function useAction(notify) {
  const [busy, setBusy] = useState(null);
  const inFlight = useRef(new Set());

  const run = useCallback(
    async (key, action, { success, after } = {}) => {
      if (inFlight.current.has(key)) return undefined;
      inFlight.current.add(key);
      setBusy(key);
      try {
        const result = await action();
        if (success) notify(typeof success === "function" ? success(result) : success);
        return result;
      } catch (e) {
        notify(e.message || "That didn't work. Please try again.", "error");
        return undefined;
      } finally {
        inFlight.current.delete(key);
        setBusy((b) => (b === key ? null : b));
        if (after) after();
      }
    },
    [notify]
  );

  return { run, busy };
}

// Tiny hash router: "#/manage" -> "manage". Survives refreshes; no dependency needed.
export function useHashRoute() {
  const read = () => window.location.hash.replace(/^#\/?/, "").split("?")[0];
  const [route, setRoute] = useState(read);

  useEffect(() => {
    const onHash = () => setRoute(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate = useCallback((next) => {
    const target = `#/${next}`;
    if (window.location.hash !== target) window.location.hash = target;
    else setRoute(next);
    window.scrollTo({ top: 0 });
  }, []);

  return [route, navigate];
}

// Debounce a changing value (search-as-you-type).
export function useDebounced(value, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}
