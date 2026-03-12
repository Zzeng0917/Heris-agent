"""Test cases for Subagent module."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from heris.schema import FunctionCall, LLMResponse, Message, ToolCall
from heris.subagent import SubagentRunner, SubagentTool, run_subagent
from heris.subagent.runner import SUBAGENT_SYSTEM_PROMPT
from heris.tools.base import Tool, ToolResult


class MockTool(Tool):
    """Mock tool for testing."""

    def __init__(self, name: str = "mock_tool"):
        super().__init__()
        self._name = name
        self.execute = AsyncMock(return_value=ToolResult(success=True, content="mock result"))

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Mock tool: {self._name}"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "arg1": {"type": "string"},
            },
        }


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate = AsyncMock()
    return client


@pytest.fixture
def mock_response_no_tools():
    """Create a mock LLM response with no tool calls."""
    return LLMResponse(
        content="Test response content",
        tool_calls=None,
        finish_reason="stop",
    )


@pytest.fixture
def mock_response_with_tools():
    """Create a mock LLM response with tool calls."""
    return LLMResponse(
        content="Using tool",
        tool_calls=[
            ToolCall(
                id="tool_1",
                type="function",
                function=FunctionCall(
                    name="mock_tool",
                    arguments={"arg1": "test"},
                ),
            )
        ],
        finish_reason="tool_use",
    )


@pytest.mark.asyncio
async def test_subagent_runner_init():
    """Test SubagentRunner initialization."""
    client = MagicMock()

    # Test with default workspace
    runner = SubagentRunner(llm_client=client)
    assert runner.llm == client
    assert runner.max_steps == 30
    assert runner.tools == {}
    assert runner.workspace_dir.exists()
    assert runner._cleanup_workspace is True

    # Cleanup
    runner.cleanup()


@pytest.mark.asyncio
async def test_subagent_runner_with_custom_workspace():
    """Test SubagentRunner with custom workspace."""
    client = MagicMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = SubagentRunner(
            llm_client=client,
            workspace_dir=tmpdir,
            max_steps=50,
        )
        assert runner.workspace_dir == Path(tmpdir)
        assert runner.max_steps == 50
        assert runner._cleanup_workspace is False

        # Should not cleanup custom workspace
        runner.cleanup()
        assert Path(tmpdir).exists()


@pytest.mark.asyncio
async def test_subagent_runner_with_tools():
    """Test SubagentRunner with tools."""
    client = MagicMock()
    mock_tool = MockTool()

    runner = SubagentRunner(
        llm_client=client,
        tools=[mock_tool],
    )

    assert "mock_tool" in runner.tools
    assert runner.tools["mock_tool"] == mock_tool

    runner.cleanup()


@pytest.mark.asyncio
async def test_subagent_runner_run_no_tools(mock_llm_client, mock_response_no_tools):
    """Test SubagentRunner.run with no tool calls."""
    mock_llm_client.generate.return_value = mock_response_no_tools

    runner = SubagentRunner(llm_client=mock_llm_client)
    result = await runner.run("Test prompt")

    assert result == "Test response content"

    # Verify LLM was called with correct messages
    call_args = mock_llm_client.generate.call_args
    messages = call_args.kwargs["messages"]
    # Messages after run: system + user prompt + assistant response
    assert len(messages) == 3
    assert messages[0].role == "system"
    assert messages[0].content == SUBAGENT_SYSTEM_PROMPT
    assert messages[1].role == "user"
    assert messages[1].content == "Test prompt"
    assert messages[2].role == "assistant"
    assert messages[2].content == "Test response content"

    runner.cleanup()


@pytest.mark.asyncio
async def test_subagent_runner_run_with_tools(mock_llm_client, mock_response_with_tools, mock_response_no_tools):
    """Test SubagentRunner.run with tool calls."""
    mock_tool = MockTool()

    # First call returns tool_use, second call returns final response
    mock_llm_client.generate.side_effect = [
        mock_response_with_tools,
        mock_response_no_tools,
    ]

    runner = SubagentRunner(
        llm_client=mock_llm_client,
        tools=[mock_tool],
    )

    result = await runner.run("Test prompt")

    # Verify tool was called
    mock_tool.execute.assert_called_once_with(arg1="test")

    # Verify result
    assert result == "Test response content"

    runner.cleanup()


@pytest.mark.asyncio
async def test_subagent_runner_run_max_steps(mock_llm_client):
    """Test SubagentRunner respects max_steps limit."""
    # Always return tool calls to force max_steps to be reached
    mock_response = LLMResponse(
        content="Using tool",
        tool_calls=[
            ToolCall(
                id="tool_1",
                type="function",
                function=FunctionCall(
                    name="mock_tool",
                    arguments={},
                ),
            )
        ],
        finish_reason="tool_use",
    )
    mock_llm_client.generate.return_value = mock_response

    mock_tool = MockTool()

    runner = SubagentRunner(
        llm_client=mock_llm_client,
        tools=[mock_tool],
        max_steps=3,
    )

    result = await runner.run("Test prompt")

    # Should stop after max_steps
    assert "maximum step limit" in result
    assert mock_llm_client.generate.call_count == 3

    runner.cleanup()


@pytest.mark.asyncio
async def test_subagent_runner_run_llm_error(mock_llm_client):
    """Test SubagentRunner handles LLM errors."""
    mock_llm_client.generate.side_effect = Exception("LLM API Error")

    runner = SubagentRunner(llm_client=mock_llm_client)
    result = await runner.run("Test prompt")

    assert "[Subagent Error]" in result
    assert "LLM API Error" in result

    runner.cleanup()


@pytest.mark.asyncio
async def test_subagent_runner_context_manager(mock_llm_client, mock_response_no_tools):
    """Test SubagentRunner as async context manager."""
    mock_llm_client.generate.return_value = mock_response_no_tools

    async with SubagentRunner(llm_client=mock_llm_client) as runner:
        result = await runner.run("Test prompt")
        assert result == "Test response content"
        workspace = runner.workspace_dir
        assert workspace.exists()

    # After exiting context, workspace should be cleaned
    # Note: cleanup happens but we can't verify easily since it's temp dir


@pytest.mark.asyncio
async def test_run_subagent_function(mock_llm_client, mock_response_no_tools):
    """Test run_subagent convenience function."""
    mock_llm_client.generate.return_value = mock_response_no_tools

    result = await run_subagent(
        prompt="Test task",
        llm_client=mock_llm_client,
        max_steps=20,
    )

    assert result == "Test response content"


@pytest.mark.asyncio
async def test_subagent_tool_init(mock_llm_client):
    """Test SubagentTool initialization."""
    tool = SubagentTool(llm_client=mock_llm_client)

    assert tool.name == "spawn_subagent"
    assert "spawn" in tool.description.lower()
    assert tool.llm_client == mock_llm_client
    assert tool.default_max_steps == 30


@pytest.mark.asyncio
async def test_subagent_tool_parameters(mock_llm_client):
    """Test SubagentTool parameters schema."""
    tool = SubagentTool(llm_client=mock_llm_client)
    params = tool.parameters

    assert params["type"] == "object"
    assert "prompt" in params["properties"]
    assert "agent_name" in params["properties"]
    assert "max_steps" in params["properties"]
    assert "workspace_dir" in params["properties"]
    assert params["required"] == ["prompt", "agent_name"]


@pytest.mark.asyncio
async def test_subagent_tool_execute_success(mock_llm_client, mock_response_no_tools):
    """Test SubagentTool execute success."""
    mock_llm_client.generate.return_value = mock_response_no_tools

    tool = SubagentTool(llm_client=mock_llm_client)
    result = await tool.execute(prompt="Test task", agent_name="general")

    assert result.success is True
    assert result.content == "Test response content"
    assert result.error is None


@pytest.mark.asyncio
async def test_subagent_tool_execute_error(mock_llm_client):
    """Test SubagentTool execute error handling."""
    mock_llm_client.generate.side_effect = Exception("Execution failed")

    tool = SubagentTool(llm_client=mock_llm_client)
    result = await tool.execute(prompt="Test task", agent_name="general")

    assert result.success is False
    assert "Execution failed" in result.error


@pytest.mark.asyncio
async def test_subagent_tool_with_custom_steps(mock_llm_client, mock_response_no_tools):
    """Test SubagentTool with custom max_steps."""
    mock_llm_client.generate.return_value = mock_response_no_tools

    tool = SubagentTool(llm_client=mock_llm_client, default_max_steps=50)

    # Execute with explicit max_steps
    result = await tool.execute(prompt="Test", agent_name="general", max_steps=25)

    assert result.success is True
    # Verify it was called (the mock doesn't check the exact steps, but the runner would use 25)


@pytest.mark.asyncio
async def test_subagent_tool_with_tools(mock_llm_client, mock_response_no_tools):
    """Test SubagentTool with additional tools."""
    mock_llm_client.generate.return_value = mock_response_no_tools

    mock_tool1 = MockTool(name="tool1")
    mock_tool2 = MockTool(name="tool2")

    tool = SubagentTool(
        llm_client=mock_llm_client,
        tools=[mock_tool1],
    )

    # Add more tools
    new_tool = tool.with_tools([mock_tool2])

    assert len(new_tool.tools) == 2
    assert mock_tool1 in new_tool.tools
    assert mock_tool2 in new_tool.tools


@pytest.mark.asyncio
async def test_subagent_tool_unknown_tool(mock_llm_client):
    """Test SubagentTool handles unknown tools gracefully."""
    # Response with unknown tool
    mock_response = LLMResponse(
        content="Using unknown tool",
        tool_calls=[
            ToolCall(
                id="tool_1",
                type="function",
                function=FunctionCall(
                    name="unknown_tool",
                    arguments={},
                ),
            )
        ],
        finish_reason="tool_use",
    )

    mock_llm_client.generate.side_effect = [
        mock_response,
        LLMResponse(content="Done", tool_calls=None, finish_reason="stop"),
    ]

    tool = SubagentTool(llm_client=mock_llm_client)
    result = await tool.execute(prompt="Test", agent_name="general")

    assert result.success is True
    # Should handle unknown tool gracefully


@pytest.mark.asyncio
async def test_subagent_system_prompt_content():
    """Verify subagent system prompt contains expected guidance."""
    prompt = SUBAGENT_SYSTEM_PROMPT

    assert "specialized subagent" in prompt.lower()
    assert "isolated" in prompt.lower()
    assert "workspace" in prompt.lower()
    assert "concise" in prompt.lower()


@pytest.mark.asyncio
async def test_subagent_integration_with_real_workspace(mock_llm_client, mock_response_no_tools):
    """Integration test with real file system operations."""
    from heris.tools.file import ReadTool, WriteTool

    mock_llm_client.generate.return_value = mock_response_no_tools

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create tools with real workspace
        read_tool = ReadTool(workspace_dir=tmpdir)
        write_tool = WriteTool(workspace_dir=tmpdir)

        # Create test file
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("Hello, World!")

        runner = SubagentRunner(
            llm_client=mock_llm_client,
            tools=[read_tool, write_tool],
            workspace_dir=tmpdir,
        )

        # Run subagent
        result = await runner.run("Read test.txt and return its content")

        # Note: Since we're mocking LLM, the actual tool execution won't happen
        # But we can verify the workspace setup
        assert runner.workspace_dir == Path(tmpdir)
        assert (Path(tmpdir) / "test.txt").exists()

        runner.cleanup()


async def main():
    """Run all subagent tests."""
    print("=" * 80)
    print("Running Subagent Tests")
    print("=" * 80)

    # Run pytest
    import sys
    sys.exit(pytest.main([__file__, "-v"]))


if __name__ == "__main__":
    asyncio.run(main())
