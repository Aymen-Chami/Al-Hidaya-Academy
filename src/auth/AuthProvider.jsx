import { useCallback, useEffect, useMemo, useState } from "react";
import { authApi } from "../api/endpoints";
import { authEvents } from "../api/client";
import { AuthContext } from "./context";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = still checking the session cookie

  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then((me) => !cancelled && setUser(me))
      // 401 = not logged in; a network error also leaves us logged out (public pages still work).
      .catch(() => !cancelled && setUser(null));
    return () => {
      cancelled = true;
    };
  }, []);

  // Any 401 (expired or revoked session) drops the app back to the logged-out state.
  useEffect(() => {
    const onUnauthorized = () => setUser((u) => (u ? null : u));
    authEvents.addEventListener("unauthorized", onUnauthorized);
    return () => authEvents.removeEventListener("unauthorized", onUnauthorized);
  }, []);

  const login = useCallback(async (email, password) => {
    const me = await authApi.login(email, password);
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(() => ({ user, setUser, login, logout }), [user, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
