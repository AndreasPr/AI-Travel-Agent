// Synthetic UI fixtures. These are not travel recommendations or measured prices.
export const citation = { chunk_id: 'synthetic-chunk', title: 'Synthetic Lisbon source', url: 'https://en.wikivoyage.org/wiki/Lisbon', license: 'CC BY-SA 4.0', attribution: 'Content from Wikivoyage is licensed under CC BY-SA 4.0.', excerpt: 'Synthetic excerpt used only for interface testing.' };
export const item = { id: 'synthetic-hotel', start: '2027-04-10T09:00:00', end: '2027-04-10T10:00:00', place: 'Synthetic Demo Hotel', category: 'hotel', cost: '120.00', currency: 'USD', chunk_ids: [citation.chunk_id], tool_result_ids: ['synthetic-price'], coords: null, coord_tool_result_id: null };
export const itinerary = { trip: { start_date: '2027-04-10', end_date: '2027-04-11', currency: 'USD' }, days: [{ date: '2027-04-10', items: [item] }, { date: '2027-04-11', items: [{ ...item, id: 'synthetic-museum', start: '2027-04-11T10:00:00', end: '2027-04-11T11:00:00', place: 'Synthetic Museum', category: 'museum', cost: null }] }] };
export const tripId = '11111111-1111-4111-8111-111111111111';
export const event = (type, fields = {}) => ({ type, request_id: '22222222-2222-4222-8222-222222222222', ...fields });
export const frame = value => `event: ${value.type}\ndata: ${JSON.stringify(value)}\n\n`;
export function streamResponse(events) {
  return new Response(new ReadableStream({ start(controller) { for (const value of events) controller.enqueue(new TextEncoder().encode(frame(value))); controller.close(); } }), { headers: { 'Content-Type': 'text/event-stream' } });
}
export function successEvents(plan = itinerary) {
  return [event('message_start'), event('tool_start', { call_id: 'call', tool: 'search_destinations', argument_summary: { fields: ['query'] } }), event('tool_end', { call_id: 'call', tool: 'search_destinations', status: 'ok', duration_ms: 12 }), event('token', { text: 'Synthetic plan ready.' }), event('itinerary_update', { itinerary: plan }), event('citations', { citations: [citation] }), event('done', { trip_id: tripId, message: 'Synthetic plan ready.', budget_met: null, usage: {} })];
}
