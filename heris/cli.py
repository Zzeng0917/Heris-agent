"""
Heris CLI - TypeScript UI 启动，Python Agent 交互
"""

import argparse
import asyncio
import platform
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import List

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import message_dialog, input_dialog
from prompt_toolkit.application import get_app

from heris import LLMClient
from heris.agents import Agent
from heris.config import Config
from heris.schema import LLMProvider
from heris.tools.base import Tool
from heris.tools.bash_tool import BashKillTool, BashOutputTool, BashTool
from heris.tools.file_tools import EditTool, ReadTool, WriteTool
from heris.tools.mcp_loader import cleanup_mcp_connections, load_mcp_tools_async, set_mcp_timeout_config
from heris.tools.note_tool import SessionNoteTool
from heris.tools.skill_tool import create_skill_tools
from heris.commands import cost_command


# Slash command definitions for interactive picker - organized by category
SLASH_COMMANDS = [
    # System commands
    ("/about", "Show version information", "system", "ℹ️"),
    ("/help", "Display help information", "system", "❓"),
    ("/clear", "Clear the terminal screen", "system", "🧹"),
    ("/exit", "Exit Heris", "system", "👋"),

    # Model commands
    ("/model", "Select model", "model", "🤖"),

    # Tool commands
    ("/tools", "List available tools", "tools", "🛠️"),
    ("/tools desc", "List tools with descriptions", "tools", "📖"),
    ("/mcp list", "List configured MCP servers", "tools", "🔌"),
    ("/mcp refresh", "Refresh MCP connections", "tools", "🔄"),

    # Session commands
    ("/chat save <tag>", "Save conversation", "session", "💾"),
    ("/chat load <tag>", "Load conversation", "session", "📂"),
    ("/chat list", "List saved conversations", "session", "📜"),
    ("/history", "Show message count", "session", "📊"),
    ("/stats", "Show session statistics", "session", "📈"),
    ("/cost", "Show API token usage and costs", "session", "💰"),
    ("/log", "View log directory", "session", "📝"),
]

# Category display configuration
COMMAND_CATEGORIES = {
    "system": ("System", "cyan"),
    "model": ("Model", "magenta"),
    "tools": ("Tools", "yellow"),
    "session": ("Session", "green"),
}


# Session save/load functions
def get_sessions_dir() -> Path:
    """Get the directory for saved sessions."""
    return Path.home() / ".heris" / "sessions"


def save_session(agent: Agent, tag: str) -> bool:
    """Save the current conversation session."""
    import json

    sessions_dir = get_sessions_dir()
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Create session file
    session_file = sessions_dir / f"{tag}.json"

    try:
        # Convert messages to serializable format
        messages_data = []
        for msg in agent.messages:
            msg_dict = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.thinking:
                msg_dict["thinking"] = msg.thinking
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            if msg.name:
                msg_dict["name"] = msg.name
            messages_data.append(msg_dict)

        session_data = {
            "timestamp": datetime.now().isoformat(),
            "messages": messages_data,
            "system_prompt": agent.system_prompt,
        }

        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        print(f"{Colors.ERROR}Failed to save session: {e}{Colors.RESET}")
        return False


def load_session(agent: Agent, tag: str) -> bool:
    """Load a saved conversation session."""
    import json
    from heris.schema import Message, ToolCall, FunctionCall

    sessions_dir = get_sessions_dir()
    session_file = sessions_dir / f"{tag}.json"

    if not session_file.exists():
        print(f"{Colors.ERROR}Session '{tag}' not found{Colors.RESET}")
        return False

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            session_data = json.load(f)

        # Restore messages
        messages = []
        for msg_dict in session_data.get("messages", []):
            tool_calls = None
            if msg_dict.get("tool_calls"):
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        type=tc["type"],
                        function=FunctionCall(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"],
                        )
                    )
                    for tc in msg_dict["tool_calls"]
                ]

            msg = Message(
                role=msg_dict["role"],
                content=msg_dict["content"],
                thinking=msg_dict.get("thinking"),
                tool_calls=tool_calls,
                tool_call_id=msg_dict.get("tool_call_id"),
                name=msg_dict.get("name"),
            )
            messages.append(msg)

        agent.messages = messages
        return True
    except Exception as e:
        print(f"{Colors.ERROR}Failed to load session: {e}{Colors.RESET}")
        return False


def list_sessions():
    """List all saved sessions."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    import json

    console = Console()
    sessions_dir = get_sessions_dir()

    if not sessions_dir.exists():
        console.print(Panel("[dim]No saved sessions[/dim]", title="Saved Sessions", border_style="dim"))
        return

    session_files = sorted(sessions_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not session_files:
        console.print(Panel("[dim]No saved sessions[/dim]", title="Saved Sessions", border_style="dim"))
        return

    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Tag", style="magenta")
    table.add_column("Saved At", style="white")
    table.add_column("Messages", style="dim", justify="right")

    for session_file in session_files[:20]:  # Show last 20
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            tag = session_file.stem
            saved_at = datetime.fromisoformat(data.get("timestamp", "")).strftime("%Y-%m-%d %H:%M")
            msg_count = len(data.get("messages", []))
            table.add_row(tag, saved_at, str(msg_count))
        except Exception:
            continue

    console.print(Panel(table, title="[bold]Saved Sessions[/bold]", border_style="dim"))
    console.print()


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Brand colors - Gemini CLI inspired
    BRAND = "\033[38;2;66;133;244m"
    BRIGHT_BRAND = "\033[38;2;91;160;255m"

    # Unified highlight color - used for selection highlighting
    # Light cyan background with dark text for visibility
    HIGHLIGHT = "\033[48;2;91;160;255m\033[30m"  # Light blue bg + black text
    HIGHLIGHT_TEXT = "\033[38;2;91;160;255m"  # Light blue text only

    # Semantic colors
    PRIMARY = "\033[36m"
    SECONDARY = "\033[90m"
    SUCCESS = "\033[32m"
    ERROR = "\033[31m"
    WARNING = "\033[33m"

    # Role colors
    USER = "\033[37m"
    ASSISTANT = "\033[96m"
    TOOL = "\033[35m"

    # Syntax highlighting
    CODE_KEYWORD = "\033[38;2;255;123;114m"
    CODE_FUNCTION = "\033[38;2;102;194;255m"
    CODE_STRING = "\033[38;2;195;232;141m"
    CODE_COMMENT = "\033[38;2;128;128;128m"

    # Compatibility aliases
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_WHITE = "\033[97m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    RED = "\033[31m"


def get_log_directory() -> Path:
    return Path.home() / ".heris" / "log"


def show_log_directory(open_file_manager: bool = True) -> None:
    log_dir = get_log_directory()
    print(f"\n{Colors.PRIMARY}日志目录: {Colors.RESET}{log_dir}")
    if not log_dir.exists() or not log_dir.is_dir():
        print(f"{Colors.ERROR}目录不存在{Colors.RESET}\n")
        return
    log_files = list(log_dir.glob("*.log"))
    if not log_files:
        print(f"{Colors.WARNING}暂无日志文件{Colors.RESET}\n")
        return
    log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    print(f"{Colors.SECONDARY}  最近日志文件:{Colors.RESET}")
    for i, log_file in enumerate(log_files[:5], 1):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        size = log_file.stat().st_size
        size_str = f"{size:,}" if size < 1024 else f"{size / 1024:.1f}K"
        print(f"  {Colors.PRIMARY}{i}.{Colors.RESET} {log_file.name} {Colors.SECONDARY}({mtime.strftime('%m-%d %H:%M')}, {size_str}){Colors.RESET}")
    if len(log_files) > 5:
        print(f"  {Colors.SECONDARY}... 还有 {len(log_files) - 5} 个文件{Colors.RESET}")
    if open_file_manager:
        _open_directory_in_file_manager(log_dir)
    print()


def _open_directory_in_file_manager(directory: Path) -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", str(directory)], check=False)
        elif system == "Windows":
            subprocess.run(["explorer", str(directory)], check=False)
        elif system == "Linux":
            subprocess.run(["xdg-open", str(directory)], check=False)
    except Exception:
        pass


def read_log_file(filename: str) -> None:
    log_dir = get_log_directory()
    log_file = log_dir / filename
    if not log_file.exists() or not log_file.is_file():
        print(f"\n{Colors.ERROR}日志文件不存在: {log_file}{Colors.RESET}\n")
        return
    print(f"\n{Colors.PRIMARY}查看: {Colors.RESET}{log_file}")
    print(f"{Colors.SECONDARY}{'─' * 60}{Colors.RESET}")
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        print(content)
        print(f"{Colors.SECONDARY}{'─' * 60}{Colors.RESET}\n")
    except Exception as e:
        print(f"\n{Colors.ERROR}读取失败: {e}{Colors.RESET}\n")


def print_help():
    """Print help with categorized commands - reference to Kode-Agent's Help component."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    from rich.columns import Columns

    console = Console()

    # Group commands by category
    categories = {}
    for cmd, desc, category, icon in SLASH_COMMANDS:
        if category not in categories:
            categories[category] = []
        categories[category].append((cmd, desc, icon))

    # Create a panel for each category
    panels = []
    for category in ["system", "model", "tools", "session"]:
        if category not in categories:
            continue

        cat_name, cat_color = COMMAND_CATEGORIES[category]

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style=cat_color, width=22)
        table.add_column(style="white")

        for cmd, desc, icon in categories[category]:
            table.add_row(f"{icon} {cmd}", desc)

        panel = Panel(table, title=f"[bold {cat_color}]{cat_name}[/bold {cat_color}]", border_style="bright_black", box=box.ROUNDED)
        panels.append(panel)

    console.print()
    console.print(Panel("[bold]Heris Commands[/bold]", border_style="cyan", box=box.DOUBLE))

    # Display command panels in columns
    if panels:
        console.print(Columns(panels, equal=True))

    # Shortcuts panel
    shortcuts = Table(show_header=False, box=None, padding=(0, 1))
    shortcuts.add_column(style="bright_cyan", width=12)
    shortcuts.add_column(style="white")
    shortcuts.add_row("Esc", "Cancel current task")
    shortcuts.add_row("Ctrl+C", "Exit program")
    shortcuts.add_row("Ctrl+U", "Clear input line")
    shortcuts.add_row("Ctrl+L", "Clear screen")
    shortcuts.add_row("Ctrl+J", "New line")
    shortcuts.add_row("↑/↓", "Browse history")
    shortcuts.add_row("Tab", "Show completions")

    console.print(Panel(shortcuts, title="[bold bright_cyan]Keyboard Shortcuts[/bold bright_cyan]", border_style="bright_black", box=box.ROUNDED))
    console.print()


def print_about():
    """Print version and about information."""
    from rich.console import Console
    from rich.panel import Panel
    from rich import box

    console = Console()

    info = """[bold]Heris[/bold] - AI assistant with file tools and MCP support

Version: 0.1.0
Python: {}""".format(sys.version.split()[0])

    console.print(Panel(info, title="[bold]About[/bold]", border_style="bright_black", box=box.ROUNDED))
    console.print()


def print_tools(agent: Agent, show_descriptions: bool = False):
    """Print available tools."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    console = Console()

    if show_descriptions:
        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED, border_style="bright_black")
        table.add_column("Tool", style="magenta", width=20)
        table.add_column("Description", style="white")

        for name, tool in agent.tools.items():
            desc = getattr(tool, 'description', 'No description')
            table.add_row(name, desc)
    else:
        table = Table(show_header=False, box=box.ROUNDED, border_style="bright_black")
        table.add_column(style="magenta")
        for name in agent.tools.keys():
            table.add_row(f"  {name}")

    console.print(Panel(table, title="[bold]Available Tools[/bold]", border_style="bright_black", box=box.ROUNDED))
    console.print()


# Model definitions - reference to Kode-Agent's models.ts design
# Provider display names and base URLs
PROVIDERS = {
    "openai": {"name": "OpenAI", "color": "bright_green"},
    "anthropic": {"name": "Anthropic", "color": "bright_yellow"},
    "gemini": {"name": "Gemini", "color": "bright_blue"},
    "mistral": {"name": "Mistral", "color": "bright_cyan"},
    "deepseek": {"name": "DeepSeek", "color": "bright_magenta"},
    "xai": {"name": "xAI", "color": "bright_white"},
    "groq": {"name": "Groq", "color": "bright_red"},
}

# Available models with full specifications (reference to Kode-Agent's models.ts)
AVAILABLE_MODELS = [
    # Anthropic Models
    ("claude-sonnet-4-6", "anthropic", "Claude Sonnet 4.6", {
        "max_tokens": 8192,
        "context": 200000,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Balanced performance and speed",
        "tier": "standard"
    }),
    ("claude-opus-4-6", "anthropic", "Claude Opus 4.6", {
        "max_tokens": 8192,
        "context": 200000,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Most capable model for complex tasks",
        "tier": "premium"
    }),
    ("claude-haiku-4-5", "anthropic", "Claude Haiku 4.5", {
        "max_tokens": 4096,
        "context": 200000,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Fast and efficient for simple tasks",
        "tier": "basic"
    }),

    # OpenAI Models
    ("gpt-4", "openai", "GPT-4", {
        "max_tokens": 4096,
        "context": 8192,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "Original GPT-4 model",
        "tier": "standard"
    }),
    ("gpt-4o", "openai", "GPT-4o", {
        "max_tokens": 16384,
        "context": 128000,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Omni model with vision capabilities",
        "tier": "standard"
    }),
    ("gpt-4o-mini", "openai", "GPT-4o Mini", {
        "max_tokens": 16384,
        "context": 128000,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Cost-effective with vision support",
        "tier": "basic"
    }),
    ("gpt-4.5-preview", "openai", "GPT-4.5 Preview", {
        "max_tokens": 16384,
        "context": 128000,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Latest preview model",
        "tier": "premium"
    }),
    ("o1", "openai", "o1", {
        "max_tokens": 100000,
        "context": 200000,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Reasoning model for complex tasks",
        "tier": "premium"
    }),
    ("o3-mini", "openai", "o3-mini", {
        "max_tokens": 100000,
        "context": 200000,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "Fast reasoning model",
        "tier": "standard"
    }),
    ("gpt-5", "openai", "GPT-5", {
        "max_tokens": 32768,
        "context": 200000,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Latest GPT-5 model",
        "tier": "premium"
    }),
    ("gpt-5-mini", "openai", "GPT-5 Mini", {
        "max_tokens": 16384,
        "context": 128000,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Efficient GPT-5 variant",
        "tier": "standard"
    }),
    ("gpt-5-nano", "openai", "GPT-5 Nano", {
        "max_tokens": 8192,
        "context": 64000,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "Fastest GPT-5 variant",
        "tier": "basic"
    }),

    # Gemini Models
    ("gemini-2.0-flash", "gemini", "Gemini 2.0 Flash", {
        "max_tokens": 8192,
        "context": 1048576,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Fast multimodal model",
        "tier": "standard"
    }),
    ("gemini-2.0-flash-lite", "gemini", "Gemini 2.0 Flash Lite", {
        "max_tokens": 8192,
        "context": 1048576,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Lightweight fast model",
        "tier": "basic"
    }),
    ("gemini-2.0-flash-thinking-exp", "gemini", "Gemini 2.0 Flash Thinking", {
        "max_tokens": 8192,
        "context": 1048576,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "Experimental thinking model",
        "tier": "experimental"
    }),

    # Mistral Models
    ("mistral-large-latest", "mistral", "Mistral Large", {
        "max_tokens": 128000,
        "context": 128000,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "Most capable Mistral model",
        "tier": "premium"
    }),
    ("mistral-small-latest", "mistral", "Mistral Small", {
        "max_tokens": 8191,
        "context": 32000,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "Efficient Mistral model",
        "tier": "standard"
    }),

    # DeepSeek Models
    ("deepseek-reasoner", "deepseek", "DeepSeek Reasoner", {
        "max_tokens": 8192,
        "context": 65536,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "Reasoning-specialized model",
        "tier": "standard"
    }),
    ("deepseek-chat", "deepseek", "DeepSeek Chat", {
        "max_tokens": 8192,
        "context": 65536,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "General chat model",
        "tier": "standard"
    }),
    ("deepseek-coder", "deepseek", "DeepSeek Coder", {
        "max_tokens": 4096,
        "context": 128000,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "Code-optimized model",
        "tier": "standard"
    }),

    # xAI Models
    ("grok-beta", "xai", "Grok Beta", {
        "max_tokens": 131072,
        "context": 131072,
        "supports_vision": True,
        "supports_function_calling": True,
        "description": "xAI's Grok model",
        "tier": "standard"
    }),

    # Groq Models
    ("llama-3.3-70b-versatile", "groq", "Llama 3.3 70B", {
        "max_tokens": 8192,
        "context": 128000,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "Fast Llama 3.3 on Groq",
        "tier": "standard"
    }),
    ("llama-3.1-8b-instant", "groq", "Llama 3.1 8B", {
        "max_tokens": 8000,
        "context": 8000,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "Fast Llama 3.1 on Groq",
        "tier": "basic"
    }),
    ("mixtral-8x7b-32768", "groq", "Mixtral 8x7B", {
        "max_tokens": 32768,
        "context": 32768,
        "supports_vision": False,
        "supports_function_calling": True,
        "description": "Mixtral MoE on Groq",
        "tier": "standard"
    }),
]


class SlashCommandPicker:
    """Interactive slash command picker - reference to Kode-Agent's Select component design.

    Displays categorized slash commands with icons, scrollable interface,
    and rich visual feedback.
    """

    VISIBLE_COUNT = 8

    def __init__(self):
        self.current_index = 0
        self.scroll_offset = 0
        self.commands = self._build_command_list()
        self._num_lines = 0

    def _build_command_list(self):
        """Build categorized command list."""
        commands = []

        # Group commands by category
        categories = {}
        for cmd, desc, category, icon in SLASH_COMMANDS:
            if category not in categories:
                categories[category] = []
            categories[category].append({
                "command": cmd,
                "description": desc,
                "icon": icon,
                "category": category
            })

        # Flatten with category headers
        for category in ["system", "model", "tools", "session"]:
            if category in categories:
                cat_name, cat_color = COMMAND_CATEGORIES[category]
                # Add category header
                commands.append({
                    "type": "header",
                    "label": cat_name.upper(),
                    "color": cat_color
                })
                # Add commands in this category
                for cmd in categories[category]:
                    commands.append({
                        "type": "command",
                        "command": cmd["command"],
                        "description": cmd["description"],
                        "icon": cmd["icon"],
                        "category": category
                    })

        return commands

    def _get_selectable_items(self):
        """Get only selectable command items (not headers)."""
        return [c for c in self.commands if c["type"] == "command"]

    def _get_display_items(self):
        """Get items for display with headers."""
        return self.commands

    def _get_display_index(self, selectable_idx):
        """Convert selectable index to display index."""
        selectable = self._get_selectable_items()
        if selectable_idx < 0 or selectable_idx >= len(selectable):
            return 0
        target = selectable[selectable_idx]
        for i, item in enumerate(self.commands):
            if item == target:
                return i
        return 0

    def _get_selectable_index(self, display_idx):
        """Convert display index to selectable index."""
        selectable = self._get_selectable_items()
        target = self.commands[display_idx]
        for i, item in enumerate(selectable):
            if item == target:
                return i
        return 0

    def _move_up(self):
        """Move selection up."""
        selectable = self._get_selectable_items()
        current_selectable = self._get_selectable_index(self.current_index)
        new_selectable = (current_selectable - 1) % len(selectable)
        self.current_index = self._get_display_index(new_selectable)

        # Adjust scroll
        visible_selectable = [i for i in range(len(self.commands))
                              if self.commands[i]["type"] == "command"]
        current_pos = visible_selectable.index(self.current_index)
        if current_pos < self.scroll_offset:
            self.scroll_offset = max(0, current_pos)

    def _move_down(self):
        """Move selection down."""
        selectable = self._get_selectable_items()
        current_selectable = self._get_selectable_index(self.current_index)
        new_selectable = (current_selectable + 1) % len(selectable)
        self.current_index = self._get_display_index(new_selectable)

        # Adjust scroll
        visible_selectable = [i for i in range(len(self.commands))
                              if self.commands[i]["type"] == "command"]
        current_pos = visible_selectable.index(self.current_index)
        visible_in_category = len([i for i in visible_selectable
                                   if self.scroll_offset <= visible_selectable.index(i) < self.scroll_offset + self.VISIBLE_COUNT])
        if current_pos >= self.scroll_offset + self.VISIBLE_COUNT:
            self.scroll_offset = current_pos - self.VISIBLE_COUNT + 1

    def _clear_and_redraw(self):
        """Clear and redraw the picker with light color theme."""
        import sys

        t = LIGHT_THEME

        if self._num_lines > 0:
            sys.stdout.write(f"\033[{self._num_lines}A")
            sys.stdout.write("\033[J")

        lines = []

        # Title bar with soft border
        lines.append(f"{t['border']}╭{'─' * 58}╮{t['reset']}")
        lines.append(f"{t['border']}│{t['reset']}  {t['title']}📋 Slash Commands{t['reset']}  (↑/↓ to move, Enter to select, Esc to cancel)  {t['border']}│{t['reset']}")
        lines.append(f"{t['border']}├{'─' * 58}┤{t['reset']}")

        # Get visible selectable items
        selectable_indices = [i for i in range(len(self.commands))
                              if self.commands[i]["type"] == "command"]

        # Calculate visible range
        start_idx = self.scroll_offset
        end_idx = min(start_idx + self.VISIBLE_COUNT, len(selectable_indices))

        for i in range(start_idx, end_idx):
            display_idx = selectable_indices[i]
            item = self.commands[display_idx]

            # Check if previous item was a header
            if display_idx > 0 and self.commands[display_idx - 1]["type"] == "header":
                header = self.commands[display_idx - 1]
                # Use accent colors for headers instead of bright colors
                header_colors = {
                    "cyan": t['accent_cyan'],
                    "magenta": t['accent_magenta'],
                    "green": t['accent_green'],
                    "yellow": t['accent_yellow'],
                }
                cat_color = header_colors.get(header["color"], t['accent_cyan'])
                lines.append(f"{t['border']}│{t['reset']}  {cat_color}◆ {header['label']}{t['reset']}")

            if display_idx == self.current_index:
                # Selected item - with light blue highlight background
                line = f"{t['border']}│{t['reset']}  {t['highlight_bg']}{t['highlight_fg']}▸ {item['icon']} {item['command']:<20}{t['reset']} {t['text_secondary']}{item['description'][:25]:<25}{t['reset']}"
            else:
                # Normal item - use soft colors
                category_colors = {
                    "system": t['accent_cyan'],
                    "model": t['accent_magenta'],
                    "tools": t['accent_yellow'],
                    "session": t['accent_green'],
                }
                cat_color = category_colors.get(item['category'], t['text_primary'])
                line = f"{t['border']}│{t['reset']}  {t['dim']}  {item['icon']} {cat_color}{item['command']:<20}{t['reset']} {t['text_secondary']}{item['description'][:25]:<25}{t['reset']}"
            lines.append(line)

        # Show scroll indicator
        if end_idx < len(selectable_indices):
            lines.append(f"{t['border']}│{t['reset']}  {t['dim']}  ↓ {len(selectable_indices) - end_idx} more commands...{t['reset']}")

        lines.append(f"{t['border']}╰{'─' * 58}╯{t['reset']}")

        output = "\n".join(lines)
        print(output)
        sys.stdout.flush()
        self._num_lines = len(lines)

    async def run(self) -> str | None:
        """Run the command picker. Returns selected command or None if cancelled."""
        import sys
        import termios
        import tty
        import select

        self.current_index = self._get_display_index(0)
        self.scroll_offset = 0
        self._num_lines = 0
        self._clear_and_redraw()

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        selected = None
        cancelled = False

        try:
            tty.setcbreak(fd)

            while selected is None and not cancelled:
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                if rlist:
                    char = sys.stdin.read(1)

                    if char == '\x1b':  # ESC
                        try:
                            next_char = sys.stdin.read(1)
                            if next_char == '[':
                                arrow = sys.stdin.read(1)
                                if arrow == 'A':  # Up
                                    self._move_up()
                                    self._clear_and_redraw()
                                elif arrow == 'B':  # Down
                                    self._move_down()
                                    self._clear_and_redraw()
                            else:
                                cancelled = True
                        except:
                            cancelled = True
                    elif char == '\n' or char == '\r':  # Enter
                        if self.commands[self.current_index]["type"] == "command":
                            selected = self.commands[self.current_index]["command"]
                    elif char == '\x03':  # Ctrl+C
                        cancelled = True

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        # Clear display
        if self._num_lines > 0:
            sys.stdout.write(f"\033[{self._num_lines}A")
            sys.stdout.write("\033[J")

        if cancelled:
            return None
        return selected


# Light color scheme for terminal UI (no black/white background)
# Using soft pastel colors for better visibility
LIGHT_THEME = {
    "border": "\033[38;2;100;149;237m",      # Cornflower blue
    "border_bright": "\033[38;2;135;206;250m",  # Light sky blue
    "title": "\033[38;2;70;130;180m",        # Steel blue
    "highlight_bg": "\033[48;2;230;245;255m",   # Very light blue background
    "highlight_fg": "\033[38;2;25;55;95m",   # Dark blue text on highlight
    "text_primary": "\033[38;2;50;50;50m",   # Dark gray
    "text_secondary": "\033[38;2;100;100;100m", # Medium gray
    "accent_cyan": "\033[38;2;0;150;180m",   # Cyan
    "accent_magenta": "\033[38;2;180;80;150m", # Magenta
    "accent_green": "\033[38;2;60;150;80m",  # Green
    "accent_yellow": "\033[38;2;200;160;50m", # Yellow
    "dim": "\033[38;2;150;150;150m",         # Light gray
    "reset": "\033[0m",
}


class ModelSelector:
    """Model selector that displays inline below the input with terminal control sequences.

    Displays up to 5 visible items, but supports scrolling through a larger list.
    """

    VISIBLE_COUNT = 5  # Maximum number of visible items

    def __init__(self, config: Config, llm_client):
        self.config = config
        self.llm_client = llm_client
        self.current_index = 0
        self.scroll_offset = 0  # Tracks which item is at the top of the visible list
        self.models = self._build_model_list()
        self._num_lines = 0

    TIER_ICONS = {
        "premium": "💎",
        "standard": "⭐",
        "basic": "🔹",
        "experimental": "🔬"
    }

    def _build_model_list(self):
        """Build the list of models to display with full specs."""
        current_model = self.config.llm.model
        current_provider = self.config.llm.provider.value if hasattr(self.config.llm.provider, 'value') else str(self.config.llm.provider)
        models = []

        # First option: Keep current
        models.append({
            "id": "default",
            "name": f"🔄 Keep Current ({current_model})",
            "meta": f"{current_provider} • Continue with current model",
            "is_current": True,
            "tier": "current"
        })

        # Group models by provider
        by_provider = {}
        for model_id, provider, name, specs in AVAILABLE_MODELS:
            if provider not in by_provider:
                by_provider[provider] = []
            by_provider[provider].append({
                "id": model_id,
                "name": name,
                "provider": provider,
                **specs
            })

        # Add models grouped by provider
        for provider in ["anthropic", "openai", "gemini", "mistral", "deepseek", "xai", "groq"]:
            if provider not in by_provider:
                continue

            # Add provider header
            provider_info = PROVIDERS.get(provider, {"name": provider, "color": "white"})
            models.append({
                "id": None,  # Header, not selectable
                "name": f"═══ {provider_info['name'].upper()} ═══",
                "meta": "",
                "is_current": False,
                "tier": "header"
            })

            # Add models for this provider
            for model in by_provider[provider]:
                if model["id"] == current_model:
                    continue  # Skip current model
                models.append({
                    "id": model["id"],
                    "name": f"{self.TIER_ICONS.get(model.get('tier', 'standard'), '⭐')} {model['name']}",
                    "meta": f"{self._format_context(model.get('context', 0))} ctx • {model.get('description', '')}",
                    "is_current": False,
                    "tier": model.get("tier", "standard"),
                    "raw_name": model["name"]
                })

        return models

    def _format_context(self, tokens: int) -> str:
        """Format context length for display."""
        if tokens >= 1000000:
            return f"{tokens / 1000000:.1f}M"
        elif tokens >= 1000:
            return f"{tokens / 1000:.1f}K"
        return str(tokens)

    def _is_selectable(self, model):
        """Check if a model entry is selectable (not a header)."""
        return model.get("id") is not None

    def _get_selectable_indices(self):
        """Get indices of all selectable items."""
        return [i for i, m in enumerate(self.models) if self._is_selectable(m)]

    def _move_up(self):
        """Move selection up and adjust scroll if needed."""
        selectable = self._get_selectable_indices()
        if not selectable:
            return

        # Find current position in selectable items
        current_pos = selectable.index(self.current_index) if self.current_index in selectable else 0
        new_pos = (current_pos - 1) % len(selectable)
        self.current_index = selectable[new_pos]

        # Adjust scroll
        if self.current_index < self.scroll_offset:
            self.scroll_offset = self.current_index

    def _move_down(self):
        """Move selection down and adjust scroll if needed."""
        selectable = self._get_selectable_indices()
        if not selectable:
            return

        # Find current position in selectable items
        current_pos = selectable.index(self.current_index) if self.current_index in selectable else 0
        new_pos = (current_pos + 1) % len(selectable)
        self.current_index = selectable[new_pos]

        # Adjust scroll
        if self.current_index >= self.scroll_offset + self.VISIBLE_COUNT:
            self.scroll_offset = self.current_index - self.VISIBLE_COUNT + 1

    def _clear_and_redraw(self):
        """Clear previous output and redraw the options (scrollable view) with light theme."""
        import sys

        t = LIGHT_THEME

        # Move cursor up and clear lines if we've printed before
        if self._num_lines > 0:
            sys.stdout.write(f"\033[{self._num_lines}A")
            sys.stdout.write("\033[J")

        lines = []
        lines.append(f"{t['border']}╭{'─' * 58}╮{t['reset']}")
        lines.append(f"{t['border']}│{t['reset']}  {t['title']}🤖 Model Selector{t['reset']}  (↑/↓ to move, Enter to select, Esc to cancel)  {t['border']}│{t['reset']}")
        lines.append(f"{t['border']}├{'─' * 58}┤{t['reset']}")

        # Calculate visible range
        start_idx = self.scroll_offset
        end_idx = min(start_idx + self.VISIBLE_COUNT, len(self.models))

        shown_count = 0
        for i in range(start_idx, len(self.models)):
            if shown_count >= self.VISIBLE_COUNT:
                break

            model = self.models[i]

            # Handle headers
            if model.get("tier") == "header":
                lines.append(f"{t['border']}│{t['reset']}  {t['accent_cyan']}◆ {model['name']}{t['reset']}")
                continue

            shown_count += 1

            if i == self.current_index:
                # Selected item - with light blue highlight background
                if model.get("is_current"):
                    line = f"{t['border']}│{t['reset']}  {t['highlight_bg']}{t['highlight_fg']}▸ {model['name']:<45}{t['reset']}"
                else:
                    line = f"{t['border']}│{t['reset']}  {t['highlight_bg']}{t['highlight_fg']}▸ {model['name']:<35}{t['reset']} {t['text_secondary']}{model['meta'][:20]:<20}{t['reset']}"
            else:
                # Normal item - soft colors
                if model.get("is_current"):
                    line = f"{t['border']}│{t['reset']}  {t['dim']}  {model['name']:<45}{t['reset']}"
                else:
                    tier_colors = {
                        "premium": t['accent_magenta'],
                        "standard": t['accent_cyan'],
                        "basic": t['accent_green'],
                        "experimental": t['accent_yellow'],
                    }
                    tier_color = tier_colors.get(model.get("tier"), t['text_primary'])
                    line = f"{t['border']}│{t['reset']}  {t['dim']}  {tier_color}{model['name'][:35]:<35}{t['reset']} {t['text_secondary']}{model['meta'][:20]:<20}{t['reset']}"
            lines.append(line)

        # Show more indicator
        selectable_count = len([m for m in self.models if self._is_selectable(m)])
        visible_selectable = len([i for i in range(start_idx, end_idx) if self._is_selectable(self.models[i])])
        remaining = selectable_count - visible_selectable - (self._get_selectable_indices().index(self.current_index) if self.current_index in self._get_selectable_indices() else 0) + 1
        if remaining > 0:
            lines.append(f"{t['border']}│{t['reset']}  {t['dim']}  ↓ {remaining} more models...{t['reset']}")

        lines.append(f"{t['border']}╰{'─' * 58}╯{t['reset']}")

        output = "\n".join(lines)
        print(output)
        sys.stdout.flush()

        self._num_lines = len(lines)

    def _print_final(self):
        """Print final selection - only show selected item with light theme."""
        import sys

        t = LIGHT_THEME

        # Clear previous output
        if self._num_lines > 0:
            sys.stdout.write(f"\033[{self._num_lines}A")
            sys.stdout.write("\033[J")

        selected = self.models[self.current_index]
        print(f"{t['border']}╭{'─' * 58}╮{t['reset']}")
        if selected.get("is_current"):
            print(f"{t['border']}│{t['reset']}  {t['accent_green']}✓ {selected['name']:<50}{t['reset']} {t['border']}│{t['reset']}")
        else:
            raw_name = selected.get('raw_name', selected['name'].replace('💎 ', '').replace('⭐ ', '').replace('🔹 ', '').replace('🔬 ', ''))
            print(f"{t['border']}│{t['reset']}  {t['accent_green']}✓ {raw_name:<50}{t['reset']} {t['border']}│{t['reset']}")
        print(f"{t['border']}╰{'─' * 58}╯{t['reset']}")

    async def run(self) -> bool:
        """Run the model selector. Returns True if model was changed."""
        import sys
        import termios
        import tty
        import select

        # Start at first selectable item
        selectable = self._get_selectable_indices()
        self.current_index = selectable[0] if selectable else 0
        self.scroll_offset = 0
        self._num_lines = 0
        self._clear_and_redraw()

        # Save terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        selected_model = None
        cancelled = False

        try:
            tty.setcbreak(fd)

            while selected_model is None and not cancelled:
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                if rlist:
                    char = sys.stdin.read(1)

                    if char == '\x1b':  # ESC sequence
                        try:
                            next_char = sys.stdin.read(1)
                            if next_char == '[':
                                arrow = sys.stdin.read(1)
                                if arrow == 'A':  # Up arrow
                                    self._move_up()
                                    self._clear_and_redraw()
                                elif arrow == 'B':  # Down arrow
                                    self._move_down()
                                    self._clear_and_redraw()
                            else:
                                # ESC key alone - cancel
                                cancelled = True
                        except:
                            cancelled = True
                    elif char == '\n' or char == '\r':  # Enter
                        selected_model = self.models[self.current_index]
                    elif char == '\x03':  # Ctrl+C
                        cancelled = True

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        if cancelled or selected_model is None:
            # Clear the selector display
            if self._num_lines > 0:
                sys.stdout.write(f"\033[{self._num_lines}A")
                sys.stdout.write("\033[J")
            print(f"{Colors.SECONDARY}Cancelled{Colors.RESET}")
            return False

        if selected_model["id"] == "default":
            # Clear and show final state
            if self._num_lines > 0:
                sys.stdout.write(f"\033[{self._num_lines}A")
                sys.stdout.write("\033[J")
            print(f"{Colors.SECONDARY}Using current model: {self.config.llm.model}{Colors.RESET}")
            return False

        # Update model
        self.config.llm.model = selected_model["id"]
        self.llm_client.model = selected_model["id"]

        # Show final selection
        self._print_final()
        print(f"{Colors.SUCCESS}✓ Model set to: {selected_model['id']}{Colors.RESET}")
        return True


def print_model_info(config: Config):
    """Print current model information."""
    from rich.console import Console
    from rich.panel import Panel
    from rich import box

    console = Console()

    info = f"""Provider: [cyan]{config.llm.provider}[/cyan]
Model: [cyan]{config.llm.model}[/cyan]
API Base: [dim]{config.llm.api_base}[/dim]"""

    console.print(Panel(info, title="[bold]Model Configuration[/bold]", border_style="bright_black", box=box.ROUNDED))
    console.print()


def print_session_info(agent: Agent, workspace_dir: Path, model: str):
    from rich.console import Console
    from rich.panel import Panel
    from rich import box
    console = Console()

    info_text = f"[dim]Responding with[/dim] [cyan]{model}[/cyan]"
    console.print(Panel(info_text, border_style="bright_black", expand=False, padding=(0, 1), box=box.ROUNDED))
    console.print()


def print_stats(agent: Agent, session_start: datetime):
    duration = datetime.now() - session_start
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    user_msgs = sum(1 for m in agent.messages if m.role == "user")
    assistant_msgs = sum(1 for m in agent.messages if m.role == "assistant")
    tool_msgs = sum(1 for m in agent.messages if m.role == "tool")
    print(f"\n{Colors.SECONDARY}  会话时长: {hours:02d}:{minutes:02d}:{seconds:02d} | "
          f"消息: {len(agent.messages)} (用户{user_msgs}/助手{assistant_msgs}/工具{tool_msgs})", end="")
    if agent.api_total_tokens > 0:
        print(f" | Token: {agent.api_total_tokens:,}")
    else:
        print()
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Heris - AI assistant with file tools and MCP support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--workspace", "-w", type=str, default=None)
    parser.add_argument("--task", "-t", type=str, default=None)
    parser.add_argument("--version", "-v", action="version", version="heris 0.1.0")
    subparsers = parser.add_subparsers(dest="command")
    log_parser = subparsers.add_parser("log")
    log_parser.add_argument("filename", nargs="?", default=None)
    return parser.parse_args()


async def initialize_base_tools(config: Config):
    tools = []
    skill_loader = None

    if config.tools.enable_bash:
        tools.append(BashOutputTool())
        tools.append(BashKillTool())

    if config.tools.enable_skills:
        try:
            skills_path = Path(config.tools.skills_dir).expanduser()
            if skills_path.is_absolute():
                skills_dir = str(skills_path)
            else:
                search_paths = [
                    skills_path,
                    Path("heris") / skills_path,
                    Config.get_package_dir() / skills_path,
                ]
                skills_dir = str(skills_path)
                for path in search_paths:
                    if path.exists():
                        skills_dir = str(path.resolve())
                        break
            skill_tools, skill_loader = create_skill_tools(skills_dir)
            if skill_tools:
                tools.extend(skill_tools)
        except Exception:
            pass

    if config.tools.enable_mcp:
        try:
            mcp_config = config.tools.mcp
            set_mcp_timeout_config(
                connect_timeout=mcp_config.connect_timeout,
                execute_timeout=mcp_config.execute_timeout,
                sse_read_timeout=mcp_config.sse_read_timeout,
            )
            mcp_config_path = Config.find_config_file(config.tools.mcp_config_path)
            if mcp_config_path:
                mcp_tools = await load_mcp_tools_async(str(mcp_config_path))
                if mcp_tools:
                    tools.extend(mcp_tools)
        except Exception:
            pass

    return tools, skill_loader


def add_workspace_tools(tools: List[Tool], config: Config, workspace_dir: Path):
    workspace_dir.mkdir(parents=True, exist_ok=True)
    if config.tools.enable_bash:
        tools.append(BashTool(workspace_dir=str(workspace_dir)))
    if config.tools.enable_file_tools:
        tools.extend([
            ReadTool(workspace_dir=str(workspace_dir)),
            WriteTool(workspace_dir=str(workspace_dir)),
            EditTool(workspace_dir=str(workspace_dir)),
        ])
    if config.tools.enable_note:
        tools.append(SessionNoteTool(memory_file=str(workspace_dir / ".agent_memory.json")))


async def _quiet_cleanup():
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(lambda _loop, _ctx: None)
    try:
        await cleanup_mcp_connections()
    except Exception:
        pass


async def run_agent(workspace_dir: Path, task: str = None):
    session_start = datetime.now()

    config_path = Config.get_default_config_path()
    if not config_path.exists():
        print(f"{Colors.ERROR}配置文件未找到{Colors.RESET}\n")
        return

    try:
        config = Config.from_yaml(config_path)
    except Exception as e:
        print(f"{Colors.ERROR}加载配置失败: {e}{Colors.RESET}")
        return

    from heris.retry import RetryConfig as RetryConfigBase

    retry_config = RetryConfigBase(
        enabled=config.llm.retry.enabled,
        max_retries=config.llm.retry.max_retries,
        initial_delay=config.llm.retry.initial_delay,
        max_delay=config.llm.retry.max_delay,
        exponential_base=config.llm.retry.exponential_base,
        retryable_exceptions=(Exception,),
    )

    def on_retry(exception: Exception, attempt: int):
        next_delay = retry_config.calculate_delay(attempt - 1)
        print(f"\n{Colors.WARNING}  请求失败 ({attempt}/{retry_config.max_retries})，{next_delay:.1f}s 后重试...{Colors.RESET}")

    provider = LLMProvider.ANTHROPIC if config.llm.provider.lower() == "anthropic" else LLMProvider.OPENAI
    llm_client = LLMClient(
        api_key=config.llm.api_key,
        provider=provider,
        api_base=config.llm.api_base,
        model=config.llm.model,
        retry_config=retry_config if config.llm.retry.enabled else None,
    )
    if config.llm.retry.enabled:
        llm_client.retry_callback = on_retry

    tools, skill_loader = await initialize_base_tools(config)
    add_workspace_tools(tools, config, workspace_dir)

    system_prompt_path = Config.find_config_file(config.agent.system_prompt_path)
    if system_prompt_path and system_prompt_path.exists():
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = "You are Heris, an intelligent assistant."

    if skill_loader:
        skills_metadata = skill_loader.get_skills_metadata_prompt()
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata or "")
    else:
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

    agent = Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=tools,
        max_steps=config.agent.max_steps,
        workspace_dir=str(workspace_dir),
    )

    # 非交互模式
    if task:
        print(f"\n{Colors.SECONDARY}  执行任务...{Colors.RESET}\n")
        agent.add_user_message(task)
        try:
            await agent.run()
        except Exception as e:
            print(f"\n{Colors.ERROR}  错误: {e}{Colors.RESET}")
        finally:
            print_stats(agent, session_start)
        await _quiet_cleanup()
        return

    # 交互模式：显示会话信息
    print_session_info(agent, workspace_dir, config.llm.model)

    # 构建 prompt_toolkit session with slash command completer
    class SlashCommandCompleter(Completer):
        """Completer for slash commands with icons and descriptions."""

        def get_completions(self, document, complete_event):
            text = document.text
            if not text.startswith('/'):
                return

            for cmd, desc, category, icon in SLASH_COMMANDS:
                if cmd.startswith(text):
                    cat_name, _ = COMMAND_CATEGORIES.get(category, ("Other", "white"))
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=f"{icon} {cmd}",
                        display_meta=f"[{cat_name}] {desc}"
                    )

    # Style for the interface - unified light highlight theme
    # Using consistent light blue (#5ba0ff) for all selection highlights
    style = Style.from_dict({
        'prompt': '#00aaaa bold',
        'completion-menu': 'bg:#1a1a1a #ffffff',
        'completion-menu.completion': 'bg:#1a1a1a #ffffff',
        # Light highlight with dark text for current selection - matches ModelSelector
        'completion-menu.completion.current': 'bg:#5ba0ff #000000 bold',
        'completion-menu.meta': '#888888',
        'completion-menu.meta.current': '#333333',
    })

    # Key bindings
    kb = KeyBindings()

    @kb.add('c-c')
    @kb.add('c-d')
    def _(event):
        event.app.exit(result=None)

    @kb.add('c-u')
    def _(event):
        event.app.current_buffer.reset()

    @kb.add('c-l')
    def _(event):
        event.app.renderer.clear()

    @kb.add('c-j')
    def _(event):
        event.app.current_buffer.insert_text('\n')

    @kb.add('c-i')  # Tab key to start completion
    def _(event):
        event.app.current_buffer.start_completion(select_first=False)

    # History
    history_file = Path.home() / ".heris" / ".history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    # Create completer
    slash_completer = SlashCommandCompleter()

    # Session with completion
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=slash_completer,
        style=style,
        key_bindings=kb,
        complete_style='multi_column',
        complete_while_typing=True,
    )

    # 交互循环
    while True:
        try:
            user_input = await session.prompt_async(
                [("class:prompt", "> "), ("", "")],
                multiline=False,
            )
            # Handle None (Ctrl+C/Ctrl+D) and empty input
            if user_input is None:
                print(f"\n{Colors.BRAND}  再见!{Colors.RESET}\n")
                print_stats(agent, session_start)
                break
            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                # If just "/" is typed, show the interactive slash command picker
                if user_input == "/":
                    picker = SlashCommandPicker()
                    selected = await picker.run()
                    if selected:
                        user_input = selected
                        # Re-parse the selected command
                        parts = user_input.split(maxsplit=2)
                        command = parts[0].lower()
                        subcommand = parts[1].lower() if len(parts) > 1 else None
                        arg = parts[2] if len(parts) > 2 else None
                    else:
                        continue
                else:
                    parts = user_input.split(maxsplit=2)
                    command = parts[0].lower()
                    subcommand = parts[1].lower() if len(parts) > 1 else None
                    arg = parts[2] if len(parts) > 2 else None

                if command in ["/exit", "/quit", "/q"]:
                    print(f"\n{Colors.BRAND}  再见!{Colors.RESET}\n")
                    print_stats(agent, session_start)
                    break

                elif command == "/about":
                    print_about()

                elif command == "/help" or command == "/?":
                    print_help()

                elif command == "/clear":
                    from rich.console import Console
                    from rich.panel import Panel
                    from rich import box

                    console = Console()

                    # Check if there's anything to clear
                    if len(agent.messages) <= 1:
                        console.print(Panel(
                            "[dim]No conversation history to clear.[/dim]",
                            border_style="bright_black",
                            box=box.ROUNDED
                        ))
                        console.print()
                        continue

                    old_count = len(agent.messages)
                    user_messages = old_count - 1  # Exclude system message

                    # Show warning and ask for confirmation
                    console.print()
                    console.print(Panel(
                        f"[bold yellow]⚠️  Warning[/bold yellow]\n\n"
                        f"You are about to clear [bold]{user_messages}[/bold] messages from the conversation history.\n"
                        f"[red]This action cannot be undone.[/red]",
                        title="[bold]Clear Conversation[/bold]",
                        border_style="yellow",
                        box=box.DOUBLE
                    ))

                    try:
                        response = console.input("Continue? ([yes]/no): ").strip().lower()
                    except KeyboardInterrupt:
                        console.print("\n[dim]Cancelled.[/dim]\n")
                        continue

                    if response in ("yes", "y", ""):
                        agent.messages = [agent.messages[0]]

                        # Clear the terminal screen
                        import os
                        os.system('cls' if os.name == 'nt' else 'clear')

                        # Print success message at the top
                        console.print()
                        console.print(Panel(
                            f"[green]✓[/green] Cleared {user_messages} messages. Starting fresh conversation.",
                            border_style="green",
                            box=box.ROUNDED
                        ))
                        console.print()
                    else:
                        console.print(Panel(
                            "[dim]Operation cancelled. Conversation history preserved.[/dim]",
                            border_style="bright_black",
                            box=box.ROUNDED
                        ))
                        console.print()

                elif command == "/history":
                    print(f"\n{Colors.SECONDARY}  当前消息数: {len(agent.messages)}{Colors.RESET}\n")

                elif command == "/stats":
                    print_stats(agent, session_start)

                elif command == "/cost":
                    from rich.console import Console
                    console = Console()
                    cost_command(agent, console, session_start)

                elif command == "/log" or command.startswith("/log "):
                    parts2 = user_input.split(maxsplit=1)
                    if len(parts2) == 1:
                        show_log_directory(open_file_manager=True)
                    else:
                        read_log_file(parts2[1].strip("\"'"))

                elif command == "/model":
                    # Show interactive model selector inline
                    selector = ModelSelector(config, llm_client)
                    await selector.run()

                elif command == "/tools":
                    show_desc = subcommand in ["desc", "descriptions"]
                    print_tools(agent, show_descriptions=show_desc)

                elif command == "/mcp":
                    if subcommand is None or subcommand in ["list", "ls"]:
                        # List MCP servers
                        from rich.console import Console
                        from rich.panel import Panel
                        console = Console()
                        if hasattr(config.tools, 'mcp_config_path') and config.tools.mcp_config_path:
                            console.print(Panel(f"MCP Config: [cyan]{config.tools.mcp_config_path}[/cyan]", border_style="bright_black", box=box.ROUNDED))
                        else:
                            console.print(Panel("[dim]No MCP servers configured[/dim]", border_style="bright_black", box=box.ROUNDED))
                    elif subcommand == "refresh":
                        print(f"{Colors.SECONDARY}Refreshing MCP connections...{Colors.RESET}")
                        # Reload MCP tools
                        if config.tools.enable_mcp:
                            try:
                                mcp_config = config.tools.mcp
                                set_mcp_timeout_config(
                                    connect_timeout=mcp_config.connect_timeout,
                                    execute_timeout=mcp_config.execute_timeout,
                                    sse_read_timeout=mcp_config.sse_read_timeout,
                                )
                                mcp_config_path = Config.find_config_file(config.tools.mcp_config_path)
                                if mcp_config_path:
                                    mcp_tools = await load_mcp_tools_async(str(mcp_config_path))
                                    if mcp_tools:
                                        # Update agent tools
                                        for tool in mcp_tools:
                                            agent.tools[tool.name] = tool
                                        from rich.console import Console
                                        from rich.panel import Panel
                                        Console().print(Panel(f"Loaded {len(mcp_tools)} MCP tools", border_style="green"))
                            except Exception as e:
                                print(f"{Colors.ERROR}Failed to refresh MCP: {e}{Colors.RESET}")
                    else:
                        print(f"{Colors.WARNING}Unknown /mcp command: {subcommand}{Colors.RESET}")

                elif command == "/chat":
                    if subcommand == "save":
                        if arg:
                            if save_session(agent, arg):
                                from rich.console import Console
                                from rich.panel import Panel
                                Console().print(Panel(f"Session saved as [cyan]{arg}[/cyan]", border_style="green"))
                        else:
                            print(f"{Colors.WARNING}Usage: /chat save <tag>{Colors.RESET}")
                    elif subcommand == "load":
                        if arg:
                            if load_session(agent, arg):
                                from rich.console import Console
                                from rich.panel import Panel
                                Console().print(Panel(f"Session [cyan]{arg}[/cyan] loaded", border_style="green"))
                        else:
                            print(f"{Colors.WARNING}Usage: /chat load <tag>{Colors.RESET}")
                    elif subcommand in ["list", "ls"]:
                        list_sessions()
                    else:
                        print(f"{Colors.WARNING}Usage: /chat save/load/list{Colors.RESET}")

                else:
                    print(f"{Colors.WARNING}  未知命令: {user_input}，输入 /help 查看帮助{Colors.RESET}\n")
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print(f"\n{Colors.BRAND}  再见!{Colors.RESET}\n")
                print_stats(agent, session_start)
                break

            agent.add_user_message(user_input)

            cancel_event = asyncio.Event()
            agent.cancel_event = cancel_event
            esc_listener_stop = threading.Event()
            esc_cancelled = [False]

            def esc_key_listener():
                if platform.system() == "Windows":
                    try:
                        import msvcrt
                        while not esc_listener_stop.is_set():
                            if msvcrt.kbhit():
                                char = msvcrt.getch()
                                if char == b"\x1b":
                                    print(f"\n{Colors.WARNING}  取消中...{Colors.RESET}")
                                    esc_cancelled[0] = True
                                    cancel_event.set()
                                    break
                            esc_listener_stop.wait(0.05)
                    except Exception:
                        pass
                    return
                try:
                    import select, termios, tty
                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)
                    try:
                        tty.setcbreak(fd)
                        while not esc_listener_stop.is_set():
                            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                            if rlist:
                                char = sys.stdin.read(1)
                                if char == "\x1b":
                                    print(f"\n{Colors.WARNING}  取消中...{Colors.RESET}")
                                    esc_cancelled[0] = True
                                    cancel_event.set()
                                    break
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass

            esc_thread = threading.Thread(target=esc_key_listener, daemon=True)
            esc_thread.start()

            try:
                agent_task = asyncio.create_task(agent.run())
                while not agent_task.done():
                    if esc_cancelled[0]:
                        cancel_event.set()
                    await asyncio.sleep(0.1)
                _ = agent_task.result()
            except asyncio.CancelledError:
                print(f"\n{Colors.WARNING}  已取消{Colors.RESET}")
            finally:
                agent.cancel_event = None
                esc_listener_stop.set()
                esc_thread.join(timeout=0.2)

            print()

        except KeyboardInterrupt:
            print(f"\n\n{Colors.BRAND}  再见!{Colors.RESET}\n")
            print_stats(agent, session_start)
            break
        except Exception as e:
            print(f"\n{Colors.ERROR}  错误: {e}{Colors.RESET}\n")

    await _quiet_cleanup()


def run_python_ui() -> bool:
    """运行 Python 启动 UI。"""
    from rich.console import Console

    console = Console()

    # Heris brand ASCII art - Gemini CLI inspired gradient
    art_lines = [
        "",
        "  ██   ██  ███████  ██████   ███████  ███████",
        "  ██   ██  ██       ██   ██    ██     ██     ",
        "  ███████  █████    ██████     ██     ███████",
        "  ██   ██  ██       ██   ██    ██          ██",
        "  ██   ██  ███████  ██   ██  ███████  ███████",
        "                                           v0.1.0"
    ]

    colors = ["#4285f4", "#5b9bd5", "#74b3d6", "#8dcbd7", "#a6e3d8", "#34a853", "#4285f4"]
    for i, line in enumerate(art_lines):
        color = colors[i % len(colors)]
        console.print(f"  [{color}]{line}[/{color}]")

    console.print("  [dim]" + "─" * 50 + "[/dim]\n")

    return True


def main():
    args = parse_args()

    if args.command == "log":
        if args.filename:
            read_log_file(args.filename)
        else:
            show_log_directory(open_file_manager=True)
        return

    if args.workspace:
        workspace_dir = Path(args.workspace).expanduser().absolute()
    else:
        workspace_dir = Path.cwd()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # 非交互任务模式，跳过 UI
    if args.task:
        asyncio.run(run_agent(workspace_dir, task=args.task))
    else:
        # 正常交互模式：先运行 Python 启动 UI
        run_python_ui()
        asyncio.run(run_agent(workspace_dir))


if __name__ == "__main__":
    main()
