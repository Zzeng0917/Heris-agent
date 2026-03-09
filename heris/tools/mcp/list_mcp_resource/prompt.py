"""Prompt for List MCP Resource Tool.

This module defines the prompt and description for the list_mcp_resources tool,
which is used to inform the LLM about the tool's functionality.
"""

TOOL_NAME = "list_mcp_resources"

DESCRIPTION = """List available resources from an MCP (Model Context Protocol) server.

This tool discovers and lists resources exposed by connected MCP servers.
MCP resources are data sources identified by URIs that can be accessed
and read using read_mcp_resource.

Use this tool when you need to:
- Discover what data sources are available through MCP servers
- Find resource URIs before reading resource content
- Browse available files, databases, or APIs exposed via MCP
"""

USAGE_EXAMPLE = """
# List all resources from all connected MCP servers
list_mcp_resources()

# List resources from a specific server
list_mcp_resources(server_name="filesystem-server")

# Handle pagination for large resource lists
list_mcp_resources(cursor="eyJwYWdlIjogMn0=")
"""

PROMPT = """When the user needs to discover what data sources are available through MCP:

1. Use `list_mcp_resources` to discover available resources
2. Review the returned resource list containing:
   - Resource name
   - URI (uniform resource identifier)
   - MIME type
   - Optional description
3. Use the URI with `read_mcp_resource` to access the content
4. If a cursor is returned, more resources are available - call again with the cursor

Always use list_mcp_resources before attempting to read MCP resources to ensure
the resource exists and to get the correct URI format.
"""

PARAMETERS = {
    "SERVER_NAME": {
        "type": "string",
        "description": "Optional name of a specific MCP server to query. If not provided, lists resources from all connected servers.",
        "required": False,
    },
    "CURSOR": {
        "type": "string",
        "description": "Optional pagination cursor for retrieving additional results from previous list_mcp_resources calls.",
        "required": False,
    },
}

RESPONSE_FORMAT = """The tool returns a formatted list of resources:

Available MCP Resources (3 total):

- Project Files
  URI: file:///workspace/project
  Type: text/directory

- Database Schema
  URI: db://localhost/schema
  Type: application/sql

[More resources available. Use cursor='abc123' to see more.]
"""
