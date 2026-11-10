"""Chat and version endpoints with injectable application services."""
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.agent.loop import Agent
from backend.agent.models import ChatRequest, ChatResponse
from backend.agent.store import StoreConflict

router = APIRouter(prefix='/api')


@lru_cache
def get_agent():
    from backend.agent.store import PostgresTripStore
    return Agent(store=PostgresTripStore())


def admitted_user(request: Request, agent=Depends(get_agent)):  # noqa: B008
    from backend.security.limits import identity, LimitExceeded
    from sqlalchemy.exc import SQLAlchemyError
    ip, user = identity(request)
    try:
        agent.guard.rate(ip, user)
    except LimitExceeded as exc:
        raise HTTPException(429, 'Request rate limit reached', headers={'Retry-After': str(exc.retry_after)}) from None
    except SQLAlchemyError:
        raise HTTPException(503, 'Security admission storage is unavailable') from None
    return user


@router.post('/chat', response_model=ChatResponse)
async def chat(request: ChatRequest, agent=Depends(get_agent), user=Depends(admitted_user)):  # noqa: B008
    try:
        return await agent.chat(request, user_id=user)
    except KeyError as exc:
        raise HTTPException(404, 'Trip not found') from exc
    except StoreConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/trips/{trip_id}/versions')
def versions(trip_id: str, agent=Depends(get_agent), user=Depends(admitted_user)):  # noqa: B008
    try:
        return {'trip_id': trip_id, 'versions': agent.store.versions(trip_id)}
    except KeyError as exc:
        raise HTTPException(404, 'Trip not found') from exc


@router.post('/trips/{trip_id}/undo')
def undo(trip_id: str, agent=Depends(get_agent), user=Depends(admitted_user)):  # noqa: B008
    try:
        state = agent.store.undo(trip_id)
        return {'trip_id': trip_id, 'itinerary': state['itinerary'], 'version': state['versions'][-1]['number']}
    except KeyError as exc:
        raise HTTPException(404, 'Trip not found') from exc
    except (ValueError, StoreConflict) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/chat/stream')
async def chat_stream(request: ChatRequest, agent=Depends(get_agent), user=Depends(admitted_user)):  # noqa: B008
    from backend.agent.streaming import response_for
    return response_for(agent, request, user_id=user)
