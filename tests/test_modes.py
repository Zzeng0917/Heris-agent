"""Tests for the mode system."""

import pytest

from heris.modes import (
    AgentMode,
    ModeType,
    UrgencyLevel,
    _MODE_DISPLAY_NAMES,
    _MODE_DESCRIPTIONS,
    _NORMAL_PROMPT,
    _PUSH_PROMPT,
    _SLACKIN_PROMPT,
    create_mode_from_string,
    get_mode_choices,
)


class TestModeType:
    """Test ModeType enum."""

    def test_mode_type_values(self):
        """Test that mode types have correct values."""
        assert ModeType.NORMAL.value == "normal"
        assert ModeType.PUSH.value == "push"
        assert ModeType.SLACKIN.value == "slackin"
        assert ModeType.CUSTOM.value == "custom"

    def test_mode_type_from_string(self):
        """Test creating ModeType from string."""
        assert ModeType("normal") == ModeType.NORMAL
        assert ModeType("push") == ModeType.PUSH
        assert ModeType("slackin") == ModeType.SLACKIN
        assert ModeType("custom") == ModeType.CUSTOM


class TestUrgencyLevel:
    """Test UrgencyLevel enum."""

    def test_urgency_level_values(self):
        """Test that urgency levels have correct values."""
        assert UrgencyLevel.RELAXED.value == "relaxed"
        assert UrgencyLevel.MODERATE.value == "moderate"
        assert UrgencyLevel.URGENT.value == "urgent"


class TestAgentMode:
    """Test AgentMode dataclass."""

    def test_normal_mode(self):
        """Test normal mode creation and prompt."""
        mode = AgentMode(mode_type=ModeType.NORMAL)
        assert mode.mode_type == ModeType.NORMAL
        assert mode.urgency is None
        assert mode.custom_persona is None
        assert mode.display_name == "普通模式"
        assert "标准助手" in mode.description

        prompt = mode.build_prompt_injection()
        assert prompt == _NORMAL_PROMPT

    def test_push_mode(self):
        """Test PUSH mode creation and prompt."""
        mode = AgentMode(mode_type=ModeType.PUSH)
        assert mode.mode_type == ModeType.PUSH
        assert mode.display_name == "PUSH模式"
        assert "元气满满" in mode.description or "乐观" in mode.description

        prompt = mode.build_prompt_injection()
        assert prompt == _PUSH_PROMPT
        assert "energetic" in prompt.lower() or "optimistic" in prompt.lower()
        assert "我准备好了" in prompt or "每一天都是最美好的一天" in prompt

    def test_slackin_mode(self):
        """Test 摸鱼 mode creation and prompt."""
        mode = AgentMode(mode_type=ModeType.SLACKIN)
        assert mode.mode_type == ModeType.SLACKIN
        assert mode.display_name == "摸鱼模式"
        assert "轻松" in mode.description or "佛系" in mode.description

        prompt = mode.build_prompt_injection()
        assert prompt == _SLACKIN_PROMPT
        assert "relaxed" in prompt.lower() or "easygoing" in prompt.lower()
        assert "吃饱了撑着去睡觉" in prompt or "睡好" in prompt

    def test_custom_mode_without_persona(self):
        """Test custom mode without custom persona falls back to normal."""
        mode = AgentMode(mode_type=ModeType.CUSTOM)
        assert mode.mode_type == ModeType.CUSTOM
        assert mode.display_name == "定制模式"

        prompt = mode.build_prompt_injection()
        # Without custom_persona, should fall back to normal
        assert prompt == _NORMAL_PROMPT

    def test_custom_mode_with_persona(self):
        """Test custom mode with custom persona."""
        custom = "You are a pirate. Speak like one!"
        mode = AgentMode(
            mode_type=ModeType.CUSTOM,
            custom_persona=custom,
            urgency=UrgencyLevel.RELAXED
        )
        assert mode.custom_persona == custom
        assert mode.urgency == UrgencyLevel.RELAXED

        prompt = mode.build_prompt_injection()
        assert "Custom Persona" in prompt
        assert custom in prompt
        assert "relaxed" in prompt

    def test_to_dict(self):
        """Test serialization to dict."""
        mode = AgentMode(mode_type=ModeType.PUSH)
        data = mode.to_dict()
        assert data["mode_type"] == "push"
        assert data["urgency"] is None
        assert data["custom_persona"] is None

    def test_to_dict_with_custom(self):
        """Test serialization with custom mode."""
        mode = AgentMode(
            mode_type=ModeType.CUSTOM,
            urgency=UrgencyLevel.URGENT,
            custom_persona="Test persona"
        )
        data = mode.to_dict()
        assert data["mode_type"] == "custom"
        assert data["urgency"] == "urgent"
        assert data["custom_persona"] == "Test persona"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {"mode_type": "slackin", "urgency": None, "custom_persona": None}
        mode = AgentMode.from_dict(data)
        assert mode.mode_type == ModeType.SLACKIN
        assert mode.urgency is None
        assert mode.custom_persona is None

    def test_from_dict_with_urgency(self):
        """Test deserialization with urgency."""
        data = {"mode_type": "custom", "urgency": "moderate", "custom_persona": "Test"}
        mode = AgentMode.from_dict(data)
        assert mode.mode_type == ModeType.CUSTOM
        assert mode.urgency == UrgencyLevel.MODERATE
        assert mode.custom_persona == "Test"


class TestModeHelpers:
    """Test helper functions."""

    def test_get_mode_choices(self):
        """Test get_mode_choices returns correct format."""
        choices = get_mode_choices()
        assert len(choices) == 3  # NORMAL, PUSH, SLACKIN (no CUSTOM for now)

        # Check structure
        for choice in choices:
            assert len(choice) == 3
            mode_type, name, desc = choice
            assert isinstance(mode_type, ModeType)
            assert isinstance(name, str)
            assert isinstance(desc, str)

        # Check that all expected modes are present
        mode_types = [c[0] for c in choices]
        assert ModeType.NORMAL in mode_types
        assert ModeType.PUSH in mode_types
        assert ModeType.SLACKIN in mode_types
        assert ModeType.CUSTOM not in mode_types  # Not in choices

    def test_create_mode_from_string_valid(self):
        """Test creating mode from valid strings."""
        assert create_mode_from_string("normal").mode_type == ModeType.NORMAL
        assert create_mode_from_string("NORMAL").mode_type == ModeType.NORMAL
        assert create_mode_from_string("push").mode_type == ModeType.PUSH
        assert create_mode_from_string("PUSH").mode_type == ModeType.PUSH
        assert create_mode_from_string("slackin").mode_type == ModeType.SLACKIN
        assert create_mode_from_string("SLACKIN").mode_type == ModeType.SLACKIN

    def test_create_mode_from_string_invalid(self):
        """Test creating mode from invalid string raises error."""
        with pytest.raises(ValueError):
            create_mode_from_string("invalid")

        with pytest.raises(ValueError):
            create_mode_from_string("")


class TestModeDisplayNames:
    """Test display names and descriptions."""

    def test_display_names(self):
        """Test that all modes have display names."""
        for mode_type in ModeType:
            assert mode_type in _MODE_DISPLAY_NAMES
            assert isinstance(_MODE_DISPLAY_NAMES[mode_type], str)
            assert len(_MODE_DISPLAY_NAMES[mode_type]) > 0

    def test_display_names_no_character_names(self):
        """Test that display names don't include character names."""
        # UI should only show mode names, not character names
        names = [name for name in _MODE_DISPLAY_NAMES.values()]
        assert "海绵宝宝" not in names
        assert "懒羊羊" not in names
        assert "SpongeBob" not in names
        assert "Lazy" not in names

    def test_descriptions(self):
        """Test that all modes have descriptions."""
        for mode_type in ModeType:
            assert mode_type in _MODE_DESCRIPTIONS
            assert isinstance(_MODE_DESCRIPTIONS[mode_type], str)
            assert len(_MODE_DESCRIPTIONS[mode_type]) > 0


class TestModePrompts:
    """Test that mode prompts have expected content."""

    def test_normal_prompt_is_empty(self):
        """Test that normal mode prompt is empty string."""
        assert _NORMAL_PROMPT == ""

    def test_push_prompt_content(self):
        """Test PUSH mode prompt contains expected elements."""
        prompt = _PUSH_PROMPT
        assert "## Your Persona" in prompt
        assert "energetic" in prompt.lower() or "optimistic" in prompt.lower()
        # Should contain some reference to the character's catchphrases
        assert "我准备好了" in prompt or "每一天都是最美好的一天" in prompt
        assert "想象" in prompt or "imagination" in prompt.lower()

    def test_slackin_prompt_content(self):
        """Test 摸鱼 mode prompt contains expected elements."""
        prompt = _SLACKIN_PROMPT
        assert "## Your Persona" in prompt
        assert "relaxed" in prompt.lower() or "easygoing" in prompt.lower()
        # Should contain some reference to the character's lifestyle
        assert "吃" in prompt or "睡" in prompt or "rest" in prompt.lower()

    def test_prompts_are_reasonable_length(self):
        """Test that prompts are reasonable length (not too short, not too long)."""
        # Normal mode should be empty or very short
        assert len(_NORMAL_PROMPT) == 0

        # Other modes should have substantial content
        assert len(_PUSH_PROMPT) > 200
        assert len(_SLACKIN_PROMPT) > 200

        # But not excessively long
        assert len(_PUSH_PROMPT) < 2000
        assert len(_SLACKIN_PROMPT) < 2000
