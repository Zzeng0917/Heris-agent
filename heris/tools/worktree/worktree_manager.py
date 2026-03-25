"""WorktreeManager - Git worktree isolation for parallel execution.

Implements s12 pattern: worktrees are the execution plane.
Tasks are coordinated by task ID, execution is isolated by directory.
"""

import json
import re
import subprocess
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from .eventbus import EventBus
from .task_manager import TaskManager


@dataclass
class Worktree:
    """Worktree data model."""

    name: str
    path: str
    branch: str
    task_id: Optional[int] = None
    status: str = "active"  # active, removed, kept
    created_at: float = field(default_factory=time.time)
    removed_at: Optional[float] = None
    kept_at: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Worktree":
        # Handle optional fields
        kwargs = {
            "name": data["name"],
            "path": data["path"],
            "branch": data["branch"],
        }
        if "task_id" in data and data["task_id"] is not None:
            kwargs["task_id"] = data["task_id"]
        if "status" in data:
            kwargs["status"] = data["status"]
        if "created_at" in data:
            kwargs["created_at"] = data["created_at"]
        if "removed_at" in data:
            kwargs["removed_at"] = data["removed_at"]
        if "kept_at" in data:
            kwargs["kept_at"] = data["kept_at"]
        return cls(**kwargs)


class WorktreeManager:
    """Git worktree manager for directory-level isolation.

    Manages parallel execution lanes using git worktrees.
    Each worktree is an isolated directory that shares git history
    but has its own working tree.
    """

    def __init__(
        self,
        repo_root: Path,
        tasks: TaskManager,
        events: EventBus,
        worktrees_dir: Optional[Path] = None,
    ):
        """Initialize WorktreeManager.

        Args:
            repo_root: Root of the git repository
            tasks: TaskManager instance for task bindings
            events: EventBus instance for lifecycle events
            worktrees_dir: Directory to store worktrees (default: .worktrees in repo_root)
        """
        self.repo_root = repo_root
        self.tasks = tasks
        self.events = events
        self.dir = worktrees_dir or (repo_root / ".worktrees")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.json"

        # Initialize index if not exists
        if not self.index_path.exists():
            self._save_index({"worktrees": []})

        self._git_available = self._check_git_available()

    def _check_git_available(self) -> bool:
        """Check if we're in a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _run_git(self, args: list[str], cwd: Optional[Path] = None) -> str:
        """Run a git command.

        Args:
            args: Git command arguments
            cwd: Working directory (default: repo_root)

        Returns:
            Command output

        Raises:
            RuntimeError: If git command fails
        """
        if not self._git_available:
            raise RuntimeError("Not in a git repository. Worktree tools require git.")

        cmd = ["git", *args]
        result = subprocess.run(
            cmd,
            cwd=cwd or self.repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            msg = (result.stdout + result.stderr).strip()
            raise RuntimeError(msg or f"git {' '.join(args)} failed")

        return (result.stdout + result.stderr).strip() or "(no output)"

    def _load_index(self) -> dict:
        """Load worktree index."""
        return json.loads(self.index_path.read_text())

    def _save_index(self, data: dict) -> None:
        """Save worktree index."""
        self.index_path.write_text(json.dumps(data, indent=2))

    def _find(self, name: str) -> Optional[Worktree]:
        """Find a worktree by name."""
        idx = self._load_index()
        for wt_data in idx.get("worktrees", []):
            if wt_data.get("name") == name:
                return Worktree.from_dict(wt_data)
        return None

    def _validate_name(self, name: str) -> None:
        """Validate worktree name.

        Args:
            name: Name to validate

        Raises:
            ValueError: If name is invalid
        """
        if not name or not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", name):
            raise ValueError(
                "Invalid worktree name. Use 1-40 chars: letters, numbers, ., _, -"
            )

    def create(
        self,
        name: str,
        task_id: Optional[int] = None,
        base_ref: str = "HEAD",
    ) -> Worktree:
        """Create a new git worktree.

        Args:
            name: Worktree name
            task_id: Optional task ID to bind
            base_ref: Base git ref (default: HEAD)

        Returns:
            Created Worktree object

        Raises:
            ValueError: If name is invalid or worktree exists
            RuntimeError: If git command fails
        """
        self._validate_name(name)

        if self._find(name):
            raise ValueError(f"Worktree '{name}' already exists in index")

        if task_id is not None and not self.tasks.exists(task_id):
            raise ValueError(f"Task {task_id} not found")

        wt_path = self.dir / name
        branch = f"wt/{name}"

        # Emit before event
        self.events.emit(
            "worktree.create.before",
            task={"id": task_id} if task_id else None,
            worktree={"name": name, "base_ref": base_ref},
        )

        try:
            # Create git worktree
            self._run_git(["worktree", "add", "-b", branch, str(wt_path), base_ref])

            # Create worktree entry
            worktree = Worktree(
                name=name,
                path=str(wt_path),
                branch=branch,
                task_id=task_id,
                status="active",
            )

            # Update index
            idx = self._load_index()
            idx["worktrees"].append(worktree.to_dict())
            self._save_index(idx)

            # Bind to task if specified
            if task_id is not None:
                self.tasks.bind_worktree(task_id, name)

            # Emit after event
            self.events.emit(
                "worktree.create.after",
                task={"id": task_id} if task_id else None,
                worktree=worktree.to_dict(),
            )

            return worktree

        except Exception as e:
            self.events.emit(
                "worktree.create.failed",
                task={"id": task_id} if task_id else None,
                worktree={"name": name, "base_ref": base_ref},
                error=str(e),
            )
            raise

    def list_all(self) -> list[Worktree]:
        """Get all worktrees."""
        idx = self._load_index()
        return [Worktree.from_dict(wt) for wt in idx.get("worktrees", [])]

    def list_active(self) -> list[Worktree]:
        """Get active worktrees."""
        return [wt for wt in self.list_all() if wt.status == "active"]

    def status(self, name: str) -> str:
        """Get git status for a worktree.

        Args:
            name: Worktree name

        Returns:
            Git status output
        """
        worktree = self._find(name)
        if not worktree:
            raise ValueError(f"Unknown worktree '{name}'")

        wt_path = Path(worktree.path)
        if not wt_path.exists():
            raise ValueError(f"Worktree path missing: {wt_path}")

        try:
            result = subprocess.run(
                ["git", "status", "--short", "--branch"],
                cwd=wt_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            text = (result.stdout + result.stderr).strip()
            return text or "Clean worktree"
        except Exception as e:
            return f"Error checking status: {e}"

    def run(self, name: str, command: str, timeout: int = 300) -> str:
        """Run a command in a worktree.

        Args:
            name: Worktree name
            command: Shell command to run
            timeout: Timeout in seconds

        Returns:
            Command output
        """
        # Security check
        dangerous = ["rm -rf /", "sudo ", "shutdown", "reboot", "> /dev/"]
        if any(d in command for d in dangerous):
            return "Error: Dangerous command blocked"

        worktree = self._find(name)
        if not worktree:
            raise ValueError(f"Unknown worktree '{name}'")

        wt_path = Path(worktree.path)
        if not wt_path.exists():
            raise ValueError(f"Worktree path missing: {wt_path}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=wt_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (result.stdout + result.stderr).strip()
            return output[:50000] if output else "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: Timeout ({timeout}s)"
        except Exception as e:
            return f"Error: {e}"

    def remove(
        self,
        name: str,
        force: bool = False,
        complete_task: bool = False,
    ) -> str:
        """Remove a worktree.

        Args:
            name: Worktree name
            force: Force removal even with uncommitted changes
            complete_task: Mark bound task as completed

        Returns:
            Status message
        """
        worktree = self._find(name)
        if not worktree:
            raise ValueError(f"Unknown worktree '{name}'")

        # Emit before event
        self.events.emit(
            "worktree.remove.before",
            task={"id": worktree.task_id} if worktree.task_id else None,
            worktree={"name": name, "path": worktree.path},
        )

        try:
            # Remove git worktree
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(worktree.path)
            self._run_git(args)

            # Complete task if requested
            if complete_task and worktree.task_id is not None:
                task_id = worktree.task_id
                self.tasks.update(task_id, status="completed")
                self.tasks.unbind_worktree(task_id)

                self.events.emit(
                    "task.completed",
                    task={"id": task_id, "status": "completed"},
                    worktree={"name": name},
                )

            # Update index
            idx = self._load_index()
            for item in idx.get("worktrees", []):
                if item.get("name") == name:
                    item["status"] = "removed"
                    item["removed_at"] = time.time()
            self._save_index(idx)

            # Emit after event
            self.events.emit(
                "worktree.remove.after",
                task={"id": worktree.task_id} if worktree.task_id else None,
                worktree={"name": name, "path": worktree.path, "status": "removed"},
            )

            return f"Removed worktree '{name}'"

        except Exception as e:
            self.events.emit(
                "worktree.remove.failed",
                task={"id": worktree.task_id} if worktree.task_id else None,
                worktree={"name": name, "path": worktree.path},
                error=str(e),
            )
            raise

    def keep(self, name: str) -> Worktree:
        """Mark a worktree as kept (preserve without removing).

        Args:
            name: Worktree name

        Returns:
            Updated Worktree object
        """
        worktree = self._find(name)
        if not worktree:
            raise ValueError(f"Unknown worktree '{name}'")

        # Update index
        idx = self._load_index()
        for item in idx.get("worktrees", []):
            if item.get("name") == name:
                item["status"] = "kept"
                item["kept_at"] = time.time()
                worktree = Worktree.from_dict(item)
        self._save_index(idx)

        # Emit event
        self.events.emit(
            "worktree.keep",
            task={"id": worktree.task_id} if worktree.task_id else None,
            worktree={"name": name, "path": worktree.path, "status": "kept"},
        )

        return worktree

    def get_for_task(self, task_id: int) -> Optional[Worktree]:
        """Get the worktree bound to a task.

        Args:
            task_id: Task ID

        Returns:
            Worktree if found, None otherwise
        """
        for wt in self.list_all():
            if wt.task_id == task_id:
                return wt
        return None

    def is_git_available(self) -> bool:
        """Check if git is available."""
        return self._git_available
