"""Write file tool."""

from pathlib import Path
from typing import Any

from ..base import Tool, ToolResult


class WriteTool(Tool):
    """Write content to a file."""

    def __init__(self, workspace_dir: str = "."):
        """Initialize WriteTool with workspace directory.

        Args:
            workspace_dir: Base directory for resolving relative paths
        """
        super().__init__()  # Initialize schema cache
        self.workspace_dir = Path(workspace_dir).resolve()

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. Will overwrite existing files completely. "
            "For existing files, you should read the file first using read_file. "
            "Prefer editing existing files over creating new ones unless explicitly needed."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "content": {
                    "type": "string",
                    "description": "Complete content to write (will replace existing content)",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str) -> ToolResult:
        """Execute write file."""
        try:
            # 防止目录遍历攻击
            if ".." in Path(path).parts:
                return ToolResult(success=False, content="", error=f"Path {path} traversal not allowed")

            # 基础路径拼接
            target = self.workspace_dir / path

            # 展开所有 .. 和 符号链接
            target = target.resolve()

            # 确保最终路径在沙箱内
            try:
                target.relative_to(self.workspace_dir)
            except ValueError:
                return ToolResult(success=False, content="", error=f"Path {path} is not within the workspace directory")

            #写入
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolResult(success=True, content=f"Successfully wrote to {target}")

        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))
