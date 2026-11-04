import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatApp from '@/components/ChatApp';
import { event, frame, itinerary, streamResponse, successEvents, tripId } from './fixtures';

vi.mock('@/components/TripMap', () => ({ default: () => <div>Map placeholder in synthetic UI test</div> }));
beforeEach(() => { localStorage.clear(); vi.stubEnv('NEXT_PUBLIC_API_URL', '/backend'); });

async function submit(text = 'Plan a synthetic trip') {
  await userEvent.type(screen.getByRole('textbox', { name: 'Your next idea' }), text);
  await userEvent.click(screen.getByRole('button', { name: /Let’s plan/ }));
}

it('streams partial text and paired progress, stores history and supports edits and Undo', async () => {
  let push;
  fetch.mockImplementationOnce(() => Promise.resolve(new Response(new ReadableStream({ start(controller) { push = value => controller.enqueue(new TextEncoder().encode(frame(value))); } }), { headers: { 'Content-Type': 'text/event-stream' } })));
  render(<ChatApp />);
  await submit();
  expect(fetch.mock.calls[0][0]).toBe('/backend/api/chat/stream');
  await act(async () => { push(event('message_start')); push(event('tool_start', { call_id: 'one', tool: 'get_weather' })); push(event('token', { text: 'Working on a synthetic plan' })); });
  expect(screen.getAllByText('Checking weather…').length).toBeGreaterThan(0);
  expect(screen.getByText('Working on a synthetic plan')).toHaveAttribute('aria-live', 'polite');
  await act(async () => { push(event('tool_end', { call_id: 'one', tool: 'get_weather', status: 'ok', duration_ms: 10 })); for (const value of successEvents().slice(4)) push(value); });
  await waitFor(() => expect(screen.getByText('Synthetic Demo Hotel')).toBeInTheDocument());
  await waitFor(() => expect(screen.getByRole('button', { name: 'Make day 2 cheaper' })).toBeEnabled());
  expect(JSON.parse(localStorage.getItem('travel-planner.trips.v1'))[0].id).toBe(tripId);
  const edited = structuredClone(itinerary); edited.days[1].items = [];
  fetch.mockResolvedValueOnce(streamResponse(successEvents(edited)));
  await userEvent.click(screen.getByRole('button', { name: 'Make day 2 cheaper' }));
  await waitFor(() => expect(screen.getByText('Removed in this edit')).toBeInTheDocument());
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ message: 'Make day 2 cheaper', trip_id: tripId });
  fetch.mockResolvedValueOnce(new Response(JSON.stringify({ itinerary, version: 3 }), { headers: { 'Content-Type': 'application/json' } }));
  await userEvent.click(screen.getByRole('button', { name: /Undo last edit/ }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith(`/backend/api/trips/${tripId}/undo`, expect.objectContaining({ method: 'POST' })));
  await waitFor(() => expect(screen.queryByText('Removed in this edit')).not.toBeInTheDocument());
  expect(screen.getByText('Synthetic Museum')).toBeInTheDocument();
});

it('Stop aborts the fetch and releases the loading state', async () => {
  let signal;
  fetch.mockImplementation((url, options) => new Promise((resolve, reject) => { signal = options.signal; signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))); }));
  render(<ChatApp />);
  await submit();
  await userEvent.click(screen.getByRole('button', { name: /Stop/ }));
  expect(signal.aborted).toBe(true);
  await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
  expect(screen.getByText(/Stopped\. A change saved/)).toBeInTheDocument();
});

it('shows server errors, retries the message and restores persisted trip history', async () => {
  fetch.mockResolvedValueOnce(streamResponse([event('message_start'), event('error', { code: 'timeout', message: 'Synthetic timeout message' })]));
  const first = render(<ChatApp />);
  await submit();
  expect(await screen.findByRole('alert')).toHaveTextContent('Synthetic timeout message');
  fetch.mockResolvedValueOnce(streamResponse(successEvents()));
  await userEvent.click(screen.getByRole('button', { name: 'Retry message' }));
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  await waitFor(() => expect(screen.getByText('Synthetic Demo Hotel')).toBeInTheDocument());
  expect(screen.getAllByText('YOU')).toHaveLength(1);
  first.unmount();
  render(<ChatApp />);
  await userEvent.click(screen.getByRole('button', { name: /Plan a synthetic trip/ }));
  expect(screen.getByText('Synthetic Demo Hotel')).toBeInTheDocument();
});

it('reports missing API configuration without a network request', async () => {
  vi.stubEnv('NEXT_PUBLIC_API_URL', '');
  render(<ChatApp />);
  await submit();
  expect(screen.getByRole('alert')).toHaveTextContent('Set NEXT_PUBLIC_API_URL');
  expect(fetch).not.toHaveBeenCalled();
});

it('uses the print action without navigating away', async () => {
  localStorage.setItem('travel-planner.trips.v1', JSON.stringify([{ id: tripId, title: 'Synthetic saved trip', messages: [], citations: [], itinerary, budget: null }]));
  const print = vi.spyOn(window, 'print').mockImplementation(() => {});
  render(<ChatApp />);
  fireEvent.click(screen.getByRole('button', { name: /Synthetic saved trip/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Print / Save PDF' }));
  expect(print).toHaveBeenCalledOnce();
});

it('explains Undo with no earlier version and does not retry a previous failed chat', async () => {
  localStorage.setItem('travel-planner.trips.v1', JSON.stringify([{ id: tripId, title: 'Synthetic saved trip', messages: [], citations: [], itinerary, budget: null }]));
  render(<ChatApp />);
  await userEvent.click(screen.getByRole('button', { name: /Synthetic saved trip/ }));
  fetch.mockResolvedValueOnce(streamResponse([event('message_start'), event('error', { code: 'invalid_output', message: 'Synthetic validation failure' })]));
  await submit('Add more museums.');
  expect(await screen.findByRole('button', { name: 'Retry message' })).toBeInTheDocument();
  fetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'No earlier itinerary version' }), { status: 409, headers: { 'Content-Type': 'application/json' } }));
  await userEvent.click(screen.getByRole('button', { name: /Undo last edit/ }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('There is no earlier itinerary version to restore'));
  expect(screen.queryByRole('button', { name: 'Retry message' })).not.toBeInTheDocument();
  expect(screen.getByText('Synthetic Demo Hotel')).toBeInTheDocument();
  expect(screen.getByText('Synthetic Museum')).toBeInTheDocument();
});

it('clearing browser history resets the open chat and draft to the home screen', async () => {
  localStorage.setItem('travel-planner.trips.v1', JSON.stringify([{ id: tripId, title: 'Synthetic saved trip', messages: [{ role: 'assistant', text: 'Synthetic saved conversation' }], citations: [], itinerary, budget: null }]));
  render(<ChatApp />);
  await userEvent.click(screen.getByRole('button', { name: /Synthetic saved trip/ }));
  await userEvent.type(screen.getByRole('textbox'), 'Synthetic unfinished edit');
  await userEvent.click(screen.getByRole('button', { name: 'Clear browser history' }));
  expect(localStorage.getItem('travel-planner.trips.v1')).toBeNull();
  expect(screen.getByRole('heading', { name: 'Where shall we go?' })).toBeInTheDocument();
  expect(screen.queryByText('Synthetic saved conversation')).not.toBeInTheDocument();
  expect(screen.queryByText('Synthetic Demo Hotel')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Synthetic saved trip/ })).not.toBeInTheDocument();
  expect(screen.getByRole('textbox')).toHaveValue('');
  expect(screen.getByRole('textbox')).toHaveFocus();
  fetch.mockResolvedValueOnce(streamResponse(successEvents()));
  await submit('Plan a new synthetic trip');
  expect(JSON.parse(fetch.mock.calls[0][1].body).trip_id).toBeNull();
});

it('the museums shortcut requests clarification without silently choosing day 1', async () => {
  localStorage.setItem('travel-planner.trips.v1', JSON.stringify([{ id: tripId, title: 'Synthetic saved trip', messages: [], citations: [], itinerary, budget: null }]));
  render(<ChatApp />);
  await userEvent.click(screen.getByRole('button', { name: /Synthetic saved trip/ }));
  const clarification = 'Which day should I change? Choose day 1 through day 2.';
  fetch.mockResolvedValueOnce(streamResponse([event('message_start'), event('token', { text: clarification }), event('citations', { citations: [] }), event('done', { trip_id: tripId, message: clarification, budget_met: null, usage: {} })]));
  await userEvent.click(screen.getByRole('button', { name: 'Add more museums' }));
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ message: 'Add more museums', trip_id: tripId });
  await waitFor(() => expect(screen.getByText(clarification)).toBeInTheDocument());
  expect(screen.getByText('Synthetic Demo Hotel')).toBeInTheDocument();
  expect(screen.getByText('Synthetic Museum')).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
