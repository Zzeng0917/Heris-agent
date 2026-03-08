"""
/help command for Heris CLI.

Displays help information about available slash commands.
"""

from typing import Dict, List, Tuple
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.columns import Columns


# Command metadata for registration
HELP_COMMAND_INFO = {
    "name": "help",
    "description": "Display help information",
    "category": "system",
    "icon": "❓",
    "aliases": ["/help", "/?"],
}

# Category display configuration
COMMAND_CATEGORIES = {
    "system": ("System", "cyan"),
    "model": ("Model", "magenta"),
    "tools": ("Tools", "yellow"),
    "session": ("Session", "green"),
}

# Slash command definitions - mirrors the one in cli.py
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

    # Session commands
    ("/chat save <tag>", "Save conversation", "session", "💾"),
    ("/chat load <tag>", "Load conversation", "session", "📂"),
    ("/chat list", "List saved conversations", "session", "📜"),
    ("/history", "Show message count", "session", "📊"),
    ("/stats", "Show session statistics", "session", "📈"),
    ("/cost", "Show API token usage and costs", "session", "💰"),
    ("/log", "View log directory", "session", "📝"),
]


def help_command(
    console: Console = None,
    show_shortcuts: bool = True,
    category_filter: str = None
) -> None:
    """
    Display help information for Heris CLI commands.

    Args:
        console: Rich console instance (creates new one if None)
        show_shortcuts: Whether to show keyboard shortcuts
        category_filter: Optional category to filter by (system, model, tools, session)
    """
    if console is None:
        console = Console()

    # Group commands by category
    categories: Dict[str, List[Tuple[str, str, str]]] = {}
    for cmd, desc, category, icon in SLASH_COMMANDS:
        if category not in categories:
            categories[category] = []
        categories[category].append((cmd, desc, icon))

    # Create a panel for each category
    panels = []
    category_order = ["system", "model", "tools", "session"]

    for category in category_order:
        if category not in categories:
            continue

        if category_filter and category != category_filter:
            continue

        cat_name, cat_color = COMMAND_CATEGORIES[category]

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style=cat_color, width=22)
        table.add_column(style="white")

        for cmd, desc, icon in categories[category]:
            table.add_row(f"{icon} {cmd}", desc)

        panel = Panel(
            table,
            title=f"[bold {cat_color}]{cat_name}[/bold {cat_color}]",
            border_style="bright_black",
            box=box.ROUNDED
        )
        panels.append(panel)

    console.print()
    console.print(
        Panel("[bold]Heris Commands[/bold]", border_style="cyan", box=box.DOUBLE)
    )

    # Display command panels in columns
    if panels:
        console.print(Columns(panels, equal=True))

    # Shortcuts panel
    if show_shortcuts:
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

        console.print(
            Panel(
                shortcuts,
                title="[bold bright_cyan]Keyboard Shortcuts[/bold bright_cyan]",
                border_style="bright_black",
                box=box.ROUNDED
            )
        )

    console.print()


def print_command_help(command_name: str) -> bool:
    """
    Print detailed help for a specific command.

    Args:
        command_name: The command to get help for (without leading slash)

    Returns:
        True if command found, False otherwise
    """
    console = Console()

    # Find the command
    target_cmd = f"/{command_name}" if not command_name.startswith("/") else command_name

    for cmd, desc, category, icon in SLASH_COMMANDS:
        if cmd == target_cmd:
            cat_name, cat_color = COMMAND_CATEGORIES[category]

            console.print()
            console.print(
                Panel(
                    f"[bold]{icon} {cmd}[/bold]\n\n{desc}",
                    title=f"[bold {cat_color}]{cat_name} Command[/bold {cat_color}]",
                    border_style=cat_color,
                    box=box.DOUBLE
                )
            )
            console.print()
            return True

    console.print(f"[red]Unknown command: {target_cmd}[/red]")
    console.print("Type /help to see all available commands.")
    return False


# For direct CLI usage
if __name__ == "__main__":
    help_command()
