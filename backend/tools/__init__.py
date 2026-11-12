"""Agent tool execution entry points."""
from backend.tools.models import Itinerary, ToolError, ToolResult

__all__ = ["ToolRuntime", "ToolResult", "ToolError", "Itinerary"]


def __getattr__(name):
    # Importing itinerary schemas must not initialize database/HTTP tooling.
    if name == "ToolRuntime":
        from backend.tools.runtime import ToolRuntime
        return ToolRuntime
    raise AttributeError(name)
