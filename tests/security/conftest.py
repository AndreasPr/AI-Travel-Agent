"""Security unit tests never use live HTTP or models."""
import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    if request.node.get_closest_marker('integration'):
        return
    def denied(*args, **kwargs):
        raise AssertionError('Security unit tests may not access the network')
    monkeypatch.setattr('socket.socket.connect', denied)
    monkeypatch.setattr('socket.create_connection', denied)
