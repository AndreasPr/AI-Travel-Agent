"""Status mapping and bounded retries; no retries for ordinary client errors."""
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from backend.llm.types import InvalidOutput, LLMError, ProviderUnavailable, RateLimited


def retry_after_seconds(value):
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (ValueError, TypeError):
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError):
            return None


def status_error(status, headers=None):
    delay = retry_after_seconds((headers or {}).get("Retry-After") or (headers or {}).get("retry-after"))
    if status == 429:
        return RateLimited("Provider rate limited the request", retry_after=delay)
    if status >= 500:
        return ProviderUnavailable("Provider server error", retry_after=delay)
    return InvalidOutput(f"Provider rejected the request (HTTP {status})")


def map_exception(exc):
    if isinstance(exc, LLMError):
        return exc
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    if status is not None:
        try:
            return status_error(int(status), getattr(response, "headers", None))
        except (ValueError, TypeError):
            pass
    return ProviderUnavailable("Provider transport unavailable")


def retry_call(call, *, attempts=3, base_delay=1.0, max_delay=30.0, sleep=time.sleep, jitter=random.random):
    for attempt in range(attempts):
        try:
            return call()
        except (RateLimited, ProviderUnavailable) as exc:
            if attempt + 1 == attempts:
                raise
            delay = min(max_delay, base_delay * 2 ** attempt) * (0.5 + jitter() / 2)
            sleep(max(delay, exc.retry_after or 0))
    raise ValueError("Retry attempts must be positive")
