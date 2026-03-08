"""
/clear command for Heris CLI.

Clears the current conversation history after user confirmation.
"""

import os
import sys
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich import box


# Command metadata for registration
CLEAR_COMMAND_INFO = {
    "name": "clear",
    "description": "Clear the conversation history",
    "category": "system",
    "icon": "🧹",
    "aliases": ["/clear"],
}


def clear_terminal_screen() -> None:
    """Clear the terminal screen using OS-specific command."""
    os.system('cls' if os.name == 'nt' else 'clear')


def clear_command(
    messages: List,
    console: Optional[Console] = None,
    force: bool = False
) -> tuple[bool, int]:
    """
    Clear the conversation history with user confirmation.

    Args:
        messages: The current conversation messages list
        console: Rich console instance (creates new one if None)
        force: If True, skip confirmation prompt (use with caution)

    Returns:
        Tuple of (cleared: bool, cleared_count: int)
        - cleared: True if history was cleared, False otherwise
        - cleared_count: Number of messages that were cleared
    """
    if console is None:
        console = Console()

    # Check if there's anything to clear (keep system message)
    if len(messages) <= 1:
        console.print(Panel(
            "[dim]No conversation history to clear.[/dim]",
            border_style="bright_black",
            box=box.ROUNDED
        ))
        return False, 0

    old_count = len(messages)
    user_messages = old_count - 1  # Exclude system message

    # Show warning about irreversible operation
    console.print()
    console.print(Panel(
        f"[bold yellow]⚠️  Warning[/bold yellow]\n\n"
        f"You are about to clear [bold]{user_messages}[/bold] messages from the conversation history.\n"
        f"[red]This action cannot be undone.[/red]",
        title="[bold]Clear Conversation[/bold]",
        border_style="yellow",
        box=box.DOUBLE
    ))

    # Ask for confirmation unless force is True
    if not force:
        try:
            confirmed = Confirm.ask("Do you want to continue?", default=False)
        except KeyboardInterrupt:
            console.print("\n[dim]Operation cancelled.[/dim]")
            return False, 0
    else:
        confirmed = True

    if confirmed:
        # Keep only the system message (first message)
        messages[:] = [messages[0]]

        # Clear the terminal screen
        clear_terminal_screen()

        # Print success message at the top
        console.print()
        console.print(Panel(
            f"[green]✓[/green] Cleared {user_messages} messages. Starting fresh conversation.",
            border_style="green",
            box=box.ROUNDED
        ))
        console.print()
        return True, user_messages
    else:
        console.print(Panel(
            "[dim]Operation cancelled. Conversation history preserved.[/dim]",
            border_style="bright_black",
            box=box.ROUNDED
        ))
        console.print()
        return False, 0


def clear_command_simple(
    messages: List,
    console: Optional[Console] = None
) -> tuple[bool, int]:
    """
    Simple version of clear command with basic yes/no prompt.

    Args:
        messages: The current conversation messages list
        console: Rich console instance (creates new one if None)

    Returns:
        Tuple of (cleared: bool, cleared_count: int)
    """
    if console is None:
        console = Console()

    # Check if there's anything to clear
    if len(messages) <= 1:
        console.print("[dim]No conversation history to clear.[/dim]\n")
        return False, 0

    old_count = len(messages)
    user_messages = old_count - 1

    # Simple confirmation prompt
    console.print(f"\n[yellow]This will clear {user_messages} messages and cannot be undone.[/yellow]")

    try:
        response = console.input("Continue? ([yes]/no): ").strip().lower()
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/dim]\n")
        return False, 0

    if response in ("yes", "y", ""):
        messages[:] = [messages[0]]
        console.print(f"[dim]Cleared {user_messages} messages[/dim]\n")
        return True, user_messages
    else:
        console.print("[dim]Cancelled.[/dim]\n")
        return False, 0


# For direct CLI usage
if __name__ == "__main__":
    # Test with mock messages
    test_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    console = Console()
    cleared, count = clear_command(test_messages, console)
    print(f"Cleared: {cleared}, Count: {count}")
    print(f"Remaining messages: {len(test_messages)}")
