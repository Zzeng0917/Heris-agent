"""Tests for the /model slash command functionality - updated for Kode-Agent design."""

import pytest
from unittest.mock import Mock

from heris.cli import (
    AVAILABLE_MODELS,
    PROVIDERS,
    COMMAND_CATEGORIES,
    SLASH_COMMANDS,
    LIGHT_THEME,
    ModelSelector,
    SlashCommandPicker,
)


class TestModelDefinitions:
    """Test the new model definitions structure."""

    def test_available_models_structure(self):
        """Test that AVAILABLE_MODELS follows the expected structure."""
        assert len(AVAILABLE_MODELS) > 0

        for model_id, provider, name, specs in AVAILABLE_MODELS:
            assert isinstance(model_id, str)
            assert isinstance(provider, str)
            assert isinstance(name, str)
            assert isinstance(specs, dict)

            # Check required fields
            assert "max_tokens" in specs
            assert "context" in specs
            assert "description" in specs
            assert "tier" in specs

            # Check tier values
            assert specs["tier"] in ["premium", "standard", "basic", "experimental"]

    def test_providers_structure(self):
        """Test that PROVIDERS follows the expected structure."""
        for key, value in PROVIDERS.items():
            assert "name" in value
            assert "color" in value

    def test_all_model_providers_defined(self):
        """Test that all model providers are defined in PROVIDERS."""
        providers_in_models = set(m[1] for m in AVAILABLE_MODELS)
        for provider in providers_in_models:
            assert provider in PROVIDERS, f"Provider {provider} not defined"


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


class TestModelSelector:
    """Tests for the ModelSelector class with new structure."""

    def test_model_selector_init(self):
        """Test ModelSelector initialization."""
        config = Mock()
        config.llm.model = "gpt-4o"
        config.llm.provider = Mock(value="openai")

        llm_client = Mock()

        selector = ModelSelector(config, llm_client)

        assert selector.current_index == 0
        assert selector._num_lines == 0
        assert len(selector.models) > 0

    def test_model_selector_build_list(self):
        """Test ModelSelector._build_model_list()."""
        config = Mock()
        config.llm.model = "gpt-4o"
        config.llm.provider = Mock(value="openai")

        llm_client = Mock()
        selector = ModelSelector(config, llm_client)
        models = selector.models

        assert len(models) > 0

        # First item should be "keep current"
        assert models[0]["is_current"] == True

        # Check that we have headers and models
        headers = [m for m in models if m.get("tier") == "header"]
        model_items = [m for m in models if m.get("tier") != "header" and not m.get("is_current")]

        assert len(headers) > 0
        assert len(model_items) > 0

    def test_is_selectable(self):
        """Test ModelSelector._is_selectable()."""
        config = Mock()
        config.llm.model = "gpt-4o"
        config.llm.provider = Mock(value="openai")

        llm_client = Mock()
        selector = ModelSelector(config, llm_client)

        # Headers should not be selectable
        header = {"id": None, "tier": "header"}
        assert selector._is_selectable(header) == False

        # Normal models should be selectable
        model = {"id": "gpt-4", "tier": "standard"}
        assert selector._is_selectable(model) == True

        # Keep current should be selectable
        current = {"id": "default", "is_current": True}
        assert selector._is_selectable(current) == True

    def test_format_context(self):
        """Test ModelSelector._format_context()."""
        config = Mock()
        config.llm.model = "gpt-4o"
        config.llm.provider = Mock(value="openai")

        llm_client = Mock()
        selector = ModelSelector(config, llm_client)

        assert selector._format_context(1000) == "1.0K"
        assert selector._format_context(128000) == "128.0K"
        assert selector._format_context(2000000) == "2.0M"

    def test_tier_icons(self):
        """Test that ModelSelector has tier icons."""
        assert "premium" in ModelSelector.TIER_ICONS
        assert "standard" in ModelSelector.TIER_ICONS
        assert "basic" in ModelSelector.TIER_ICONS


class TestMainstreamModels:
    """Tests to verify mainstream models are included."""

    def test_anthropic_models_present(self):
        """Test that Anthropic models are included."""
        model_ids = [m[0] for m in AVAILABLE_MODELS]
        assert "claude-sonnet-4-6" in model_ids
        assert "claude-opus-4-6" in model_ids
        assert "claude-haiku-4-5" in model_ids

    def test_openai_models_present(self):
        """Test that OpenAI models are included."""
        model_ids = [m[0] for m in AVAILABLE_MODELS]
        assert "gpt-4" in model_ids
        assert "gpt-4o" in model_ids
        assert "gpt-4o-mini" in model_ids
        assert "o1" in model_ids
        assert "o3-mini" in model_ids
        assert "gpt-5" in model_ids

    def test_gemini_models_present(self):
        """Test that Gemini models are included."""
        model_ids = [m[0] for m in AVAILABLE_MODELS]
        assert "gemini-2.0-flash" in model_ids
        assert "gemini-2.0-flash-lite" in model_ids

    def test_deepseek_models_present(self):
        """Test that DeepSeek models are included."""
        model_ids = [m[0] for m in AVAILABLE_MODELS]
        assert "deepseek-chat" in model_ids
        assert "deepseek-reasoner" in model_ids
        assert "deepseek-coder" in model_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
