"""Tools module.

This module provides a collection of tools for various tasks:
- File operations (read, write, edit)
- Shell command execution (bash)
- Web/HTTP operations (fetch, search)
- Memory/Note management (record, recall)
- Skill system (get_skill)
- MCP integration (web_search, MCP tools)
"""

# Base classes
from .base import Tool, ToolResult

# File operations
from .file import EditTool, ReadTool, WriteTool

# Shell execution
from .shell import BashKillTool, BashOutputTool, BashTool

# Web/HTTP operations
from .web import WebFetchTool, WebSearchTool, cleanup_http_clients

# Memory/Notes
from .memory import RecallNoteTool, SessionNoteTool

# Skill system
from .skill import GetSkillTool, SkillLoader, create_skill_tools

# MCP integration
from .mcp import (
    WebSearchTool,
    cleanup_mcp_connections,
    load_mcp_tools_async,
    set_mcp_timeout_config,
)

__all__ = [
    # Base
    "Tool",
    "ToolResult",
    # File
    "ReadTool",
    "WriteTool",
    "EditTool",
    # Shell
    "BashTool",
    "BashOutputTool",
    "BashKillTool",
    # Web
    "WebFetchTool",
    "WebSearchTool",
    "cleanup_http_clients",
    # Memory
    "SessionNoteTool",
    "RecallNoteTool",
    # Skill
    "GetSkillTool",
    "SkillLoader",
    "create_skill_tools",
    # MCP
    "load_mcp_tools_async",
    "cleanup_mcp_connections",
    "set_mcp_timeout_config",
]
