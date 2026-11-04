export function safeUrl(value) {
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}

export function isSyntheticPrice(item) {
  // These categories currently use only the backend's synthetic inventory.
  return item.cost != null && /\b(hotels?|flights?|accommodations?|lodging)\b/i.test(item.category);
}

export function mappedItems(itinerary) {
  return (itinerary?.days || []).flatMap(day => day.items).filter(item =>
    item.coord_tool_result_id && Number.isFinite(item.coords?.lat) && Number.isFinite(item.coords?.lon)
    && Math.abs(item.coords.lat) <= 90 && Math.abs(item.coords.lon) <= 180);
}

export function changesBetween(before, after) {
  const old = new Map((before?.days || []).flatMap(day => day.items).map(item => [item.id, item]));
  const current = (after?.days || []).flatMap(day => day.items);
  return {
    changed: current.filter(item => before && JSON.stringify(old.get(item.id)) !== JSON.stringify(item)).map(item => item.id),
    removed: [...old.values()].filter(item => !current.some(next => next.id === item.id)),
  };
}

const escapeICS = value => String(value).replace(/\\/g, "\\\\").replace(/\r?\n/g, "\\n").replace(/;/g, "\\;").replace(/,/g, "\\,");
const localTime = value => value.replace(/[-:]/g, "").slice(0, 15);
function foldLine(line) {
  const encoder = new TextEncoder();
  let result = "", length = 0;
  for (const character of line) {
    const size = encoder.encode(character).length;
    if (length + size > 75) { result += "\r\n "; length = 1; }
    result += character; length += size;
  }
  return result;
}
export function itineraryICS(itinerary, tripId, citations = [], now = new Date()) {
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Travel Planner//Itinerary//EN", "CALSCALE:GREGORIAN"];
  for (const day of itinerary.days) for (const item of day.items) {
    const sources = citations.filter(c => item.chunk_ids.includes(c.chunk_id)).map(c => `${c.title}: ${safeUrl(c.url) || ""} (${c.license || "License not supplied"})`).join("\n");
    const price = item.cost == null ? "Cost unknown" : `${item.cost} ${item.currency}${isSyntheticPrice(item) ? " — Synthetic data; not booking availability" : ""}`;
    lines.push("BEGIN:VEVENT", `UID:${escapeICS(`${tripId}-${item.id}`)}@travel-planner`,
      `DTSTAMP:${now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "")}`,
      `DTSTART:${localTime(item.start)}`, `DTEND:${localTime(item.end)}`,
      `SUMMARY:${escapeICS(item.place)}`, `LOCATION:${escapeICS(item.place)}`,
      `DESCRIPTION:${escapeICS(`${item.category}\n${price}\nLocal destination time; check your calendar timezone.\n${sources}`)}`, "END:VEVENT");
  }
  return [...lines, "END:VCALENDAR"].map(foldLine).join("\r\n") + "\r\n";
}
