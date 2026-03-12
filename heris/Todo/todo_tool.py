"""Todo Tool - Integrates TodoManager with Heris Agent."""

from typing import Literal

from ..tools.base import Tool, ToolResult
from .todomanager import TodoManager


class TodoTool(Tool):
    """Tool for managing todo items."""

    name = "todo"
    description = "Manage todo items: add, remove, update status, or view list"

    # Define the JSON schema for the tool parameters
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "remove", "status", "list", "clear", "assign", "ready", "by_owner"],
                "description": "Action to perform on todos"
            },
            "text": {
                "type": "string",
                "description": "Text for the todo item (required for add)"
            },
            "item_id": {
                "type": "integer",
                "description": "ID of the todo item (required for remove/status/assign)"
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "done"],
                "description": "Status to set (for status action)"
            },
            "owner": {
                "type": "string",
                "description": "Agent name to assign task to (for add/assign actions)"
            },
            "parent_id": {
                "type": "integer",
                "description": "Parent task ID for subtasks (optional for add)"
            },
            "dependencies": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of task IDs this task depends on (optional for add)"
            }
        },
        "required": ["action"]
    }

    def __init__(self, todo_manager: TodoManager):
        """Initialize with TodoManager instance.

        Args:
            todo_manager: The TodoManager to use
        """
        super().__init__()
        self.todo_manager = todo_manager

    async def execute(self, action: str, text: str = "", item_id: int = 0,
                      status: Literal["pending", "in_progress", "done"] = "pending",
                      owner: str = None, parent_id: int = None, dependencies: list = None) -> ToolResult:
        """Execute todo action.

        Args:
            action: Action to perform (add, remove, status, list, clear, assign, ready, by_owner)
            text: Text for new todo item
            item_id: ID of item to modify
            status: Status to set
            owner: Agent name for assignment
            parent_id: Parent task ID for subtasks
            dependencies: List of task IDs this task depends on

        Returns:
            ToolResult with rendered todo list or query result
        """
        try:
            if action == "add":
                if not text:
                    return ToolResult(success=False, error="Text is required for add action")
                result = self.todo_manager.add(text, status, owner, parent_id, dependencies)
                return ToolResult(success=True, content=result)

            elif action == "remove":
                if not item_id:
                    return ToolResult(success=False, error="item_id is required for remove action")
                result = self.todo_manager.remove(item_id)
                return ToolResult(success=True, content=result)

            elif action == "status":
                if not item_id:
                    return ToolResult(success=False, error="item_id is required for status action")
                result = self.todo_manager.set_status(item_id, status)
                return ToolResult(success=True, content=result)

            elif action == "list":
                result = self.todo_manager.render()
                return ToolResult(success=True, content=result)

            elif action == "clear":
                result = self.todo_manager.clear()
                return ToolResult(success=True, content=result)

            elif action == "assign":
                if not item_id:
                    return ToolResult(success=False, error="item_id is required for assign action")
                if not owner:
                    return ToolResult(success=False, error="owner is required for assign action")
                result = self.todo_manager.assign(item_id, owner)
                return ToolResult(success=True, content=result)

            elif action == "ready":
                tasks = self.todo_manager.get_ready_tasks()
                if not tasks:
                    return ToolResult(success=True, content="No ready tasks.")
                lines = ["## Ready Tasks (dependencies met)", ""]
                for task in tasks:
                    lines.append(f"{task['id']}. {task['text']}")
                return ToolResult(success=True, content="\n".join(lines))

            elif action == "by_owner":
                if not owner:
                    return ToolResult(success=False, error="owner is required for by_owner action")
                tasks = self.todo_manager.get_by_owner(owner)
                if not tasks:
                    return ToolResult(success=True, content=f"No tasks assigned to {owner}.")
                lines = [f"## Tasks for @{owner}", ""]
                for task in tasks:
                    icon = {"pending": "[ ]", "in_progress": "[→]", "done": "[✓]"}.get(task["status"], "[ ]")
                    lines.append(f"{task['id']}. {icon} {task['text']}")
                return ToolResult(success=True, content="\n".join(lines))

            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")

        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Todo operation failed: {e}")
