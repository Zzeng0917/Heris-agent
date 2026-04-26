"""Tests for the /model slash command functionality - updated for ModelsConfig."""

import pytest
from unittest.mock import Mock

from heris.cli import (
    get_models_config,
    COMMAND_CATEGORIES,
    SLASH_COMMANDS,
    LIGHT_THEME,
    SlashCommandPicker,
)
from heris.config import ModelsConfig


class TestModelDefinitions:
    """Test the new model definitions structure."""

    def test_available_models_structure(self):
        """Test that ModelsConfig follows the expected structure."""
        models_cfg = get_models_config()
        assert len(models_cfg.models) > 0

        for model in models_cfg.models:
            assert isinstance(model.id, str)
            assert isinstance(model.provider, str)
            assert isinstance(model.name, str)
            assert isinstance(model.max_tokens, int)
            assert isinstance(model.context, int)

            # Check tier values
            assert model.tier in ["premium", "standard", "basic", "experimental"]

    def test_providers_defined(self):
        """Test that providers are defined in ModelsConfig."""
        models_cfg = get_models_config()
        assert len(models_cfg.providers) > 0

        for key, provider in models_cfg.providers.items():
            assert isinstance(provider.name, str)
            assert isinstance(provider.color, str)
            assert isinstance(provider.api_base, str)

    def test_all_model_providers_defined(self):
        """Test that all model providers are defined."""
        models_cfg = get_models_config()
        providers_in_models = set(m.provider for m in models_cfg.models)
        for provider in providers_in_models:
            assert provider in models_cfg.providers, f"Provider {provider} not defined"


class TestSlashCommands:
    """Test the new slash command structure."""

    def test_slash_commands_format(self):
        """Test that SLASH_COMMANDS uses the new 4-element format."""
        for item in SLASH_COMMANDS:
            assert len(item) == 4
            cmd, desc, category, icon = item
            assert isinstance(cmd, str)
            assert isinstance(desc, str)
            assert isinstance(category, str)
            assert isinstance(icon, str)
            assert category in COMMAND_CATEGORIES

    def test_command_categories(self):
        """Test that COMMAND_CATEGORIES is properly defined."""
        for category, (name, color) in COMMAND_CATEGORIES.items():
            assert isinstance(name, str)
            assert isinstance(color, str)

    def test_all_commands_have_valid_categories(self):
        """Test that all commands reference valid categories."""
        for cmd, desc, category, icon in SLASH_COMMANDS:
            assert category in COMMAND_CATEGORIES, f"Invalid category: {category}"


class TestLightTheme:
    """Tests for the LIGHT_THEME color scheme."""

    def test_light_theme_has_required_keys(self):
        """Test that LIGHT_THEME has all required color keys."""
        required_keys = [
            "border", "border_bright", "title", "highlight_bg", "highlight_fg",
            "text_primary", "text_secondary", "accent_cyan", "accent_magenta",
            "accent_green", "accent_yellow", "dim", "reset"
        ]
        for key in required_keys:
            assert key in LIGHT_THEME, f"Missing key: {key}"

    def test_light_theme_values_are_strings(self):
        """Test that all LIGHT_THEME values are strings (ANSI codes)."""
        for key, value in LIGHT_THEME.items():
            assert isinstance(value, str), f"{key} should be a string"
            assert value.startswith("\033["), f"{key} should be an ANSI escape code"


class TestSlashCommandPicker:
    """Tests for the SlashCommandPicker class."""

    def test_build_command_list(self):
        """Test SlashCommandPicker._build_command_list()."""
        picker = SlashCommandPicker()
        commands = picker.commands

        assert len(commands) > 0

        # Check that we have headers and commands
        headers = [c for c in commands if c["type"] == "header"]
        cmds = [c for c in commands if c["type"] == "command"]

        assert len(headers) > 0
        assert len(cmds) > 0

    def test_get_selectable_items(self):
        """Test SlashCommandPicker._get_selectable_items()."""
        picker = SlashCommandPicker()
        selectable = picker._get_selectable_items()

        # All selectable items should be commands
        for item in selectable:
            assert item["type"] == "command"

    def test_command_navigation(self):
        """Test navigation methods."""
        picker = SlashCommandPicker()
        picker.current_index = picker._get_display_index(0)
        picker.scroll_offset = 0

        # Test that we have items to navigate
        selectable = picker._get_selectable_items()
        assert len(selectable) > 0

        # Test initial state
        assert picker.current_index >= 0


class TestModelCommand:
    """Tests for the /model command functionality."""

    def test_available_model_ids(self):
        """Test that all model IDs are accessible."""
        models_cfg = get_models_config()
        model_ids = {m.id for m in models_cfg.models}
        assert len(model_ids) > 0
        assert "claude-sonnet-4-6" in model_ids
        assert "gpt-4o" in model_ids
        assert "gemini-2.0-flash" in model_ids

    def test_model_command_in_slash_commands(self):
        """Test that /model command is in SLASH_COMMANDS."""
        model_cmds = [c for c in SLASH_COMMANDS if c[0] == "/model"]
        assert len(model_cmds) == 1
        cmd, desc, category, icon = model_cmds[0]
        assert desc == "Show or set model"
        assert category == "model"


class TestMainstreamModels:
    """Tests to verify mainstream models are included."""

    def test_anthropic_models_present(self):
        """Test that Anthropic models are included."""
        models_cfg = get_models_config()
        model_ids = [m.id for m in models_cfg.models]
        assert "claude-sonnet-4-6" in model_ids
        assert "claude-opus-4-6" in model_ids
        assert "claude-haiku-4-5" in model_ids

    def test_openai_models_present(self):
        """Test that OpenAI models are included."""
        models_cfg = get_models_config()
        model_ids = [m.id for m in models_cfg.models]
        assert "gpt-4" in model_ids
        assert "gpt-4o" in model_ids
        assert "gpt-4o-mini" in model_ids
        assert "o1" in model_ids
        assert "o3-mini" in model_ids
        assert "gpt-5" in model_ids

    def test_gemini_models_present(self):
        """Test that Gemini models are included."""
        models_cfg = get_models_config()
        model_ids = [m.id for m in models_cfg.models]
        assert "gemini-2.0-flash" in model_ids
        assert "gemini-2.0-flash-lite" in model_ids

    def test_deepseek_models_present(self):
        """Test that DeepSeek models are included."""
        models_cfg = get_models_config()
        model_ids = [m.id for m in models_cfg.models]
        assert "deepseek-chat" in model_ids
        assert "deepseek-reasoner" in model_ids
        assert "deepseek-coder" in model_ids


class TestModelsConfig:
    """Tests for ModelsConfig functionality."""

    def test_get_model(self):
        """Test get_model() method."""
        models_cfg = get_models_config()
        model = models_cfg.get_model("claude-sonnet-4-6")
        assert model is not None
        assert model.id == "claude-sonnet-4-6"
        assert model.provider == "anthropic"

    def test_get_model_not_found(self):
        """Test get_model() returns None for unknown model."""
        models_cfg = get_models_config()
        model = models_cfg.get_model("nonexistent-model")
        assert model is None

    def test_get_provider(self):
        """Test get_provider() method."""
        models_cfg = get_models_config()
        provider = models_cfg.get_provider("anthropic")
        assert provider is not None
        assert provider.name == "Anthropic"

    def test_get_model_api_base(self):
        """Test get_model_api_base() returns provider api_base."""
        models_cfg = get_models_config()
        api_base = models_cfg.get_model_api_base("claude-sonnet-4-6")
        assert api_base is not None
        # Should return the provider's api_base, not model override
        provider = models_cfg.get_provider("anthropic")
        assert api_base == provider.api_base


if __name__ == "__main__":
    pytest.main([__file__, "-v"])