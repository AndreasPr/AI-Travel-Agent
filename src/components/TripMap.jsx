"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { mappedItems } from "@/lib/trip";

export default function TripMap({ itinerary }) {
  const container = useRef(null);
  const [error, setError] = useState(false);
  const items = useMemo(() => mappedItems(itinerary), [itinerary]);
  const unmapped = (itinerary?.days || []).flatMap(day => day.items).filter(item => !items.includes(item));
  useEffect(() => {
    if (!items.length) return;
    let disposed = false, map;
    setError(false);
    import("leaflet").then(module => {
      if (disposed) return;
      const L = module.default || module;
      map = L.map(container.current, { scrollWheelZoom: false });
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map).on("tileerror", () => setError(true));
      const points = items.map(item => [item.coords.lat, item.coords.lon]);
      items.forEach((item, index) => {
        const label = document.createElement("span"); label.textContent = `${index + 1}. ${item.place}`;
        L.marker(points[index], { title: item.place, icon: L.divIcon({ className: "trip-marker", html: `<span>${index + 1}</span>`, iconSize: [28, 28], iconAnchor: [14, 14] }) }).addTo(map).bindPopup(label);
      });
      // Draw each day's supplied points only; no inferred coordinates or routing service.
      for (const day of itinerary.days) {
        const route = day.items.filter(item => items.includes(item)).map(item => [item.coords.lat, item.coords.lon]);
        if (route.length > 1) L.polyline(route, { color: "#126b60", weight: 3, dashArray: "6 6" }).addTo(map);
      }
      map.fitBounds(L.latLngBounds(points), { padding: [32, 32], maxZoom: 14 });
    }).catch(() => { if (!disposed) setError(true); });
    return () => { disposed = true; map?.remove(); };
  }, [items, itinerary]);
  return <section className="map-card" aria-label="Itinerary map">
    <div className="section-heading"><h3>Your route</h3><span className="eyebrow">On the map</span></div>
    {items.length ? <div ref={container} className="map-canvas" aria-label="Map of supplied itinerary coordinates" /> : <div className="map-empty"><span aria-hidden="true">⌖</span><p>Your places will appear here</p><small>Only verified itinerary coordinates are mapped.</small></div>}
    {error && <p role="status">Map tiles could not load. Your itinerary is still available.</p>}
    {items.length > 0 && <><p className="map-caption">Dotted lines connect stops; they are not navigation directions.</p><ol className="mapped-list">{items.map(item => <li key={item.id}>{item.place}</li>)}</ol></>}
    {unmapped.length > 0 && <details><summary>{unmapped.length} locations not mapped</summary><ul>{unmapped.map(item => <li key={item.id}>{item.place} — location not mapped</li>)}</ul></details>}
    <p className="map-attribution">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a></p>
  </section>;
}
