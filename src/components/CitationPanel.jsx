"use client";
import { useEffect, useRef } from "react";
import { safeUrl } from "@/lib/trip";

export default function CitationPanel({ citation, onClose }) {
  const dialog = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    const node = dialog.current;
    node.showModal();
    return () => { node.close(); previous?.focus(); };
  }, []);
  const url = safeUrl(citation.url);
  const wikivoyage = url && (new URL(url).hostname === "wikivoyage.org" || new URL(url).hostname.endsWith(".wikivoyage.org"));
  return <dialog ref={dialog} className="citation-panel" aria-labelledby="source-title" onCancel={onClose} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="panel-heading"><p className="eyebrow">Behind the recommendation</p><button autoFocus className="icon-button" onClick={onClose} aria-label="Close source">✕</button></div>
    <span className="source-icon" aria-hidden="true">↗</span><h2 id="source-title">{citation.title || "Source"}</h2>
    <p className="source-license">{wikivoyage ? "Wikivoyage, " : ""}{citation.license || "License not supplied"}</p>
    <blockquote>{citation.excerpt || "No excerpt supplied."}</blockquote>
    {citation.attribution && <p className="muted">{citation.attribution}</p>}
    {url && <a className="primary link-button" href={url} target="_blank" rel="noopener noreferrer">Read original source ↗</a>}
    {url && <p className="source-url">{url}</p>}
  </dialog>;
}
