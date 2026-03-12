"""SubagentTool - Tool for spawning subagents from parent agent.

Upgraded version with support for:
- SubagentRegistry integration
- Named subagent spawning
- Built-in agent types
- Enhanced parameter schema
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from heris.tools.base import Tool, ToolResult

from .types import SubagentType, Thoroughness
from .runner import SubagentRunner

if TYPE_CHECKING:
    from heris import LLMClient
    from heris.tools.base import Tool as BaseTool

    from .registry import SubagentRegistry


class SubagentTool(Tool):
    """Tool for spawning specialized subagents with isolated context.

    This tool allows the parent agent to delegate tasks to subagents:
    - Each subagent gets a fresh, isolated message context
    - Subagents can use tools independently
    - Results are returned to the parent agent
    - Supports named subagents from registry or built-in types

    Enhanced features:
    - Spawn by name (from registry)
    - Spawn built-in types (explore, plan, general-purpose)
    - Thoroughness levels for explore agents
    - Custom workspace directories

    Example usage:
        >>> tool = SubagentTool(llm_client=client, registry=registry)
        >>> result = await tool.execute(
        ...     prompt="Analyze the file structure in /src",
        ...     agent_name="explore",
        ...     thoroughness="medium",
        ... )
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tools: list[BaseTool] | None = None,
        registry: SubagentRegistry | None = None,
        default_workspace: str | Path | None = None,
        default_max_steps: int = 30,
        default_thoroughness: str = "medium",
    ):
        """Initialize SubagentTool.

        Args:
            llm_client: LLM client for subagents
            tools: Default tools available to subagents
            registry: SubagentRegistry for named subagents
            default_workspace: Default workspace directory
            default_max_steps: Default max steps for subagents
            default_thoroughness: Default thoroughness for explore agents
        """
        super().__init__()
        self.llm_client = llm_client
        self.tools = tools or []
        self.registry = registry
        self.default_workspace = default_workspace
        self.default_max_steps = default_max_steps
        self.default_thoroughness = Thoroughness(default_thoroughness)

    @property
    def name(self) -> str:
        """Tool name."""
        return "spawn_subagent"

    @property
    def description(self) -> str:
        """Tool description."""
        registry_hint = ""
        if self.registry:
            available = self.registry.list_names()
            if available:
                registry_hint = f"\n\nAvailable subagents: {', '.join(available)}"

        return (
            "Spawn a specialized subagent to handle a specific task with isolated context. "
            "Use this when you need to:\n"
            "1. Delegate a complex subtask that can be worked on independently\n"
            "2. Explore a codebase or directory structure in parallel\n"
            "3. Perform research or analysis without cluttering your main context\n"
            "4. Run a task that might require many tool calls\n"
            "5. Use specialized expertise (code review, debugging, planning)\n\n"
            "The subagent will have its own isolated workspace and context, "
            "and will return a concise summary of results."
            f"{registry_hint}"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """Tool parameters schema."""
        # Build agent_name enum if registry is available
        agent_names = None
        if self.registry:
            available = self.registry.list_names()
            if available:
                agent_names = {"enum": available}

        properties: dict[str, Any] = {
            "prompt": {
                "type": "string",
                "description": (
                    "Detailed task description for the subagent. "
                    "Be specific about what you want the subagent to do and return."
                ),
            },
            "agent_name": {
                "type": "string",
                "description": (
                    "Name of the subagent to spawn. "
                    "Built-in types: explore, plan, general-purpose, code-reviewer, debug. "
                    "Or use a custom agent name from the registry."
                ),
                **(agent_names or {}),
            },
            "max_steps": {
                "type": "integer",
                "description": (
                    f"Maximum number of execution steps (default: {self.default_max_steps}). "
                    "Increase for complex tasks, decrease for simple ones."
                ),
                "minimum": 1,
                "maximum": 100,
            },
            "workspace_dir": {
                "type": "string",
                "description": (
                    "Optional working directory for the subagent. "
                    "If not provided, a temporary directory will be created."
                ),
            },
            "thoroughness": {
                "type": "string",
                "description": (
                    "Thoroughness level for explore agents (default: medium). "
                    "quick: Fast results, check obvious locations only. "
                    "medium: Balanced exploration. "
                    "very_thorough: Comprehensive analysis, check edge cases."
                ),
                "enum": ["quick", "medium", "very_thorough"],
            },
        }

        return {
            "type": "object",
            "properties": properties,
            "required": ["prompt", "agent_name"],
        }

    async def execute(
        self,
        prompt: str,
        agent_name: str,
        max_steps: int | None = None,
        workspace_dir: str | Path | None = None,
        thoroughness: str | None = None,
    ) -> ToolResult:
        """Execute the subagent tool.

        Args:
            prompt: Task description for the subagent
            agent_name: Name of subagent to spawn (builtin type or registry name)
            max_steps: Maximum execution steps (uses default if None)
            workspace_dir: Working directory (uses default/temp if None)
            thoroughness: Thoroughness level (uses default if None)

        Returns:
            ToolResult with subagent output
        """
        # Use provided values or defaults
        steps = max_steps if max_steps is not None else self.default_max_steps
        workspace = workspace_dir if workspace_dir is not None else self.default_workspace
        thorough = Thoroughness(thoroughness or self.default_thoroughness.value)

        try:
            # Try to spawn as built-in type first
            try:
                agent_type = SubagentType(agent_name)
                return await self._spawn_builtin(
                    prompt=prompt,
                    agent_type=agent_type,
                    max_steps=steps,
                    workspace_dir=workspace,
                    thoroughness=thorough,
                )
            except ValueError:
                # Not a built-in type, try registry
                pass

            # Try registry
            if self.registry:
                definition = self.registry.get(agent_name)
                if definition:
                    return await self._spawn_from_definition(
                        prompt=prompt,
                        definition=definition,
                        max_steps=steps,
                        workspace_dir=workspace,
                    )

            # Unknown agent name
            available_builtin = [t.value for t in SubagentType]
            available_registry = self.registry.list_names() if self.registry else []
            all_available = list(set(available_builtin + available_registry))

            return ToolResult(
                success=False,
                error=(
                    f"Unknown subagent: '{agent_name}'. "
                    f"Available: {', '.join(sorted(all_available))}"
                ),
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Subagent execution failed: {type(e).__name__}: {e}",
            )

    async def _spawn_builtin(
        self,
        prompt: str,
        agent_type: SubagentType,
        max_steps: int,
        workspace_dir: str | Path | None,
        thoroughness: Thoroughness,
    ) -> ToolResult:
        """Spawn a built-in subagent type.

        Args:
            prompt: Task description
            agent_type: Built-in agent type
            max_steps: Maximum steps
            workspace_dir: Workspace directory
            thoroughness: Thoroughness level

        Returns:
            ToolResult with execution result
        """
        runner = SubagentRunner.from_builtin(
            agent_type=agent_type,
            llm_client=self.llm_client,
            tools=self.tools.copy() if self.tools else None,
            workspace_dir=workspace_dir,
            thoroughness=thoroughness,
        )

        try:
            result = await runner.run(prompt)
            if result.startswith("[Subagent Error]"):
                return ToolResult(success=False, error=result)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Subagent execution failed: {type(e).__name__}: {e}",
            )
        finally:
            runner.cleanup()

    async def _spawn_from_definition(
        self,
        prompt: str,
        definition: Any,  # SubagentDefinition
        max_steps: int,
        workspace_dir: str | Path | None,
    ) -> ToolResult:
        """Spawn a subagent from a definition.

        Args:
            prompt: Task description
            definition: Subagent definition
            max_steps: Maximum steps
            workspace_dir: Workspace directory

        Returns:
            ToolResult with execution result
        """
        runner = SubagentRunner.from_definition(
            definition=definition,
            llm_client=self.llm_client,
            tools=self.tools.copy() if self.tools else None,
            workspace_dir=workspace_dir,
        )

        try:
            result = await runner.run(prompt)
            if result.startswith("[Subagent Error]"):
                return ToolResult(success=False, error=result)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Subagent execution failed: {type(e).__name__}: {e}",
            )
        finally:
            runner.cleanup()

    def with_tools(self, tools: list[BaseTool]) -> "SubagentTool":
        """Create a new SubagentTool with additional tools.

        Args:
            tools: Additional tools to add

        Returns:
            New SubagentTool instance with combined tools
        """
        combined_tools = (self.tools or []) + tools
        return SubagentTool(
            llm_client=self.llm_client,
            tools=combined_tools,
            registry=self.registry,
            default_workspace=self.default_workspace,
            default_max_steps=self.default_max_steps,
            default_thoroughness=self.default_thoroughness.value,
        )

    def with_registry(self, registry: SubagentRegistry) -> "SubagentTool":
        """Create a new SubagentTool with a registry.

        Args:
            registry: SubagentRegistry to use

        Returns:
            New SubagentTool instance with registry
        """
        return SubagentTool(
            llm_client=self.llm_client,
            tools=self.tools.copy() if self.tools else None,
            registry=registry,
            default_workspace=self.default_workspace,
            default_max_steps=self.default_max_steps,
            default_thoroughness=self.default_thoroughness.value,
        )

    def list_available(self) -> dict[str, list[str]]:
        """List all available subagents.

        Returns:
            Dictionary with 'builtin' and 'registry' keys
        """
        result: dict[str, list[str]] = {
            "builtin": [t.value for t in SubagentType],
        }

        if self.registry:
            result["registry"] = self.registry.list_names()
        else:
            result["registry"] = []

        return result
