"""Core Agent implementation."""

import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Optional

import tiktoken
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ..llm import LLMClient
from ..logger import AgentLogger
from ..schema import Message, StreamChunk
from ..tools.base import Tool, ToolResult


# ANSI color codes - Gemini CLI inspired theme
class Colors:
    """Terminal color definitions - Gemini CLI inspired"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Brand colors
    BRAND = "\033[38;2;66;133;244m"
    BRIGHT_BRAND = "\033[38;2;91;160;255m"

    # Semantic colors
    PRIMARY = "\033[96m"
    SECONDARY = "\033[90m"
    SUCCESS = "\033[32m"
    ERROR = "\033[31m"
    WARNING = "\033[33m"

    # Role colors
    USER = "\033[37m"
    ASSISTANT = "\033[96m"
    TOOL = "\033[35m"

    # UI symbols
    ASSISTANT_ICON = "◆"
    TOOL_ICON = "✓"
    USER_ICON = ">"

    # Compatibility aliases
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    RED = "\033[31m"


class Agent:
    """Single agent with basic tools and MCP support."""

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[Tool],
        max_steps: int = 50,
        workspace_dir: str = "./workspace",
        token_limit: int = 80000,  # Summary triggered when tokens exceed this value
    ):
        self.llm = llm_client
        self.tools = {tool.name: tool for tool in tools}
        self.max_steps = max_steps
        self.token_limit = token_limit
        self.workspace_dir = Path(workspace_dir)
        # Cancellation event for interrupting agent execution (set externally, e.g., by Esc key)
        self.cancel_event: Optional[asyncio.Event] = None

        # Ensure workspace exists
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Inject workspace information into system prompt if not already present
        if "Current Workspace" not in system_prompt:
            workspace_info = f"\n\n## Current Workspace\nYou are currently working in: `{self.workspace_dir.absolute()}`\nAll relative paths will be resolved relative to this directory."
            system_prompt = system_prompt + workspace_info

        self.system_prompt = system_prompt

        # Initialize message history
        self.messages: list[Message] = [Message(role="system", content=system_prompt)]

        # Initialize logger
        self.logger = AgentLogger()

        # Token usage from last API response (updated after each LLM call)
        self.api_total_tokens: int = 0
        # Flag to skip token check right after summary (avoid consecutive triggers)
        self._skip_next_token_check: bool = False

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append(Message(role="user", content=content))

    def _check_cancelled(self) -> bool:
        """Check if agent execution has been cancelled.

        Returns:
            True if cancelled, False otherwise.
        """
        if self.cancel_event is not None and self.cancel_event.is_set():
            return True
        return False

    def _cleanup_incomplete_messages(self):
        """Remove the incomplete assistant message and its partial tool results.

        This ensures message consistency after cancellation by removing
        only the current step's incomplete messages, preserving completed steps.
        """
        # Find the index of the last assistant message
        last_assistant_idx = -1
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].role == "assistant":
                last_assistant_idx = i
                break

        if last_assistant_idx == -1:
            # No assistant message found, nothing to clean
            return

        # Remove the last assistant message and all tool results after it
        removed_count = len(self.messages) - last_assistant_idx
        if removed_count > 0:
            self.messages = self.messages[:last_assistant_idx]

    def _estimate_tokens(self) -> int:
        """Accurately calculate token count for message history using tiktoken

        Uses cl100k_base encoder (GPT-4/Claude/M2 compatible)
        """
        try:
            # Use cl100k_base encoder (used by GPT-4 and most modern models)
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # Fallback: if tiktoken initialization fails, use simple estimation
            return self._estimate_tokens_fallback()

        total_tokens = 0

        for msg in self.messages:
            # Count text content
            if isinstance(msg.content, str):
                total_tokens += len(encoding.encode(msg.content))
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        # Convert dict to string for calculation
                        total_tokens += len(encoding.encode(str(block)))

            # Count thinking
            if msg.thinking:
                total_tokens += len(encoding.encode(msg.thinking))

            # Count tool_calls
            if msg.tool_calls:
                total_tokens += len(encoding.encode(str(msg.tool_calls)))

            # Metadata overhead per message (approximately 4 tokens)
            total_tokens += 4

        return total_tokens

    def _estimate_tokens_fallback(self) -> int:
        """Fallback token estimation method (when tiktoken is unavailable)"""
        total_chars = 0
        for msg in self.messages:
            if isinstance(msg.content, str):
                total_chars += len(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        total_chars += len(str(block))

            if msg.thinking:
                total_chars += len(msg.thinking)

            if msg.tool_calls:
                total_chars += len(str(msg.tool_calls))

        # Rough estimation: average 2.5 characters = 1 token
        return int(total_chars / 2.5)

    async def _summarize_messages(self):
        """Message history summarization: summarize conversations between user messages when tokens exceed limit

        Strategy (Agent mode):
        - Keep all user messages (these are user intents)
        - Summarize content between each user-user pair (agent execution process)
        - If last round is still executing (has agent/tool messages but no next user), also summarize
        - Structure: system -> user1 -> summary1 -> user2 -> summary2 -> user3 -> summary3 (if executing)

        Summary is triggered when EITHER:
        - Local token estimation exceeds limit
        - API reported total_tokens exceeds limit
        """
        # Skip check if we just completed a summary (wait for next LLM call to update api_total_tokens)
        if self._skip_next_token_check:
            self._skip_next_token_check = False
            return

        estimated_tokens = self._estimate_tokens()

        # Check both local estimation and API reported tokens
        should_summarize = estimated_tokens > self.token_limit or self.api_total_tokens > self.token_limit

        # If neither exceeded, no summary needed
        if not should_summarize:
            return

        print(
            f"\n{Colors.WARNING}Token 使用率: {estimated_tokens}/{self.token_limit}，触发自动总结...{Colors.RESET}"
        )

        # Find all user message indices (skip system prompt)
        user_indices = [i for i, msg in enumerate(self.messages) if msg.role == "user" and i > 0]

        # Need at least 1 user message to perform summary
        if len(user_indices) < 1:
            print(f"{Colors.SECONDARY}  消息不足，无法总结{Colors.RESET}")
            return

        # Build new message list
        new_messages = [self.messages[0]]  # Keep system prompt
        summary_count = 0

        # Iterate through each user message and summarize the execution process after it
        for i, user_idx in enumerate(user_indices):
            # Add current user message
            new_messages.append(self.messages[user_idx])

            # Determine message range to summarize
            # If last user, go to end of message list; otherwise to before next user
            if i < len(user_indices) - 1:
                next_user_idx = user_indices[i + 1]
            else:
                next_user_idx = len(self.messages)

            # Extract execution messages for this round
            execution_messages = self.messages[user_idx + 1 : next_user_idx]

            # If there are execution messages in this round, summarize them
            if execution_messages:
                summary_text = await self._create_summary(execution_messages, i + 1)
                if summary_text:
                    summary_message = Message(
                        role="user",
                        content=f"[Assistant Execution Summary]\n\n{summary_text}",
                    )
                    new_messages.append(summary_message)
                    summary_count += 1

        # Replace message list
        self.messages = new_messages

        # Skip next token check to avoid consecutive summary triggers
        # (api_total_tokens will be updated after next LLM call)
        self._skip_next_token_check = True

        new_tokens = self._estimate_tokens()
        print(f"{Colors.SECONDARY}  总结完成: {estimated_tokens} → {new_tokens} tokens{Colors.RESET}")

    async def _create_summary(self, messages: list[Message], round_num: int) -> str:
        """Create summary for one execution round

        Args:
            messages: List of messages to summarize
            round_num: Round number

        Returns:
            Summary text
        """
        if not messages:
            return ""

        # Build summary content
        summary_content = f"Round {round_num} execution process:\n\n"
        for msg in messages:
            if msg.role == "assistant":
                content_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"Assistant: {content_text}\n"
                if msg.tool_calls:
                    tool_names = [tc.function.name for tc in msg.tool_calls]
                    summary_content += f"  → Called tools: {', '.join(tool_names)}\n"
            elif msg.role == "tool":
                result_preview = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"  ← Tool returned: {result_preview}...\n"

        # Call LLM to generate concise summary
        try:
            summary_prompt = f"""Please provide a concise summary of the following Agent execution process:

{summary_content}

Requirements:
1. Focus on what tasks were completed and which tools were called
2. Keep key execution results and important findings
3. Be concise and clear, within 1000 words
4. Use English
5. Do not include "user" related content, only summarize the Agent's execution process"""

            summary_msg = Message(role="user", content=summary_prompt)
            response = await self.llm.generate(
                messages=[
                    Message(
                        role="system",
                        content="You are an assistant skilled at summarizing Agent execution processes.",
                    ),
                    summary_msg,
                ]
            )

            summary_text = response.content
            return summary_text

        except Exception:
            # Use simple text summary on failure
            return summary_content

    async def run(self, cancel_event: Optional[asyncio.Event] = None) -> str:
        """Execute agent loop until task is complete or max steps reached.

        Args:
            cancel_event: Optional asyncio.Event that can be set to cancel execution.
                          When set, the agent will stop at the next safe checkpoint
                          (after completing the current step to keep messages consistent).

        Returns:
            The final response content, or error message (including cancellation message).
        """
        # Set cancellation event (can also be set via self.cancel_event before calling run())
        if cancel_event is not None:
            self.cancel_event = cancel_event

        # Start new run, initialize log file
        self.logger.start_new_run()
        step = 0
        run_start_time = perf_counter()

        while step < self.max_steps:
            # Check for cancellation at start of each step
            if self._check_cancelled():
                self._cleanup_incomplete_messages()
                cancel_msg = "已取消"
                print(f"\n{Colors.WARNING}  {cancel_msg}{Colors.RESET}")
                return cancel_msg

            step_start_time = perf_counter()
            # Check and summarize message history to prevent context overflow
            await self._summarize_messages()

            # Step indicator - simplified, no box
            if step > 0:
                print()

            # Get tool list for LLM call
            tool_list = list(self.tools.values())

            # Log LLM request and call LLM with Tool objects directly
            self.logger.log_request(messages=self.messages, tools=tool_list)

            # Use streaming output - Kode style: direct streaming, no thinking indicator
            content_parts = []
            thinking_parts = []
            tool_calls = None
            usage = None
            finish_reason = "stop"

            # Track display state
            has_started = False
            thinking_displayed = False  # Track if thinking has been displayed

            # Buffer for smooth streaming - optimized for better FPS and user experience
            buffer = []
            buffer_chars = 0
            last_flush_time = perf_counter()
            # Optimized parameters for smoother output:
            # - Larger buffer to reduce system calls while maintaining responsiveness
            # - Lower FPS target (30fps) to match typical terminal refresh rates
            BUFFER_SIZE = 12  # Characters to buffer before flushing
            FLUSH_INTERVAL = 0.033  # Max seconds between flushes (~30 fps)
            # Natural break characters that trigger immediate flush for readability
            BREAK_CHARS = frozenset('.!?。！？\n')

            try:
                async for chunk in self.llm.generate_stream(messages=self.messages, tools=tool_list):
                    # Check for cancellation
                    if self._check_cancelled():
                        break

                    # Handle thinking content - accumulate but don't display yet
                    if chunk.thinking:
                        thinking_parts.append(chunk.thinking)

                    # Handle text content - stream with buffering for smoothness
                    elif chunk.content:
                        # Before first content, display thinking if available
                        if not has_started:
                            has_started = True
                            # Display accumulated thinking first (collapsible style)
                            if thinking_parts and not thinking_displayed:
                                full_thinking = "".join(thinking_parts)
                                if full_thinking.strip():
                                    try:
                                        console = Console()
                                        # Show thinking count only, not full content
                                        thinking_lines = full_thinking.strip().split('\n')
                                        thinking_summary = f"{len(thinking_lines)} lines"
                                        console.print(f"[dim]Thinking... ({thinking_summary})[/dim]")
                                    except Exception:
                                        pass
                                thinking_displayed = True
                            print(f"\n{Colors.ASSISTANT}{Colors.ASSISTANT_ICON}{Colors.RESET} ", end="", flush=True)

                        # Add to buffer
                        buffer.append(chunk.content)
                        buffer_chars += len(chunk.content)
                        content_parts.append(chunk.content)

                        # Flush conditions: buffer full, interval exceeded, or natural break point
                        current_time = perf_counter()
                        # Check for natural break points (end of sentence, punctuation)
                        ends_with_break = chunk.content and chunk.content[-1] in BREAK_CHARS
                        should_flush = (
                            buffer_chars >= BUFFER_SIZE or
                            (current_time - last_flush_time) >= FLUSH_INTERVAL or
                            ends_with_break
                        )

                        if should_flush:
                            if buffer:
                                text = "".join(buffer)
                                sys.stdout.write(text)
                                sys.stdout.flush()
                                buffer.clear()
                                buffer_chars = 0
                                last_flush_time = current_time

                    # Handle completion
                    elif chunk.is_complete:
                        tool_calls = chunk.tool_calls
                        usage = chunk.usage
                        break

                # Flush any remaining content
                if buffer:
                    sys.stdout.write("".join(buffer))
                    sys.stdout.flush()

            except Exception as e:
                # Check if it's a retry exhausted error
                from ..retry import RetryExhaustedError

                if isinstance(e, RetryExhaustedError):
                    error_msg = f"请求失败 ({e.attempts} 次重试)"
                    print(f"\n{Colors.ERROR}  {error_msg}{Colors.RESET}")
                else:
                    error_msg = f"请求失败: {str(e)}"
                    print(f"\n{Colors.ERROR}  {error_msg}{Colors.RESET}")
                return error_msg

            # Final newline if we printed anything
            if has_started:
                print()

            # Check for cancellation after streaming
            if self._check_cancelled():
                self._cleanup_incomplete_messages()
                cancel_msg = "已取消"
                print(f"\n{Colors.WARNING}  {cancel_msg}{Colors.RESET}")
                return cancel_msg

            # Build full response
            full_content = "".join(content_parts)
            full_thinking = "".join(thinking_parts) if thinking_parts else None

            # Accumulate API reported token usage
            if usage:
                self.api_total_tokens = usage.total_tokens

            # Log LLM response
            self.logger.log_response(
                content=full_content,
                thinking=full_thinking,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )

            # Add assistant message
            assistant_msg = Message(
                role="assistant",
                content=full_content,
                thinking=full_thinking,
                tool_calls=tool_calls,
            )
            self.messages.append(assistant_msg)

            # Check if task is complete (no tool calls)
            if not tool_calls:
                return full_content

            # Check for cancellation before executing tools
            if self._check_cancelled():
                self._cleanup_incomplete_messages()
                cancel_msg = "已取消"
                print(f"\n{Colors.WARNING}  {cancel_msg}{Colors.RESET}")
                return cancel_msg

            # Execute tool calls in parallel - Gemini CLI style display
            # First, display all tool calls being initiated
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                print(f"\n{Colors.SUCCESS}{Colors.TOOL_ICON}{Colors.RESET} {Colors.TOOL}{function_name}{Colors.RESET}", end="", flush=True)

            # Define async helper to execute a single tool
            async def execute_single_tool(tool_call) -> tuple[str, str, ToolResult]:
                """Execute a single tool and return (tool_call_id, function_name, result)."""
                tool_call_id = tool_call.id
                function_name = tool_call.function.name
                arguments = tool_call.function.arguments

                if function_name not in self.tools:
                    result = ToolResult(
                        success=False,
                        content="",
                        error=f"未知工具: {function_name}",
                    )
                else:
                    try:
                        tool = self.tools[function_name]
                        result = await tool.execute(**arguments)
                    except Exception as e:
                        import traceback
                        error_detail = f"{type(e).__name__}: {str(e)}"
                        error_trace = traceback.format_exc()
                        result = ToolResult(
                            success=False,
                            content="",
                            error=f"执行失败: {error_detail}\n\n{error_trace}",
                        )

                return tool_call_id, function_name, arguments, result

            # Execute all tools in parallel
            tool_tasks = [execute_single_tool(tc) for tc in tool_calls]
            tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)

            # Process results and add to messages
            for i, tool_result in enumerate(tool_results):
                if isinstance(tool_result, Exception):
                    # Handle exception from gather
                    tool_call = tool_calls[i]
                    tool_call_id = tool_call.id
                    function_name = tool_call.function.name
                    arguments = tool_call.function.arguments
                    result = ToolResult(
                        success=False,
                        content="",
                        error=f"工具执行异常: {str(tool_result)}",
                    )
                else:
                    tool_call_id, function_name, arguments, result = tool_result

                # Log tool execution result
                self.logger.log_tool_result(
                    tool_name=function_name,
                    arguments=arguments,
                    result_success=result.success,
                    result_content=result.content if result.success else None,
                    result_error=result.error if not result.success else None,
                )

                # Display result indented on next line
                if result.success:
                    result_text = result.content.replace("\n", " ")
                    if len(result_text) > 60:
                        result_text = result_text[:60] + "..."
                    print(f"\n{Colors.SECONDARY}  {result_text}{Colors.RESET}")
                else:
                    error_text = result.error.replace("\n", " ") if result.error else "错误"
                    if len(error_text) > 60:
                        error_text = error_text[:60] + "..."
                    print(f"\n{Colors.ERROR}  ✗ {error_text}{Colors.RESET}")

                # Add tool result message
                tool_msg = Message(
                    role="tool",
                    content=result.content if result.success else f"Error: {result.error}",
                    tool_call_id=tool_call_id,
                    name=function_name,
                )
                self.messages.append(tool_msg)

                # Check for cancellation
                if self._check_cancelled():
                    self._cleanup_incomplete_messages()
                    cancel_msg = "已取消"
                    print(f"\n{Colors.WARNING}  {cancel_msg}{Colors.RESET}")
                    return cancel_msg

            step += 1

        # Max steps reached
        error_msg = f"达到最大步数限制 ({self.max_steps})"
        print(f"\n{Colors.WARNING}  {error_msg}{Colors.RESET}")
        return error_msg

    def get_history(self) -> list[Message]:
        """Get message history."""
        return self.messages.copy()

    def update_persona(self, mode_prompt: str):
        """Update the persona/mode portion of the system prompt.

        This method updates the system message (messages[0]) by replacing
        the {MODE_PROMPT} placeholder with the actual mode prompt content.

        Args:
            mode_prompt: The mode-specific prompt text to inject.
        """
        if not self.messages or not self.messages[0].role == "system":
            return

        current_system = self.messages[0].content

        # Replace the {MODE_PROMPT} placeholder with actual content
        if "{MODE_PROMPT}" in current_system:
            new_system = current_system.replace("{MODE_PROMPT}", mode_prompt)
        else:
            # If placeholder was already replaced, we need to strip the old mode prompt
            # and inject the new one. We assume mode prompts start with "## Your Persona"
            # or are empty for normal mode.
            lines = current_system.split("\n")
            new_lines = []
            in_mode_section = False

            for line in lines:
                # Detect start of mode section
                if "## Your Persona" in line or "## Custom Persona" in line:
                    in_mode_section = True
                    continue
                # Detect end of mode section (next ## heading that is not part of persona)
                if in_mode_section and line.startswith("## "):
                    in_mode_section = False

                if not in_mode_section:
                    new_lines.append(line)

            new_system = "\n".join(new_lines)

            # Insert new mode prompt before "## Core Capabilities"
            if "## Core Capabilities" in new_system:
                new_system = new_system.replace(
                    "## Core Capabilities",
                    f"{mode_prompt}\n\n## Core Capabilities" if mode_prompt else "## Core Capabilities"
                )
            else:
                new_system = f"{new_system}\n\n{mode_prompt}" if mode_prompt else new_system

        self.messages[0].content = new_system
        self.system_prompt = new_system

        # Track current mode on agent for reference
        if not hasattr(self, "current_mode"):
            self.current_mode = None
