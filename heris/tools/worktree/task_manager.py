"""TaskManager - Persistent task board with optional worktree binding.

Implements s12 pattern: tasks are the control plane.
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from threading import Lock


@dataclass
class Task:
    """Task data model."""

    id: int
    subject: str
    description: str = ""
    status: str = "pending"  # pending, in_progress, completed
    owner: str = ""  # Agent name or empty
    worktree: str = ""  # Worktree name or empty
    blockedBy: list[int] = field(default_factory=list)
    blocks: list[int] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(**data)


class TaskManager:
    """Persistent task board manager.

    Tasks are stored as individual JSON files in the tasks directory.
    Each task can be bound to a worktree for isolated execution.
    """

    def __init__(self, tasks_dir: Path):
        """Initialize TaskManager.

        Args:
            tasks_dir: Directory to store task JSON files
        """
        self.dir = tasks_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._next_id = self._max_id() + 1

    def _max_id(self) -> int:
        """Find the maximum existing task ID."""
        ids = []
        for f in self.dir.glob("task_*.json"):
            try:
                ids.append(int(f.stem.split("_")[1]))
            except (ValueError, IndexError):
                pass
        return max(ids) if ids else 0

    def _path(self, task_id: int) -> Path:
        """Get file path for a task."""
        return self.dir / f"task_{task_id}.json"

    def _load(self, task_id: int) -> Task:
        """Load a task by ID."""
        path = self._path(task_id)
        if not path.exists():
            raise ValueError(f"Task {task_id} not found")
        return Task.from_dict(json.loads(path.read_text()))

    def _save(self, task: Task) -> None:
        """Save a task to file."""
        task.updated_at = time.time()
        self._path(task.id).write_text(json.dumps(task.to_dict(), indent=2))

    def create(self, subject: str, description: str = "") -> Task:
        """Create a new task.

        Args:
            subject: Task title/subject
            description: Detailed description

        Returns:
            The created Task object
        """
        with self._lock:
            task = Task(
                id=self._next_id,
                subject=subject,
                description=description,
            )
            self._save(task)
            self._next_id += 1
            return task

    def get(self, task_id: int) -> Task:
        """Get a task by ID."""
        return self._load(task_id)

    def exists(self, task_id: int) -> bool:
        """Check if a task exists."""
        return self._path(task_id).exists()

    def update(
        self,
        task_id: int,
        status: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> Task:
        """Update task status and/or owner.

        Args:
            task_id: Task ID to update
            status: New status (pending, in_progress, completed)
            owner: New owner (or "" to clear)

        Returns:
            Updated Task object
        """
        with self._lock:
            task = self._load(task_id)

            if status is not None:
                if status not in ("pending", "in_progress", "completed"):
                    raise ValueError(f"Invalid status: {status}")
                task.status = status

                # Auto-unblock dependent tasks when completing
                if status == "completed":
                    self._unblock_dependents(task_id)

            if owner is not None:
                task.owner = owner

            self._save(task)
            return task

    def _unblock_dependents(self, completed_task_id: int) -> None:
        """Remove completed task from blockedBy lists of other tasks."""
        for f in self.dir.glob("task_*.json"):
            try:
                task = Task.from_dict(json.loads(f.read_text()))
                if completed_task_id in task.blockedBy:
                    task.blockedBy.remove(completed_task_id)
                    self._save(task)
            except Exception:
                pass

    def bind_worktree(self, task_id: int, worktree: str, owner: str = "") -> Task:
        """Bind a task to a worktree.

        Args:
            task_id: Task ID
            worktree: Worktree name
            owner: Optional owner to set

        Returns:
            Updated Task object
        """
        with self._lock:
            task = self._load(task_id)
            task.worktree = worktree
            if owner:
                task.owner = owner
            if task.status == "pending":
                task.status = "in_progress"
            self._save(task)
            return task

    def unbind_worktree(self, task_id: int) -> Task:
        """Unbind a task from its worktree.

        Args:
            task_id: Task ID

        Returns:
            Updated Task object
        """
        with self._lock:
            task = self._load(task_id)
            task.worktree = ""
            self._save(task)
            return task

    def add_dependency(self, task_id: int, blocked_by: int) -> Task:
        """Add a dependency relationship.

        Args:
            task_id: The task that is blocked
            blocked_by: The task that blocks it

        Returns:
            Updated Task object
        """
        with self._lock:
            task = self._load(task_id)
            if blocked_by not in task.blockedBy:
                task.blockedBy.append(blocked_by)
            self._save(task)

            # Update the blocking task's blocks list
            try:
                blocker = self._load(blocked_by)
                if task_id not in blocker.blocks:
                    blocker.blocks.append(task_id)
                self._save(blocker)
            except ValueError:
                pass  # Blocking task doesn't exist

            return task

    def list_all(self) -> list[Task]:
        """Get all tasks."""
        tasks = []
        for f in sorted(self.dir.glob("task_*.json")):
            try:
                tasks.append(Task.from_dict(json.loads(f.read_text())))
            except Exception:
                pass
        return tasks

    def list_unclaimed(self) -> list[Task]:
        """Get unclaimed tasks with no blockers."""
        unclaimed = []
        for task in self.list_all():
            if (
                task.status == "pending"
                and not task.owner
                and not task.blockedBy
            ):
                unclaimed.append(task)
        return unclaimed

    def delete(self, task_id: int) -> bool:
        """Delete a task.

        Args:
            task_id: Task ID to delete

        Returns:
            True if deleted, False if not found
        """
        path = self._path(task_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def render_list(self) -> str:
        """Render task list as formatted string."""
        tasks = self.list_all()
        if not tasks:
            return "No tasks."

        lines = []
        for t in tasks:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }.get(t.status, "[?]")
            owner = f" @{t.owner}" if t.owner else ""
            wt = f" wt={t.worktree}" if t.worktree else ""
            blocked = f" (blocked by: {t.blockedBy})" if t.blockedBy else ""
            lines.append(f"{marker} #{t.id}: {t.subject}{owner}{wt}{blocked}")

        return "\n".join(lines)
