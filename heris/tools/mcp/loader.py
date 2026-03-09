"""MCP Loader - Load and manage MCP (Model Context Protocol) tools.

This module provides functions to load MCP tools from configuration,
manage MCP connections, and configure MCP settings.
"""

from typing import Any

from .web_search import WebSearchTool


# Global timeout configuration
_mcp_timeout_config = {
    "request_timeout": 30,
    "connect_timeout": 10,
}

# Registry of built-in MCP tools
_BUILTIN_MCP_TOOLS = {
    "web_search": WebSearchTool,
}


def set_mcp_timeout_config(request_timeout: int = 30, connect_timeout: int = 10) -> None:
    """Set MCP connection timeout configuration.

    Args:
        request_timeout: Request timeout in seconds
        connect_timeout: Connection timeout in seconds
    """
    global _mcp_timeout_config
    _mcp_timeout_config["request_timeout"] = request_timeout
    _mcp_timeout_config["connect_timeout"] = connect_timeout


def get_builtin_mcp_tools() -> list[Any]:
    """Get all built-in MCP tools.

    Returns:
        List of instantiated built-in MCP tools
    """
    tools = []
    for tool_class in _BUILTIN_MCP_TOOLS.values():
        try:
            tools.append(tool_class())
        except Exception as e:
            print(f"⚠️  Failed to load MCP tool {tool_class.__name__}: {e}")
    return tools


async def load_mcp_tools_async(config_path: str | None = None) -> list[Any]:
    """Load MCP tools from configuration file.

    Args:
        config_path: Path to the MCP configuration file (optional)

    Returns:
        List of loaded MCP tools
    """
    tools = []

    # Load built-in MCP tools
    tools.extend(get_builtin_mcp_tools())

    # TODO: Load external MCP tools from config if provided
    if config_path:
        # External MCP server loading would go here
        pass

    return tools


async def cleanup_mcp_connections() -> None:
    """Clean up all MCP connections.

    This function should be called on shutdown to properly close
    all MCP server connections.
    """
    # TODO: Implement actual MCP connection cleanup
    pass


def register_mcp_tool(name: str, tool_class: type) -> None:
    """Register a new MCP tool.

    Args:
        name: Tool name/identifier
        tool_class: Tool class (must inherit from Tool)
    """
    _BUILTIN_MCP_TOOLS[name] = tool_class
