"""Chat and version endpoints with injectable application services."""
from functools import lru_cache
from copy import copy
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.agent.loop import Agent
from backend.agent.models import ChatRequest, ChatResponse
from backend.agent.store import StoreConflict
from backend.auth.api import current_user, get_auth_service
from backend.security.limits import UsageGuard

router = APIRouter(prefix='/api')


@lru_cache
def get_agent():
    from backend.agent.store import PostgresTripStore
    from backend.testing.synthetic import enabled, synthetic_agent
    if enabled():
        return synthetic_agent(store=PostgresTripStore())
    return Agent(store=PostgresTripStore())


def owned_agent(user=Depends(current_user), agent=Depends(get_agent)):  # noqa: B008
    scoped = copy(agent)
    scoped.store = agent.store.for_owner(user['id'])
    scoped.guard = UsageGuard(agent.guard.store, agent.guard.settings, agent.guard.clock, enforce_daily=False)
    return scoped


def admitted_user(request: Request, user=Depends(current_user), agent=Depends(owned_agent)):  # noqa: B008
    from backend.security.limits import LimitExceeded
    from sqlalchemy.exc import SQLAlchemyError
    try:
        agent.guard.rate(request.client.host if request.client else 'unknown-peer', user['id'])
    except LimitExceeded as exc:
        raise HTTPException(429, 'Request rate limit reached', headers={'Retry-After': str(exc.retry_after)}) from None
    except SQLAlchemyError:
        raise HTTPException(503, 'Security admission storage is unavailable') from None
    return user['id']


class ReservedTurn:
    def __init__(self, agent, service, reservation):
        self.agent, self.service, self.reservation = agent, service, reservation

    def __getattr__(self, name):
        return getattr(self.agent, name)

    async def chat(self, *args, **kwargs):
        import asyncio
        result = await self.agent.chat(*args, **kwargs)
        # Uncertain provider usage on failure/disconnect retains the conservative reservation.
        if not any(issue.get('severity') == 'error' for issue in result.issues):
            from sqlalchemy.exc import SQLAlchemyError
            try:
                await asyncio.to_thread(self.service.settle_turn, self.reservation, result.usage.tokens_in + result.usage.tokens_out)
            except SQLAlchemyError:
                import logging
                logging.getLogger(__name__).warning('Daily quota settlement could not be confirmed')
        return result


def admit_turn(request, agent, service, user):
    if request.trip_id:
        try:
            agent.store.load(request.trip_id)
        except KeyError:
            raise HTTPException(404, 'Trip not found') from None
    from sqlalchemy.exc import SQLAlchemyError
    try:
        reservation = service.reserve_turn(user, agent.config['guardrails']['turn_tokens'])
    except SQLAlchemyError:
        raise HTTPException(503, 'Quota storage unavailable') from None
    return ReservedTurn(agent, service, reservation)


@router.post('/chat', response_model=ChatResponse)
async def chat(request: ChatRequest, agent=Depends(owned_agent), user=Depends(admitted_user), service=Depends(get_auth_service)):  # noqa: B008
    try:
        admitted = await asyncio.to_thread(admit_turn, request, agent, service, user)
        return await admitted.chat(request, user_id=user)
    except KeyError as exc:
        raise HTTPException(404, 'Trip not found') from exc
    except StoreConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/trips/{trip_id}/versions')
def versions(trip_id: str, agent=Depends(owned_agent), user=Depends(admitted_user)):  # noqa: B008
    try:
        return {'trip_id': trip_id, 'versions': agent.store.versions(trip_id)}
    except KeyError as exc:
        raise HTTPException(404, 'Trip not found') from exc


@router.post('/trips/{trip_id}/undo')
def undo(trip_id: str, agent=Depends(owned_agent), user=Depends(admitted_user)):  # noqa: B008
    try:
        state = agent.store.undo(trip_id)
        return {'trip_id': trip_id, 'itinerary': state['itinerary'], 'version': state['versions'][-1]['number']}
    except KeyError as exc:
        raise HTTPException(404, 'Trip not found') from exc
    except (ValueError, StoreConflict) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/chat/stream')
async def chat_stream(request: ChatRequest, agent=Depends(owned_agent), user=Depends(admitted_user), service=Depends(get_auth_service)):  # noqa: B008
    from backend.agent.streaming import response_for
    admitted = await asyncio.to_thread(admit_turn, request, agent, service, user)
    return response_for(admitted, request, user_id=user)


@router.get('/trips')
def trips(agent=Depends(owned_agent), user=Depends(admitted_user)):  # noqa: B008
    return {'trips': agent.store.list_trips()}


@router.get('/trips/{trip_id}')
def read_trip(trip_id: str, agent=Depends(owned_agent), user=Depends(admitted_user)):  # noqa: B008
    try:
        state = agent.store.load(trip_id)
        return {key: state[key] for key in ('id', 'itinerary', 'history', 'citations', 'preferences')}
    except KeyError:
        raise HTTPException(404, 'Trip not found') from None


@router.delete('/trips/{trip_id}', status_code=204)
def delete_trip(trip_id: str, agent=Depends(owned_agent), user=Depends(admitted_user)):  # noqa: B008
    try:
        agent.store.delete(trip_id)
    except KeyError:
        raise HTTPException(404, 'Trip not found') from None
