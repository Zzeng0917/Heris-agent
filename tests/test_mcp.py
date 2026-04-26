"""Test cases for MCP tool loading."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from heris.tools.mcp.loader import (
    cleanup_mcp_connections,
    get_builtin_mcp_tools,
    load_mcp_tools_async,
)


@pytest.mark.asyncio
async def test_builtin_mcp_tools():
    """Test loading built-in MCP tools."""
    tools = get_builtin_mcp_tools()
    assert isinstance(tools, list)


@pytest.mark.asyncio
async def test_load_mcp_tools_async_empty():
    """Test load_mcp_tools_async with no config."""
    tools = await load_mcp_tools_async(None)
    assert isinstance(tools, list)


@pytest.mark.asyncio
async def test_url_config_validation():
    """Test that URL-based config without url is skipped (builtin tools still loaded)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config = {
            "mcpServers": {
                "broken-sse": {
                    "type": "sse",
                }
            }
        }
        json.dump(config, f)
        f.flush()

        try:
            tools = await load_mcp_tools_async(f.name)
            # Built-in tools should still be loaded
            assert len(tools) >= 1
        finally:
            await cleanup_mcp_connections()
            Path(f.name).unlink()


@pytest.mark.asyncio
async def test_stdio_config_validation():
    """Test that STDIO config without command is skipped (builtin tools still loaded)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config = {
            "mcpServers": {
                "broken-stdio": {
                    "type": "stdio",
                }
            }
        }
        json.dump(config, f)
        f.flush()

        try:
            tools = await load_mcp_tools_async(f.name)
            # Built-in tools should still be loaded
            assert len(tools) >= 1
        finally:
            await cleanup_mcp_connections()
            Path(f.name).unlink()


@pytest.mark.asyncio
async def test_mixed_config_loading():
    """Test loading config with both STDIO and URL-based servers."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config = {
            "mcpServers": {
                "stdio-server": {"command": "npx", "args": ["-y", "nonexistent-server"], "disabled": True},
                "url-server": {"url": "https://mcp.nonexistent.example.com/mcp", "disabled": True},
            }
        }
        json.dump(config, f)
        f.flush()

        try:
            tools = await load_mcp_tools_async(f.name)
            # Built-in tools should still be loaded (at least WebSearchTool)
            assert len(tools) >= 1
        finally:
            await cleanup_mcp_connections()
            Path(f.name).unlink()


@pytest.mark.asyncio
async def test_mcp_tools_loading():
    """Test loading MCP tools from mcp.json."""
    tools = await load_mcp_tools_async("heris/config/mcp.json")
    assert isinstance(tools, list)
    await cleanup_mcp_connections()
