# Chat product

The home page is a JavaScript App Router chat client using Tailwind v4. `jsconfig.json` is retained. Removed: `src/app/flights/`, `src/app/airports/`, and `src/app/utils/`; these were the old prediction/list/detail screens and endpoint helpers. Backend routes are unchanged. The layout, metadata and styles were replaced; the favicon was kept. Fonts use the system/Georgia stack, so production builds do not fetch fonts.

## Components and contracts

- `src/components/ChatApp.jsx`: POST SSE conversation, progress by call ID, abort, retry, quick edits, preference confirmation, Undo and browser-local history.
- `src/lib/sse.js`: incremental UTF-8/line decoding, CRLF and heartbeat support, request ID consistency, terminal events and premature-close detection.
- `src/components/ItineraryCard.jsx`: itinerary values, unknown costs, citations, generated-inventory badges and edit highlights. Prices are displayed from the server itinerary, never calculated or supplied by the UI. Hotel/flight/accommodation/lodging categories currently denote synthetic inventory; the itinerary contract has no per-item source field. If mixed real inventory is added, extend that contract before changing the badge behavior.
- `src/components/CitationPanel.jsx`: native modal dialog with focus restoration, Escape dismissal, source excerpt, validated HTTP(S) link and supplied license. Wikivoyage sources display `Wikivoyage, CC BY-SA 4.0` when the supplied license is CC BY-SA 4.0; other sources retain their own license.
- `src/components/TripMap.jsx`: client-loaded Leaflet, attributed OpenStreetMap tiles, only supplied finite coordinates with a `coord_tool_result_id`. No frontend geocoding. Each day's dotted line connects mapped stops and is not a walking/transit route. Missing/unverified coordinates appear under “locations not mapped.”
- `src/lib/trip.js`: item comparisons, URL filtering and ICS export. Calendar times are floating local destination times because the backend itinerary uses local wall-clock datetimes without offsets. Check your calendar timezone when importing. ICS includes synthetic price labeling and citations. Print styles include source URLs/licenses and synthetic badges while hiding interactive controls.

There is no backend trip-list endpoint. The sidebar keeps up to 20 completed trip snapshots and IDs in this browser's localStorage; it does not synchronize history across browsers. Existing IDs are used for subsequent turns. “Check latest saved itinerary” reads the versions endpoint; Undo posts to `/api/trips/{id}/undo`. Local messages/citations remain the browser's snapshot when reloading server itinerary versions. Clearing browser history does not delete Postgres records. Avoid sensitive information on shared devices.

The existing stream sends final-message text chunks after validation, not raw model tokens. Progress events and heartbeats arrive during planning. A disconnected request may already have committed its itinerary; inspect the latest saved version before repeating an edit. A new trip whose connection closes before `done` may have no recoverable ID in the browser, because the backend only supplies the new ID at completion. There is no automatic retry.

## Configuration

Set `NEXT_PUBLIC_API_URL` to the browser-reachable backend base URL before starting development or building. There is no hardcoded backend host or fallback in application code. If unset, sending a message shows a configuration error. Next embeds public variables at build time; changing one for production requires rebuilding. Dockerfile/Compose pass this value as a build argument. It is a public URL, never a place for credentials.

A separate-origin backend must allow the frontend origin via `FRONTEND_ORIGINS`. OpenStreetMap tiles use their public HTTPS endpoint with attribution. No paid mapping service or routing API is used. See [Leaflet's reference](https://leafletjs.com/reference) for the map APIs and [Next's Vitest guide](https://nextjs.org/docs/14/app/building-your-application/testing/vitest) for the component-test setup. The TypeScript dev dependency satisfies the existing ESLint parser; application files remain JavaScript, with no tsconfig.

## M7 — Verify locally

Prerequisites: complete M4–M6 for the local database, synthetic inventory, retrieval corpus/models and Ollama. No new model/key/recording is required.

From the repository root:

```bash
npm ci
npm run lint
npm test
npm run build
```

Terminal A, using the existing host Postgres configuration:

```bash
source venv/bin/activate
export PYTHONPATH=.
export DEBUG=false
export OLLAMA_BASE_URL=http://localhost:11434
export RECORD=0 LLM_REPLAY=0
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export FRONTEND_ORIGINS=http://localhost:3000
unset GEMINI_API_KEY
python -m uvicorn backend.main:app --host localhost --port 8082
```

Terminal B:

```bash
export NEXT_PUBLIC_API_URL=http://localhost:8082
npm run dev
```

Open the frontend URL printed by Next. If port 3000 was occupied and Next selects another port, update `FRONTEND_ORIGINS` and restart the backend.

1. Check desktop and narrow/mobile layouts; use Tab to reach New trip, history, the composer and Send. The skip link should move to the planner.
2. Click “Try five days in Lisbon,” inspect the prompt, then submit. Tool progress should update and Stop should be available. Text appears when the backend emits it; it need not appear during the model's initial planning.
3. Inspect days/times, unknown costs and synthetic hotel badges. Focus or hover a badge to read its explanation. No inferred price or total should appear.
4. Open a citation. Verify title/excerpt, source URL and license; Tab should remain inside the native dialog, Escape should close it, and focus should return to its trigger. No source badge is shown as a working button if its details are absent.
5. Inspect the map. Items without geocode-result coordinates must say “location not mapped.” For an itinerary with supplied coordinates, verify markers, per-day dotted lines and OSM attribution. This UI does not invent coordinates to fill an empty map.
6. Use “Make day 2 cheaper” and “Add more museums.” Inspect changed-item labels or the removed-items list. Undo should restore the preceding saved itinerary. Failed edits should leave the previous itinerary available.
7. Export the calendar and import it into a local calendar, checking local times and synthetic labeling. Use Print / Save PDF; verify days, source URLs/licenses and synthetic labels remain readable and controls are hidden.
8. Start another request and press Stop before completion. Loading should clear. If editing an existing trip, use “Check latest saved itinerary” before retrying; a commit preceding disconnection remains saved.
9. With the backend stopped, submit a message: an error and Retry should appear. Restart it and retry. Do not assume a disconnected mutation failed before committing.
10. Reload the page and open the saved trip in the sidebar. Start New trip and confirm follow-ups to the saved trip still carry its ID. Clear browser history when using a shared machine; this is not server deletion.

## Automated coverage

All frontend tests use synthetic fixtures. HTTP/Leaflet are mocked and unit tests make no live network/model calls.

- `tests/ui/sse.test.js`: chunked/split events, CRLF, heartbeat comments, split UTF-8, terminal error, premature closure, invalid JSON/request IDs, HTTP/content-type failure.
- `tests/ui/components.test.jsx`: ItineraryCard values, priced-flight/hotel synthetic badges (including zero), citation panel/license/focus, coordinate-only map markers/lines, map cleanup, ICS escaping and item diffs.
- `tests/ui/chat.test.jsx`: partial text/progress, stop/abort, error/retry, persisted history, quick edit, Undo endpoint, missing API config and print action.

Verification on this branch: 15 frontend tests passed; frontend lint and production build passed. Python regression checks passed (164 tests, 15 deselected, 3 existing Pydantic deprecation warnings). The first Python command lacked `PYTHONPATH=.` and failed collection; it was rerun with that environment variable and passed. Native Chrome automation timed out, so live browser layout, tile rendering, PDF output and end-to-end model-backed UI verification are **not run**. Docker image rebuild is **not run**. No commit/push/PR was performed.

## Edit clarification and Undo errors

Edits must identify one existing day using `day N`, for example `Add more museums to day 2`. The agent asks for a day rather than trusting a classifier-invented day when none is stated. A rejected or clarification-only edit does not create an itinerary version. Undo returns HTTP 409 when there is no preceding version; the UI explains this separately from concurrent-update conflicts and clears any old chat Retry action. No validation rules have been weakened.
