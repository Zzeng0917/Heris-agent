"""Prompt for MCP Invoke Tool.

This module defines the prompt and description for the mcp_invoke tool,
which is used to inform the LLM about the tool's functionality.
"""

TOOL_NAME = "mcp_invoke"

DESCRIPTION = """Invoke tools (functions) exposed by MCP (Model Context Protocol) servers.

This tool calls functions provided by MCP servers to perform actions,
process data, query databases, manipulate files, or interact with
external systems through a standardized protocol.

Use this tool when you need to:
- Execute actions on MCP servers (read/write files, query databases, etc.)
- Process data through specialized MCP functions
- Interact with external systems via MCP tools
"""

USAGE_EXAMPLE = """
# Call a simple MCP tool with no arguments
mcp_invoke(tool_name="get_system_info")

# Call an MCP tool with arguments
mcp_invoke(
    tool_name="read_file",
    arguments={"path": "/etc/config.txt"}
)

# Call a tool from a specific server
mcp_invoke(
    tool_name="query_database",
    arguments={"sql": "SELECT * FROM users LIMIT 10"},
    server_name="postgres-server"
)

# Complex tool invocation with multiple arguments
mcp_invoke(
    tool_name="send_email",
    arguments={
        "to": "user@example.com",
        "subject": "Hello",
        "body": "Message content",
        "attachments": []
    }
)
"""

PROMPT = """When the user needs to perform an action through an MCP server:

1. Identify the appropriate MCP tool to use (discover via list_mcp_tools if needed)
2. Construct the tool call with:
   - TOOL_NAME: The exact name of the MCP tool
   - ARGUMENTS: Dictionary of parameters matching the tool's schema
   - SERVER_NAME: (Optional) Specific server if multiple servers expose the same tool
3. Execute the tool call using mcp_invoke
4. Handle the response which may contain:
   - Text content
   - Image data
   - Resource references
   - Error information
5. Report the results or errors to the user

Important: Always verify tool names and argument schemas before calling.
Be aware that MCP tools may have side effects (file writes, database updates, etc.).
"""

PARAMETERS = {
    "TOOL_NAME": {
        "type": "string",
        "description": "The name of the MCP tool to invoke, as defined by the MCP server (e.g., 'read_file', 'query_database').",
        "required": True,
    },
    "ARGUMENTS": {
        "type": "object",
        "description": "Arguments to pass to the MCP tool. Must match the tool's expected parameter schema.",
        "required": False,
    },
    "SERVER_NAME": {
        "type": "string",
        "description": "Optional name of the MCP server that exposes this tool. Required if multiple servers have tools with the same name.",
        "required": False,
    },
}

RESPONSE_FORMAT = """The tool returns the MCP tool's output:

Success:
Tool executed successfully:
File content:
Hello, World!

Error:
Failed to call MCP tool 'read_file': File not found: /path/to/file
"""
