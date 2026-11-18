// Access tokens live only in this module; refresh credentials are HttpOnly cookies.
let accessToken = null;
let refreshing = null;
const listeners = new Set();
let currentUser = null;
export function endpoint(path) {
  const base = process.env.NEXT_PUBLIC_API_URL;
  if (!base) throw new Error("Set NEXT_PUBLIC_API_URL and restart the frontend.");
  return `${base.replace(/\/$/, "")}${path}`;
}
export function subscribeAuth(listener) { listeners.add(listener); return () => listeners.delete(listener); }
function publish(user) { currentUser = user; listeners.forEach(listener => listener(user)); }
export function authUser() { return currentUser; }
async function authPost(path, body) {
  const response = await fetch(endpoint(`/api/auth/${path}`), {
    method: "POST", credentials: "include", cache: "no-store",
    headers: { "Content-Type": "application/json", "X-CSRF-Protection": "1" },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json();
  if (!response.ok) {
    const retry = response.headers.get("Retry-After");
    throw new Error(`${typeof data.detail === "string" ? data.detail : "Authentication failed"}${retry ? ` Retry in ${retry} seconds.` : ""}`);
  }
  return data;
}
function accept(data) { accessToken = data.access_token; publish(data.user); return data.user; }
export async function login(email, password) {
  if (refreshing) await refreshing.catch(() => {});
  return accept(await authPost("login", { email, password }));
}
export async function register(email, password) { await authPost("register", { email, password }); return login(email, password); }
export function refresh() {
  if (!refreshing) {
    const run = () => authPost("refresh").then(accept);
    // Serialize cookie rotation across tabs when Web Locks is available.
    refreshing = (globalThis.navigator?.locks ? navigator.locks.request("travel-auth-refresh", run) : run())
      .catch(error => { accessToken = null; publish(null); throw error; })
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}
export async function logout() {
  if (refreshing) await refreshing.catch(() => {});
  await authPost("logout");
  accessToken = null;
  publish(null);
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i);
    if (key?.startsWith("travel-planner.trips.")) localStorage.removeItem(key);
  }
}
export async function authFetch(path, options = {}) {
  if (!accessToken) await refresh();
  const send = () => fetch(endpoint(path), { ...options, credentials: "include", headers: { ...options.headers, Authorization: `Bearer ${accessToken}` } });
  let response = await send();
  // A 401 is returned before any chat admission; do not replay streamed or other errors.
  if (response.status === 401) { await refresh(); response = await send(); }
  if (response.status === 429) {
    const data = await response.json().catch(() => ({}));
    const seconds = response.headers.get("Retry-After");
    throw new Error(`${typeof data.detail === "string" ? data.detail : "Usage limit reached"}${seconds ? ` Retry in ${seconds} seconds.` : ""}`);
  }
  return response;
}
