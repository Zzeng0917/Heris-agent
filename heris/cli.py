"""
Heris CLI - TypeScript UI 启动，Python Agent 交互
"""

import argparse
import asyncio
import os
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
from prompt_toolkit.document import Document

from heris import LLMClient
from heris.agents import Agent
from heris.config import Config, ModelsConfig, ModelConfig, ProviderConfig
from heris.schema import LLMProvider
from heris.tools.base import Tool
from heris.tools.shell import BackgroundCheckTool, BashKillTool, BashOutputTool, BashTool
from heris.tools.file import EditTool, ReadTool, WriteTool
from heris.tools.mcp import cleanup_mcp_connections, load_mcp_tools_async, set_mcp_timeout_config
from heris.tools.memory import SessionNoteTool
from heris.tools.skill import create_skill_tools
from heris.tools.worktree import (
    init_worktree_system,
    TaskCreateTool, TaskListTool, TaskGetTool, TaskUpdateTool, TaskBindWorktreeTool,
    WorktreeCreateTool, WorktreeListTool, WorktreeStatusTool, WorktreeRunTool,
    WorktreeKeepTool, WorktreeRemoveTool, WorktreeEventsTool,
    # Autonomous agent tools
    IdleTool, ClaimTaskTool, TaskAddDependencyTool, ListUnclaimedTasksTool,
)
from heris.tools.team import (
    init_team_system,
    MessageSendTool, MessagePollTool, MessageReadTool,
    ShutdownRequestTool, ShutdownAckTool, ShutdownCheckTool,
    PlanSubmitTool, PlanApproveTool, PlanListPendingTool, PlanCheckResponseTool,
)
from heris.commands import cost_command
from heris.Todo import TodoManager, TodoTool
from heris.subagent import SubagentTool, SubagentRegistry


# Slash command definitions for interactive picker - organized by category
SLASH_COMMANDS = [
    # System commands
    ("/about", "Show version information", "system", "[i]"),
    ("/help", "Display help information", "system", "[?]"),
    ("/clear", "Clear the terminal screen", "system", "[X]"),
    ("/exit", "Exit Heris", "system", "[-]"),

    # Model commands
    ("/model", "Show or set model", "model", "[M]"),

    # Tool commands
    ("/tools", "List available tools", "tools", "[T]"),
    ("/tools desc", "List tools with descriptions", "tools", "[D]"),
    ("/agents", "List available subagents", "tools", "[A]"),
    ("/mcp list", "List configured MCP servers", "tools", "[+]"),
    ("/mcp refresh", "Refresh MCP connections", "tools", "[R]"),

    # Session commands
    ("/chat save <tag>", "Save conversation", "session", "[S]"),
    ("/chat load <tag>", "Load conversation", "session", "[L]"),
    ("/chat list", "List saved conversations", "session", "[*]"),
    ("/history", "Show message count", "session", "[#]"),
    ("/stats", "Show session statistics", "session", "[%]"),
    ("/cost", "Show API token usage and costs", "session", "[$]"),
    ("/log", "View log directory", "session", "[.]"),
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


def print_agents(registry: SubagentRegistry | None = None):
    """Print available subagents."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    from heris.subagent import SubagentType

    console = Console()

    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED, border_style="bright_black")
    table.add_column("Name", style="magenta", width=20)
    table.add_column("Type", style="yellow", width=12)
    table.add_column("Description", style="white")

    # Add built-in agents
    for agent_type in SubagentType:
        from heris.subagent import get_builtin_definition
        defn = get_builtin_definition(agent_type)
        table.add_row(defn.name, "built-in", defn.description[:60] + "..." if len(defn.description) > 60 else defn.description)

    # Add custom agents from registry
    if registry:
        for defn in registry.list_all():
            if not defn.is_builtin_type():
                table.add_row(defn.name, "custom", defn.description[:60] + "..." if len(defn.description) > 60 else defn.description)

    console.print(Panel(table, title="[bold]Available Subagents[/bold]", border_style="bright_black", box=box.ROUNDED))
    console.print("[dim]Use spawn_subagent tool with agent_name to delegate tasks[/dim]")
    console.print()


# Models configuration - loaded from models.yaml
_models_config: ModelsConfig | None = None


def get_models_config() -> ModelsConfig:
    """Get the models configuration, loading from file if needed."""
    global _models_config
    if _models_config is None:
        try:
            _models_config = ModelsConfig.load()
        except FileNotFoundError:
            # Fallback to empty config if models.yaml not found
            _models_config = ModelsConfig(providers={}, models=[])
    return _models_config


def _find_model_by_id(model_id: str) -> ModelConfig | None:
    """Find model configuration by model ID."""
    return get_models_config().get_model(model_id)


def _get_provider_config(provider_name: str) -> ProviderConfig | None:
    """Get provider configuration by name."""
    return get_models_config().get_provider(provider_name)


def _get_provider_from_name(provider_name: str) -> LLMProvider:
    """Convert provider name to LLMProvider enum."""
    provider_name = provider_name.lower()
    if provider_name == "anthropic":
        return LLMProvider.ANTHROPIC
    else:
        # All other providers (openai, gemini, minimax, etc.) use OpenAI-compatible format
        return LLMProvider.OPENAI


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

        # Build all lines first so we know how many to clear
        lines = []

        # Title bar with soft border
        lines.append(f"{t['border']}╭{'─' * 58}╮{t['reset']}")
        lines.append(f"{t['border']}│{t['reset']}  {t['title']}Slash Commands{t['reset']}  (up/down to move, Enter to select, Esc to cancel)  {t['border']}│{t['reset']}")
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
                header_colors = {
                    "cyan": t['accent_cyan'],
                    "magenta": t['accent_magenta'],
                    "green": t['accent_green'],
                    "yellow": t['accent_yellow'],
                }
                cat_color = header_colors.get(header["color"], t['accent_cyan'])
                lines.append(f"{t['border']}│{t['reset']}  {cat_color}>> {header['label']}{t['reset']}")

            if display_idx == self.current_index:
                # Selected item - with light blue highlight background
                line = f"{t['border']}│{t['reset']}  {t['highlight_bg']}{t['highlight_fg']}>> {item['icon']} {item['command']:<20}{t['reset']} {t['text_secondary']}{item['description'][:25]:<25}{t['reset']}"
            else:
                # Normal item - use soft colors
                category_colors = {
                    "system": t['accent_cyan'],
                    "model": t['accent_magenta'],
                    "tools": t['accent_yellow'],
                    "session": t['accent_green'],
                }
                cat_color = category_colors.get(item['category'], t['text_primary'])
                line = f"{t['border']}│{t['reset']}  {t['dim']}   {item['icon']} {cat_color}{item['command']:<20}{t['reset']} {t['text_secondary']}{item['description'][:25]:<25}{t['reset']}"
            lines.append(line)

        # Show scroll indicator
        if end_idx < len(selectable_indices):
            lines.append(f"{t['border']}│{t['reset']}  {t['dim']}   > {len(selectable_indices) - end_idx} more commands...{t['reset']}")

        lines.append(f"{t['border']}╰{'─' * 58}╯{t['reset']}")

        # Clear entire screen and move cursor to top-left before drawing
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

        output = "\n".join(lines)
        sys.stdout.write(output + "\n")
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
            sys.stdout.flush()

        # Clear display
        if self._num_lines > 0:
            sys.stdout.write(f"\033[{self._num_lines}A")
            sys.stdout.write("\033[J")
            sys.stdout.write("\n")  # Move to new line for next prompt
            sys.stdout.flush()

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


def _print_model_list(config: Config):
    """Print the list of available models grouped by provider."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    models_cfg = get_models_config()
    current_model = config.llm.model

    current_provider = (
        config.llm.provider.value
        if hasattr(config.llm.provider, "value")
        else str(config.llm.provider)
    )

    console.print(f"\n  {Colors.SECONDARY}Current: {current_model} ({current_provider}){Colors.RESET}")
    console.print()

    # Group models by provider
    by_provider: dict[str, list[ModelConfig]] = {}
    for model in models_cfg.models:
        if model.provider not in by_provider:
            by_provider[model.provider] = []
        by_provider[model.provider].append(model)

    table = Table(show_header=True, header_style="bold dim", box=None, padding=(0, 1))
    table.add_column("Provider")
    table.add_column("Model ID")
    table.add_column("Context")
    table.add_column("Description")

    for provider in ["anthropic", "openai", "gemini", "mistral", "deepseek", "xai", "groq", "minimax"]:
        if provider not in by_provider:
            continue
        provider_cfg = models_cfg.get_provider(provider)
        rows = by_provider[provider]

        # Provider header row
        table.add_section()
        provider_name = provider_cfg.name if provider_cfg else provider
        table.add_row(
            f"[bold]{provider_name.upper()}[/bold]", "", "", ""
        )

        for model in rows:
            ctx = model.context
            if ctx >= 1000000:
                ctx_str = f"{ctx / 1000000:.0f}M"
            elif ctx >= 1000:
                ctx_str = f"{ctx / 1000:.0f}K"
            else:
                ctx_str = str(ctx)

            desc = model.description
            mark = " [dim]<=[/dim]" if model.id == current_model else ""
            table.add_row("", model.id, ctx_str, f"{desc}{mark}")

    console.print(table)
    console.print(
        f"  {Colors.SECONDARY}Usage: /model set <model_id>{Colors.RESET}\n"
    )


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


def _refresh_status_bar(model: str):
    """Refresh the status bar in place using ANSI escape codes."""
    # Move cursor up to the session info panel (adjust based on actual line count)
    # The panel is 2 lines + 1 blank line = 3 lines above prompt
    sys.stdout.write("\033[3A")
    sys.stdout.write("\033[J")
    sys.stdout.flush()

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
    parser.add_argument("--version", "-v", action="version", version="heris 0.1.1")
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
        tools.append(BackgroundCheckTool())

    # Fast mode: skip skill tools to reduce startup time
    if config.tools.enable_skills and not config.agent.fast_mode:
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

    # Fast mode: skip MCP tools to reduce startup time
    if config.tools.enable_mcp and not config.agent.fast_mode:
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


def add_workspace_tools(tools: List[Tool], config: Config, workspace_dir: Path, todo_manager: TodoManager = None):
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
    # Add TodoTool
    if todo_manager is None:
        todo_manager = TodoManager()
    tools.append(TodoTool(todo_manager))

    # Initialize and add worktree tools (s12 pattern)
    init_worktree_system(workspace_dir)
    tools.extend([
        TaskCreateTool(),
        TaskListTool(),
        TaskGetTool(),
        TaskUpdateTool(),
        TaskBindWorktreeTool(),
        WorktreeCreateTool(),
        WorktreeListTool(),
        WorktreeStatusTool(),
        WorktreeRunTool(),
        WorktreeKeepTool(),
        WorktreeRemoveTool(),
        WorktreeEventsTool(),
        # Autonomous agent tools
        IdleTool(),
        ClaimTaskTool(),
        TaskAddDependencyTool(),
        ListUnclaimedTasksTool(),
    ])

    # Initialize and add team protocol tools (s10 pattern)
    init_team_system(workspace_dir)
    tools.extend([
        MessageSendTool(),
        MessagePollTool(),
        MessageReadTool(),
        ShutdownRequestTool(),
        ShutdownAckTool(),
        ShutdownCheckTool(),
        PlanSubmitTool(),
        PlanApproveTool(),
        PlanListPendingTool(),
        PlanCheckResponseTool(),
    ])


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
        timeout=config.llm.timeout,
    )
    if config.llm.retry.enabled:
        llm_client.retry_callback = on_retry

    tools, skill_loader = await initialize_base_tools(config)
    todo_manager = TodoManager()
    add_workspace_tools(tools, config, workspace_dir, todo_manager)

    # Fast mode: skip subagent to reduce startup time
    if config.tools.enable_subagent and not config.agent.fast_mode:
        subagent_tools = [t for t in tools if hasattr(t, 'workspace_dir') or hasattr(t, 'name')]

        # Create subagent registry with project directory
        # Note: discover() is called lazily when first needed (in get/list methods)
        subagent_registry = SubagentRegistry()
        subagent_registry.set_project_directory(workspace_dir)

        subagent_tool = SubagentTool(
            llm_client=llm_client,
            tools=subagent_tools,
            registry=subagent_registry,
            default_workspace=str(workspace_dir),
        )
        tools.append(subagent_tool)

    system_prompt_path = Config.find_config_file(config.agent.system_prompt_path)
    if system_prompt_path and system_prompt_path.exists():
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = "You are Heris, an intelligent assistant."

    # Fast mode: skip skills metadata to reduce token usage and startup time
    if config.agent.fast_mode:
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")
    elif skill_loader:
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
        token_limit=config.agent.token_limit,
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

    # Path completer for @ file references
    class PathCompleter(Completer):
        """Completer for file paths when typing @."""

        def __init__(self, base_dir: Path):
            self.base_dir = base_dir

        def get_completions(self, document, complete_event):
            text = document.text

            # Check if this is a sub-document (no @ in text) or full document
            at_pos = text.rfind('@')
            if at_pos == -1:
                # Sub-document: use entire text as partial path
                partial = text
            else:
                # Full document with @: get path after @
                partial = text[at_pos + 1:]

            # Determine search directory
            if '/' in partial:
                # User is typing a path with subdirectories
                search_dir = self.base_dir / partial.rsplit('/', 1)[0]
                prefix = partial.rsplit('/', 1)[0] + '/'
            else:
                # User is typing in current directory
                search_dir = self.base_dir
                prefix = ''

            # Ensure search_dir exists
            if not search_dir.exists():
                return

            try:
                # Get all entries in the search directory
                entries = list(search_dir.iterdir())

                # Sort: directories first, then files
                entries.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

                for entry in entries:
                    name = entry.name

                    # Skip hidden files unless user typed a dot
                    if name.startswith('.') and not partial.startswith('.'):
                        continue

                    # Build the full path for matching
                    if prefix:
                        full_path = prefix + name
                    else:
                        full_path = name

                    # Check if it matches the partial path
                    if full_path.startswith(partial):
                        # Calculate start position (relative to @)
                        start_pos = -(len(partial))

                        # Add trailing slash for directories
                        display_name = name
                        insert_name = name
                        if entry.is_dir():
                            display_name = name + '/'
                            insert_name = name + '/'

                        # Get icon based on type
                        if entry.is_dir():
                            icon = '📁'
                        elif entry.is_file():
                            # Choose icon based on file extension
                            ext = entry.suffix.lower()
                            if ext in ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.go', '.rs']:
                                icon = '📝'
                            elif ext in ['.md', '.txt', '.rst']:
                                icon = '📄'
                            elif ext in ['.json', '.yaml', '.yml', '.toml', '.ini']:
                                icon = '⚙️'
                            elif ext in ['.jpg', '.png', '.gif', '.svg', '.ico']:
                                icon = '🖼️'
                            else:
                                icon = '📎'
                        else:
                            icon = '📎'

                        yield Completion(
                            insert_name,
                            start_position=start_pos,
                            display=f"{icon} {display_name}",
                            display_meta='📂 folder' if entry.is_dir() else f"📄 {self._format_size(entry.stat().st_size)}" if entry.is_file() else ''
                        )
            except (PermissionError, OSError):
                return

        def _format_size(self, size: int) -> str:
            """Format file size for display."""
            if size < 1024:
                return f"{size} B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            elif size < 1024 * 1024 * 1024:
                return f"{size / (1024 * 1024):.1f} MB"
            else:
                return f"{size / (1024 * 1024 * 1024):.1f} GB"

    # Combined completer that handles slash commands, model IDs, and file paths
    class CombinedCompleter(Completer):
        """Combines slash command, model ID, and path completion."""

        def __init__(self, slash_completer: Completer, path_completer: Completer):
            self.slash_completer = slash_completer
            self.path_completer = path_completer

        def _get_model_ids(self) -> set[str]:
            """Get available model IDs from config."""
            return {m.id for m in get_models_config().models}

        def get_completions(self, document, complete_event):
            text = document.text

            # Check if we're completing a file path after @
            at_pos = text.rfind('@')
            if at_pos != -1:
                after_at = text[at_pos + 1:document.cursor_position]
                if '@' not in after_at:
                    sub_text = text[at_pos + 1:]
                    sub_cursor_pos = document.cursor_position - at_pos - 1
                    sub_doc = Document(sub_text, cursor_position=sub_cursor_pos)
                    for completion in self.path_completer.get_completions(sub_doc, complete_event):
                        yield completion
                    return

            # Handle /model set <model_id> completion
            if text.startswith('/model set '):
                prefix = text[len('/model set '):]
                for model_id in self._get_model_ids():
                    if model_id.startswith(prefix):
                        yield Completion(
                            model_id,
                            start_position=-len(prefix),
                            display=f"[M] {model_id}",
                            display_meta="model"
                        )
                return

            # Handle /model set completion (no model ID typed yet)
            if text == '/model set ':
                for model_id in self._get_model_ids():
                    yield Completion(
                        model_id,
                        start_position=0,
                        display=f"[M] {model_id}",
                        display_meta="model"
                    )
                return

            # Otherwise use slash command completer
            if text.startswith('/'):
                for completion in self.slash_completer.get_completions(document, complete_event):
                    yield completion

    # Slash command completer
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

    @kb.add('c-i')  # Tab key - insert auto-completion if available
    def _(event):
        buffer = event.app.current_buffer
        if buffer.complete_state:
            # Menu is visible - insert the current selection
            completions = list(buffer.complete_state.completions)
            if completions:
                current = buffer.complete_state.current_completion
                buffer.apply_completion(current if current else completions[0])
                buffer.complete_state = None
        else:
            # Menu not visible - get completions directly from completer and auto-insert
            completer = buffer.completer
            if completer:
                completions = list(completer.get_completions(buffer.document, None))
                if completions:
                    # Insert the first completion
                    completion = completions[0]
                    start = completion.start_position
                    if start < 0:
                        # Delete characters before cursor to replace
                        buffer.delete_before_cursor(abs(start))
                    buffer.insert_text(completion.text)
            # If no completions available - do nothing

    @kb.add('@')
    def _(event):
        """Insert @ and start file path completion."""
        event.app.current_buffer.insert_text('@')
        event.app.current_buffer.start_completion(select_first=False)

    @kb.add('enter')
    def _(event):
        """Handle Enter key - accept completion if menu is open, else submit."""
        buffer = event.app.current_buffer
        # If completion menu is visible, accept the current completion
        if buffer.complete_state:
            # Get current completion and apply it
            completion = buffer.complete_state.current_completion
            if completion:
                buffer.apply_completion(completion)
            else:
                buffer.complete_state = None
            # Don't submit - let user continue typing
        else:
            # No completion menu, submit the input
            buffer.validate_and_handle()

    # History
    history_file = Path.home() / ".heris" / ".history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    # Create completers
    slash_completer = SlashCommandCompleter()
    path_completer = PathCompleter(workspace_dir)
    combined_completer = CombinedCompleter(slash_completer, path_completer)

    # Session with completion
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=combined_completer,
        style=style,
        key_bindings=kb,
        complete_style='multi_column',
        complete_while_typing=True,
    )

    # 交互循环
    conversation_round = 0
    last_todo_call_round = 0

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
                    if subcommand == "set" and arg:
                        # Set model - find model definition and update all settings
                        model_id = arg.strip()
                        models_cfg = get_models_config()
                        model_def = models_cfg.get_model(model_id)

                        if not model_def:
                            print(f"{Colors.ERROR}Unknown model: {model_id}{Colors.RESET}")
                            print(f"  Run {Colors.PRIMARY}/model{Colors.RESET} to see available models.")
                        else:
                            # Get provider configuration for api_base
                            provider_cfg = models_cfg.get_provider(model_def.provider)
                            api_base = model_def.api_base or (provider_cfg.api_base if provider_cfg else config.llm.api_base)

                            # Update all model settings
                            config.llm.model = model_id
                            config.llm.provider = model_def.provider
                            config.llm.api_base = api_base

                            # Update LLM client
                            llm_client.model = model_id
                            llm_client.set_api_base(api_base)
                            llm_client.set_provider(_get_provider_from_name(model_def.provider))

                            print(f"{Colors.SUCCESS}Model set to: {model_id}{Colors.RESET}")
                            _refresh_status_bar(model_id)
                    else:
                        # Show available models
                        _print_model_list(config)

                elif command == "/tools":
                    show_desc = subcommand in ["desc", "descriptions"]
                    print_tools(agent, show_descriptions=show_desc)

                elif command == "/agents":
                    print_agents(subagent_registry if config.tools.enable_subagent else None)

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

            # Increment conversation round
            conversation_round += 1

            # Check if we should inject reminder (3+ rounds since last todo call)
            rounds_since_todo = conversation_round - last_todo_call_round
            if rounds_since_todo >= 3:
                user_input = f"<reminder> Update your todos.</reminder>\n\n{user_input}"

            agent.add_user_message(user_input)
            print()  # New line before status display

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

            # Check if todo tool was called in this round
            for msg in agent.messages:
                if msg.role == "assistant" and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if tc.function.name == "todo":
                            last_todo_call_round = conversation_round
                            todo_manager.mark_called(conversation_round)
                            break

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
        "                                           v0.1.1"
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
