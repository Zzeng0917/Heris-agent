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
from rich.spinner import Spinner
from rich.text import Text


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
        "thinking": "◐",
        "reading": "◑",
        "writing": "◒",
        "running": "◓",
        "complete": "✓",
        "error": "✗",
        "waiting": "○",
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
        self._lock = threading.Lock()
        self._timer_thread: Optional[threading.Thread] = None
        self._stop_timer = threading.Event()

    def _timer_loop(self):
        """Background thread that refreshes display every second for accurate time."""
        while not self._stop_timer.is_set():
            should_refresh = False
            with self._lock:
                if self._running and self._live is not None:
                    should_refresh = True
            # Refresh display OUTSIDE the lock to avoid deadlock with stop()
            if should_refresh:
                try:
                    self._live.update(self._render())
                except Exception:
                    # Ignore errors during refresh (display may be closing)
                    pass
            # Wait 1 second or until stopped
            self._stop_timer.wait(1.0)

    def start(self, status_text: str = "Thinking"):
        """Start the live status display.

        Args:
            status_text: Initial status text to display
        """
        with self._lock:
            if self._running:
                return

            # Ensure any previous timer thread is cleaned up
            if self._timer_thread is not None and self._timer_thread.is_alive():
                self._stop_timer.set()
                # Briefly release lock to let timer thread exit
                timer_thread = self._timer_thread
                self._timer_thread = None
                self._lock.release()
                try:
                    timer_thread.join(timeout=1.0)
                finally:
                    self._lock.acquire()
                self._stop_timer.clear()

            self.state.status_text = status_text
            self.state.start_time = time.time()
            self._running = True

            # Create live display with higher refresh rate for smoother animation
            self._live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=15,
                transient=False,  # Keep display after stopping so user can see it
                vertical_overflow="visible",
                auto_refresh=True,
            )
            self._live.start()

            # Start background timer thread for accurate time display
            self._stop_timer.clear()
            self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
            self._timer_thread.start()

    def stop(self):
        """Stop the live status display."""
        with self._lock:
            if not self._running or self._live is None:
                return

            self._running = False
            # Signal timer thread to stop
            self._stop_timer.set()
            # Stop live display
            self._live.stop()
            self._live = None
            # Print a newline to move to next line
            print()
            # Capture thread reference before releasing lock
            timer_thread = self._timer_thread
            self._timer_thread = None

        # Wait for timer thread to finish OUTSIDE the lock to avoid deadlock
        if timer_thread is not None:
            timer_thread.join(timeout=2.0)

    def update_status(self, text: str, icon_key: str = "thinking"):
        """Update the main status text.

        Args:
            text: New status text
            icon_key: Key for status icon
        """
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            tool_info.status = status
            tool_info.result_preview = result_preview
            self._refresh()

    def set_token_count(self, count: int):
        """Update the token count display.

        Args:
            count: Current token count
        """
        with self._lock:
            self.state.token_count = count
            self._refresh()

    def add_detail(self, detail: str):
        """Add a detail line to the display.

        Args:
            detail: Detail text to add
        """
        with self._lock:
            self.state.details.append(detail)
            self._refresh()

    def set_expanded(self, expanded: bool):
        """Set whether details are expanded.

        Args:
            expanded: True to expand details
        """
        with self._lock:
            self.state.expanded = expanded
            self._refresh()

    def toggle_expanded(self):
        """Toggle the expanded state."""
        with self._lock:
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
            # Cycle through thinking animation
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
            status_parts.append(f" · {tokens}")
        status_parts.append(")")
        status_line = "".join(status_parts)

        # Add spinner with smoother style
        spinner = Spinner("dots", text=status_line, style="bright_cyan")
        elements.append(spinner)

        # Tool calls section (if any)
        if self.state.tool_calls:
            for tool in self.state.tool_calls:
                status_icon = "✓" if tool.status == "completed" else "✗" if tool.status == "error" else "○"
                status_color = "green" if tool.status == "completed" else "red" if tool.status == "error" else "yellow"
                tool_text = f"  [{status_color}]{status_icon}[/{status_color}] {tool.name}"
                if tool.result_preview:
                    tool_text += f" [dim]- {tool.result_preview[:50]}[/dim]"
                elements.append(Text(tool_text))

        # Expanded details section
        if self.state.expanded and self.state.details:
            details_text = "\n".join(f"  ⎿ {d}" for d in self.state.details[-10:])  # Show last 10
            elements.append(Text(details_text, style="dim"))

        return Group(*elements)

    def _refresh(self):
        """Refresh the live display."""
        if self._live is not None and self._running:
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
