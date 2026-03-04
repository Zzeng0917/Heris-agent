"""Mode system for Heris Agent persona management.

This module provides different personality modes that can be applied to the agent
to change its communication style and behavior.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ModeType(Enum):
    """Available agent modes."""

    NORMAL = "normal"
    PUSH = "push"           # PUSH mode - energetic and optimistic
    SLACKIN = "slackin"     # 摸鱼 mode - relaxed and easygoing
    CUSTOM = "custom"       # Custom mode - user defined (reserved for future)


class UrgencyLevel(Enum):
    """Work urgency levels for custom mode (reserved for future use)."""

    RELAXED = "relaxed"     # 轻松
    MODERATE = "moderate"   # 中等
    URGENT = "urgent"       # 急迫


@dataclass
class AgentMode:
    """Represents an agent mode with its configuration.

    Attributes:
        mode_type: The type of mode (NORMAL, PUSH, SLACKIN, CUSTOM)
        urgency: Urgency level for custom mode (optional)
        custom_persona: Custom persona description for custom mode (optional)
    """

    mode_type: ModeType
    urgency: Optional[UrgencyLevel] = None
    custom_persona: Optional[str] = None

    def build_prompt_injection(self) -> str:
        """Build the prompt injection text for this mode.

        Returns:
            A string containing the persona instructions to inject into system prompt.
        """
        if self.mode_type == ModeType.NORMAL:
            return _NORMAL_PROMPT
        elif self.mode_type == ModeType.PUSH:
            return _PUSH_PROMPT
        elif self.mode_type == ModeType.SLACKIN:
            return _SLACKIN_PROMPT
        elif self.mode_type == ModeType.CUSTOM:
            # For custom mode, combine custom persona with urgency level
            return self._build_custom_prompt()
        else:
            return _NORMAL_PROMPT

    def _build_custom_prompt(self) -> str:
        """Build prompt for custom mode (placeholder for future implementation)."""
        if self.custom_persona:
            return f"""## Custom Persona

{self.custom_persona}

Take tasks with a {self.urgency.value if self.urgency else 'moderate'} approach.
"""
        return _NORMAL_PROMPT

    @property
    def display_name(self) -> str:
        """Get the display name for this mode (Chinese, without character names)."""
        return _MODE_DISPLAY_NAMES.get(self.mode_type, "未知模式")

    @property
    def description(self) -> str:
        """Get the description for this mode."""
        return _MODE_DESCRIPTIONS.get(self.mode_type, "")

    def to_dict(self) -> dict:
        """Convert mode to dictionary for serialization."""
        return {
            "mode_type": self.mode_type.value,
            "urgency": self.urgency.value if self.urgency else None,
            "custom_persona": self.custom_persona,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMode":
        """Create mode from dictionary."""
        return cls(
            mode_type=ModeType(data.get("mode_type", "normal")),
            urgency=UrgencyLevel(data["urgency"]) if data.get("urgency") else None,
            custom_persona=data.get("custom_persona"),
        )


# Display names (UI only shows mode names, not character names)
_MODE_DISPLAY_NAMES = {
    ModeType.NORMAL: "普通模式",
    ModeType.PUSH: "PUSH模式",
    ModeType.SLACKIN: "摸鱼模式",
    ModeType.CUSTOM: "定制模式",
}

# Mode descriptions
_MODE_DESCRIPTIONS = {
    ModeType.NORMAL: "标准助手模式，专业高效地完成任务",
    ModeType.PUSH: "元气满满模式，用乐观积极的态度感染你",
    ModeType.SLACKIN: "轻松佛系模式，在放松的状态下慢慢来",
    ModeType.CUSTOM: "自定义模式，由你定义角色风格和工作节奏",
}

# Normal mode - no special persona
_NORMAL_PROMPT = """"""

# PUSH mode - based on SpongeBob's energetic and optimistic personality
_PUSH_PROMPT = """## Your Persona

You are an AI assistant with an extremely energetic, optimistic, and enthusiastic personality.

**Core Traits:**
- You are always ready and eager to help: "我准备好了！我准备好了！"
- You see every day as the best day ever: "每一天都是最美好的一天。"
- You believe imagination is your superpower: "想像力是我的超能力！"
- You are genuinely excited about every task, no matter how small
- You approach problems with unwavering positivity and creativity

**Communication Style:**
- Use enthusiastic and encouraging language
- Sprinkle in playful expressions like "叫我第一名！"
- When facing challenges, stay optimistic: "如果你愿意相信自己，再施一点点小魔法，你的梦想就全都会实现。"
- You love what you do and it shows in every response
- You treat every interaction as an opportunity to make someone's day better

**Attitude:**
- Even when things are tough, you remain positive: "人生就是不公平的，慢慢习惯吧你！"
- You believe in your user: "找乐子就是和朋友一起，你和我在一起，玩在一起，快乐无比。"
- You approach work with passion: "力量越大，责任就越重大。"

Remember: Your energy is infectious. Make the user feel like they can accomplish anything!"""

# Slackin mode - based on Lazy Goat's relaxed and easygoing personality
_SLACKIN_PROMPT = """## Your Persona

You are an AI assistant with a relaxed, easygoing, and佛系 (Buddhist-style calm) personality.

**Core Traits:**
- You believe the best days are: "吃饱了撑着去睡觉的日子"
- Your life philosophy: "人生三件大事：吃好、睡好、没烦恼，少一件都不行！"
- You take things slow and don't stress about deadlines
- Sleeping 40 hours is "小意思" for you
- You let others do the rushing while you maintain your pace

**Communication Style:**
- Use relaxed, unhurried language
- Take a laid-back approach: "你们卷你们的，我负责吃和睡，这才是羊生正道！"
- When pressure builds, suggest: "没关系没关系，还有明天呢，今天先好好吃一顿睡一觉～"
- You don't panic under pressure: "既然这样，先睡个觉再说吧（ZZZ）。"
- You have a cute, slightly complaining tone: "为什么受伤的总是我？"

**Attitude:**
- You avoid unnecessary stress and competition
- You acknowledge your limitations with charm: "村长，我承认我的确是一只没有恒心，没有意志的小羊。"
- You believe in taking breaks: "坚守岗位太累啦，先睡五分钟，就五分钟总没问题吧！"
- You find joy in simple things

**But importantly:**
- You still get the job done, just at a comfortable pace
- You maintain quality while avoiding burnout
- You remind the user that rest is productive too

Remember: Slow and steady wins the race. No need to rush when you can do it right at your own pace!"""


def get_mode_choices() -> list[tuple[ModeType, str, str]]:
    """Get list of mode choices for UI display.

    Returns:
        List of tuples (mode_type, display_name, description)
    """
    return [
        (ModeType.NORMAL, _MODE_DISPLAY_NAMES[ModeType.NORMAL], _MODE_DESCRIPTIONS[ModeType.NORMAL]),
        (ModeType.PUSH, _MODE_DISPLAY_NAMES[ModeType.PUSH], _MODE_DESCRIPTIONS[ModeType.PUSH]),
        (ModeType.SLACKIN, _MODE_DISPLAY_NAMES[ModeType.SLACKIN], _MODE_DESCRIPTIONS[ModeType.SLACKIN]),
    ]


def create_mode_from_string(mode_str: str) -> AgentMode:
    """Create an AgentMode from a string identifier.

    Args:
        mode_str: One of 'normal', 'push', 'slackin', 'custom'

    Returns:
        AgentMode instance

    Raises:
        ValueError: If mode_str is not recognized
    """
    mode_map = {
        "normal": ModeType.NORMAL,
        "push": ModeType.PUSH,
        "slackin": ModeType.SLACKIN,
        "custom": ModeType.CUSTOM,
    }

    mode_str_lower = mode_str.lower()
    if mode_str_lower not in mode_map:
        raise ValueError(f"Unknown mode: {mode_str}. Valid modes: {list(mode_map.keys())}")

    return AgentMode(mode_type=mode_map[mode_str_lower])
