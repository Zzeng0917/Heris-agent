"""Mode system placeholder - modes have been removed."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ModeType(Enum):
    """Available agent modes."""
    NORMAL = "normal"


@dataclass
class AgentMode:
    """Represents an agent mode with its configuration."""

    mode_type: ModeType
    urgency: Optional[str] = None
    custom_persona: Optional[str] = None

    def build_prompt_injection(self) -> str:
        """Build the prompt injection text for this mode."""
        return ""

    @property
    def display_name(self) -> str:
        """Get the display name for this mode."""
        return "普通模式"

    @property
    def description(self) -> str:
        """Get the description for this mode."""
        return "标准助手模式，专业高效地完成任务"

    def to_dict(self) -> dict:
        """Convert mode to dictionary for serialization."""
        return {"mode_type": self.mode_type.value}

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMode":
        """Create mode from dictionary."""
        return cls(mode_type=ModeType(data.get("mode_type", "normal")))


def get_mode_choices() -> list[tuple[ModeType, str, str]]:
    """Get list of mode choices for UI display."""
    return [(ModeType.NORMAL, "普通模式", "标准助手模式，专业高效地完成任务")]


def create_mode_from_string(mode_str: str) -> AgentMode:
    """Create an AgentMode from a string identifier."""
    return AgentMode(mode_type=ModeType.NORMAL)
