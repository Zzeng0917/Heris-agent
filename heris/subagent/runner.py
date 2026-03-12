"""Subagent runner - handles execution of subagents with isolated context.

Upgraded version supporting:
- SubagentDefinition-based configuration
- Built-in agent types (Explore, Plan, General)
- Thoroughness levels for exploration
- Tool filtering based on allowed/disallowed lists
- Permission modes

Design principles:
1. "大任务拆小, 每个小任务干净的上下文" -- 子智能体用独立 messages[], 不污染主对话
2. "智能体工作越久, messages 数组越胖" -- 子智能体独立处理，避免污染父智能体上下文
3. "工作空间要隔离" -- 子智能体在独立 workspace/ 下干活
4. "记得善后" -- 子智能体完事后可选择清理 workspace/
5. "保持清醒" -- 子智能体不自己改 todo list, 让父智能体统一管理
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from heris import LLMClient
from heris.schema import Message
from heris.tools.base import Tool

from .types import (
    SubagentDefinition,
    SubagentType,
    Thoroughness,
    PermissionMode,
)
from .builtin import get_builtin_definition

if TYPE_CHECKING:
    from ..llm.base import BaseLLMClient


# Legacy system prompt for backward compatibility
SUBAGENT_SYSTEM_PROMPT = """You are a specialized subagent working on a specific task assigned by a parent agent.

## Your Role
- Focus exclusively on the task you've been given
- Use available tools to complete the task efficiently
- Return a concise summary of your findings or results

## Key Principles
1. **Isolated Context** - You have a fresh conversation context, independent of the parent agent
2. **Tool Access** - You have access to file operations, bash commands, and web search tools
3. **Workspace Isolation** - Work in your assigned workspace directory only
4. **Concise Output** - Return only the essential results, not your thought process
5. **No Task Management** - Do not create or manage todo lists; the parent handles task coordination

## Output Format
When complete, provide:
- A brief summary of what you did
- Key findings or results
- Any files created or modified (with paths)
- Any errors or blockers encountered

Be thorough but concise. The parent agent will use your output to make decisions."""


class SubagentRunner:
    """Runner for subagents with isolated context.

    This class manages the execution of subagents:
    - Creates isolated message context (fresh messages array)
    - Manages workspace directory for subagent operations
    - Handles tool execution loop
    - Returns concise results to parent agent

    Enhanced features:
    - Support for SubagentDefinition configuration
    - Built-in agent types
    - Tool filtering
    - Thoroughness levels
    """

    def __init__(
        self,
        llm_client: LLMClient | BaseLLMClient,
        tools: list[Tool] | None = None,
        workspace_dir: str | Path | None = None,
        max_steps: int = 30,
        system_prompt: str | None = None,
        definition: SubagentDefinition | None = None,
        thoroughness: Thoroughness | str = Thoroughness.MEDIUM,
    ):
        """Initialize subagent runner.

        Args:
            llm_client: LLM client for generating responses
            tools: List of tools available to the subagent (defaults to basic tools)
            workspace_dir: Working directory for subagent (creates temp if None)
            max_steps: Maximum execution steps before stopping
            system_prompt: Custom system prompt (uses default if None)
            definition: SubagentDefinition for advanced configuration
            thoroughness: Thoroughness level for explore agents
        """
        self.llm = llm_client
        self.max_steps = definition.max_turns if definition and definition.max_turns else max_steps
        self.definition = definition

        # Handle thoroughness
        if isinstance(thoroughness, str):
            thoroughness = Thoroughness(thoroughness)
        self.thoroughness = thoroughness

        # Determine system prompt
        if definition and definition.system_prompt:
            self.system_prompt = self._prepare_system_prompt(definition.system_prompt)
        elif system_prompt:
            self.system_prompt = system_prompt
        else:
            self.system_prompt = SUBAGENT_SYSTEM_PROMPT

        # Filter tools based on definition
        self.all_tools = {tool.name: tool for tool in (tools or [])}
        self.tools = self._filter_tools(tools or [], definition)

        # Setup workspace
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir)
            self._cleanup_workspace = False
        elif definition and definition.memory:
            # Use memory directory if memory is enabled
            self.workspace_dir = self._get_memory_directory()
            self._cleanup_workspace = False
        else:
            self.workspace_dir = Path(tempfile.mkdtemp(prefix="subagent_"))
            self._cleanup_workspace = True

        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Permission mode
        self.permission_mode = (
            definition.permission_mode if definition else PermissionMode.DEFAULT
        )

        # Execution tracking
        self._executed_steps = 0
        self._cancelled = False

    def _prepare_system_prompt(self, base_prompt: str) -> str:
        """Prepare system prompt with thoroughness hints if applicable.

        Args:
            base_prompt: Base system prompt from definition

        Returns:
            Prepared system prompt
        """
        if not self.definition or self.definition.name != "explore":
            return base_prompt

        # Add thoroughness guidance for explore agents
        thoroughness_guide = {
            Thoroughness.QUICK: "\n\n## Thoroughness: QUICK\nFocus on fast results. Check only the most obvious locations.",
            Thoroughness.MEDIUM: "\n\n## Thoroughness: MEDIUM\nBalance speed and thoroughness. Check likely candidates and common patterns.",
            Thoroughness.VERY_THOROUGH: "\n\n## Thoroughness: VERY THOROUGH\nBe comprehensive. Check multiple locations, naming conventions, and edge cases.",
        }

        return base_prompt + thoroughness_guide.get(self.thoroughness, "")

    def _filter_tools(
        self, tools: list[Tool], definition: SubagentDefinition | None
    ) -> dict[str, Tool]:
        """Filter tools based on definition constraints.

        Args:
            tools: All available tools
            definition: Subagent definition with tool constraints

        Returns:
            Filtered tools dictionary
        """
        if not definition:
            return {tool.name: tool for tool in tools}

        filtered = {}
        for tool in tools:
            # Check allowed tools
            if definition.tools is not None:
                if tool.name not in definition.tools:
                    continue

            # Check disallowed tools
            if definition.disallowed_tools and tool.name in definition.disallowed_tools:
                continue

            filtered[tool.name] = tool

        return filtered

    def _get_memory_directory(self) -> Path:
        """Get memory directory for persistent storage.

        Returns:
            Path to memory directory
        """
        if not self.definition or not self.definition.memory:
            return Path(tempfile.mkdtemp(prefix="subagent_"))

        # Determine base directory
        if self.definition.memory.value == "user":
            base_dir = Path.home() / ".heris" / "agent-memory"
        elif self.definition.memory.value == "project":
            base_dir = Path.cwd() / ".heris" / "agent-memory"
        else:  # local
            base_dir = Path.cwd() / ".heris" / "agent-memory-local"

        memory_dir = base_dir / self.definition.name
        memory_dir.mkdir(parents=True, exist_ok=True)
        return memory_dir

    @classmethod
    def from_builtin(
        cls,
        agent_type: SubagentType,
        llm_client: LLMClient | BaseLLMClient,
        tools: list[Tool] | None = None,
        workspace_dir: str | Path | None = None,
        thoroughness: Thoroughness | str = Thoroughness.MEDIUM,
    ) -> SubagentRunner:
        """Create a runner from a built-in subagent type.

        Args:
            agent_type: Built-in subagent type
            llm_client: LLM client
            tools: Available tools
            workspace_dir: Working directory
            thoroughness: Thoroughness level for explore agents

        Returns:
            Configured SubagentRunner
        """
        definition = get_builtin_definition(agent_type)
        return cls(
            llm_client=llm_client,
            tools=tools,
            workspace_dir=workspace_dir,
            definition=definition,
            thoroughness=thoroughness,
        )

    @classmethod
    def from_definition(
        cls,
        definition: SubagentDefinition,
        llm_client: LLMClient | BaseLLMClient,
        tools: list[Tool] | None = None,
        workspace_dir: str | Path | None = None,
    ) -> SubagentRunner:
        """Create a runner from a subagent definition.

        Args:
            definition: Subagent definition
            llm_client: LLM client
            tools: Available tools
            workspace_dir: Working directory

        Returns:
            Configured SubagentRunner
        """
        return cls(
            llm_client=llm_client,
            tools=tools,
            workspace_dir=workspace_dir,
            definition=definition,
        )

    async def run(self, prompt: str) -> str:
        """Run subagent with a fresh context.

        Args:
            prompt: The task prompt for the subagent

        Returns:
            Summary of subagent execution results
        """
        # Fresh messages array - isolated from parent
        messages: list[Message] = [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content=prompt),
        ]

        step = 0
        final_response = ""

        while step < self.max_steps:
            self._executed_steps = step

            # Check for cancellation
            if self._cancelled:
                return "[Subagent Cancelled]"

            # Get LLM response
            tool_list = list(self.tools.values())

            try:
                response = await self.llm.generate(messages=messages, tools=tool_list)
            except Exception as e:
                return f"[Subagent Error] LLM request failed: {type(e).__name__}: {e}"

            # Extract content and tool calls
            content = response.content or ""
            tool_calls = response.tool_calls

            # Add assistant message to subagent context
            messages.append(
                Message(
                    role="assistant",
                    content=content,
                    tool_calls=tool_calls,
                )
            )

            # If no tool calls, task is complete
            if not tool_calls:
                final_response = content
                break

            # Execute tools in parallel
            tool_tasks = []
            for tc in tool_calls:
                tool_name = tc.function.name
                arguments = tc.function.arguments

                if tool_name in self.tools:
                    tool = self.tools[tool_name]
                    task = self._execute_tool(tool, tool_name, arguments, tc.id)
                    tool_tasks.append(task)
                else:
                    # Unknown tool - create error result
                    tool_tasks.append(
                        asyncio.create_task(
                            self._create_error_result(tc.id, f"Unknown tool: {tool_name}")
                        )
                    )

            results = await asyncio.gather(*tool_tasks, return_exceptions=True)

            # Add tool results to messages
            for result in results:
                if isinstance(result, Exception):
                    # Handle exception
                    messages.append(
                        Message(
                            role="tool",
                            content=f"Error: {result}",
                            tool_call_id="unknown",
                        )
                    )
                else:
                    tool_call_id, content = result
                    messages.append(
                        Message(
                            role="tool",
                            content=content,
                            tool_call_id=tool_call_id,
                        )
                    )

            step += 1

        if step >= self.max_steps:
            final_response += "\n[Subagent reached maximum step limit]"

        return final_response or "(no output from subagent)"

    async def _execute_tool(
        self, tool: Tool, tool_name: str, arguments: dict[str, Any], tool_call_id: str
    ) -> tuple[str, str]:
        """Execute a single tool and return (tool_call_id, result_content)."""
        try:
            result = await tool.execute(**arguments)
            if result.success:
                return tool_call_id, result.content
            else:
                return tool_call_id, f"Error: {result.error}"
        except Exception as e:
            return tool_call_id, f"Error executing {tool_name}: {type(e).__name__}: {e}"

    async def _create_error_result(self, tool_call_id: str, error: str) -> tuple[str, str]:
        """Create an error result tuple."""
        return tool_call_id, error

    def cancel(self) -> None:
        """Cancel subagent execution."""
        self._cancelled = True

    def cleanup(self) -> None:
        """Clean up subagent workspace if it was created temporarily."""
        if self._cleanup_workspace and self.workspace_dir.exists():
            import shutil

            try:
                shutil.rmtree(self.workspace_dir)
            except Exception:
                pass  # Best effort cleanup

    async def __aenter__(self) -> SubagentRunner:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Async context manager exit - cleanup workspace."""
        self.cleanup()
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics.

        Returns:
            Dictionary with execution stats
        """
        return {
            "executed_steps": self._executed_steps,
            "max_steps": self.max_steps,
            "available_tools": list(self.tools.keys()),
            "workspace_dir": str(self.workspace_dir),
            "permission_mode": self.permission_mode.value,
        }


async def run_subagent(
    prompt: str,
    llm_client: LLMClient | BaseLLMClient,
    tools: list[Tool] | None = None,
    workspace_dir: str | Path | None = None,
    max_steps: int = 30,
    cleanup: bool = True,
    definition: SubagentDefinition | None = None,
    agent_type: SubagentType | None = None,
    thoroughness: Thoroughness | str = Thoroughness.MEDIUM,
) -> str:
    """Convenience function to run a subagent task.

    Args:
        prompt: Task description for the subagent
        llm_client: LLM client instance
        tools: Available tools (None for default set)
        workspace_dir: Working directory (None for temp directory)
        max_steps: Maximum execution steps
        cleanup: Whether to cleanup workspace after execution
        definition: Subagent definition for advanced configuration
        agent_type: Built-in agent type (alternative to definition)
        thoroughness: Thoroughness level for explore agents

    Returns:
        Subagent execution result

    Example:
        >>> from heris import LLMClient
        >>> from heris.subagent import run_subagent, SubagentType
        >>> client = LLMClient(api_key="...")
        >>> result = await run_subagent(
        ...     "List all Python files in /src directory",
        ...     llm_client=client,
        ...     agent_type=SubagentType.EXPLORE,
        ... )
        >>> print(result)
    """
    # Determine runner configuration
    if definition:
        runner = SubagentRunner.from_definition(
            definition=definition,
            llm_client=llm_client,
            tools=tools,
            workspace_dir=workspace_dir,
        )
    elif agent_type:
        runner = SubagentRunner.from_builtin(
            agent_type=agent_type,
            llm_client=llm_client,
            tools=tools,
            workspace_dir=workspace_dir,
            thoroughness=thoroughness,
        )
    else:
        runner = SubagentRunner(
            llm_client=llm_client,
            tools=tools,
            workspace_dir=workspace_dir,
            max_steps=max_steps,
        )

    try:
        result = await runner.run(prompt)
        return result
    finally:
        if cleanup:
            runner.cleanup()
