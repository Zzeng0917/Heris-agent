"""MCP Invoke Tool - Invoke tools exposed by MCP servers.

This tool invokes tools exposed by MCP (Model Context Protocol) servers.
MCP tools are functions that can perform actions, process data, or interact
with external systems.
"""

from typing import Any

from ...base import Tool, ToolResult
from .prompt import DESCRIPTION, TOOL_NAME


class MCPInvokeTool(Tool):
    """Tool for calling MCP (Model Context Protocol) tools.

    MCP tools are functions exposed by MCP servers that can perform actions,
    process data, or interact with external systems. This tool invokes those
    functions with the specified arguments.

    Example usage:
    - Call a file system tool to read/write files
    - Invoke database operations
    - Execute commands on remote systems
    - Process data through specialized MCP tools
    """

    def __init__(self, mcp_client=None):
        """Initialize MCPInvokeTool.

        Args:
            mcp_client: MCP client instance for making tool calls
        """
        super().__init__()
        self._mcp_client = mcp_client

    @property
    def name(self) -> str:
        return TOOL_NAME

    @property
    def description(self) -> str:
        return DESCRIPTION

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "The name of the MCP tool to invoke, as defined by the MCP server (e.g., 'read_file', 'query_database').",
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments to pass to the MCP tool. Must match the tool's expected parameter schema.",
                },
                "server_name": {
                    "type": "string",
                    "description": "Optional name of the MCP server that exposes this tool. Required if multiple servers have tools with the same name.",
                },
            },
            "required": ["tool_name"],
        }

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        server_name: str | None = None,
    ) -> ToolResult:
        """Call an MCP tool with the specified arguments.

        Args:
            tool_name: Name of the MCP tool to invoke
            arguments: Arguments to pass to the tool
            server_name: Optional specific server to use

        Returns:
            ToolResult with tool output or error
        """
        try:
            if self._mcp_client is None:
                return ToolResult(
                    success=False,
                    content="",
                    error="MCP client not initialized",
                )

            # Execute the MCP tool call
            result = await self._mcp_client.call_tool(
                tool_name=tool_name,
                arguments=arguments or {},
                server_name=server_name,
            )

            # Extract content from the result
            content_items = result.get("content", [])
            if not content_items:
                return ToolResult(
                    success=True,
                    content="Tool executed successfully (no output)",
                )

            # Format the output
            output_parts = []
            for item in content_items:
                item_type = item.get("type", "text")
                if item_type == "text":
                    output_parts.append(item.get("text", ""))
                elif item_type == "image":
                    output_parts.append("[Image content]")
                elif item_type == "resource":
                    resource = item.get("resource", {})
                    output_parts.append(f"[Resource: {resource.get('uri', 'unknown')}]")
                else:
                    output_parts.append(str(item))

            content = "\n".join(output_parts)

            # Check for errors in the result
            is_error = result.get("isError", False)
            if is_error:
                return ToolResult(
                    success=False,
                    content=content,
                    error=f"MCP tool '{tool_name}' returned an error",
                )

            return ToolResult(success=True, content=content)

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to call MCP tool '{tool_name}': {str(e)}",
            )
