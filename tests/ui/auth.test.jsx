// Synthetic credentials and mocked HTTP responses; no live authentication service.
import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { login, logout, authFetch, refresh } from '@/lib/auth';
import AuthForm from '@/components/AuthForm';
import { AuthProvider, RequireAuth } from '@/components/AuthProvider';
const navigation = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => navigation }));
const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
const credentials = { access_token: 'synthetic-access', user: { id: 'synthetic-user', email: 'synthetic@example.invalid' } };
beforeEach(() => { localStorage.clear(); navigation.replace.mockClear(); vi.stubEnv('NEXT_PUBLIC_API_URL', '/backend'); });

it('keeps tokens out of localStorage and sends the access token as a bearer', async () => {
  fetch.mockResolvedValueOnce(response(credentials));
  await login('synthetic@example.invalid', 'Synthetic password phrase');
  expect(localStorage.length).toBe(0);
  expect(fetch.mock.calls[0][1]).toEqual(expect.objectContaining({credentials: 'include', headers: expect.objectContaining({'X-CSRF-Protection': '1'})}));
  fetch.mockResolvedValueOnce(response({trips: []}));
  await authFetch('/api/trips');
  expect(fetch.mock.calls.at(-1)[1].headers.Authorization).toBe('Bearer synthetic-access');
});

it('rotates once for concurrent refreshes and retries a pre-admission 401', async () => {
  fetch.mockResolvedValueOnce(response(credentials));
  await Promise.all([refresh(), refresh()]);
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/refresh'))).toHaveLength(1);
  fetch.mockResolvedValueOnce(response({detail: 'expired'}, 401));
  fetch.mockResolvedValueOnce(response({...credentials, access_token: 'synthetic-rotated'}));
  fetch.mockResolvedValueOnce(response({trips: []}));
  expect((await authFetch('/api/trips')).status).toBe(200);
  expect(fetch.mock.calls.at(-1)[1].headers.Authorization).toBe('Bearer synthetic-rotated');
});

it('logout revokes the cookie session and clears cached trip data', async () => {
  localStorage.setItem('travel-planner.trips.v1.synthetic-user', '[]');
  fetch.mockResolvedValueOnce(response({message: 'Logged out'}));
  await logout();
  expect(fetch.mock.calls.at(-1)[0]).toBe('/backend/api/auth/logout');
  expect(localStorage.length).toBe(0);
});

it('redirects unauthenticated users and never renders the planner', async () => {
  fetch.mockResolvedValueOnce(response({detail: 'Authentication required'}, 401));
  render(<AuthProvider><RequireAuth>{() => <div>Synthetic protected planner</div>}</RequireAuth></AuthProvider>);
  await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith('/login'));
  expect(screen.queryByText('Synthetic protected planner')).not.toBeInTheDocument();
});

it('registers then logs in through labeled accessible fields', async () => {
  fetch.mockResolvedValueOnce(response(credentials.user, 201));
  fetch.mockResolvedValueOnce(response(credentials));
  render(<AuthForm registering />);
  await userEvent.type(screen.getByLabelText('Email'), 'synthetic@example.invalid');
  await userEvent.type(screen.getByLabelText('Password'), 'Synthetic password phrase');
  await userEvent.click(screen.getByRole('button', {name: 'Register'}));
  await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith('/'));
  expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/backend/api/auth/register', '/backend/api/auth/login']);
  expect(screen.getByLabelText('Password')).toHaveValue('');
});

it('shows quota retry time without retrying the model request', async () => {
  fetch.mockResolvedValueOnce(response(credentials));
  await login('synthetic@example.invalid', 'Synthetic password phrase');
  fetch.mockResolvedValueOnce(new Response(JSON.stringify({detail: 'Daily quota exhausted'}), {status: 429, headers: {'Retry-After': '60'}}));
  await expect(authFetch('/api/chat/stream', {method: 'POST'})).rejects.toThrow('Daily quota exhausted Retry in 60 seconds.');
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/api/chat/stream'))).toHaveLength(1);
});
