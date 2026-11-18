"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authUser, refresh, subscribeAuth, logout } from "@/lib/auth";
const AuthContext = createContext(null);
export function AuthProvider({ children }) {
  const [user, setUser] = useState(authUser);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const unsubscribe = subscribeAuth(setUser);
    refresh().catch(() => {}).finally(() => setLoading(false));
    return unsubscribe;
  }, []);
  return <AuthContext.Provider value={{ user, loading }}>{children}</AuthContext.Provider>;
}
export function useAuth() { return useContext(AuthContext); }
export function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [error, setError] = useState("");
  useEffect(() => { if (!loading && !user) router.replace("/login"); }, [user, loading, router]);
  if (loading || !user) return <main className="p-8" role="status">Checking your session…</main>;
  return <><div className="flex items-center justify-end gap-4 bg-white px-6 py-3 text-slate-900"><span>Signed in</span><button className="rounded border px-4 py-2 focus-visible:outline-2" onClick={async () => {
    try { await logout(); router.replace("/login"); } catch (e) { setError(e.message); }
  }}>Log out</button>{error && <p role="alert">{error}</p>}</div>{children(user)}</>;
}
