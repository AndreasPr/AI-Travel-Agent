"use client";
import ChatApp from "@/components/ChatApp";
import { RequireAuth } from "@/components/AuthProvider";
import { useEffect, useState } from "react";
import { endpoint } from "@/lib/auth";
export default function Home() {
  const [config, setConfig] = useState(null);
  useEffect(() => {
    const abort = new AbortController();
    fetch(endpoint("/api/config"), { signal: abort.signal }).then(r => r.ok ? r.json() : null).then(setConfig).catch(() => {});
    return () => abort.abort();
  }, []);
  return <RequireAuth>{user => <ChatApp key={user.id} userId={user.id} demoConfig={config} />}</RequireAuth>; }
