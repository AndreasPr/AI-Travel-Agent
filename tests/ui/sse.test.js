import { describe, expect, it, vi } from 'vitest';
import { createSSEParser, consumeSSE } from '@/lib/sse';
import { event, frame, streamResponse } from './fixtures';

describe('SSE parser', () => {
  it('parses chunked input, split events, CRLF and heartbeat comments', () => {
    const result = [], parser = createSSEParser(value => result.push(value));
    const text = ': heartbeat\r\nevent: token\r\ndata: first\r\ndata: second\r\n\r\nevent: done\ndata: {}\n\n';
    for (const character of text) parser.push(character);
    expect(result).toEqual([{ event: 'token', data: 'first\nsecond' }, { event: 'done', data: '{}' }]);
  });
  it('decodes UTF-8 characters across byte boundaries and stops on done', async () => {
    const bytes = new TextEncoder().encode(frame(event('token', { text: 'café ☀' })) + frame(event('done')));
    const response = new Response(new ReadableStream({ start(controller) { for (const byte of bytes) controller.enqueue(new Uint8Array([byte])); controller.close(); } }), { headers: { 'Content-Type': 'text/event-stream' } });
    const received = [];
    await consumeSSE(response, value => received.push(value));
    expect(received.map(value => value.type)).toEqual(['token', 'done']);
    expect(received[0].text).toBe('café ☀');
  });
  it('delivers a typed error event and ignores events after the terminal error', async () => {
    const callback = vi.fn();
    await consumeSSE(streamResponse([event('error', { code: 'timeout', message: 'Timed out' }), event('done')]), callback);
    expect(callback).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ type: 'error', code: 'timeout' }));
  });
  it('rejects truncated streams, malformed JSON and mismatched request IDs', async () => {
    await expect(consumeSSE(streamResponse([event('message_start')]), () => {})).rejects.toThrow('before completion');
    await expect(consumeSSE(streamResponse([event('message_start'), event('done', { request_id: 'other' })]), () => {})).rejects.toThrow('invalid stream');
    const response = new Response('event: token\ndata: {bad}\n\n', { headers: { 'Content-Type': 'text/event-stream' } });
    await expect(consumeSSE(response, () => {})).rejects.toThrow();
  });
  it('rejects HTTP and content-type errors', async () => {
    await expect(consumeSSE(new Response('', { status: 503 }), () => {})).rejects.toThrow('503');
    await expect(consumeSSE(new Response('{}'), () => {})).rejects.toThrow('event stream');
  });
});
