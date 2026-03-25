"""Worktree tools - Integration with Heris Agent.

Provides tools for task and worktree management.
"""

from typing import Any, Optional
from pathlib import Path

from ..base import Tool, ToolResult
from .task_manager import TaskManager
from .worktree_manager import WorktreeManager
from .eventbus import EventBus


# Global instances (initialized once and shared)
_task_manager: Optional[TaskManager] = None
_worktree_manager: Optional[WorktreeManager] = None
_event_bus: Optional[EventBus] = None


def init_worktree_system(workspace_dir: Path) -> tuple[TaskManager, WorktreeManager, EventBus]:
    """Initialize the worktree system.

    Args:
        workspace_dir: Base workspace directory

    Returns:
        Tuple of (TaskManager, WorktreeManager, EventBus)
    """
    global _task_manager, _worktree_manager, _event_bus

    if _task_manager is None:
        tasks_dir = workspace_dir / ".tasks"
        worktrees_dir = workspace_dir / ".worktrees"

        _event_bus = EventBus(worktrees_dir / "events.jsonl")
        _task_manager = TaskManager(tasks_dir)
        _worktree_manager = WorktreeManager(
            repo_root=workspace_dir,
            tasks=_task_manager,
            events=_event_bus,
            worktrees_dir=worktrees_dir,
        )

    return _task_manager, _worktree_manager, _event_bus


def get_managers() -> tuple[Optional[TaskManager], Optional[WorktreeManager], Optional[EventBus]]:
    """Get the global manager instances."""
    return _task_manager, _worktree_manager, _event_bus


# =============================================================================
# Task Tools
# =============================================================================

class TaskCreateTool(Tool):
    """Create a new task on the shared task board."""

    @property
    def name(self) -> str:
        return "task_create"

    @property
    def description(self) -> str:
        return """Create a new task on the shared task board.

Use this for multi-step work that can be done in parallel or needs isolation.
Each task gets a unique ID and can be bound to a worktree for execution."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Task title/subject (required)"},
                "description": {"type": "string", "description": "Detailed description (optional)"},
            },
            "required": ["subject"],
        }

    async def execute(self, subject: str, description: str = "") -> ToolResult:
        try:
            tm, _, _ = get_managers()
            if tm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            task = tm.create(subject, description)
            return ToolResult(
                success=True,
                content=f"Created task #{task.id}: {task.subject}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class TaskListTool(Tool):
    """List all tasks with status, owner, and worktree binding."""

    @property
    def name(self) -> str:
        return "task_list"

    @property
    def description(self) -> str:
        return """List all tasks on the board.

Shows status, owner, and worktree binding for each task.
Use this to see what's pending, in progress, or completed."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self) -> ToolResult:
        try:
            tm, _, _ = get_managers()
            if tm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            result = tm.render_list()
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class TaskGetTool(Tool):
    """Get task details by ID."""

    @property
    def name(self) -> str:
        return "task_get"

    @property
    def description(self) -> str:
        return """Get detailed information about a specific task.

Shows full task data including status, owner, worktree binding, and dependencies."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to get"},
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: int) -> ToolResult:
        try:
            tm, _, _ = get_managers()
            if tm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            task = tm.get(task_id)
            import json
            return ToolResult(
                success=True,
                content=json.dumps(task.to_dict(), indent=2),
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class TaskUpdateTool(Tool):
    """Update task status or owner."""

    @property
    def name(self) -> str:
        return "task_update"

    @property
    def description(self) -> str:
        return """Update a task's status or owner.

Status options: pending, in_progress, completed
When marking completed, dependent tasks are automatically unblocked."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to update"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed"],
                    "description": "New status (optional)",
                },
                "owner": {"type": "string", "description": "New owner (optional, empty to clear)"},
            },
            "required": ["task_id"],
        }

    async def execute(
        self,
        task_id: int,
        status: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> ToolResult:
        try:
            tm, _, _ = get_managers()
            if tm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            task = tm.update(task_id, status=status, owner=owner)
            return ToolResult(
                success=True,
                content=f"Updated task #{task.id}: status={task.status}, owner={task.owner or 'none'}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class TaskBindWorktreeTool(Tool):
    """Bind a task to a worktree."""

    @property
    def name(self) -> str:
        return "task_bind_worktree"

    @property
    def description(self) -> str:
        return """Bind a task to a worktree.

This links the task to an isolated execution environment.
The task status is automatically set to 'in_progress' when bound."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to bind"},
                "worktree": {"type": "string", "description": "Worktree name"},
                "owner": {"type": "string", "description": "Owner name (optional)"},
            },
            "required": ["task_id", "worktree"],
        }

    async def execute(
        self,
        task_id: int,
        worktree: str,
        owner: str = "",
    ) -> ToolResult:
        try:
            tm, _, _ = get_managers()
            if tm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            task = tm.bind_worktree(task_id, worktree, owner)
            return ToolResult(
                success=True,
                content=f"Bound task #{task.id} to worktree '{worktree}'",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# =============================================================================
# Worktree Tools
# =============================================================================

class WorktreeCreateTool(Tool):
    """Create a git worktree."""

    @property
    def name(self) -> str:
        return "worktree_create"

    @property
    def description(self) -> str:
        return """Create a new git worktree for isolated execution.

A worktree is an isolated directory sharing the same git history
but with its own working tree. Use this for parallel or risky changes.

Optionally bind to a task for automatic tracking."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Worktree name (1-40 chars: letters, numbers, ., _, -)",
                },
                "task_id": {"type": "integer", "description": "Optional task ID to bind"},
                "base_ref": {"type": "string", "description": "Base git ref (default: HEAD)"},
            },
            "required": ["name"],
        }

    async def execute(
        self,
        name: str,
        task_id: Optional[int] = None,
        base_ref: str = "HEAD",
    ) -> ToolResult:
        try:
            _, wm, _ = get_managers()
            if wm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            if not wm.is_git_available():
                return ToolResult(
                    success=False,
                    error="Not in a git repository. Worktree tools require git.",
                )

            worktree = wm.create(name, task_id, base_ref)
            return ToolResult(
                success=True,
                content=f"Created worktree '{name}' at {worktree.path} (branch: {worktree.branch})",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WorktreeListTool(Tool):
    """List all worktrees."""

    @property
    def name(self) -> str:
        return "worktree_list"

    @property
    def description(self) -> str:
        return """List all worktrees tracked in the index.

Shows status, path, branch, and bound task for each worktree."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self) -> ToolResult:
        try:
            _, wm, _ = get_managers()
            if wm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            worktrees = wm.list_all()
            if not worktrees:
                return ToolResult(success=True, content="No worktrees.")

            lines = []
            for wt in worktrees:
                suffix = f" task={wt.task_id}" if wt.task_id else ""
                lines.append(
                    f"[{wt.status}] {wt.name} -> {wt.path} ({wt.branch}){suffix}"
                )
            return ToolResult(success=True, content="\n".join(lines))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WorktreeStatusTool(Tool):
    """Get git status for a worktree."""

    @property
    def name(self) -> str:
        return "worktree_status"

    @property
    def description(self) -> str:
        return """Show git status for a worktree.

Displays changed files, branch info, and commit status."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Worktree name"},
            },
            "required": ["name"],
        }

    async def execute(self, name: str) -> ToolResult:
        try:
            _, wm, _ = get_managers()
            if wm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            status = wm.status(name)
            return ToolResult(success=True, content=status)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WorktreeRunTool(Tool):
    """Run a command in a worktree."""

    @property
    def name(self) -> str:
        return "worktree_run"

    @property
    def description(self) -> str:
        return """Run a shell command in a worktree directory.

Use this to execute commands in the isolated worktree environment.
Commands are run with a 5-minute timeout."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Worktree name"},
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
            },
            "required": ["name", "command"],
        }

    async def execute(
        self,
        name: str,
        command: str,
        timeout: int = 300,
    ) -> ToolResult:
        try:
            _, wm, _ = get_managers()
            if wm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            output = wm.run(name, command, timeout)
            return ToolResult(success=True, content=output)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WorktreeKeepTool(Tool):
    """Mark a worktree as kept."""

    @property
    def name(self) -> str:
        return "worktree_keep"

    @property
    def description(self) -> str:
        return """Mark a worktree as kept in lifecycle state.

Use this to preserve a worktree without removing it.
Kept worktrees are tracked but not deleted."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Worktree name"},
            },
            "required": ["name"],
        }

    async def execute(self, name: str) -> ToolResult:
        try:
            _, wm, _ = get_managers()
            if wm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            worktree = wm.keep(name)
            return ToolResult(
                success=True,
                content=f"Kept worktree '{name}' at {worktree.path}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WorktreeRemoveTool(Tool):
    """Remove a worktree."""

    @property
    def name(self) -> str:
        return "worktree_remove"

    @property
    def description(self) -> str:
        return """Remove a worktree and optionally complete its bound task.

Use force=true to remove even with uncommitted changes.
Use complete_task=true to mark the bound task as completed."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Worktree name"},
                "force": {"type": "boolean", "description": "Force removal even with uncommitted changes"},
                "complete_task": {"type": "boolean", "description": "Mark bound task as completed"},
            },
            "required": ["name"],
        }

    async def execute(
        self,
        name: str,
        force: bool = False,
        complete_task: bool = False,
    ) -> ToolResult:
        try:
            _, wm, _ = get_managers()
            if wm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            result = wm.remove(name, force, complete_task)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WorktreeEventsTool(Tool):
    """List recent worktree lifecycle events."""

    @property
    def name(self) -> str:
        return "worktree_events"

    @property
    def description(self) -> str:
        return """List recent worktree and task lifecycle events.

Shows create, remove, keep, and complete events for observability."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max events to show (default: 20, max: 200)"},
            },
        }

    async def execute(self, limit: int = 20) -> ToolResult:
        try:
            _, _, eb = get_managers()
            if eb is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            events = eb.list_recent(limit)
            if not events:
                return ToolResult(success=True, content="No events.")

            import json
            return ToolResult(success=True, content=json.dumps(events, indent=2))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# =============================================================================
# Autonomous Agent Tools (s11 pattern)
# =============================================================================

class IdleTool(Tool):
    """Signal that agent has no more work and should enter idle state."""

    @property
    def name(self) -> str:
        return "idle"

    @property
    def description(self) -> str:
        return """Signal that you have no more work to do.

Use this tool when you have completed your current task and want to
enter the idle polling phase. While idle, the system will check for:
- New messages in your inbox
- Unclaimed tasks on the task board
- Background task completions

After 60 seconds of no new work, the agent will shut down gracefully.

This implements the s11 autonomous agent idle cycle pattern."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Optional reason for idling"},
            },
        }

    async def execute(self, reason: str = "") -> ToolResult:
        # This tool is handled specially by the agent loop
        # The result message signals the agent to enter idle phase
        msg = "Entering idle phase. Will poll for new tasks."
        if reason:
            msg = f"Entering idle phase: {reason}. Will poll for new tasks."
        return ToolResult(success=True, content=msg)


class ClaimTaskTool(Tool):
    """Claim a task from the task board."""

    @property
    def name(self) -> str:
        return "claim_task"

    @property
    def description(self) -> str:
        return """Claim an unclaimed task from the task board.

Use this to take ownership of a pending task that has no blockers.
Once claimed, the task status becomes 'in_progress' and you are
the owner.

This is the primary mechanism for autonomous agents to find work.
Claim the first available task that matches your capabilities."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to claim"},
                "owner": {"type": "string", "description": "Your name/identifier (optional)"},
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: int, owner: str = "") -> ToolResult:
        try:
            tm, _, _ = get_managers()
            if tm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            task = tm.update(task_id, status="in_progress", owner=owner)
            return ToolResult(
                success=True,
                content=f"Claimed task #{task.id}: {task.subject}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class TaskAddDependencyTool(Tool):
    """Add a dependency relationship between tasks."""

    @property
    def name(self) -> str:
        return "task_add_dependency"

    @property
    def description(self) -> str:
        return """Make one task depend on another.

The dependent task will be blocked until the blocking task is completed.
Use this to create task workflows and execution order."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task that is blocked (dependent)"},
                "blocked_by": {"type": "integer", "description": "Task that blocks it"},
            },
            "required": ["task_id", "blocked_by"],
        }

    async def execute(self, task_id: int, blocked_by: int) -> ToolResult:
        try:
            tm, _, _ = get_managers()
            if tm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            task = tm.add_dependency(task_id, blocked_by)
            return ToolResult(
                success=True,
                content=f"Task #{task_id} now depends on task #{blocked_by}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ListUnclaimedTasksTool(Tool):
    """List unclaimed tasks that are ready to work on."""

    @property
    def name(self) -> str:
        return "list_unclaimed_tasks"

    @property
    def description(self) -> str:
        return """List all unclaimed tasks with no blockers.

Shows pending tasks that:
- Have no owner
- Have no unmet dependencies
- Are ready to be claimed and worked on

Use this to find work as an autonomous agent."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self) -> ToolResult:
        try:
            tm, _, _ = get_managers()
            if tm is None:
                return ToolResult(success=False, error="Worktree system not initialized")

            tasks = tm.list_unclaimed()
            if not tasks:
                return ToolResult(success=True, content="No unclaimed tasks available.")

            lines = ["## Unclaimed Tasks (ready to work)", ""]
            for t in tasks:
                lines.append(f"  #{t.id}: {t.subject}")
                if t.description:
                    desc = t.description[:60] + "..." if len(t.description) > 60 else t.description
                    lines.append(f"      {desc}")

            return ToolResult(success=True, content="\n".join(lines))
        except Exception as e:
            return ToolResult(success=False, error=str(e))
