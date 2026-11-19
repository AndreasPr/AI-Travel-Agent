"""Synthetic scripted tests of HTTP response shapes, not model behavior."""
import json
from pathlib import Path

from test_auth import environment, register_login, HEADERS  # noqa: F401


def shape(value):
    if isinstance(value, dict):
        return {key: shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        variants = {json.dumps(shape(item), sort_keys=True) for item in value}
        return [json.loads(item) for item in sorted(variants)]
    return type(value).__name__


def response_shapes(client, agent):
    login, headers = register_login(client)
    response = client.post('/api/chat', json={'message': 'Synthetic trip request under 1500 USD'}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['itinerary'] is not None
    trip_id = body['trip_id']
    results = {'login': shape(login), 'me': shape(client.get('/api/auth/me', headers=headers).json()),
               'chat': shape(body), 'trips': shape(client.get('/api/trips', headers=headers).json()),
               'trip': shape(client.get('/api/trips/' + trip_id, headers=headers).json()),
               'versions': shape(client.get('/api/trips/' + trip_id + '/versions', headers=headers).json())}
    # Persist a second version through the store to exercise the public undo contract.
    store = agent.store.for_owner(login['user']['id'])
    state = store.load(trip_id)
    state['itinerary']['days'][0]['items'][0]['place'] = 'Synthetic changed stay'
    store.save(state, state['revision'])
    undo = client.post('/api/trips/' + trip_id + '/undo', headers=headers)
    assert undo.status_code == 200
    results['undo'] = shape(undo.json())
    refresh = client.post('/api/auth/refresh', headers=HEADERS)
    assert refresh.status_code == 200
    results['refresh'] = shape(refresh.json())
    deleted = client.delete('/api/trips/' + trip_id, headers=headers)
    assert deleted.status_code == 204 and deleted.content == b''
    results['logout'] = shape(client.post('/api/auth/logout', headers=HEADERS).json())
    results['unauthorized'] = shape(client.get('/api/auth/me', headers=headers).json())
    return results


def test_synthetic_http_response_shapes(environment):  # noqa: F811 - imported pytest fixture
    client, _, agent = environment
    actual = response_shapes(client, agent)
    expected = json.loads(Path('tests/snapshots/http-shapes.json').read_text())
    assert actual == expected
