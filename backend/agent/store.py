"""TripStore interface and isolated in-memory implementation."""
from copy import deepcopy
from threading import RLock
from typing import Protocol
from uuid import uuid4


class StoreConflict(Exception):
    pass


class TripStore(Protocol):
    def create(self) -> dict: ...
    def load(self, trip_id: str) -> dict: ...
    def save(self, state: dict, expected_revision: int) -> None: ...
    def versions(self, trip_id: str) -> list[dict]: ...
    def undo(self, trip_id: str) -> dict: ...


def new_state():
    return dict(id=str(uuid4()), revision=0, itinerary=None, budget=None, preferences={}, proposal=None,
                history=[], summary='', summarized_count=0, versions=[], evidence=[], citations=[])


class MemoryTripStore:
    def __init__(self):
        self.states = {}
        self.lock = RLock()

    def create(self):
        state = new_state()
        with self.lock:
            self.states[state['id']] = deepcopy(state)
        return state

    def load(self, trip_id):
        with self.lock:
            if trip_id not in self.states:
                raise KeyError(trip_id)
            return deepcopy(self.states[trip_id])

    def save(self, state, expected_revision):
        validate_state(state)
        with self.lock:
            old = self.load(state['id'])
            if old['revision'] != expected_revision:
                raise StoreConflict('Conversation changed; retry the turn')
            if state['itinerary'] != old['itinerary'] or state['budget'] != old['budget'] or 'undo_parent' in state:
                parent = state.pop('undo_parent', old['versions'][-1]['number'] if old['versions'] else None)
                state['versions'] = old['versions'] + [dict(number=len(old['versions']) + 1, parent_number=parent, itinerary=deepcopy(state['itinerary']), budget=state['budget'])]
            state['revision'] = expected_revision + 1
            self.states[state['id']] = deepcopy(state)

    def versions(self, trip_id):
        return self.load(trip_id)['versions']

    def undo(self, trip_id):
        with self.lock:
            state = self.load(trip_id)
            restore_previous(state)
            self.save(state, state['revision'])
            return state


class PostgresTripStore:
    """Transactional state writes with optimistic concurrency and immutable history."""
    def __init__(self, engine=None):
        if engine is None:
            from backend.db.connect import engine
        self.engine = engine

    def create(self):
        from backend.db.models import AgentConversation, AgentTrip
        state = new_state()
        with self.engine.begin() as conn:
            conn.execute(AgentConversation.__table__.insert().values(id=state['id'], revision=0, preferences={}, state=self._metadata(state)))
            conn.execute(AgentTrip.__table__.insert().values(id=state['id'], itinerary=None))
        return state

    @staticmethod
    def _metadata(state):
        return {key: deepcopy(value) for key, value in state.items() if key not in {'id', 'revision', 'preferences', 'itinerary', 'history', 'versions', 'undo_parent'}}

    def _load(self, conn, trip_id):
        from sqlalchemy import select
        from backend.db.models import AgentConversation, AgentMessage, AgentTrip, AgentItineraryVersion
        conversations, messages, trips, versions = (entry.__table__ for entry in (AgentConversation, AgentMessage, AgentTrip, AgentItineraryVersion))
        row = conn.execute(select(conversations).where(conversations.c.id == trip_id)).mappings().first()
        if row is None:
            raise KeyError(trip_id)
        state = dict(row['state'], id=trip_id, revision=row['revision'], preferences=row['preferences'])
        state['itinerary'] = conn.scalar(select(trips.c.itinerary).where(trips.c.id == trip_id))
        state['history'] = [dict(item) for item in conn.execute(select(messages.c.role, messages.c.content).where(messages.c.conversation_id == trip_id).order_by(messages.c.position)).mappings()]
        state['versions'] = [dict(item) for item in conn.execute(select(versions.c.number, versions.c.parent_number, versions.c.itinerary, versions.c.budget).where(versions.c.trip_id == trip_id).order_by(versions.c.number)).mappings()]
        return state

    def load(self, trip_id):
        # A repeatable-read snapshot prevents a concurrent save mixing history/versions.
        options = {'isolation_level': 'REPEATABLE READ'} if self.engine.dialect.name == 'postgresql' else {}
        with self.engine.connect().execution_options(**options) as conn, conn.begin():
            return self._load(conn, trip_id)

    def save(self, state, expected_revision):
        from sqlalchemy import select, update
        from backend.db.models import AgentConversation, AgentMessage, AgentTrip, AgentItineraryVersion
        validate_state(state)
        conversations, messages, trips, versions = (entry.__table__ for entry in (AgentConversation, AgentMessage, AgentTrip, AgentItineraryVersion))
        with self.engine.begin() as conn:
            # Compare-and-swap acquires the row lock before reading the old trip/history.
            changed = conn.execute(update(conversations).where(conversations.c.id == state['id'], conversations.c.revision == expected_revision).values(revision=expected_revision + 1))
            if changed.rowcount != 1:
                raise StoreConflict('Conversation changed; retry the turn')
            old = self._load(conn, state['id'])
            if state['history'][:len(old['history'])] != old['history']:
                raise ValueError('Message history is append-only')
            if state['itinerary'] != old['itinerary'] or state['budget'] != old['budget'] or 'undo_parent' in state:
                number = len(old['versions']) + 1
                parent = state.pop('undo_parent', old['versions'][-1]['number'] if old['versions'] else None)
                conn.execute(versions.insert().values(trip_id=state['id'], number=number, parent_number=parent, itinerary=state['itinerary'], budget=state['budget']))
                conn.execute(update(trips).where(trips.c.id == state['id']).values(itinerary=state['itinerary']))
            for index, message in enumerate(state['history'][len(old['history']):], start=len(old['history'])):
                conn.execute(messages.insert().values(conversation_id=state['id'], position=index, **message))
            conn.execute(update(conversations).where(conversations.c.id == state['id']).values(preferences=state['preferences'], state=self._metadata(state)))
            state['versions'] = [dict(item) for item in conn.execute(select(versions.c.number, versions.c.parent_number, versions.c.itinerary, versions.c.budget).where(versions.c.trip_id == state['id']).order_by(versions.c.number)).mappings()]
        state['revision'] = expected_revision + 1

    def versions(self, trip_id):
        return self.load(trip_id)['versions']

    def undo(self, trip_id):
        state = self.load(trip_id)
        restore_previous(state)
        self.save(state, state['revision'])
        return state


def validate_state(state):
    import json
    from backend.agent.models import Preferences
    from backend.agent.policy import sensitive
    Preferences.model_validate(state['preferences'])
    if state['proposal'] is not None:
        Preferences.model_validate(state['proposal'])
    if sensitive(json.dumps(state, default=str)):
        raise ValueError('Sensitive content cannot be persisted')


def restore_previous(state):
    if not state['versions'] or state['versions'][-1]['parent_number'] is None:
        raise ValueError('No earlier itinerary version')
    target_number = state['versions'][-1]['parent_number']
    target = next(row for row in state['versions'] if row['number'] == target_number)
    state['itinerary'], state['budget'] = deepcopy(target['itinerary']), target['budget']
    state['undo_parent'] = target['parent_number']
