"""Bound HTTP bodies before JSON parsing; never echo rejected request bodies."""
from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/api/'):
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body = message.get('body', b'')
            size += len(body)
            if size > self.max_bytes:
                return await JSONResponse({'detail': 'Request body too large'}, status_code=413)(scope, receive, send)
            chunks.append(body)
            if not message.get('more_body', False):
                break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)
