"""Web Search MCP Tool.

This module provides web search functionality for real-time information retrieval.
"""

from .web_search_tool import WebSearchTool, WebSearchResult
from .prompt import (
    TOOL_NAME,
    DESCRIPTION,
    USAGE_EXAMPLE,
    PROMPT,
    PARAMETERS,
    RESPONSE_FORMAT,
)

__all__ = [
    "WebSearchTool",
    "WebSearchResult",
    "TOOL_NAME",
    "DESCRIPTION",
    "USAGE_EXAMPLE",
    "PROMPT",
    "PARAMETERS",
    "RESPONSE_FORMAT",
]
