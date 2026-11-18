"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { login, register } from "@/lib/auth";
export default function AuthForm({ registering = false }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError("");
    try { await (registering ? register : login)(email, password); setPassword(""); router.replace("/"); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  return <main className="mx-auto max-w-md p-8 text-slate-900"><h1 className="mb-6 text-3xl font-semibold">{registering ? "Create an account" : "Log in"}</h1>
    <form onSubmit={submit} className="grid gap-4">
      <label className="grid gap-2">Email<input className="rounded border bg-white p-3" type="email" autoComplete="username" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label className="grid gap-2">Password<input className="rounded border bg-white p-3" type="password" autoComplete={registering ? "new-password" : "current-password"} required minLength={registering ? 12 : 1} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} /></label>
      {registering && <p>Use 12–128 characters. A long, unique passphrase is welcome; repetitive passwords are rejected.</p>}
      {error && <p role="alert" className="text-red-800">{error}</p>}
      <button disabled={busy} className="rounded bg-slate-900 px-4 py-3 text-white disabled:opacity-60">{busy ? "Please wait…" : registering ? "Register" : "Log in"}</button>
    </form><p className="mt-6"><Link className="underline" href={registering ? "/login" : "/register"}>{registering ? "Already have an account? Log in" : "Create an account"}</Link></p>
  </main>;
}
