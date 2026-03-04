"""Tests for Agent's persona update functionality."""

import pytest
from unittest.mock import MagicMock, patch

from heris.agent import Agent
from heris.modes import AgentMode, ModeType


class TestAgentUpdatePersona:
    """Test Agent.update_persona method."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        return MagicMock()

    @pytest.fixture
    def basic_system_prompt(self):
        """Basic system prompt with MODE_PROMPT placeholder."""
        return """You are Heris, an AI assistant.

{MODE_PROMPT}

## Core Capabilities
You can help with various tasks."""

    @pytest.fixture
    def agent_with_placeholder(self, mock_llm_client, basic_system_prompt):
        """Create an agent with MODE_PROMPT placeholder."""
        return Agent(
            llm_client=mock_llm_client,
            system_prompt=basic_system_prompt,
            tools=[],
            workspace_dir="/tmp/test"
        )

    def test_update_persona_with_placeholder(self, agent_with_placeholder):
        """Test updating persona when {MODE_PROMPT} placeholder exists."""
        mode_prompt = "You are energetic!"

        agent_with_placeholder.update_persona(mode_prompt)

        # Check that placeholder was replaced
        assert "{MODE_PROMPT}" not in agent_with_placeholder.messages[0].content
        assert mode_prompt in agent_with_placeholder.messages[0].content
        assert mode_prompt in agent_with_placeholder.system_prompt

    def test_update_persona_preserves_structure(self, agent_with_placeholder):
        """Test that updating persona preserves other parts of system prompt."""
        mode_prompt = "You are energetic!"

        agent_with_placeholder.update_persona(mode_prompt)

        content = agent_with_placeholder.messages[0].content
        assert "You are Heris" in content
        assert "## Core Capabilities" in content
        assert "You can help" in content
        assert mode_prompt in content

    def test_update_persona_without_placeholder(self, agent_with_placeholder):
        """Test updating persona when placeholder doesn't exist (replaces old mode)."""
        # First set a mode (with proper section header as real mode prompts have)
        first_mode = "## Your Persona\n\nYou are energetic!"
        agent_with_placeholder.update_persona(first_mode)

        # Now update to a new mode
        second_mode = "## Your Persona\n\nYou are relaxed!"
        agent_with_placeholder.update_persona(second_mode)

        content = agent_with_placeholder.messages[0].content
        # New mode should be present
        assert "You are relaxed!" in content
        # Old mode should not be present
        assert "You are energetic!" not in content
        # Other content should be preserved
        assert "You are Heris" in content
        assert "## Core Capabilities" in content

    def test_update_persona_strips_old_mode_section(self, agent_with_placeholder):
        """Test that old mode section is properly stripped."""
        # Set first mode with Your Persona header
        first_mode = "## Your Persona\n\nYou are energetic!"
        agent_with_placeholder.update_persona(first_mode)

        # Update to new mode
        second_mode = "## Your Persona\n\nYou are relaxed!"
        agent_with_placeholder.update_persona(second_mode)

        content = agent_with_placeholder.messages[0].content
        # Should only have one mode section
        assert content.count("## Your Persona") == 1
        # Should have new mode content
        assert "You are relaxed!" in content
        # Should not have old mode content
        assert "You are energetic!" not in content

    def test_update_persona_sets_current_mode_attribute(self, agent_with_placeholder):
        """Test that update_persona sets current_mode attribute on agent."""
        mode_prompt = "You are energetic!"

        assert not hasattr(agent_with_placeholder, 'current_mode')

        agent_with_placeholder.update_persona(mode_prompt)

        assert hasattr(agent_with_placeholder, 'current_mode')

    def test_update_persona_with_empty_mode(self, agent_with_placeholder):
        """Test updating with empty mode prompt (normal mode)."""
        mode_prompt = ""

        agent_with_placeholder.update_persona(mode_prompt)

        content = agent_with_placeholder.messages[0].content
        assert "You are Heris" in content
        assert "## Core Capabilities" in content

    def test_update_persona_no_system_message(self, mock_llm_client):
        """Test updating when there's no system message."""
        agent = Agent(
            llm_client=mock_llm_client,
            system_prompt="Test",
            tools=[],
            workspace_dir="/tmp/test"
        )

        # Remove system message
        agent.messages = []

        # Should not raise error
        agent.update_persona("Test persona")

    def test_update_persona_first_message_not_system(self, mock_llm_client):
        """Test updating when first message is not system."""
        agent = Agent(
            llm_client=mock_llm_client,
            system_prompt="Test",
            tools=[],
            workspace_dir="/tmp/test"
        )

        # Replace system message with user message
        from heris.schema import Message
        agent.messages = [Message(role="user", content="Hello")]

        # Should not modify anything
        original_content = agent.messages[0].content
        agent.update_persona("Test persona")
        assert agent.messages[0].content == original_content


class TestAgentModeIntegration:
    """Test integration between Agent and Mode system."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        return MagicMock()

    @pytest.fixture
    def agent(self, mock_llm_client):
        """Create a basic agent."""
        return Agent(
            llm_client=mock_llm_client,
            system_prompt="You are Heris.\n\n{MODE_PROMPT}\n\n## Core Capabilities",
            tools=[],
            workspace_dir="/tmp/test"
        )

    def test_agent_with_normal_mode(self, agent):
        """Test agent behavior with normal mode."""
        mode = AgentMode(mode_type=ModeType.NORMAL)
        prompt = mode.build_prompt_injection()

        agent.update_persona(prompt)

        # Normal mode prompt is empty
        assert "You are Heris" in agent.messages[0].content

    def test_agent_with_push_mode(self, agent):
        """Test agent behavior with PUSH mode."""
        mode = AgentMode(mode_type=ModeType.PUSH)
        prompt = mode.build_prompt_injection()

        agent.update_persona(prompt)

        content = agent.messages[0].content
        assert "energetic" in content.lower() or "optimistic" in content.lower()
        assert "You are Heris" in content
        assert "## Core Capabilities" in content

    def test_agent_with_slackin_mode(self, agent):
        """Test agent behavior with 摸鱼 mode."""
        mode = AgentMode(mode_type=ModeType.SLACKIN)
        prompt = mode.build_prompt_injection()

        agent.update_persona(prompt)

        content = agent.messages[0].content
        assert "relaxed" in content.lower() or "easygoing" in content.lower()
        assert "You are Heris" in content
        assert "## Core Capabilities" in content

    def test_multiple_mode_switches(self, agent):
        """Test switching modes multiple times."""
        # Start with PUSH
        push_mode = AgentMode(mode_type=ModeType.PUSH)
        agent.update_persona(push_mode.build_prompt_injection())

        # Switch to SLACKIN
        slackin_mode = AgentMode(mode_type=ModeType.SLACKIN)
        agent.update_persona(slackin_mode.build_prompt_injection())

        # Switch back to NORMAL
        normal_mode = AgentMode(mode_type=ModeType.NORMAL)
        agent.update_persona(normal_mode.build_prompt_injection())

        content = agent.messages[0].content
        # Should still have the base content
        assert "You are Heris" in content
        assert "## Core Capabilities" in content


class TestAgentCurrentMode:
    """Test agent's current_mode attribute behavior."""

    @pytest.fixture
    def mock_llm_client(self):
        return MagicMock()

    def test_current_mode_defaults_to_none(self, mock_llm_client):
        """Test that current_mode is not set by default."""
        agent = Agent(
            llm_client=mock_llm_client,
            system_prompt="Test",
            tools=[],
            workspace_dir="/tmp/test"
        )

        assert not hasattr(agent, 'current_mode') or agent.current_mode is None

    def test_current_mode_can_be_set(self, mock_llm_client):
        """Test that current_mode can be set externally."""
        agent = Agent(
            llm_client=mock_llm_client,
            system_prompt="Test",
            tools=[],
            workspace_dir="/tmp/test"
        )

        mode = AgentMode(mode_type=ModeType.PUSH)
        agent.current_mode = mode

        assert agent.current_mode == mode
        assert agent.current_mode.mode_type == ModeType.PUSH
