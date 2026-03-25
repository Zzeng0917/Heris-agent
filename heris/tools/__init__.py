"""Tools module.

This module provides a collection of tools for various tasks:
- File operations (read, write, edit)
- Shell command execution (bash)
- Web/HTTP operations (fetch, search)
- Memory/Note management (record, recall)
- Skill system (get_skill)
- MCP integration (web_search, MCP tools)
- Worktree isolation (tasks, worktrees)
"""

# Base classes
from .base import Tool, ToolResult

# File operations
from .file import EditTool, ReadTool, WriteTool

# Shell execution
from .shell import BashKillTool, BashOutputTool, BashTool

# Web/HTTP operations
from .web import WebFetchTool, WebSearchTool as WebSearchNative, cleanup_http_clients

# Memory/Notes
from .memory import RecallNoteTool, SessionNoteTool

# Skill system
from .skill import GetSkillTool, SkillLoader, create_skill_tools

# MCP integration
from .mcp import (
    WebSearchTool as WebSearchMCP,
    cleanup_mcp_connections,
    load_mcp_tools_async,
    set_mcp_timeout_config,
)

# Worktree isolation
from .worktree import (
    TaskCreateTool,
    TaskListTool,
    TaskGetTool,
    TaskUpdateTool,
    TaskBindWorktreeTool,
    WorktreeCreateTool,
    WorktreeListTool,
    WorktreeStatusTool,
    WorktreeRunTool,
    WorktreeKeepTool,
    WorktreeRemoveTool,
    WorktreeEventsTool,
    init_worktree_system,
    # Autonomous agent tools
    IdleTool,
    ClaimTaskTool,
    TaskAddDependencyTool,
    ListUnclaimedTasksTool,
)

# Team protocols (s10)
from .team import (
    init_team_system,
    MessageSendTool,
    MessagePollTool,
    MessageReadTool,
    ShutdownRequestTool,
    ShutdownAckTool,
    ShutdownCheckTool,
    PlanSubmitTool,
    PlanApproveTool,
    PlanListPendingTool,
    PlanCheckResponseTool,
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
    "WebSearchNative",
    "WebSearchMCP",
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
    # Worktree
    "TaskCreateTool",
    "TaskListTool",
    "TaskGetTool",
    "TaskUpdateTool",
    "TaskBindWorktreeTool",
    "WorktreeCreateTool",
    "WorktreeListTool",
    "WorktreeStatusTool",
    "WorktreeRunTool",
    "WorktreeKeepTool",
    "WorktreeRemoveTool",
    "WorktreeEventsTool",
    "init_worktree_system",
    # Autonomous agent tools
    "IdleTool",
    "ClaimTaskTool",
    "TaskAddDependencyTool",
    "ListUnclaimedTasksTool",
    # Team protocols (s10)
    "init_team_system",
    "MessageSendTool",
    "MessagePollTool",
    "MessageReadTool",
    "ShutdownRequestTool",
    "ShutdownAckTool",
    "ShutdownCheckTool",
    "PlanSubmitTool",
    "PlanApproveTool",
    "PlanListPendingTool",
    "PlanCheckResponseTool",
]
