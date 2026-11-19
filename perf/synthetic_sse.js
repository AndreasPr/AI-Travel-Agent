// Synthetic scripted tests of the pipeline, not model behavior.
import { browser } from 'k6/browser';
import { Trend, Rate, Counter } from 'k6/metrics';
import { sleep } from 'k6';
const ttft = new Trend('sse_time_to_first_token_ms', true);
const errors = new Rate('sse_error_rate');
const completed = new Counter('sse_completed_sessions');
const sessions = Number(__ENV.PERF_SESSIONS || 2);
export const options = {
  scenarios: { synthetic: { executor: 'ramping-vus', startVUs: 0,
    stages: [{duration: '5s', target: sessions}, {duration: __ENV.PERF_HOLD || '10s', target: sessions}, {duration: '5s', target: 0}],
    gracefulRampDown: '15s', options: {browser: {type: 'chromium'}} } },
  thresholds: {sse_error_rate: ['rate==0'], sse_completed_sessions: ['count>0']},
};
let identity;
export default async function () {
  let page;
  try {
    page = await browser.newPage();
    await page.goto(__ENV.TEST_WEB_URL || 'http://localhost:13100');
    const result = await page.evaluate(async ({api, identity, vu, run}) => {
      const headers = {'Content-Type': 'application/json', 'X-CSRF-Protection': '1'};
      if (!identity) {
        identity = {email: `synthetic-perf-${run}-${vu}@example.invalid`, password: `Synthetic-${crypto.randomUUID()}!`};
        const registered = await fetch(`${api}/api/auth/register`, {method: 'POST', headers, body: JSON.stringify(identity)});
        if (!registered.ok) return {error: true, phase: 'register'};
      }
      let token = identity.accessToken;
      if (!token) {
      const login = await fetch(`${api}/api/auth/login`, {method: 'POST', headers, body: JSON.stringify(identity)});
      if (!login.ok) return {error: true, phase: 'login', identity};
      token = (await login.json()).access_token;
      identity.accessToken = token;
      }
      const started = performance.now();
      const abort = new AbortController();
      const timer = setTimeout(() => abort.abort(), 15000);
      let first = null, final = false, failed = false, buffer = '';
      try {
        const response = await fetch(`${api}/api/chat/stream`, {method: 'POST', signal: abort.signal,
          headers: {...headers, Authorization: `Bearer ${token}`},
          body: JSON.stringify({message: 'Plan a synthetic museum visit in Lisbon under 1500 USD.'})});
        if (!response.ok) return {error: true, phase: 'admission', identity};
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          buffer += decoder.decode(part.value, {stream: true}).replace(/\r\n/g, '\n');
          let boundary;
          while ((boundary = buffer.indexOf('\n\n')) !== -1) {
            const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
            const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).join('\n');
            if (!data) continue;
            const event = JSON.parse(data);
            if (event.type === 'token' && first === null) first = performance.now() - started;
            if (event.type === 'error') failed = true;
            if (event.type === 'done') {
              final = true;
              // Refuse to count a run against a real model as synthetic performance.
              if (!event.usage.calls.length || event.usage.calls.some(call => call.provider !== 'synthetic')) failed = true;
            }
          }
        }
        return {error: failed || !final || first === null, first, identity};
      } catch (_) { return {error: true, identity}; }
      finally { clearTimeout(timer); }
    }, {api: __ENV.TEST_API_URL || 'http://localhost:18100', identity, vu: __VU, run: __ENV.PERF_RUN_ID});
    identity = result.identity;
    errors.add(result.error);
    if (!result.error) completed.add(1);
    if (result.first !== null && result.first !== undefined) ttft.add(result.first);
  } catch (_) { errors.add(true); }
  finally { if (page) await page.close(); }
  sleep(5);
}
export function handleSummary(data) {
  const result = {provenance: 'synthetic: scripted tests of the pipeline, not model behavior',
    hardware: JSON.parse(__ENV.PERF_HARDWARE), sessions, created_at: new Date().toISOString(),
    note: 'Includes local browser/load-generator overhead. TTFT measures the first token event, not HTTP response headers. Quotas remain enabled.',
    metrics: data.metrics};
  return {[__ENV.PERF_OUTPUT]: JSON.stringify(result, null, 2), stdout: JSON.stringify({sessions,
    ttft: data.metrics.sse_time_to_first_token_ms, errors: data.metrics.sse_error_rate}, null, 2) + '\n'};
}
