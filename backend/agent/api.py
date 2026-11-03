"""Chat and version endpoints with injectable application services."""
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from backend.agent.loop import Agent
from backend.agent.models import ChatRequest, ChatResponse
from backend.agent.store import StoreConflict

router = APIRouter(prefix='/api')


@lru_cache
def get_agent():
    from backend.agent.store import PostgresTripStore
    return Agent(store=PostgresTripStore())


@router.post('/chat', response_model=ChatResponse)
async def chat(request: ChatRequest, agent=Depends(get_agent)):  # noqa: B008
    try:
        return await agent.chat(request)
    except KeyError as exc:
        raise HTTPException(404, 'Trip not found') from exc
    except StoreConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/trips/{trip_id}/versions')
def versions(trip_id: str, agent=Depends(get_agent)):  # noqa: B008
    try:
        return {'trip_id': trip_id, 'versions': agent.store.versions(trip_id)}
    except KeyError as exc:
        raise HTTPException(404, 'Trip not found') from exc


@router.post('/trips/{trip_id}/undo')
def undo(trip_id: str, agent=Depends(get_agent)):  # noqa: B008
    try:
        state = agent.store.undo(trip_id)
        return {'trip_id': trip_id, 'itinerary': state['itinerary'], 'version': state['versions'][-1]['number']}
    except KeyError as exc:
        raise HTTPException(404, 'Trip not found') from exc
    except (ValueError, StoreConflict) as exc:
        raise HTTPException(409, str(exc)) from exc
