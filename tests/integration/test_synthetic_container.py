"""Synthetic scripted tests of the pipeline, not model behavior."""
from copy import deepcopy
import importlib
import json
import secrets

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker

from backend.agent.api import get_agent, router
from backend.agent.store import PostgresTripStore
from backend.auth.api import get_auth_service, install_auth_handlers, router as auth_router
from backend.auth.service import AuthService, Settings
from backend.db.models import Hotel, DocumentChunk, AuthDailyUsage
from backend.llm.config import load_config
from backend.testing.synthetic import FIXTURE, synthetic_agent
from backend.tools.runtime import ToolRuntime
from backend.tools.storage import PostgresStore


class SyntheticEmbedder:
    """Constant synthetic vectors exercise SQL vector operations, not semantic quality."""
    def encode(self, texts):
        return [[1.0] + [0.0] * 383 for _ in texts]

    def encode_query(self, text):
        return self.encode([text])[0]


def test_full_chat_turn_with_postgres_container_synthetic(postgres_container_engine, monkeypatch):
    engine = postgres_container_engine
    sessions = sessionmaker(engine)
    ingest = importlib.import_module('backend.rag.ingest')
    search = importlib.import_module('backend.rag.search')
    fixture = json.loads(FIXTURE.read_text())
    chunk = fixture['chunk']
    monkeypatch.setattr(ingest, 'SessionLocal', sessions)
    monkeypatch.setattr(search, 'SessionLocal', sessions)
    monkeypatch.setattr(ingest, 'LocalEmbedder', SyntheticEmbedder)
    monkeypatch.setattr(search, 'get_local_embedder', SyntheticEmbedder)
    monkeypatch.setattr(ingest, 'fetch_city_pages', lambda cities: [dict(city='Lisbon', country='Portugal',
        retrieved_at='2027-01-01T00:00:00+00:00', revision_id='synthetic', title=chunk['title'], url=chunk['source_url'], text=chunk['text'], license=chunk['license'])])
    ingest.ingest_cities(max_pages=1)
    with engine.connect() as connection:
        count = connection.scalar(select(func.count()).select_from(DocumentChunk))
    ingest.ingest_cities(max_pages=1)
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(DocumentChunk)) == count > 0
    rows = search.search('museum', mode='vector', city='Lisbon', auto_filters=False, expand_queries=False)
    assert rows and 'Synthetic Sample Museum' in rows[0]['text']
    assert search.search('museum', mode='fts', city='Lisbon', auto_filters=False, expand_queries=False)
    from backend.scripts.generate_inventory import generate_inventory
    from backend.scripts.seed_inventory import seed_inventory
    inventory = generate_inventory()
    small = {'flights': inventory['flights'][:2], 'hotels': inventory['hotels'][:2]}
    with engine.begin() as connection:
        seed_inventory(connection, small)
        seed_inventory(connection, small)
        assert connection.scalar(select(func.count()).select_from(Hotel)) == 2
    # Adapt the synthetic script's citation ID to the actually ingested chunk ID.
    from backend.testing.synthetic import SyntheticProvider
    fixture['itinerary']['days'][0]['items'][0]['chunk_ids'] = [rows[0]['chunk_id']]
    def retrieve(query, **kwargs):
        kwargs['rerank'] = False
        return search.search(query, mode='fts', auto_filters=False, expand_queries=False, **kwargs)
    runtime = ToolRuntime(store=PostgresStore(engine), session_factory=sessions, search=retrieve)
    agent = synthetic_agent(PostgresTripStore(engine), runtime)
    agent.providers = lambda role: SyntheticProvider(fixture)
    config = deepcopy(load_config()['auth'])
    config['daily_messages'] = 1
    service = AuthService(engine, Settings(secrets.token_urlsafe(48), False, ('http://frontend.test',)), config)
    app = FastAPI()
    install_auth_handlers(app)
    app.include_router(auth_router)
    app.include_router(router)
    app.dependency_overrides[get_agent] = lambda: agent
    app.dependency_overrides[get_auth_service] = lambda: service
    try:
        with TestClient(app) as client:
            assert client.post('/api/chat', json={'message': fixture['request']}).status_code == 401
            headers = {'Origin': 'http://frontend.test', 'X-CSRF-Protection': '1'}
            credentials = {'email': 'synthetic-container@example.invalid', 'password': secrets.token_urlsafe(24)}
            assert client.post('/api/auth/register', json=credentials, headers=headers).status_code == 201
            login = client.post('/api/auth/login', json=credentials, headers=headers)
            assert login.status_code == 200
            auth = {'Authorization': 'Bearer ' + login.json()['access_token']}
            response = client.post('/api/chat', json={'message': fixture['request']}, headers=auth)
            assert response.status_code == 200
            body = response.json()
            assert body['itinerary'] is not None, body
            assert body['citations']
            assert body['usage']['calls'][0]['provider'] == 'synthetic'
            assert PostgresTripStore(engine).for_owner(login.json()['user']['id']).load(body['trip_id'])['itinerary']
            blocked = client.post('/api/chat', json={'message': fixture['request']}, headers=auth)
            assert blocked.status_code == 429
            assert int(blocked.headers['Retry-After']) > 0
            with engine.connect() as connection:
                assert connection.scalar(select(func.count()).select_from(AuthDailyUsage)) == 1
    finally:
        runtime.close()
