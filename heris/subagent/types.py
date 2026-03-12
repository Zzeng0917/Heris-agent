"""Subagent type definitions - Pydantic models for subagent configuration."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubagentType(str, Enum):
    """Built-in subagent types.

    These are specialized agents optimized for specific tasks.
    """

    EXPLORE = "explore"
    PLAN = "plan"
    GENERAL = "general"
    CODE_REVIEW = "code-review"
    DEBUG = "debug"
    DB_READER = "db-reader"


class Thoroughness(str, Enum):
    """Thoroughness level for explore subagent."""

    QUICK = "quick"
    MEDIUM = "medium"
    VERY_THOROUGH = "very_thorough"


class PermissionMode(str, Enum):
    """Permission modes for subagent execution."""

    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    DONT_ASK = "dontAsk"
    BYPASS_PERMISSIONS = "bypassPermissions"
    PLAN = "plan"


class MemoryScope(str, Enum):
    """Memory scope for persistent agent memory."""

    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class SubagentDefinition(BaseModel):
    """Subagent definition from YAML frontmatter.

    This model represents a subagent configuration loaded from a Markdown file
    with YAML frontmatter, compatible with Claude Code's agent format.

    Example:
        ---
        name: code-reviewer
        description: Reviews code for quality
        tools: Read, Grep, Glob
        model: inherit
        ---

        You are a code reviewer...
    """

    # Required fields
    name: str = Field(..., description="Unique identifier (lowercase with hyphens)")
    description: str = Field(
        ..., description="When Claude should delegate to this subagent"
    )

    # Optional tool configuration
    tools: list[str] | None = Field(
        default=None, description="Allowed tools list (None means all tools)"
    )
    disallowed_tools: list[str] | None = Field(
        default=None, description="Explicitly disallowed tools"
    )

    # Model and execution configuration
    model: str = Field(
        default="inherit", description="Model to use: sonnet/opus/haiku/inherit"
    )
    permission_mode: PermissionMode = Field(
        default=PermissionMode.DEFAULT, description="Permission mode for execution"
    )
    max_turns: int | None = Field(
        default=None, description="Maximum agent turns (None means unlimited)"
    )

    # Skills and MCP
    skills: list[str] | None = Field(
        default=None, description="Skills to load at startup"
    )
    mcp_servers: list[str] | None = Field(
        default=None, description="Available MCP servers"
    )

    # Memory and persistence
    memory: MemoryScope | None = Field(
        default=None, description="Persistent memory scope: user/project/local"
    )

    # Execution behavior
    background: bool = Field(
        default=False, description="Whether to always run as background task"
    )
    isolation: str | None = Field(
        default=None, description="Isolation mode: worktree for git worktree"
    )

    # System prompt content (from markdown body)
    system_prompt: str = Field(
        default="", description="System prompt content (markdown body)"
    )

    # Source tracking
    source_path: Path | None = Field(
        default=None, description="Path to source file (set by loader)"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name format (lowercase letters, numbers, hyphens)."""
        if not v:
            raise ValueError("Name cannot be empty")
        if not all(c.islower() or c.isdigit() or c == "-" for c in v):
            raise ValueError(
                "Name must contain only lowercase letters, numbers, and hyphens"
            )
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Name cannot start or end with a hyphen")
        return v

    def is_builtin_type(self) -> bool:
        """Check if this definition matches a builtin type."""
        try:
            SubagentType(self.name)
            return True
        except ValueError:
            return False

    def get_memory_path(self, project_dir: Path | None = None) -> Path | None:
        """Get the memory directory path for this subagent.

        Args:
            project_dir: Project directory (required for project/local scope)

        Returns:
            Path to memory directory, or None if memory not enabled
        """
        if not self.memory:
            return None

        if self.memory == MemoryScope.USER:
            return Path.home() / ".heris" / "agent-memory" / self.name
        elif self.memory == MemoryScope.PROJECT:
            if project_dir is None:
                raise ValueError("project_dir required for project memory scope")
            return project_dir / ".heris" / "agent-memory" / self.name
        elif self.memory == MemoryScope.LOCAL:
            if project_dir is None:
                raise ValueError("project_dir required for local memory scope")
            return project_dir / ".heris" / "agent-memory-local" / self.name

        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excluding source_path)."""
        return {
            "name": self.name,
            "description": self.description,
            "tools": self.tools,
            "disallowed_tools": self.disallowed_tools,
            "model": self.model,
            "permission_mode": self.permission_mode.value,
            "max_turns": self.max_turns,
            "skills": self.skills,
            "mcp_servers": self.mcp_servers,
            "memory": self.memory.value if self.memory else None,
            "background": self.background,
            "isolation": self.isolation,
            "system_prompt": self.system_prompt,
        }


class SubagentConfig(BaseModel):
    """Runtime configuration for subagent execution."""

    definition: SubagentDefinition
    llm_client: Any  # LLMClient instance
    tools: list[Any] | None = None  # List of Tool instances
    workspace_dir: Path | None = None
    thoroughness: Thoroughness = Thoroughness.MEDIUM
    cancel_event: Any | None = None  # asyncio.Event

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SubagentSearchPath(BaseModel):
    """Subagent search path configuration."""

    path: Path
    scope: str  # "cli", "project", "user", "builtin"
    priority: int

    def __hash__(self) -> int:
        return hash((self.path, self.scope, self.priority))
