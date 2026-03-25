"""EventBus - Append-only lifecycle events for observability.

Implements s12 pattern: events are emitted during worktree/task lifecycle
for monitoring and debugging.
"""

import json
import time
from pathlib import Path
from typing import Any
from threading import Lock


class EventBus:
    """Event bus for worktree and task lifecycle events.

    Events are stored in append-only JSONL format for durability
    and easy log analysis.
    """

    def __init__(self, event_log_path: Path):
        """Initialize EventBus.

        Args:
            event_log_path: Path to the JSONL event log file
        """
        self.path = event_log_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

        # Initialize file if not exists
        if not self.path.exists():
            self.path.write_text("")

    def emit(
        self,
        event: str,
        task: dict | None = None,
        worktree: dict | None = None,
        error: str | None = None,
        **extra: Any,
    ) -> None:
        """Emit a lifecycle event.

        Args:
            event: Event type/name (e.g., "worktree.create.before")
            task: Optional task data dict
            worktree: Optional worktree data dict
            error: Optional error message
            **extra: Additional event data
        """
        payload = {
            "event": event,
            "ts": time.time(),
            "task": task or {},
            "worktree": worktree or {},
        }

        if error:
            payload["error"] = error

        if extra:
            payload.update(extra)

        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def list_recent(self, limit: int = 20) -> list[dict]:
        """Get recent events from the log.

        Args:
            limit: Maximum number of events to return (1-200)

        Returns:
            List of event dictionaries, newest last
        """
        n = max(1, min(int(limit), 200))

        with self._lock:
            if not self.path.exists():
                return []

            lines = self.path.read_text(encoding="utf-8").splitlines()

        recent = lines[-n:] if lines else []
        items = []

        for line in recent:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                items.append({"event": "parse_error", "raw": line})

        return items

    def clear(self) -> None:
        """Clear all events (use with caution)."""
        with self._lock:
            self.path.write_text("")
