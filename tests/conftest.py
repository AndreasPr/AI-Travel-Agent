"""Isolate test signing keys from developer credentials; never persist them."""

import os
import secrets

# Set before test-module imports construct the application. Production-mode tests
# explicitly replace these settings and exercise startup rejection.
os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
os.environ["APP_ENV"] = "development"


def pytest_collection_modifyitems(items):
    """Classify by directory without overriding explicit service markers."""
    import pytest
    for item in items:
        parts = item.path.parts
        for marker in ('integration', 'e2e', 'contract'):
            if marker in parts:
                item.add_marker(getattr(pytest.mark, marker))
        if not any(item.get_closest_marker(name) for name in ('integration', 'e2e', 'live', 'contract')):
            item.add_marker(pytest.mark.unit)


import pytest


@pytest.fixture(autouse=True)
def offline_network_guard(request, monkeypatch):
    if any(request.node.get_closest_marker(name) for name in ('integration', 'e2e', 'live')):
        return
    def denied(*args, **kwargs):
        raise AssertionError('Offline tests must not open network connections')
    monkeypatch.setattr('socket.socket.connect', denied)
    monkeypatch.setattr('socket.create_connection', denied)
    monkeypatch.setenv('HF_HUB_OFFLINE', '1')
    monkeypatch.setenv('TRANSFORMERS_OFFLINE', '1')
