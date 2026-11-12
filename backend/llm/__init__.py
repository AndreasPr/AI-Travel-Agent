from backend.llm.types import (
    Event,
    InvalidOutput,
    LLMProvider,
    ProviderUnavailable,
    QuotaExhausted,
    RateLimited,
    Response,
    ToolCall,
)

__all__ = ["get_provider", "LLMProvider", "Response", "Event", "ToolCall", "QuotaExhausted", "RateLimited", "ProviderUnavailable", "InvalidOutput"]


def __getattr__(name):
    # Config and response types are also used by the offline evaluation path.
    if name == "get_provider":
        from backend.llm.router import get_provider
        return get_provider
    raise AttributeError(name)
