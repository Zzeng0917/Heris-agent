"""MCP (Model Context Protocol) tools and loader.

This module provides:
- MCP tool integration (invoke, read_resource, list_resources)
- Web search tool (built-in MCP-style tool)
- MCP loader for loading and managing MCP connections
"""

from .loader import (
    cleanup_mcp_connections,
    load_mcp_tools_async,
    register_mcp_tool,
    set_mcp_timeout_config,
)
from .web_search import WebSearchTool, WebSearchResult

__all__ = [
    "WebSearchTool",
    "WebSearchResult",
    "load_mcp_tools_async",
    "cleanup_mcp_connections",
    "set_mcp_timeout_config",
    "register_mcp_tool",
]
