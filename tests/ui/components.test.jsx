import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ItineraryCard from '@/components/ItineraryCard';
import CitationPanel from '@/components/CitationPanel';
import TripMap from '@/components/TripMap';
import { changesBetween, itineraryICS, safeUrl } from '@/lib/trip';
import { citation, itinerary, item, tripId } from './fixtures';

const leaflet = vi.hoisted(() => {
  const layer = () => ({ addTo: vi.fn().mockReturnThis(), bindPopup: vi.fn().mockReturnThis(), on: vi.fn().mockReturnThis() });
  return { map: vi.fn(() => ({ fitBounds: vi.fn(), remove: vi.fn() })), tileLayer: vi.fn(layer), marker: vi.fn(layer), divIcon: vi.fn(value => value), polyline: vi.fn(layer), latLngBounds: vi.fn(value => value) };
});
vi.mock('leaflet', () => ({ default: leaflet }));

describe('ItineraryCard', () => {
  it('renders time, place, category, cost, unknown costs and citation badges', () => {
    render(<ItineraryCard day={{ ...itinerary.days[0], items: [item, itinerary.days[1].items[0]] }} number={1} citations={[citation]} onCitation={() => {}} />);
    expect(screen.getByText('09:00')).toBeInTheDocument();
    expect(screen.getByText('Synthetic Demo Hotel')).toBeInTheDocument();
    expect(screen.getByText('hotel')).toBeInTheDocument();
    expect(screen.getByText('USD 120.00')).toBeInTheDocument();
    expect(screen.getByText('Cost unknown')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Source 1 for Synthetic Demo Hotel' })).toBeInTheDocument();
  });
  it('deduplicates repeated citation records and chunk IDs in badges and print sources', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const second = { ...citation, chunk_id: 'synthetic-second', title: 'Synthetic second source' };
    const onCitation = vi.fn();
    const day = { ...itinerary.days[0], items: [{ ...item, chunk_ids: [citation.chunk_id, citation.chunk_id, second.chunk_id, 'missing', 'missing'] }] };
    const { container, rerender } = render(<ItineraryCard day={day} number={1} citations={[citation, { ...citation }, second]} onCitation={onCitation} />);
    expect(screen.getAllByRole('button', { name: /Source \d for/ })).toHaveLength(2);
    expect(container.querySelectorAll('.print-sources p')).toHaveLength(2);
    expect(screen.getAllByText('Source details unavailable')).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: 'Source 1 for Synthetic Demo Hotel' }));
    expect(onCitation).toHaveBeenLastCalledWith(citation);
    rerender(<ItineraryCard day={day} number={1} citations={[second, citation, citation, second]} onCitation={onCitation} />);
    expect(container.querySelectorAll('.print-sources p')).toHaveLength(2);
    expect(container.querySelector('.print-sources p')).toHaveTextContent(citation.title);
    expect(consoleError).not.toHaveBeenCalled();
  });
  it('shows a synthetic data badge on priced hotels and flights, including zero', () => {
    render(<ItineraryCard day={{ date: itinerary.days[0].date, items: [item, { ...item, id: 'synthetic-flight', category: 'flight', cost: 0 }] }} number={1} />);
    expect(screen.getAllByText('Synthetic data')).toHaveLength(2);
    expect(screen.getAllByTitle(/Generated inventory/)).toHaveLength(2);
  });
  it('opens the citation panel with the right license, excerpt and URL and restores focus', async () => {
    function Harness() {
      const [selected, select] = useState(null);
      return <><ItineraryCard day={itinerary.days[0]} number={1} citations={[citation]} onCitation={select} />{selected && <CitationPanel citation={selected} onClose={() => select(null)} />}</>;
    }
    render(<Harness />);
    const trigger = screen.getByRole('button', { name: 'Source 1 for Synthetic Demo Hotel' });
    await userEvent.click(trigger);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Wikivoyage, CC BY-SA 4.0')).toBeInTheDocument();
    expect(screen.getByText(citation.excerpt)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Read original/ })).toHaveAttribute('href', citation.url);
    expect(screen.getByRole('button', { name: 'Close source' })).toHaveFocus();
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});

it('map renders only items with coordinates and a geocode reference, without geocoding', async () => {
  const located = { ...item, id: 'synthetic-located', coords: { lat: 10, lon: 20 }, coord_tool_result_id: 'synthetic-geocode' };
  const second = { ...located, id: 'synthetic-next', coords: { lat: 11, lon: 21 } };
  const unverified = { ...located, id: 'synthetic-unverified', coord_tool_result_id: null };
  const plan = { ...itinerary, days: [{ date: '2027-04-10', items: [located, item, unverified, second] }] };
  const { unmount } = render(<TripMap itinerary={plan} />);
  await waitFor(() => expect(leaflet.marker).toHaveBeenCalledTimes(2));
  expect(leaflet.marker.mock.calls.map(args => args[0])).toEqual([[10, 20], [11, 21]]);
  expect(leaflet.polyline).toHaveBeenCalledWith([[10, 20], [11, 21]], expect.any(Object));
  expect(screen.getAllByText(/location not mapped/)).toHaveLength(2);
  expect(screen.getByRole('link', { name: 'OpenStreetMap contributors' })).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
  const map = leaflet.map.mock.results[0].value;
  unmount(); expect(map.remove).toHaveBeenCalled();
});

it('exports escaped ICS with local times and synthetic labeling; diffs include removals', () => {
  const plan = { ...itinerary, days: [{ date: '2027-04-10', items: [{ ...item, place: 'Synthetic, Hotel;\nNew line' }] }] };
  const output = itineraryICS(plan, tripId, [citation], new Date('2026-11-03T12:00:00Z'));
  expect(output).toContain('DTSTART:20270410T090000\r\n');
  expect(output).toContain('SUMMARY:Synthetic\\, Hotel\\;\\nNew line');
  expect(output).toContain('Synthetic data');
  expect(output).toContain('END:VCALENDAR\r\n');
  expect(changesBetween(itinerary, plan)).toEqual({ changed: [item.id], removed: [itinerary.days[1].items[0]] });
  expect(safeUrl('javascript:alert(1)')).toBeNull();
});
