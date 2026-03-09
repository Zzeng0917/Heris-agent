"""Prompt for Read MCP Resource Tool.

This module defines the prompt and description for the read_mcp_resource tool,
which is used to inform the LLM about the tool's functionality.
"""

TOOL_NAME = "read_mcp_resource"

DESCRIPTION = """Read content from resources exposed by MCP (Model Context Protocol) servers.

This tool reads data from MCP resources identified by URIs. Resources can
include files, database schemas, API responses, configuration files, or
any other data source exposed via the MCP protocol.

Use this tool when you need to:
- Read file content from MCP filesystem servers
- Fetch database schema or table information
- Retrieve API documentation or responses
- Access configuration data from MCP servers
"""

USAGE_EXAMPLE = """
# Read a file resource
read_mcp_resource(uri="file:///workspace/project/README.md")

# Read a database table schema
read_mcp_resource(uri="db://localhost/schema/users")

# Read from a specific server
read_mcp_resource(
    uri="config://app/settings",
    server_name="config-server"
)

# Read API documentation
read_mcp_resource(uri="https://api.example.com/openapi.json")
"""

PROMPT = """When the user needs to access data from an MCP resource:

1. First use `list_mcp_resources` to discover available resources and get their URIs
2. Identify the resource URI you need to access
3. Call `read_mcp_resource` with:
   - URI: The exact resource URI from the list
   - SERVER_NAME: (Optional) Specific server if URI exists on multiple servers
4. The tool returns the resource content which may be:
   - Text content (truncated if too long, >50KB)
   - Binary content (with size information)
   - Empty if the resource has no content
5. Present the content to the user or use it for further processing

Best practices:
- Always use list_mcp_resources first to discover valid URIs
- Handle both text and binary content appropriately based on the MIME type
- Use SERVER_NAME when working with multiple MCP servers to avoid ambiguity
- Consider caching results if the same resource is read multiple times
"""

PARAMETERS = {
    "URI": {
        "type": "string",
        "description": "The URI of the MCP resource to read, as returned by list_mcp_resources (e.g., 'file:///path/to/file', 'db://schema/table').",
        "required": True,
    },
    "SERVER_NAME": {
        "type": "string",
        "description": "Optional name of the MCP server that exposes this resource. Required if multiple servers have resources with the same URI.",
        "required": False,
    },
}

RESPONSE_FORMAT = """The tool returns the resource content formatted as:

Text content:
--- Resource: file:///workspace/README.md (Type: text/markdown) ---
# Project Title

This is the README content...

Binary content:
--- Resource: file:///workspace/image.png (Type: image/png) ---
[Binary content: 15324 bytes]
"""
