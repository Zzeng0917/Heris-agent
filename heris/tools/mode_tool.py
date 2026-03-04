"""Tools for managing agent mode/persona at runtime."""

from typing import Any

from ..modes import AgentMode, ModeType, create_mode_from_string
from .base import Tool, ToolResult


class SetModeTool(Tool):
    """Tool for changing the agent's mode/persona at runtime."""

    def __init__(self, agent=None):
        """Initialize the tool.

        Args:
            agent: The Agent instance to update. Can be set later via set_agent().
        """
        self._agent = agent

    def set_agent(self, agent):
        """Set the agent reference.

        Args:
            agent: The Agent instance to update.
        """
        self._agent = agent

    @property
    def name(self) -> str:
        return "set_mode"

    @property
    def description(self) -> str:
        return (
            "Change the agent's personality mode at runtime. "
            "Available modes: 'normal' (standard assistant), "
            "'push' (energetic and optimistic), "
            "'slackin' (relaxed and easygoing). "
            "This will immediately update the agent's communication style."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["normal", "push", "slackin"],
                    "description": "The mode to switch to. "
                                   "'normal' for standard assistant behavior, "
                                   "'push' for energetic/optimistic personality, "
                                   "'slackin' for relaxed/easygoing personality.",
                }
            },
            "required": ["mode"],
        }

    async def execute(self, mode: str) -> ToolResult:
        """Execute the mode change.

        Args:
            mode: The mode to switch to ('normal', 'push', or 'slackin')

        Returns:
            ToolResult indicating success or failure
        """
        if not self._agent:
            return ToolResult(
                success=False,
                error="Agent not initialized. Cannot change mode.",
            )

        try:
            # Validate and create the mode
            new_mode = create_mode_from_string(mode)

            # Get the mode display name
            display_name = new_mode.display_name

            # Build the prompt injection
            mode_prompt = new_mode.build_prompt_injection()

            # Update the agent's persona
            self._agent.update_persona(mode_prompt)

            # Store current mode info on agent for retrieval
            self._agent.current_mode = new_mode

            return ToolResult(
                success=True,
                content=f"已切换至{display_name}",
            )

        except ValueError as e:
            return ToolResult(
                success=False,
                error=f"无效的模式: {e}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"切换模式失败: {type(e).__name__}: {e}",
            )


class GetCurrentModeTool(Tool):
    """Tool for getting the current agent mode information."""

    def __init__(self, agent=None):
        """Initialize the tool.

        Args:
            agent: The Agent instance. Can be set later via set_agent().
        """
        self._agent = agent

    def set_agent(self, agent):
        """Set the agent reference.

        Args:
            agent: The Agent instance.
        """
        self._agent = agent

    @property
    def name(self) -> str:
        return "get_current_mode"

    @property
    def description(self) -> str:
        return (
            "Get information about the current agent mode/persona. "
            "Returns the current mode name and description."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self) -> ToolResult:
        """Get the current mode information.

        Returns:
            ToolResult containing the current mode information
        """
        if not self._agent:
            return ToolResult(
                success=False,
                error="Agent not initialized.",
            )

        try:
            # Get current mode from agent, default to NORMAL if not set
            if hasattr(self._agent, "current_mode") and self._agent.current_mode:
                current_mode = self._agent.current_mode
            else:
                current_mode = AgentMode(mode_type=ModeType.NORMAL)

            mode_info = {
                "mode": current_mode.mode_type.value,
                "display_name": current_mode.display_name,
                "description": current_mode.description,
            }

            content = (
                f"当前模式: {mode_info['display_name']}\n"
                f"模式说明: {mode_info['description']}"
            )

            return ToolResult(
                success=True,
                content=content,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"获取模式信息失败: {type(e).__name__}: {e}",
            )
