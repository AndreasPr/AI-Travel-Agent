"""Allowlisted failure metadata; never log SDK payloads, URLs or credentials."""
import logging
import socket
import ssl

import httpx
from psycopg import Error as PsycopgError
from sqlalchemy.exc import SQLAlchemyError


def log_provider_failure(exc):
    reason, status = 'unknown', None
    category = 'unknown'
    seen = set()
    current = exc
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if str(current) == 'M3: export GEMINI_API_KEY for the free-tier project':
            reason = 'missing_api_key'
        elif str(current) == 'Daily quota store unavailable; run database migrations':
            reason = 'quota_database'
        elif isinstance(current, (PsycopgError, SQLAlchemyError)):
            reason = 'quota_database'
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
        # Match fixed categories only; never emit the provider's raw text.
        detail = str(current).lower()
        for needle, label in (('thought_signature', 'thought_signature'),
                              ('thought signature', 'thought_signature'),
                              ('response_json_schema', 'response_schema'),
                              ('response_schema', 'response_schema'),
                              ('schema is too complex', 'schema_complexity'),
                              ('too many states', 'schema_complexity'),
                              ('function response', 'function_response'),
                              ('function_response', 'function_response'),
                              ('api key not valid', 'api_key_invalid')):
            if needle in detail:
                category = label
                break
        response = getattr(current, 'response', None)
        code = getattr(current, 'status_code', None) or getattr(current, 'code', None) or getattr(response, 'status_code', None)
        if type(code) is int and 400 <= code <= 599:
            status, reason = code, 'http_error'
        current = current.__cause__ or current.__context__
    logging.getLogger(__name__).warning('Provider failure diagnostic: reason=%s http_status=%s', reason, status)
    if status == 400:
        logging.getLogger(__name__).warning('Provider request rejection: category=%s', category)
    return {'reason': reason, 'http_status': status}
