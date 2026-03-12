"""Todo Manager - Task management for Heris Agent."""

from typing import Literal


class TodoManager:
    """Manages todo items with status tracking and reminder functionality."""

    def __init__(self):
        self.items: list[dict] = []
        self._last_call_round: int = 0
        self._current_round: int = 0

    def update(self, items: list[dict]) -> str:
        """Update all todo items.

        Args:
            items: List of todo items with id, text, and optional status

        Returns:
            Rendered todo list as string
        """
        validated = []
        in_progress_count = 0

        for item in items:
            status = item.get("status", "pending")
            if status == "in_progress":
                in_progress_count += 1
            validated.append({
                "id": item.get("id", len(validated) + 1),
                "text": item["text"],
                "status": status
            })
            if in_progress_count > 1:
                raise ValueError("Only one task can be in progress at a time")

        self.items = validated
        return self.render()

    def add(self, text: str, status: Literal["pending", "in_progress", "done"] = "pending") -> str:
        """Add a new todo item.

        Args:
            text: Todo item text
            status: Item status (pending, in_progress, done)

        Returns:
            Rendered todo list as string
        """
        if status == "in_progress":
            # Ensure only one in_progress
            for item in self.items:
                if item["status"] == "in_progress":
                    item["status"] = "pending"

        new_item = {
            "id": len(self.items) + 1,
            "text": text,
            "status": status
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
        # Reassign IDs
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
        if status == "in_progress":
            # Ensure only one in_progress
            for item in self.items:
                if item["status"] == "in_progress":
                    item["status"] = "pending"

        for item in self.items:
            if item["id"] == item_id:
                item["status"] = status
                break

        return self.render()

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
            Formatted todo list
        """
        if not self.items:
            return "No todos yet."

        lines = ["## Todo List", ""]
        for item in self.items:
            status_icon = {
                "pending": "[ ]",
                "in_progress": "[→]",
                "done": "[✓]"
            }.get(item["status"], "[ ]")

            lines.append(f"{item['id']}. {status_icon} {item['text']}")

        return "\n".join(lines)

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
