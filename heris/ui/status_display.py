"""Dynamic status display for terminal UI.

Similar to Claude Code's UI with live status updates, timing, and expandable details.
"""

import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text
from rich.tree import Tree


@dataclass
class ToolCallInfo:
    """Information about a tool call."""
    name: str
    args: dict
    status: str = "running"  # running, completed, error
    result_preview: str = ""


@dataclass
class StatusState:
    """Current state of the status display."""
    status_text: str = "Thinking"
    spinner_style: str = "dots"
    tool_calls: list[ToolCallInfo] = field(default_factory=list)
    token_count: int = 0
    start_time: float = field(default_factory=time.time)
    expanded: bool = False
    details: list[str] = field(default_factory=list)


class StatusDisplay:
    """Dynamic status display for AI agent operations.

    Displays live status with spinner, elapsed time, token count,
    and expandable details similar to Claude Code's UI.
    """

    # Status icons
    ICONS = {
        "thinking": "✻",
        "reading": "📄",
        "writing": "✏️",
        "running": "⚡",
        "complete": "✓",
        "error": "✗",
        "waiting": "◌",
    }

    def __init__(self, console: Optional[Console] = None):
        """Initialize the status display.

        Args:
            console: Optional Rich console instance
        """
        self.console = console or Console()
        self.state = StatusState()
        self._live: Optional[Live] = None
        self._running = False
        self._timer_thread: Optional[threading.Thread] = None
        self._stop_timer = threading.Event()

    def _timer_loop(self):
        """Background thread that refreshes display every second for accurate time."""
        while not self._stop_timer.is_set():
            if self._running and self._live is not None:
                # Refresh display to update elapsed time
                self._refresh()
            # Wait 1 second or until stopped
            self._stop_timer.wait(1.0)

    def start(self, status_text: str = "Thinking"):
        """Start the live status display.

        Args:
            status_text: Initial status text to display
        """
        if self._running:
            return

        self.state.status_text = status_text
        self.state.start_time = time.time()
        self._running = True
        self._stop_timer.clear()

        # Create live display with higher refresh rate for smoother animation
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=10,
            transient=True,  # Clear display when stopped
            vertical_overflow="visible",
        )
        self._live.start()

        # Start background timer thread for accurate time display
        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

    def stop(self):
        """Stop the live status display."""
        if not self._running or self._live is None:
            return

        self._running = False
        # Signal timer thread to stop
        self._stop_timer.set()
        # Stop live display
        self._live.stop()
        self._live = None
        # Wait for timer thread to finish
        if self._timer_thread is not None:
            self._timer_thread.join(timeout=0.5)
            self._timer_thread = None

    def update_status(self, text: str, icon_key: str = "thinking"):
        """Update the main status text.

        Args:
            text: New status text
            icon_key: Key for status icon
        """
        self.state.status_text = text
        self._refresh()

    def add_tool_call(self, name: str, args: dict) -> ToolCallInfo:
        """Add a new tool call to the display.

        Args:
            name: Tool name
            args: Tool arguments

        Returns:
            ToolCallInfo object for updating later
        """
        tool_info = ToolCallInfo(name=name, args=args, status="running")
        self.state.tool_calls.append(tool_info)
        self._refresh()
        return tool_info

    def update_tool_call(self, tool_info: ToolCallInfo, status: str, result_preview: str = ""):
        """Update a tool call's status.

        Args:
            tool_info: Tool call info to update
            status: New status (running, completed, error)
            result_preview: Preview of result
        """
        tool_info.status = status
        tool_info.result_preview = result_preview
        self._refresh()

    def set_token_count(self, count: int):
        """Update the token count display.

        Args:
            count: Current token count
        """
        self.state.token_count = count

    def add_detail(self, detail: str):
        """Add a detail line to the display.

        Args:
            detail: Detail text to add
        """
        self.state.details.append(detail)
        self._refresh()

    def set_expanded(self, expanded: bool):
        """Set whether details are expanded.

        Args:
            expanded: True to expand details
        """
        self.state.expanded = expanded
        self._refresh()

    def toggle_expanded(self):
        """Toggle the expanded state."""
        self.state.expanded = not self.state.expanded
        self._refresh()

    def _format_elapsed_time(self) -> str:
        """Format elapsed time for display."""
        elapsed = time.time() - self.state.start_time
        if elapsed < 60:
            return f"{int(elapsed)}s"
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        return f"{minutes}m {seconds:02d}s"

    def _format_token_count(self) -> str:
        """Format token count for display."""
        if self.state.token_count == 0:
            return ""
        if self.state.token_count < 1000:
            return f"{self.state.token_count} tokens"
        return f"{self.state.token_count / 1000:.1f}k tokens"

    def _get_status_icon(self) -> str:
        """Get the appropriate status icon."""
        text_lower = self.state.status_text.lower()
        if "read" in text_lower:
            return self.ICONS["reading"]
        elif "write" in text_lower or "edit" in text_lower:
            return self.ICONS["writing"]
        elif "run" in text_lower or "execut" in text_lower:
            return self.ICONS["running"]
        elif "complete" in text_lower or "done" in text_lower:
            return self.ICONS["complete"]
        else:
            return self.ICONS["thinking"]

    def _render(self) -> Group:
        """Render the current state as a Rich Group."""
        elements = []

        # Main status line with spinner
        icon = self._get_status_icon()
        elapsed = self._format_elapsed_time()
        tokens = self._format_token_count()

        # Build status line
        status_parts = [f"{icon} {self.state.status_text}… ({elapsed}"]
        if tokens:
            status_parts.append(f" · ↓ {tokens}")
        status_parts.append(")")
        status_line = "".join(status_parts)

        # Add spinner with smoother style
        spinner = Spinner("dots2", text=status_line, style="bright_cyan")
        elements.append(spinner)

        # Tool calls section (if any)
        if self.state.tool_calls:
            tool_tree = Tree("[dim]Tools[/dim]")
            for tool in self.state.tool_calls:
                status_icon = "✓" if tool.status == "completed" else "✗" if tool.status == "error" else "◌"
                status_color = "green" if tool.status == "completed" else "red" if tool.status == "error" else "yellow"
                tool_text = f"[{status_color}]{status_icon}[/{status_color}] {tool.name}"
                if tool.result_preview:
                    tool_text += f" [dim]- {tool.result_preview[:50]}[/dim]"
                tool_tree.add(tool_text)
            elements.append(tool_tree)

        # Expanded details section
        if self.state.expanded and self.state.details:
            details_text = "\n".join(f"  ⎿ {d}" for d in self.state.details[-10:])  # Show last 10
            elements.append(Text(details_text, style="dim"))

        # Hint for expansion
        if not self.state.expanded and self.state.details:
            elements.append(Text("  ⎿ (ctrl+o to expand)", style="dim"))

        return Group(*elements)

    def _refresh(self):
        """Refresh the live display."""
        if self._live is not None:
            self._live.update(self._render())


class SilentStatusDisplay:
    """No-op status display for when UI is disabled."""

    def start(self, status_text: str = ""):
        pass

    def stop(self):
        pass

    def update_status(self, text: str, icon_key: str = ""):
        pass

    def add_tool_call(self, name: str, args: dict) -> ToolCallInfo:
        return ToolCallInfo(name=name, args=args)

    def update_tool_call(self, tool_info: ToolCallInfo, status: str, result_preview: str = ""):
        pass

    def set_token_count(self, count: int):
        pass

    def add_detail(self, detail: str):
        pass

    def set_expanded(self, expanded: bool):
        pass

    def toggle_expanded(self):
        pass
