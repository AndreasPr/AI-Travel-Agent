// Decode lines independently of network chunk and UTF-8 boundaries.
export function createSSEParser(onEvent) {
  let buffer = "", data = [], event = "message";
  function line(value) {
    if (!value) {
      if (data.length) onEvent({ event, data: data.join("\n") });
      data = []; event = "message";
      return;
    }
    if (value.startsWith(":")) return;
    const colon = value.indexOf(":");
    const field = colon < 0 ? value : value.slice(0, colon);
    const content = colon < 0 ? "" : value.slice(colon + 1).replace(/^ /, "");
    if (field === "data") data.push(content);
    if (field === "event") event = content;
  }
  return {
    push(text) {
      buffer += text;
      let index;
      while ((index = buffer.search(/[\r\n]/)) >= 0) {
        if (buffer[index] === "\r" && index === buffer.length - 1) break;
        const length = buffer[index] === "\r" && buffer[index + 1] === "\n" ? 2 : 1;
        line(buffer.slice(0, index));
        buffer = buffer.slice(index + length);
      }
    },
    finish() { if (buffer.endsWith("\r")) this.push("\n"); },
  };
}

export async function consumeSSE(response, onEvent) {
  if (!response.ok) throw new Error(`Request failed (HTTP ${response.status}). Please try again.`);
  if (!response.headers.get("content-type")?.includes("text/event-stream") || !response.body)
    throw new Error("The server did not return an event stream.");
  let terminal = false, requestId;
  const parser = createSSEParser(({ event, data }) => {
    if (terminal) return;
    const value = JSON.parse(data);
    if (!value.request_id || value.type !== event || (requestId && requestId !== value.request_id))
      throw new Error("The server returned an invalid stream event.");
    requestId = value.request_id;
    onEvent(value);
    terminal = event === "done" || event === "error";
  });
  const reader = response.body.getReader(), decoder = new TextDecoder();
  try {
    while (!terminal) {
      const { value, done } = await reader.read();
      if (done) { parser.push(decoder.decode()); parser.finish(); break; }
      parser.push(decoder.decode(value, { stream: true }));
    }
    if (!terminal) throw new Error("Connection closed before completion. Check the saved trip before retrying.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
