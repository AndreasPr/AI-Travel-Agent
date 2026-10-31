"""Record five small real responses only with explicit opt-in and a free-tier key."""
import os

from backend.llm.config import load_config, role_chain
from backend.llm.replay import Recorder
from backend.llm.router import build_provider

PROMPTS = ["Say hi.", "Reply with the word travel.", "Name one continent.", "Reply with the number 2.", "Say goodbye."]


def main():
    if os.getenv("RECORD") != "1":
        raise SystemExit("Recording disabled. Set RECORD=1 explicitly.")
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("M3: export GEMINI_API_KEY from your free-tier project; no calls were made.")
    if os.getenv("LLM_REPLAY") == "1":
        raise SystemExit("Unset LLM_REPLAY before recording real responses.")
    config = load_config()
    entry = role_chain("extract", None, config)[0]
    if entry["provider"] != "gemini":
        raise SystemExit("M3: extract's first provider must be the configured free-tier Gemini provider for recording.")
    provider = build_provider(entry["provider"], entry["model"], config)
    recorder = Recorder(provider, secrets=(os.environ["GEMINI_API_KEY"],))
    for prompt in PROMPTS:
        recorder.generate([{"role": "user", "content": prompt}])
    print("Recorded 5 responses. Review sanitized files before committing.")


if __name__ == "__main__":
    main()
