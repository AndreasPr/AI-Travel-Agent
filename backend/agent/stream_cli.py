"""Print SSE events from the chat endpoint; Ctrl+C closes the connection."""
import argparse
from datetime import datetime, timezone
import json

import httpx

from backend.agent.events import EVENT_ADAPTER
from backend.llm.config import load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('message')
    parser.add_argument('--trip-id')
    parser.add_argument('--url', default='http://localhost:8000/api/chat/stream')
    args = parser.parse_args()
    payload = {'message': args.message, 'trip_id': args.trip_id}
    timeout = load_config()['agent']['request_timeout_seconds'] + 30
    terminal = False
    try:
        with httpx.Client(timeout=timeout) as client, client.stream('POST', args.url, json=payload) as response:
            response.raise_for_status()
            data = []
            for line in response.iter_lines():
                if line.startswith(':'):
                    print(datetime.now(timezone.utc).isoformat(), line, flush=True)
                elif line.startswith('data:'):
                    data.append(line[5:].lstrip())
                elif not line and data:
                    event = EVENT_ADAPTER.validate_json('\n'.join(data))
                    data.clear()
                    print(datetime.now(timezone.utc).isoformat(), event.type,
                          json.dumps(event.model_dump(mode='json'), ensure_ascii=False), flush=True)
                    if event.type in {'done', 'error'}:
                        terminal = True
                        if event.type == 'error':
                            raise SystemExit(1)
                        break
        if not terminal:
            raise SystemExit('Stream ended without done or error')
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except httpx.HTTPError:
        raise SystemExit('Streaming request failed; check the backend URL and connection') from None


if __name__ == '__main__':
    main()
