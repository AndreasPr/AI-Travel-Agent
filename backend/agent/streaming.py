"""SSE delivery, bounded backpressure, heartbeats and disconnect-owned cancellation."""
import asyncio
import logging
from contextlib import suppress
from uuid import uuid4

from starlette.responses import StreamingResponse

from backend.agent.events import MessageStart, Token, ItineraryUpdate, Citations, Done, ErrorEvent
from backend.agent.models import Usage
from backend.agent.store import StoreConflict
from backend.agent.errors import public_failure_detail

HEARTBEAT_SECONDS = 15
ERROR_MESSAGES = {
    'tool_unavailable': 'A required tool is unavailable. Check the database and local dependencies before retrying.',
    'sensitive_content': 'The generated content contained sensitive information and was not saved.',
    'usage_limit': 'The session, user or turn usage limit has been reached.',
    'timeout': 'The request exceeded its deadline. Please retry.',
    'not_found': 'The trip was not found.',
    'conflict': 'The trip changed during this request. Please retry.',
    'provider_unavailable': 'The configured provider is unavailable. Please retry.',
    'rate_limited': 'The provider is rate limited. Please retry later.',
    'quota_exhausted': 'The configured provider quota is exhausted.',
    'invalid_output': 'The itinerary could not be validated. Please revise the request.',
    'step_limit': 'The planning step limit was reached. Please narrow the request.',
    'internal_error': 'The request could not be completed. Please retry.',
}


def encode(event):
    return f'event: {event.type}\ndata: {event.model_dump_json()}\n\n'.encode()


async def stream_events(agent, request, request_id, *, sleep=asyncio.sleep, user_id="local-cli"):
    queue = asyncio.Queue(maxsize=32)
    usage = Usage()

    async def emit(event):
        await queue.put(event)

    async def error(code):
        await emit(ErrorEvent(request_id=request_id, code=code, message=ERROR_MESSAGES[code], usage=usage))

    async def run():
        try:
            async with asyncio.timeout(agent.settings['request_timeout_seconds']):
                result = await agent.chat(request, event_sink=emit, request_id=request_id, usage=usage, user_id=user_id)
                errors = [issue for issue in result.issues if issue['severity'] == 'error']
                if errors and result.itinerary is None:
                    name = errors[0].get('name', '')
                    code = 'timeout' if name == 'provider_timeout' else name if name in ERROR_MESSAGES else 'invalid_output'
                    detail = public_failure_detail(errors)
                    logging.getLogger(__name__).warning('Agent turn failed: %s', detail)
                    await emit(ErrorEvent(request_id=request_id, code=code,
                                          message=detail if code == 'invalid_output' else ERROR_MESSAGES[code], usage=usage))
                    return
                # Only server-authored, post-validation text is public. Model JSON stays private.
                for offset in range(0, len(result.message), 80):
                    await emit(Token(request_id=request_id, text=result.message[offset:offset + 80]))
                if result.itinerary is not None:
                    await emit(ItineraryUpdate(request_id=request_id, itinerary=result.itinerary, diff=result.diff))
                await emit(Citations(request_id=request_id, citations=result.citations))
                await emit(Done(request_id=request_id, trip_id=result.trip_id, usage=result.usage,
                                message=result.message, budget_met=result.budget_met,
                                preference_proposal=result.preference_proposal))
        except TimeoutError:
            await error('timeout')
        except KeyError:
            await error('not_found')
        except StoreConflict:
            await error('conflict')
        except Exception:
            await error('internal_error')

    producer = None
    pending = set()
    try:
        yield encode(MessageStart(request_id=request_id, trip_id=request.trip_id))
        producer = asyncio.create_task(run(), name=f'agent-stream-{request_id}')
        incoming = asyncio.create_task(queue.get())
        heartbeat = asyncio.create_task(sleep(HEARTBEAT_SECONDS))
        pending = {incoming, heartbeat}
        while True:
            if producer.done() and not incoming.done() and queue.empty():
                yield encode(ErrorEvent(request_id=request_id, code='internal_error',
                                        message=ERROR_MESSAGES['internal_error'], usage=usage))
                return
            watched = pending | ({producer} if not producer.done() else set())
            completed, _ = await asyncio.wait(watched, return_when=asyncio.FIRST_COMPLETED)
            if producer in completed and not incoming.done() and queue.empty():
                yield encode(ErrorEvent(request_id=request_id, code='internal_error',
                                        message=ERROR_MESSAGES['internal_error'], usage=usage))
                return
            if incoming in completed:
                event = incoming.result()
                yield encode(event)
                if event.type in {'done', 'error'}:
                    return
                pending.remove(incoming)
                incoming = asyncio.create_task(queue.get())
                pending.add(incoming)
            if heartbeat in completed:
                yield b': heartbeat\n\n'
                pending.remove(heartbeat)
                heartbeat = asyncio.create_task(sleep(HEARTBEAT_SECONDS))
                pending.add(heartbeat)
    finally:
        if producer is not None:
            pending.add(producer)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


class AgentStreamResponse(StreamingResponse):
    """Always watch http.disconnect, including with ASGI 2.4 servers and send failures."""
    async def __call__(self, scope, receive, send):
        sender = asyncio.create_task(self.stream_response(send))
        listener = asyncio.create_task(self.listen_for_disconnect(receive))
        try:
            completed, _ = await asyncio.wait({sender, listener}, return_when=asyncio.FIRST_COMPLETED)
            if sender in completed:
                with suppress(OSError):
                    await sender
            else:
                await listener
        finally:
            for task in (sender, listener):
                task.cancel()
            await asyncio.gather(sender, listener, return_exceptions=True)
            await self.body_iterator.aclose()


def response_for(agent, request, *, user_id="local-cli"):
    request_id = uuid4()
    return AgentStreamResponse(stream_events(agent, request, request_id, user_id=user_id), media_type='text/event-stream',
                               headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no',
                                        'X-Request-ID': str(request_id)})
