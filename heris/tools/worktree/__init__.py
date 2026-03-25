"""Worktree isolation system for parallel task execution.

Implements s12 pattern: tasks are the control plane, worktrees are the execution plane.
"""

from .eventbus import EventBus
from .task_manager import TaskManager, Task
from .worktree_manager import WorktreeManager
from .tools import (
    init_worktree_system,
    TaskCreateTool,
    TaskListTool,
    TaskGetTool,
    TaskUpdateTool,
    TaskBindWorktreeTool,
    # Autonomous agent tools
    IdleTool,
    ClaimTaskTool,
    TaskAddDependencyTool,
    ListUnclaimedTasksTool,
    WorktreeCreateTool,
    WorktreeListTool,
    WorktreeStatusTool,
    WorktreeRunTool,
    WorktreeKeepTool,
    WorktreeRemoveTool,
    WorktreeEventsTool,
)

__all__ = [
    "EventBus",
    "TaskManager",
    "Task",
    "WorktreeManager",
    # Initialization
    "init_worktree_system",
    # Task Tools
    "TaskCreateTool",
    "TaskListTool",
    "TaskGetTool",
    "TaskUpdateTool",
    "TaskBindWorktreeTool",
    # Autonomous Agent Tools
    "IdleTool",
    "ClaimTaskTool",
    "TaskAddDependencyTool",
    "ListUnclaimedTasksTool",
    # Worktree Tools
    "WorktreeCreateTool",
    "WorktreeListTool",
    "WorktreeStatusTool",
    "WorktreeRunTool",
    "WorktreeKeepTool",
    "WorktreeRemoveTool",
    "WorktreeEventsTool",
]
