"""Tests for the mode tools."""

import asyncio
import pytest
from unittest.mock import MagicMock, patch

from heris.modes import AgentMode, ModeType
from heris.tools.mode_tool import GetCurrentModeTool, SetModeTool
from heris.tools.base import ToolResult


class TestSetModeTool:
    """Test SetModeTool."""

    def test_tool_properties(self):
        """Test tool name, description, and parameters."""
        tool = SetModeTool()
        assert tool.name == "set_mode"
        assert "mode" in tool.description.lower()
        assert "personality" in tool.description.lower() or "persona" in tool.description.lower()

        params = tool.parameters
        assert params["type"] == "object"
        assert "mode" in params["properties"]
        assert params["properties"]["mode"]["type"] == "string"
        assert "enum" in params["properties"]["mode"]
        assert set(params["properties"]["mode"]["enum"]) == {"normal", "push", "slackin"}
        assert "mode" in params["required"]

    def test_set_agent(self):
        """Test setting agent reference."""
        tool = SetModeTool()
        mock_agent = MagicMock()
        tool.set_agent(mock_agent)
        assert tool._agent == mock_agent

    @pytest.mark.asyncio
    async def test_execute_without_agent(self):
        """Test execution without agent returns error."""
        tool = SetModeTool()
        result = await tool.execute(mode="normal")
        assert not result.success
        assert "Agent not initialized" in result.error

    @pytest.mark.asyncio
    async def test_execute_normal_mode(self):
        """Test switching to normal mode."""
        tool = SetModeTool()
        mock_agent = MagicMock()
        mock_agent.current_mode = None
        tool.set_agent(mock_agent)

        result = await tool.execute(mode="normal")

        assert result.success
        assert "普通模式" in result.content
        mock_agent.update_persona.assert_called_once()
        assert mock_agent.current_mode.mode_type == ModeType.NORMAL

    @pytest.mark.asyncio
    async def test_execute_push_mode(self):
        """Test switching to PUSH mode."""
        tool = SetModeTool()
        mock_agent = MagicMock()
        mock_agent.current_mode = None
        tool.set_agent(mock_agent)

        result = await tool.execute(mode="push")

        assert result.success
        assert "PUSH模式" in result.content
        mock_agent.update_persona.assert_called_once()
        assert mock_agent.current_mode.mode_type == ModeType.PUSH

    @pytest.mark.asyncio
    async def test_execute_slackin_mode(self):
        """Test switching to 摸鱼 mode."""
        tool = SetModeTool()
        mock_agent = MagicMock()
        mock_agent.current_mode = None
        tool.set_agent(mock_agent)

        result = await tool.execute(mode="slackin")

        assert result.success
        assert "摸鱼模式" in result.content
        mock_agent.update_persona.assert_called_once()
        assert mock_agent.current_mode.mode_type == ModeType.SLACKIN

    @pytest.mark.asyncio
    async def test_execute_case_insensitive(self):
        """Test that mode names are case insensitive."""
        tool = SetModeTool()
        mock_agent = MagicMock()
        mock_agent.current_mode = None
        tool.set_agent(mock_agent)

        result = await tool.execute(mode="PUSH")
        assert result.success
        assert mock_agent.current_mode.mode_type == ModeType.PUSH

        result = await tool.execute(mode="Slackin")
        assert result.success
        assert mock_agent.current_mode.mode_type == ModeType.SLACKIN

    @pytest.mark.asyncio
    async def test_execute_invalid_mode(self):
        """Test switching to invalid mode returns error."""
        tool = SetModeTool()
        mock_agent = MagicMock()
        tool.set_agent(mock_agent)

        result = await tool.execute(mode="invalid_mode")

        assert not result.success
        assert "无效的模式" in result.error or "Unknown mode" in result.error


class TestGetCurrentModeTool:
    """Test GetCurrentModeTool."""

    def test_tool_properties(self):
        """Test tool name, description, and parameters."""
        tool = GetCurrentModeTool()
        assert tool.name == "get_current_mode"
        assert "current" in tool.description.lower() or "mode" in tool.description.lower()

        params = tool.parameters
        assert params["type"] == "object"
        assert len(params["properties"]) == 0  # No parameters

    def test_set_agent(self):
        """Test setting agent reference."""
        tool = GetCurrentModeTool()
        mock_agent = MagicMock()
        tool.set_agent(mock_agent)
        assert tool._agent == mock_agent

    @pytest.mark.asyncio
    async def test_execute_without_agent(self):
        """Test execution without agent returns error."""
        tool = GetCurrentModeTool()
        result = await tool.execute()
        assert not result.success
        assert "Agent not initialized" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_normal_mode(self):
        """Test getting current mode when set to normal."""
        tool = GetCurrentModeTool()
        mock_agent = MagicMock()
        mock_agent.current_mode = AgentMode(mode_type=ModeType.NORMAL)
        tool.set_agent(mock_agent)

        result = await tool.execute()

        assert result.success
        assert "普通模式" in result.content
        assert "标准助手" in result.content

    @pytest.mark.asyncio
    async def test_execute_with_push_mode(self):
        """Test getting current mode when set to PUSH."""
        tool = GetCurrentModeTool()
        mock_agent = MagicMock()
        mock_agent.current_mode = AgentMode(mode_type=ModeType.PUSH)
        tool.set_agent(mock_agent)

        result = await tool.execute()

        assert result.success
        assert "PUSH模式" in result.content

    @pytest.mark.asyncio
    async def test_execute_with_slackin_mode(self):
        """Test getting current mode when set to 摸鱼."""
        tool = GetCurrentModeTool()
        mock_agent = MagicMock()
        mock_agent.current_mode = AgentMode(mode_type=ModeType.SLACKIN)
        tool.set_agent(mock_agent)

        result = await tool.execute()

        assert result.success
        assert "摸鱼模式" in result.content

    @pytest.mark.asyncio
    async def test_execute_without_current_mode(self):
        """Test getting current mode when not set (defaults to normal)."""
        tool = GetCurrentModeTool()
        mock_agent = MagicMock()
        # Simulate agent without current_mode attribute
        del mock_agent.current_mode
        tool.set_agent(mock_agent)

        result = await tool.execute()

        assert result.success
        assert "普通模式" in result.content


class TestModeToolsIntegration:
    """Integration tests for mode tools working together."""

    @pytest.mark.asyncio
    async def test_full_mode_switching_flow(self):
        """Test complete workflow of switching between modes."""
        # Create mock agent
        mock_agent = MagicMock()
        mock_agent.current_mode = None

        set_tool = SetModeTool(mock_agent)
        get_tool = GetCurrentModeTool(mock_agent)

        # Initial state: no mode set
        result = await get_tool.execute()
        assert "普通模式" in result.content

        # Switch to PUSH mode
        result = await set_tool.execute(mode="push")
        assert result.success
        assert mock_agent.current_mode.mode_type == ModeType.PUSH

        # Verify current mode
        result = await get_tool.execute()
        assert "PUSH模式" in result.content

        # Switch to 摸鱼 mode
        result = await set_tool.execute(mode="slackin")
        assert result.success
        assert mock_agent.current_mode.mode_type == ModeType.SLACKIN

        # Verify current mode
        result = await get_tool.execute()
        assert "摸鱼模式" in result.content

        # Back to normal
        result = await set_tool.execute(mode="normal")
        assert result.success
        assert mock_agent.current_mode.mode_type == ModeType.NORMAL

        # Verify update_persona was called each time
        assert mock_agent.update_persona.call_count == 3


class TestToolSchemas:
    """Test tool schema generation."""

    def test_set_mode_to_schema(self):
        """Test SetModeTool schema generation."""
        tool = SetModeTool()
        schema = tool.to_schema()

        assert schema["name"] == "set_mode"
        assert "input_schema" in schema
        assert schema["input_schema"]["type"] == "object"
        assert "mode" in schema["input_schema"]["properties"]

    def test_set_mode_to_openai_schema(self):
        """Test SetModeTool OpenAI schema generation."""
        tool = SetModeTool()
        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "set_mode"
        assert "parameters" in schema["function"]

    def test_get_mode_to_schema(self):
        """Test GetCurrentModeTool schema generation."""
        tool = GetCurrentModeTool()
        schema = tool.to_schema()

        assert schema["name"] == "get_current_mode"
        assert "input_schema" in schema

    def test_get_mode_to_openai_schema(self):
        """Test GetCurrentModeTool OpenAI schema generation."""
        tool = GetCurrentModeTool()
        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_current_mode"
