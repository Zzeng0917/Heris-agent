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
                "enum": ["add", "remove", "status", "list", "clear"],
                "description": "Action to perform on todos"
            },
            "text": {
                "type": "string",
                "description": "Text for the todo item (required for add)"
            },
            "item_id": {
                "type": "integer",
                "description": "ID of the todo item (required for remove/status)"
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "done"],
                "description": "Status to set (for status action)"
            }
        },
        "required": ["action"]
    }

    def __init__(self, todo_manager: TodoManager):
        """Initialize with TodoManager instance.

        Args:
            todo_manager: The TodoManager to use
        """
        self.todo_manager = todo_manager

    async def execute(self, action: str, text: str = "", item_id: int = 0,
                      status: Literal["pending", "in_progress", "done"] = "pending") -> ToolResult:
        """Execute todo action.

        Args:
            action: Action to perform (add, remove, status, list, clear)
            text: Text for new todo item
            item_id: ID of item to modify
            status: Status to set

        Returns:
            ToolResult with rendered todo list
        """
        try:
            if action == "add":
                if not text:
                    return ToolResult(success=False, error="Text is required for add action")
                result = self.todo_manager.add(text, status)
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

            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")

        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Todo operation failed: {e}")
