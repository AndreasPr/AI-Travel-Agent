"""Run one planning turn with config-selected providers or offline replay."""
import argparse
import asyncio

from backend.agent.loop import Agent
from backend.agent.models import ChatRequest
from backend.agent.store import PostgresTripStore
from backend.agent.providers import provider_for
from backend.llm.config import load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('message')
    parser.add_argument('--provider')
    parser.add_argument('--replay', action='store_true')
    parser.add_argument('--trip-id')
    args = parser.parse_args()
    config = load_config()
    agent = Agent(store=PostgresTripStore(), config=config, providers=lambda role: provider_for(role, config, args.provider, args.replay))
    try:
        result = asyncio.run(agent.chat(ChatRequest(trip_id=args.trip_id, message=args.message)))
        print(result.model_dump_json(indent=2))
    finally:
        agent.runtime.close()


if __name__ == '__main__':
    main()
