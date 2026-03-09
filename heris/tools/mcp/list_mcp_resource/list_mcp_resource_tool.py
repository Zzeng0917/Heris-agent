"""List MCP Resources Tool.

This tool lists available resources from an MCP (Model Context Protocol) server.
Resources are data sources that can be accessed via the MCP protocol.
"""

from typing import Any

from ...base import Tool, ToolResult
from .prompt import DESCRIPTION, TOOL_NAME


class ListMCPResourceTool(Tool):
    """Tool for listing available MCP resources.

    MCP resources are data sources that expose content via URIs.
    This tool queries an MCP server to discover what resources are available,
    including their names, URIs, and MIME types.

    Example usage:
    - List resources from a connected MCP server
    - Discover available data sources before reading
    - Browse resource hierarchies
    """

    def __init__(self, mcp_client=None):
        """Initialize ListMCPResourceTool.

        Args:
            mcp_client: MCP client instance for making requests
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
                "server_name": {
                    "type": "string",
                    "description": "Optional name of a specific MCP server to query. If not provided, lists resources from all connected servers.",
                },
                "cursor": {
                    "type": "string",
                    "description": "Optional pagination cursor for retrieving additional results from previous list_mcp_resources calls.",
                },
            },
        }

    async def execute(
        self,
        server_name: str | None = None,
        cursor: str | None = None,
    ) -> ToolResult:
        """List available MCP resources.

        Args:
            server_name: Optional specific server to query
            cursor: Optional pagination cursor

        Returns:
            ToolResult with list of resources or error
        """
        try:
            if self._mcp_client is None:
                return ToolResult(
                    success=False,
                    content="",
                    error="MCP client not initialized",
                )

            # List resources from MCP client
            result = await self._mcp_client.list_resources(
                server_name=server_name,
                cursor=cursor,
            )

            if not result.get("resources"):
                message = "No MCP resources available"
                if server_name:
                    message += f" from server '{server_name}'"
                return ToolResult(success=True, content=message)

            # Format resources for display
            resources = result["resources"]
            formatted = []

            for resource in resources:
                name = resource.get("name", "Unnamed")
                uri = resource.get("uri", "")
                mime_type = resource.get("mimeType", "unknown")
                description = resource.get("description", "")

                formatted.append(
                    f"- {name}\n  URI: {uri}\n  Type: {mime_type}"
                    + (f"\n  Description: {description}" if description else "")
                )

            header = f"Available MCP Resources ({len(resources)} total):\n\n"
            content = header + "\n\n".join(formatted)

            # Add pagination info if present
            next_cursor = result.get("nextCursor")
            if next_cursor:
                content += f"\n\n[More resources available. Use cursor='{next_cursor}' to see more.]"

            return ToolResult(success=True, content=content)

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to list MCP resources: {str(e)}",
            )
