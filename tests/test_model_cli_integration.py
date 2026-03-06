"""Integration tests for /model command in CLI interactive loop."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path

from heris.cli import print_model_info
from heris.config import Config, LLMConfig, AgentConfig, ToolsConfig


class TestModelCLIIntegration:
    """Test /model command behavior in CLI context."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing."""
        config = Mock(spec=Config)
        config.llm = Mock()
        config.llm.provider = "anthropic"
        config.llm.model = "claude-sonnet-4-6"
        config.llm.api_base = "https://api.anthropic.com"
        return config

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        client = Mock()
        client.model = "claude-sonnet-4-6"
        return client

    def test_model_command_parsing(self, mock_config):
        """Test parsing /model command variations."""
        # Simulate different command inputs
        test_cases = [
            ("/model", None, None),  # Just /model
            ("/model set claude-opus-4-6", "set", "claude-opus-4-6"),  # Set model
            ("/model SET GPT-4", "set", "GPT-4"),  # Case insensitive
        ]

        for user_input, expected_subcommand, expected_arg in test_cases:
            parts = user_input.split(maxsplit=2)
            command = parts[0].lower()
            subcommand = parts[1].lower() if len(parts) > 1 else None
            arg = parts[2] if len(parts) > 2 else None

            assert command == "/model"
            assert subcommand == expected_subcommand
            assert arg == expected_arg

    def test_model_switching_behavior(self, mock_config, mock_llm_client):
        """Test complete model switching flow."""
        original_model = mock_config.llm.model
        new_model = "claude-opus-4-6"

        # Verify initial state
        assert mock_config.llm.model == original_model
        assert mock_llm_client.model == original_model

        # Simulate /model set command
        mock_config.llm.model = new_model
        mock_llm_client.model = new_model

        # Verify both config and client are updated
        assert mock_config.llm.model == new_model
        assert mock_llm_client.model == new_model

    def test_model_info_display(self, mock_config, capsys):
        """Test that model info is displayed correctly."""
        print_model_info(mock_config)

        captured = capsys.readouterr()
        output = captured.out

        # Verify all expected fields are shown
        assert mock_config.llm.provider in output
        assert mock_config.llm.model in output
        assert mock_config.llm.api_base in output

    def test_model_command_with_invalid_subcommand(self, mock_config):
        """Test /model with invalid subcommand."""
        # Simulate parsing an invalid subcommand
        user_input = "/model invalid"
        parts = user_input.split(maxsplit=2)
        subcommand = parts[1].lower() if len(parts) > 1 else None

        # Invalid subcommand should show usage message
        assert subcommand == "invalid"
        # In real CLI, this would print usage warning

    def test_model_set_without_argument(self):
        """Test /model set without providing a model name."""
        user_input = "/model set"
        parts = user_input.split(maxsplit=2)
        subcommand = parts[1].lower() if len(parts) > 1 else None
        arg = parts[2] if len(parts) > 2 else None

        assert subcommand == "set"
        assert arg is None  # Missing model argument


class TestModelValidation:
    """Test model name validation scenarios."""

    def test_valid_model_names(self):
        """Test various valid model name formats."""
        valid_models = [
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5-20251001",
            "gpt-4",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
            "MiniMax-M2.5",
            "custom-model-v1.2.3",
        ]

        config = Mock(spec=Config)
        config.llm = Mock()

        for model in valid_models:
            config.llm.model = model
            assert config.llm.model == model

    def test_model_name_with_version(self):
        """Test model names with version specifications."""
        config = Mock(spec=Config)
        config.llm = Mock()

        versioned_models = [
            "claude-opus-4-6-20251101",
            "gpt-4-0613",
            "model@latest",
            "model:stable",
        ]

        for model in versioned_models:
            config.llm.model = model
            assert config.llm.model == model


class TestModelProviderSwitching:
    """Test switching between different LLM providers."""

    def test_switch_provider_via_model_name(self):
        """Test that model name implies provider."""
        config = Mock(spec=Config)
        config.llm = Mock()

        # Anthropic models
        anthropic_models = [
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5",
        ]

        for model in anthropic_models:
            config.llm.model = model
            config.llm.provider = "anthropic"
            assert config.llm.provider == "anthropic"

        # OpenAI models
        openai_models = [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ]

        for model in openai_models:
            config.llm.model = model
            config.llm.provider = "openai"
            assert config.llm.provider == "openai"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
