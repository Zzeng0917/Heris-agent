"""Base tool classes."""

from functools import lru_cache
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    """Tool execution result."""

    success: bool
    content: str = ""
    error: str | None = None


class Tool:
    """Base class for all tools."""

    def __init__(self):
        # Instance-level cache for tool schemas to avoid regeneration
        self._schema_cache: dict[str, Any] | None = None
        self._openai_schema_cache: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        """Tool name."""
        raise NotImplementedError

    @property
    def description(self) -> str:
        """Tool description."""
        raise NotImplementedError

    @property
    def parameters(self) -> dict[str, Any]:
        """Tool parameters schema (JSON Schema format)."""
        raise NotImplementedError

    async def execute(self, *args, **kwargs) -> ToolResult:  # type: ignore
        """Execute the tool with arbitrary arguments."""
        raise NotImplementedError

    def to_schema(self) -> dict[str, Any]:
        """Convert tool to Anthropic tool schema (cached)."""
        if getattr(self, '_schema_cache', None) is None:
            self._schema_cache = {
                "name": self.name,
                "description": self.description,
                "input_schema": self.parameters,
            }
        return self._schema_cache

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert tool to OpenAI tool schema (cached)."""
        if getattr(self, '_openai_schema_cache', None) is None:
            self._openai_schema_cache = {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters,
                },
            }
        return self._openai_schema_cache
