"use client";
import { useEffect, useRef, useState } from "react";
import { consumeSSE } from "@/lib/sse";
import { changesBetween, itineraryICS } from "@/lib/trip";
import ItineraryCard from "./ItineraryCard";
import CitationPanel from "./CitationPanel";
import TripMap from "./TripMap";

const STORAGE = "travel-planner.trips.v1";
const blankTrip = () => ({ id: null, title: "New trip", messages: [], itinerary: null, citations: [], budget: null });
const toolLabels = { search_destinations: "Searching destinations…", get_weather: "Checking weather…", convert_currency: "Converting currency…", geocode_place: "Locating places…", search_flights: "Searching synthetic flights…", search_hotels: "Searching synthetic hotels…", validate_itinerary: "Validating budget…" };
const starter = "Plan five days in Lisbon from 2027-04-10 through 2027-04-14 under $1,500 USD, with museums and food. Use synthetic hotel quotes and leave unknown activity costs unpriced.";
function endpoint(path) {
  const base = process.env.NEXT_PUBLIC_API_URL;
  if (!base) throw new Error("Set NEXT_PUBLIC_API_URL and restart the frontend to connect to the planner.");
  return `${base.replace(/\/$/, "")}${path}`;
}

export default function ChatApp() {
  const [trip, setTrip] = useState(blankTrip);
  const [history, setHistory] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");
  const [storageError, setStorageError] = useState("");
  const [partial, setPartial] = useState("");
  const [progress, setProgress] = useState([]);
  const [citation, setCitation] = useState(null);
  const [changes, setChanges] = useState({ changed: [], removed: [] });
  const [proposal, setProposal] = useState(null);
  const controller = useRef(null), input = useRef(null), retry = useRef(null);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE) || "[]");
      if (!Array.isArray(saved)) throw new Error();
      setHistory(saved.filter(value => value && typeof value.id === "string" && typeof value.title === "string" && Array.isArray(value.messages) && Array.isArray(value.citations)).slice(0, 20));
    } catch { setStorageError("Browser history could not be read. You can still plan a new trip."); }
    return () => controller.current?.abort();
  }, []);

  function remember(value) {
    if (!value.id) return;
    setHistory(previous => {
      const next = [value, ...previous.filter(entry => entry.id !== value.id)].slice(0, 20);
      try { localStorage.setItem(STORAGE, JSON.stringify(next)); }
      catch { setStorageError("Browser storage is unavailable or full. This trip may not appear here after reload."); }
      return next;
    });
  }

  async function send(message, isRetry = false) {
    if (controller.current || !message.trim()) return;
    const abort = new AbortController(); controller.current = abort;
    retry.current = message;
    let current = { ...trip, messages: isRetry ? trip.messages : [...trip.messages, { role: "user", text: message }], title: trip.id ? trip.title : message.slice(0, 70) };
    const before = trip.itinerary;
    setTrip(current); setDraft(""); setError(""); setPartial(""); setProgress([]); setProposal(null);
    setBusy(true); setPhase("Planning your trip…");
    try {
      const response = await fetch(endpoint("/api/chat/stream"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, trip_id: trip.id }), signal: abort.signal });
      await consumeSSE(response, event => {
        if (event.type === "token") setPartial(previous => previous + event.text);
        if (event.type === "tool_start") {
          setPhase(toolLabels[event.tool] || "Working on your trip…");
          setProgress(previous => [...previous, { ...event, status: "running" }]);
        }
        if (event.type === "tool_end") setProgress(previous => previous.map(call => call.call_id === event.call_id ? { ...call, ...event } : call));
        if (event.type === "itinerary_update") {
          current = { ...current, itinerary: event.itinerary };
          setTrip(current); setChanges(changesBetween(before, event.itinerary));
        }
        if (event.type === "citations") { current = { ...current, citations: event.citations }; setTrip(current); }
        if (event.type === "error") { setError(event.message); setPhase("Could not complete this turn."); }
        if (event.type === "done") {
          current = { ...current, id: event.trip_id, budget: event.budget_met, messages: [...current.messages, { role: "assistant", text: event.message }] };
          setTrip(current); remember(current); setPartial(""); setProposal(event.preference_proposal);
          setPhase("Ready for your next idea."); retry.current = null;
        }
      });
    } catch (failure) {
      if (abort.signal.aborted) setPhase("Stopped. A change saved before stopping may still exist; check the latest version before retrying.");
      else setError(failure instanceof SyntaxError ? "The server returned an unreadable event. Please retry." : failure.message || "Could not connect to the planner.");
    } finally {
      setProgress(previous => previous.map(call => call.status === "running" ? { ...call, status: "interrupted" } : call));
      setBusy(false); controller.current = null;
    }
  }

  useEffect(() => { if (!busy && phase) input.current?.focus(); }, [busy, phase]);

  async function syncTrip(undo = false) {
    if (!trip.id || controller.current) return;
    const abort = new AbortController(); controller.current = abort;
    retry.current = null;
    setBusy(true); setError(""); setPhase(undo ? "Restoring the previous version…" : "Checking the latest saved version…");
    try {
      const response = await fetch(endpoint(`/api/trips/${trip.id}/${undo ? "undo" : "versions"}`), { method: undo ? "POST" : "GET", signal: abort.signal });
      if (!response.ok) {
        const failure = await response.json().catch(() => ({}));
        if (undo && response.status === 409 && failure.detail === "No earlier itinerary version")
          throw new Error("There is no earlier itinerary version to restore. A failed edit does not create a version; your saved itinerary is unchanged.");
        if (response.status === 409)
          throw new Error("The trip changed during this request. Check the latest saved itinerary before trying again.");
        throw new Error(`Could not load the saved trip (HTTP ${response.status}).`);
      }
      const data = await response.json();
      const itinerary = undo ? data.itinerary : data.versions.at(-1)?.itinerary;
      const current = { ...trip, itinerary: itinerary || null, budget: null };
      setChanges(changesBetween(trip.itinerary, current.itinerary)); setTrip(current); remember(current);
      setPhase(undo ? "Previous itinerary restored. Budget status will be checked on your next turn." : "Showing the latest saved itinerary.");
    } catch (failure) { if (!abort.signal.aborted) setError(failure.message); else setPhase("Request stopped."); }
    finally { controller.current = null; setBusy(false); }
  }

  function selectTrip(value) {
    if (busy) return;
    setTrip(value); setError(""); setPartial(""); setProgress([]); setPhase(""); setProposal(null);
    setChanges({ changed: [], removed: [] }); retry.current = null; input.current?.focus();
  }
  function download() {
    const blob = new Blob([itineraryICS(trip.itinerary, trip.id, trip.citations)], { type: "text/calendar;charset=utf-8" });
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = "trip-itinerary.ics"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <div className="app-shell">
    <a className="skip-link" href="#planner">Skip to planner</a>
    <aside className="sidebar" aria-label="Trip history">
      <a className="brand" href="/" aria-label="Travel planner home"><span className="brand-symbol" aria-hidden="true">↗</span><span>elsewhere<span className="brand-sub">A little more considered.</span></span></a>
      <button className="new-trip" disabled={busy} onClick={() => selectTrip(blankTrip())}><span>＋</span> New trip</button>
      <p className="eyebrow history-label">Your journeys</p>
      <nav aria-label="Saved trips">{history.length ? history.map(saved => <button key={saved.id} disabled={busy} className={`history-item ${trip.id === saved.id ? "selected" : ""}`} aria-current={trip.id === saved.id ? "page" : undefined} onClick={() => selectTrip(saved)}><span aria-hidden="true">↗</span><span>{saved.title}<small>{saved.itinerary?.trip.start_date || "Conversation"}</small></span></button>) : <p className="history-empty">A fresh page.<br />Your trips will collect here.</p>}</nav>
      <div className="sidebar-note"><span className="small-compass" aria-hidden="true">✳</span><p>Good trips start<br />with good questions.</p><small>History is saved in this browser. Avoid entering sensitive personal information.</small><button disabled={busy} className="text-button" onClick={() => { try { localStorage.removeItem(STORAGE); setHistory([]); selectTrip(blankTrip()); setDraft(""); setCitation(null); setStorageError(""); } catch { setStorageError("Could not clear browser history."); } }}>Clear browser history</button>{storageError && <p role="status">{storageError}</p>}</div>
    </aside>
    <main id="planner" className="workspace">
      <header className="topbar"><span className="eyebrow">THE TRIP STUDIO</span><span className="grounded-label"><span aria-hidden="true">●</span> Sources, not guesses</span></header>
      <div className="workspace-content">
        <div className="page-heading"><div><p className="eyebrow">A plan that feels like you</p><h1>{trip.itinerary ? "Your next chapter." : "Where shall we go?"}</h1><p className="intro">Tell us what you love. We’ll work on the details.</p></div><span className="heading-art" aria-hidden="true">✳</span></div>
        <div className="studio-grid"><div className="conversation-column">
          {!trip.messages.length && <section className="welcome-card"><span className="eyebrow">Room for a little discovery</span><h2>Museums before lunch.<br />Something local after.</h2><p>A thoughtful itinerary, with sources you can open and costs you can question.</p><button className="starter" disabled={busy} onClick={() => setDraft(starter)}>Try five days in Lisbon <span aria-hidden="true">↗</span></button><small>Example request · generated hotel inventory</small></section>}
          <section className="conversation" aria-label="Conversation">{trip.messages.map((message, index) => <div key={index} className={`message ${message.role}`}><span className="message-author">{message.role === "user" ? "YOU" : "YOUR PLANNER"}</span><p>{message.text}</p></div>)}</section>
          <div className="stream-text" role="status" aria-live="polite" aria-atomic="false">{partial}</div>
          {progress.length > 0 && <section className="progress-feed" aria-label="Planning progress"><p className="eyebrow">Making it happen</p><ul>{progress.map(call => <li key={call.call_id}><span aria-hidden="true">{call.status === "running" ? "◌" : call.status === "ok" ? "✓" : "—"}</span><span>{toolLabels[call.tool] || "Working on your trip…"}</span><small>{call.status === "running" ? "In progress" : call.status === "no_data" ? "No matching data" : call.status === "ok" ? "Done" : call.status === "interrupted" ? "Interrupted" : "Failed"}</small></li>)}</ul></section>}
          {phase && <p className="phase" role="status">{phase}</p>}
          {error && <div className="error-box" role="alert"><p>{error}</p>{retry.current && <button disabled={busy} onClick={() => send(retry.current, true)}>Retry message</button>}</div>}
          {proposal && <div className="proposal"><p>Save these preferences?</p><pre>{JSON.stringify(proposal, null, 2)}</pre><button disabled={busy} onClick={() => send("confirm preferences")}>Confirm preferences</button></div>}
          {trip.itinerary && <><div className="itinerary-heading"><div><p className="eyebrow">The day-by-day</p><h2>Your itinerary</h2></div><span className="budget-label">{trip.budget === true ? "Within stated budget" : trip.budget === false ? "Over budget" : "Total cost not confirmed"}</span></div>
            <div className="edit-actions"><button disabled={busy || trip.itinerary.days.length < 2} onClick={() => send("Make day 2 cheaper")}>Make day 2 cheaper</button><button disabled={busy} onClick={() => send("Add more museums")}>Add more museums</button></div>
            {changes.removed.length > 0 && <div className="removed-items"><strong>Removed in this edit</strong><ul>{changes.removed.map(item => <li key={item.id}>{item.place}</li>)}</ul></div>}
            {trip.itinerary.days.map((day, index) => <ItineraryCard key={day.date} day={day} number={index + 1} citations={trip.citations} onCitation={setCitation} changed={changes.changed} />)}
            <div className="export-actions"><button onClick={download} disabled={busy}>↓ Export calendar</button><button onClick={() => window.print()} disabled={busy}>Print / Save PDF</button><button onClick={() => syncTrip(true)} disabled={busy || !trip.id}>↶ Undo last edit</button></div><p className="export-note">Calendar times are local destination times. Synthetic quotes are not booking offers.</p></>}
          {trip.id && <button className="text-button refresh-button" disabled={busy} onClick={() => syncTrip(false)}>Check latest saved itinerary</button>}
          <form className="composer" onSubmit={event => { event.preventDefault(); send(draft); }}><label htmlFor="message">Your next idea</label><textarea ref={input} id="message" value={draft} onChange={event => setDraft(event.target.value)} maxLength={12000} rows={3} placeholder="A place, a date, a budget. Or just a feeling…" disabled={busy} required /><div className="composer-footer"><small>Grounded recommendations. Space to change your mind.</small>{busy ? <button type="button" className="stop-button" onClick={() => { controller.current?.abort(); setPhase("Stopping…"); }}>■ Stop</button> : <button className="primary" type="submit" disabled={!draft.trim()}>Let’s plan <span aria-hidden="true">↑</span></button>}</div></form>
        </div><aside className="trip-aside" aria-label="Trip overview"><TripMap itinerary={trip.itinerary} /><section className="principles-card"><span aria-hidden="true">✧</span><h3>A little transparency.</h3><p>Open a source badge to see where a recommendation comes from.</p><hr /><p>Flight and hotel prices use <strong>synthetic data</strong>. They’re generated examples, never live booking offers.</p></section></aside></div>
      </div>
      <footer className="page-footer">Less guesswork. More going places.</footer>
    </main>
    {citation && <CitationPanel citation={citation} onClose={() => setCitation(null)} />}
  </div>;
}
