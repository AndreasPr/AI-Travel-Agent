import { isSyntheticPrice } from "@/lib/trip";

export default function ItineraryCard({ day, number, citations = [], onCitation, changed = [] }) {
  // A source may recur across tool results; render it once per item.
  const sourcesById = new Map();
  for (const source of citations) {
    if (!sourcesById.has(source.chunk_id)) sourcesById.set(source.chunk_id, source);
  }
  return <section className="day-card" aria-labelledby={`day-${number}`}>
    <header className="day-heading"><span className="day-number">{String(number).padStart(2, "0")}</span><div>
      <p className="eyebrow">Day {number}</p><h3 id={`day-${number}`}>{new Date(`${day.date}T12:00:00`).toLocaleDateString("en", { weekday: "long", month: "short", day: "numeric" })}</h3>
    </div><span className="count-label">{day.items.length} stops</span></header>
    <ol className="day-items">{day.items.map(item => <li key={item.id} className={changed.includes(item.id) ? "item changed" : "item"}>
      <div className="item-time"><time dateTime={item.start}>{item.start.slice(11, 16)}</time><span>— {item.end.slice(11, 16)}</span></div>
      <div className="item-content"><span className="category">{item.category}</span><h4>{item.place}</h4>
        {changed.includes(item.id) && <span className="change-label">Updated in this edit</span>}
        <div className="citation-badges">{[...new Set(item.chunk_ids)].map((id, index) => {
          const citation = sourcesById.get(id);
          return citation ? <button key={id} className="citation-badge" onClick={() => onCitation(citation)} aria-label={`Source ${index + 1} for ${item.place}`}>↗ Source {index + 1}</button>
            : <span key={id} className="muted">Source details unavailable</span>;
        })}</div>
        <div className="print-sources">{[...new Set(item.chunk_ids)].map(id => sourcesById.get(id)).filter(Boolean).map(source => <p key={source.chunk_id}>{source.title} — {source.url} — {source.license}</p>)}</div>
      </div>
      <div className="item-price">{item.cost == null ? <span className="muted">Cost unknown</span> : <strong>{item.currency} {Number(item.cost).toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>}
        {isSyntheticPrice(item) && <span className="synthetic" tabIndex={0} title="Generated inventory for demonstration. These are not real prices or booking availability." aria-label="Synthetic data: generated inventory, not real prices or booking availability">Synthetic data<span className="synthetic-tip" role="tooltip">Generated inventory for demonstration. Not real prices or booking availability.</span></span>}
      </div>
    </li>)}</ol>
  </section>;
}
