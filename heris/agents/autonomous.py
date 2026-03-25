"""Autonomous Agent - Self-directed execution with idle polling (s11 pattern).

Implements autonomous agent patterns:
- Idle cycle: Poll for work when no active task
- Auto-claim: Automatically claim tasks from the task board
- Identity re-injection: Recover context after compression
- Shutdown handling: Respond to graceful shutdown requests
"""

import asyncio
import time
from pathlib import Path
from typing import Optional

from .agent import Agent, Colors
from ..llm import LLMClient
from ..schema import Message
from ..tools.base import Tool


class AutonomousAgent(Agent):
    """Autonomous agent with idle polling and auto-task claiming.

    Extends base Agent with autonomous execution capabilities:
    - Runs continuously until shutdown requested
    - Polls for unclaimed tasks when idle
    - Handles shutdown protocol gracefully
    """

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[Tool],
        agent_id: str = "agent",
        max_steps: int = 50,
        workspace_dir: str = "./workspace",
        token_limit: int = 80000,
        idle_poll_interval: float = 5.0,
        idle_timeout_seconds: float = 60.0,
    ):
        """Initialize AutonomousAgent.

        Args:
            llm_client: LLM client for API calls
            system_prompt: System prompt for the agent
            tools: List of available tools
            agent_id: Unique identifier for this agent
            max_steps: Maximum steps per task execution
            workspace_dir: Working directory
            token_limit: Token limit before summarization
            idle_poll_interval: Seconds between idle polls
            idle_timeout_seconds: Seconds to wait before shutting down when idle
        """
        super().__init__(
            llm_client=llm_client,
            system_prompt=system_prompt,
            tools=tools,
            max_steps=max_steps,
            workspace_dir=workspace_dir,
            token_limit=token_limit,
        )

        self.agent_id = agent_id
        self.idle_poll_interval = idle_poll_interval
        self.idle_timeout_seconds = idle_timeout_seconds

        # State tracking
        self._idle_since: Optional[float] = None
        self._shutdown_requested = False
        self._current_task_id: Optional[int] = None

        # Inject autonomous behavior into system prompt
        self._inject_autonomous_prompt()

    def _inject_autonomous_prompt(self):
        """Add autonomous behavior instructions to system prompt."""
        autonomous_instructions = """

## Autonomous Operation Mode

You are running in autonomous mode with the following capabilities:

1. **Task Management**: Use `list_unclaimed_tasks` to find work, `claim_task` to take ownership
2. **Idle Handling**: When no work remains, use `idle` to enter polling state
3. **Plan Approval**: Submit plans via `plan_submit` if approval is required for significant changes
4. **Shutdown**: Acknowledge shutdown requests via `shutdown_ack`

**Workflow**:
1. Check for unclaimed tasks with `list_unclaimed_tasks`
2. Claim an available task with `claim_task`
3. Execute the task (use worktrees for isolation if needed)
4. Mark task complete with `task_update` when done
5. If no tasks available, use `idle` and wait for new work
6. Respond to shutdown requests promptly

**Identity Re-injection**: After context compression, remind yourself:
- Your current task and progress
- Active worktrees or pending operations
- Any blocked tasks waiting on dependencies
"""
        self.system_prompt += autonomous_instructions
        # Update system message
        if self.messages and self.messages[0].role == "system":
            self.messages[0].content = self.system_prompt

    async def run_autonomous(self) -> None:
        """Run autonomous execution loop until shutdown.

        This is the main entry point for autonomous operation.
        The agent will continuously:
        1. Check for shutdown requests
        2. Claim and execute tasks
        3. Enter idle state when no work available
        """
        print(f"\n{Colors.BRAND}Autonomous Agent '{self.agent_id}' started{Colors.RESET}")
        print(f"{Colors.SECONDARY}Workspace: {self.workspace_dir}{Colors.RESET}")
        print(f"{Colors.SECONDARY}Idle timeout: {self.idle_timeout_seconds}s{Colors.RESET}\n")

        while not self._shutdown_requested:
            # Check for shutdown messages
            if await self._check_shutdown():
                break

            # Try to claim and execute a task
            task_executed = await self._try_claim_and_execute()

            if not task_executed:
                # No tasks available, enter idle state
                await self._idle_poll()

        print(f"\n{Colors.BRAND}Autonomous Agent '{self.agent_id}' shutting down{Colors.RESET}")

    async def _check_shutdown(self) -> bool:
        """Check for shutdown request in messages.

        Returns:
            True if shutdown should proceed, False otherwise
        """
        # This would check the MessageBus for shutdown.requests
        # For now, we check if there's a shutdown request in the last message
        if len(self.messages) > 1:
            last_msg = self.messages[-1]
            if (
                last_msg.role == "user"
                and "shutdown" in last_msg.content.lower()
                and "request" in last_msg.content.lower()
            ):
                print(f"\n{Colors.WARNING}Shutdown request received{Colors.RESET}")
                return True
        return False

    async def _try_claim_and_execute(self) -> bool:
        """Try to claim and execute an unclaimed task.

        Returns:
            True if a task was claimed and executed, False if no tasks available
        """
        # Check if we have the list_unclaimed_tasks tool
        if "list_unclaimed_tasks" not in self.tools:
            return False

        # List unclaimed tasks
        try:
            tool = self.tools["list_unclaimed_tasks"]
            result = await tool.execute()

            if not result.success:
                return False

            # Check if there are any tasks
            if "No unclaimed tasks" in result.content:
                return False

            # Parse task IDs from the result
            # Format: "#1: Task Subject"
            import re
            task_ids = re.findall(r'#(\d+):', result.content)

            if not task_ids:
                return False

            # Claim the first available task
            task_id = int(task_ids[0])

            if "claim_task" not in self.tools:
                return False

            claim_tool = self.tools["claim_task"]
            claim_result = await claim_tool.execute(task_id=task_id, owner=self.agent_id)

            if not claim_result.success:
                print(f"{Colors.ERROR}Failed to claim task #{task_id}{Colors.RESET}")
                return False

            print(f"\n{Colors.SUCCESS}✓ Claimed task #{task_id}{Colors.RESET}")
            self._current_task_id = task_id
            self._idle_since = None

            # Get task details
            if "task_get" in self.tools:
                get_tool = self.tools["task_get"]
                task_info = await get_tool.execute(task_id=task_id)
                if task_info.success:
                    print(f"{Colors.SECONDARY}{task_info.content[:200]}...{Colors.RESET}\n")

            # Execute the task
            await self._execute_task(task_id)
            return True

        except Exception as e:
            print(f"{Colors.ERROR}Error claiming task: {e}{Colors.RESET}")
            return False

    async def _execute_task(self, task_id: int):
        """Execute a claimed task.

        Args:
            task_id: The task ID to execute
        """
        # Add task context to messages
        self.add_user_message(
            f"You have claimed task #{task_id}. Please review the task details and execute it. "
            f"Use worktree_create for isolation if needed. "
            f"When complete, mark the task as completed with task_update."
        )

        # Run the agent loop
        await self.run()

        # Mark task as completed if not already done
        if "task_update" in self.tools:
            try:
                update_tool = self.tools["task_update"]
                await update_tool.execute(task_id=task_id, status="completed")
                print(f"\n{Colors.SUCCESS}✓ Task #{task_id} marked as completed{Colors.RESET}")
            except Exception as e:
                print(f"{Colors.ERROR}Failed to mark task complete: {e}{Colors.RESET}")

        self._current_task_id = None

    async def _idle_poll(self):
        """Enter idle state and poll for work."""
        if self._idle_since is None:
            self._idle_since = time.time()
            print(f"\n{Colors.SECONDARY}No tasks available. Entering idle state...{Colors.RESET}")

        # Check if idle timeout reached
        idle_time = time.time() - self._idle_since
        if idle_time >= self.idle_timeout_seconds:
            print(f"\n{Colors.WARNING}Idle timeout ({self.idle_timeout_seconds}s) reached{Colors.RESET}")
            self._shutdown_requested = True
            return

        # Wait for next poll
        remaining = self.idle_timeout_seconds - idle_time
        print(f"{Colors.SECONDARY}  Idle for {idle_time:.0f}s, timeout in {remaining:.0f}s{Colors.RESET}", end="\r")

        await asyncio.sleep(self.idle_poll_interval)

    async def handle_idle_tool(self, reason: str = "") -> str:
        """Handle the idle tool call.

        This is called when the agent uses the IdleTool to signal
        it has no more work to do.

        Args:
            reason: Optional reason for idling

        Returns:
            Idle status message
        """
        if self._idle_since is None:
            self._idle_since = time.time()

        msg = f"Agent {self.agent_id} entering idle state"
        if reason:
            msg += f": {reason}"

        print(f"\n{Colors.SECONDARY}{msg}{Colors.RESET}")
        return msg

    def request_shutdown(self):
        """Request the agent to shut down gracefully."""
        self._shutdown_requested = True
        print(f"\n{Colors.WARNING}Shutdown requested for agent {self.agent_id}{Colors.RESET}")


class AutonomousAgentRunner:
    """Runner for autonomous agents with lifecycle management.

    Manages the autonomous agent lifecycle including:
    - Initialization with proper tools
    - Running the idle-claim-execute loop
    - Handling shutdown signals
    """

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[Tool],
        agent_id: str = "agent",
        workspace_dir: str = "./workspace",
    ):
        """Initialize the runner.

        Args:
            llm_client: LLM client
            system_prompt: System prompt
            tools: Available tools (should include team/worktree tools)
            agent_id: Agent identifier
            workspace_dir: Working directory
        """
        self.agent = AutonomousAgent(
            llm_client=llm_client,
            system_prompt=system_prompt,
            tools=tools,
            agent_id=agent_id,
            workspace_dir=workspace_dir,
        )

    async def run(self) -> None:
        """Run the autonomous agent until shutdown."""
        try:
            await self.agent.run_autonomous()
        except KeyboardInterrupt:
            print(f"\n{Colors.WARNING}Interrupted{Colors.RESET}")
        finally:
            print(f"\n{Colors.BRAND}Autonomous runner stopped{Colors.RESET}")

    def shutdown(self):
        """Request graceful shutdown."""
        self.agent.request_shutdown()
