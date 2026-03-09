"""Read MCP Resource Tool.

This tool reads content from resources exposed by MCP (Model Context Protocol) servers.
Resources are data sources identified by URIs that can be accessed and read via the MCP protocol.
"""

from typing import Any

from ...base import Tool, ToolResult
from .prompt import DESCRIPTION, TOOL_NAME


class ReadMCPResourceTool(Tool):
    """Tool for reading MCP resources.

    MCP resources are data sources identified by URIs. This tool reads the
    content of a resource given its URI. Resources can include files,
    database contents, API responses, or other structured data.

    Example usage:
    - Read a file from a filesystem MCP server
    - Fetch database schema information
    - Retrieve API documentation
    - Access configuration files
    """

    def __init__(self, mcp_client=None):
        """Initialize ReadMCPResourceTool.

        Args:
            mcp_client: MCP client instance for making resource requests
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
                "uri": {
                    "type": "string",
                    "description": "The URI of the MCP resource to read, as returned by list_mcp_resources (e.g., 'file:///path/to/file', 'db://schema/table').",
                },
                "server_name": {
                    "type": "string",
                    "description": "Optional name of the MCP server that exposes this resource. Required if multiple servers have resources with the same URI.",
                },
            },
            "required": ["uri"],
        }

    async def execute(
        self,
        uri: str,
        server_name: str | None = None,
    ) -> ToolResult:
        """Read content from an MCP resource.

        Args:
            uri: The URI of the resource to read
            server_name: Optional specific server to use

        Returns:
            ToolResult with resource content or error
        """
        try:
            if self._mcp_client is None:
                return ToolResult(
                    success=False,
                    content="",
                    error="MCP client not initialized",
                )

            # Read the resource from MCP client
            result = await self._mcp_client.read_resource(
                uri=uri,
                server_name=server_name,
            )

            contents = result.get("contents", [])
            if not contents:
                return ToolResult(
                    success=True,
                    content=f"Resource '{uri}' is empty",
                )

            # Format the content
            output_parts = []
            for content_item in contents:
                uri_info = content_item.get("uri", uri)
                mime_type = content_item.get("mimeType", "unknown")
                text_content = content_item.get("text")
                blob_content = content_item.get("blob")

                output_parts.append(f"--- Resource: {uri_info} (Type: {mime_type}) ---")

                if text_content is not None:
                    # Truncate if too long
                    if len(text_content) > 50000:
                        text_content = text_content[:50000] + "\n... [Content truncated]"
                    output_parts.append(text_content)
                elif blob_content is not None:
                    output_parts.append(f"[Binary content: {len(blob_content)} bytes]")
                else:
                    output_parts.append("[No content]")

            formatted_content = "\n\n".join(output_parts)

            return ToolResult(success=True, content=formatted_content)

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to read MCP resource '{uri}': {str(e)}",
            )
