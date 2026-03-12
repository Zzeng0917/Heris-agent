"""Todo Manager - Task management for Heris Agent."""

from typing import Literal


class TodoManager:
    """Manages todo items with status tracking and reminder functionality.

    Supports collaboration features:
    - owner: task assignment to specific agents
    - parent_id: subtask grouping
    - dependencies: task dependency tracking
    """

    def __init__(self):
        self.items: list[dict] = []
        self._last_call_round: int = 0
        self._current_round: int = 0

    def update(self, items: list[dict]) -> str:
        """Update all todo items.

        Args:
            items: List of todo items with id, text, and optional fields

        Returns:
            Rendered todo list as string
        """
        validated = []

        for item in items:
            validated.append({
                "id": item.get("id", len(validated) + 1),
                "text": item["text"],
                "status": item.get("status", "pending"),
                "owner": item.get("owner"),
                "parent_id": item.get("parent_id"),
                "dependencies": item.get("dependencies", [])
            })

        self.items = validated
        return self.render()

    def add(self, text: str, status: Literal["pending", "in_progress", "done"] = "pending",
            owner: str = None, parent_id: int = None, dependencies: list[int] = None) -> str:
        """Add a new todo item.

        Args:
            text: Todo item text
            status: Item status (pending, in_progress, done)
            owner: Agent assigned to this task
            parent_id: Parent task ID for subtasks
            dependencies: List of task IDs this task depends on

        Returns:
            Rendered todo list as string
        """
        new_item = {
            "id": len(self.items) + 1,
            "text": text,
            "status": status,
            "owner": owner,
            "parent_id": parent_id,
            "dependencies": dependencies or []
        }
        self.items.append(new_item)
        return self.render()

    def remove(self, item_id: int) -> str:
        """Remove a todo item by id.

        Args:
            item_id: ID of the item to remove

        Returns:
            Rendered todo list as string
        """
        self.items = [item for item in self.items if item["id"] != item_id]
        # Reassign IDs and update parent_id references
        for i, item in enumerate(self.items, 1):
            item["id"] = i
        return self.render()

    def set_status(self, item_id: int, status: Literal["pending", "in_progress", "done"]) -> str:
        """Set status of a todo item.

        Args:
            item_id: ID of the item to update
            status: New status

        Returns:
            Rendered todo list as string
        """
        for item in self.items:
            if item["id"] == item_id:
                item["status"] = status
                break

        return self.render()

    def assign(self, item_id: int, owner: str) -> str:
        """Assign a task to an owner.

        Args:
            item_id: ID of the item to assign
            owner: Agent name to assign to

        Returns:
            Rendered todo list as string
        """
        for item in self.items:
            if item["id"] == item_id:
                item["owner"] = owner
                break
        return self.render()

    def get_ready_tasks(self) -> list[dict]:
        """Get tasks that are ready to be worked on.

        A task is ready if:
        - Status is pending
        - All dependencies are done

        Returns:
            List of ready tasks
        """
        done_ids = {item["id"] for item in self.items if item["status"] == "done"}
        ready = []
        for item in self.items:
            if item["status"] != "pending":
                continue
            deps = item.get("dependencies", [])
            if all(dep in done_ids for dep in deps):
                ready.append(item)
        return ready

    def get_by_owner(self, owner: str) -> list[dict]:
        """Get tasks assigned to a specific owner.

        Args:
            owner: Agent name

        Returns:
            List of tasks for that owner
        """
        return [item for item in self.items if item.get("owner") == owner]

    def get_subtasks(self, parent_id: int) -> list[dict]:
        """Get subtasks of a parent task.

        Args:
            parent_id: Parent task ID

        Returns:
            List of subtasks
        """
        return [item for item in self.items if item.get("parent_id") == parent_id]

    def clear(self) -> str:
        """Clear all todo items.

        Returns:
            Confirmation message
        """
        self.items = []
        return "All todos cleared."

    def render(self) -> str:
        """Render todo list as formatted string.

        Returns:
            Formatted todo list with collaboration info
        """
        if not self.items:
            return "No todos yet."

        lines = ["## Todo List", ""]

        # Group by parent task (top-level first)
        top_level = [item for item in self.items if item.get("parent_id") is None]

        for item in top_level:
            lines.append(self._format_item(item))
            # Show subtasks indented
            subtasks = self.get_subtasks(item["id"])
            for sub in subtasks:
                lines.append("  " + self._format_item(sub))

        return "\n".join(lines)

    def _format_item(self, item: dict) -> str:
        """Format a single todo item for display.

        Args:
            item: Todo item dict

        Returns:
            Formatted string
        """
        status_icon = {
            "pending": "[ ]",
            "in_progress": "[→]",
            "done": "[✓]"
        }.get(item["status"], "[ ]")

        parts = [f"{item['id']}. {status_icon} {item['text']}"]

        # Add owner if assigned
        if item.get("owner"):
            parts.append(f"[@{item['owner']}]")

        # Add dependencies if any
        if item.get("dependencies"):
            deps = ",".join(str(d) for d in item["dependencies"])
            parts.append(f"(dep: {deps})")

        return " ".join(parts)

    def to_list(self) -> list[dict]:
        """Get items as list.

        Returns:
            List of todo items
        """
        return self.items.copy()

    def mark_called(self, round_num: int):
        """Mark that todo was called in current round.

        Args:
            round_num: Current conversation round number
        """
        self._last_call_round = round_num

    def should_remind(self, current_round: int) -> bool:
        """Check if reminder should be shown.

        Args:
            current_round: Current conversation round number

        Returns:
            True if reminder should be shown
        """
        rounds_since = current_round - self._last_call_round
        return rounds_since >= 3
