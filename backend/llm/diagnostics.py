"""Allowlisted failure metadata; never log SDK payloads, URLs or credentials."""
import logging
import socket
import ssl

import httpx


def log_provider_failure(exc):
    reason, status = 'unknown', None
    seen = set()
    current = exc
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if str(current) == 'M3: export GEMINI_API_KEY for the free-tier project':
            reason = 'missing_api_key'
        elif isinstance(current, ImportError):
            reason = 'sdk_import'
        elif isinstance(current, (httpx.TimeoutException, TimeoutError)):
            reason = 'timeout'
        elif isinstance(current, httpx.ConnectError):
            reason = 'connection'
        elif isinstance(current, ssl.SSLError):
            reason = 'tls'
        elif isinstance(current, socket.gaierror):
            reason = 'dns'
        elif isinstance(current, httpx.TransportError):
            reason = 'transport'
        elif isinstance(current, (TypeError, AttributeError)):
            reason = 'sdk_interface'
        elif isinstance(current, ValueError):
            reason = 'sdk_value'
        response = getattr(current, 'response', None)
        code = getattr(current, 'status_code', None) or getattr(current, 'code', None) or getattr(response, 'status_code', None)
        if type(code) is int and 400 <= code <= 599:
            status, reason = code, 'http_error'
        current = current.__cause__ or current.__context__
    logging.getLogger(__name__).warning('Provider failure diagnostic: reason=%s http_status=%s', reason, status)
    return {'reason': reason, 'http_status': status}
