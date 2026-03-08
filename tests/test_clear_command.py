"""
Tests for the /clear command module.

Run with: python -m pytest tests/test_clear_command.py -v
"""

import os
import sys
from unittest.mock import MagicMock, patch, call

# Add parent directory to path for direct module import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import directly from the module file to avoid heris package dependencies
import importlib.util
spec = importlib.util.spec_from_file_location("clear", "heris/commands/clear.py")
clear_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clear_module)

# Now access the functions
clear_command = clear_module.clear_command
clear_command_simple = clear_module.clear_command_simple
clear_terminal_screen = clear_module.clear_terminal_screen
CLEAR_COMMAND_INFO = clear_module.CLEAR_COMMAND_INFO


class TestClearCommandInfo:
    """Test command metadata."""

    def test_command_info_structure(self):
        """Test that command info has all required fields."""
        assert "name" in CLEAR_COMMAND_INFO
        assert "description" in CLEAR_COMMAND_INFO
        assert "category" in CLEAR_COMMAND_INFO
        assert "icon" in CLEAR_COMMAND_INFO
        assert "aliases" in CLEAR_COMMAND_INFO
        assert CLEAR_COMMAND_INFO["name"] == "clear"
        assert "/clear" in CLEAR_COMMAND_INFO["aliases"]


class TestClearTerminalScreen:
    """Test terminal screen clearing."""

    @patch("os.system")
    def test_clear_screen_unix(self, mock_system):
        """Test clear screen on Unix-like systems."""
        with patch("os.name", "posix"):
            clear_terminal_screen()
            mock_system.assert_called_once_with("clear")

    @patch("os.system")
    def test_clear_screen_windows(self, mock_system):
        """Test clear screen on Windows."""
        with patch("os.name", "nt"):
            clear_terminal_screen()
            mock_system.assert_called_once_with("cls")


class TestClearCommand:
    """Test the main clear_command function."""

    def test_no_messages_to_clear(self, capsys):
        """Test behavior when there's nothing to clear."""
        messages = [{"role": "system", "content": "You are a helpful assistant."}]

        # Mock console
        mock_console = MagicMock()

        cleared, count = clear_command(messages, console=mock_console)

        assert cleared is False
        assert count == 0
        assert len(messages) == 1  # System message preserved

    def test_clear_with_force(self):
        """Test clearing with force=True (no prompt)."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        mock_console = MagicMock()

        with patch.object(clear_module, 'clear_terminal_screen') as mock_clear:
            cleared, count = clear_command(messages, console=mock_console, force=True)

        assert cleared is True
        assert count == 2  # 2 user/assistant messages
        assert len(messages) == 1  # Only system message remains
        assert messages[0]["role"] == "system"
        mock_clear.assert_called_once()
        mock_console.print.assert_called()  # Success message printed

    @patch.object(clear_module, 'clear_terminal_screen')
    @patch.object(clear_module, 'Confirm')
    def test_clear_with_confirmation_yes(self, MockConfirm, mock_clear):
        """Test clearing when user confirms with 'yes'."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        mock_console = MagicMock()
        MockConfirm.ask.return_value = True

        cleared, count = clear_command(messages, console=mock_console)

        assert cleared is True
        assert count == 1
        assert len(messages) == 1
        mock_clear.assert_called_once()

    @patch.object(clear_module, 'Confirm')
    def test_clear_with_confirmation_no(self, MockConfirm):
        """Test clearing when user declines."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi!"},
        ]
        original_count = len(messages)
        mock_console = MagicMock()
        MockConfirm.ask.return_value = False

        cleared, count = clear_command(messages, console=mock_console)

        assert cleared is False
        assert count == 0
        assert len(messages) == original_count  # Messages preserved

    @patch.object(clear_module, 'Confirm')
    def test_clear_keyboard_interrupt(self, MockConfirm):
        """Test behavior when user interrupts with Ctrl+C."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        original_count = len(messages)
        mock_console = MagicMock()
        MockConfirm.ask.side_effect = KeyboardInterrupt()

        cleared, count = clear_command(messages, console=mock_console)

        assert cleared is False
        assert count == 0
        assert len(messages) == original_count  # Messages preserved


class TestClearCommandSimple:
    """Test the simple version of clear command."""

    def test_simple_no_messages(self):
        """Test simple version when there's nothing to clear."""
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        mock_console = MagicMock()

        cleared, count = clear_command_simple(messages, console=mock_console)

        assert cleared is False
        assert count == 0

    def test_simple_confirm_yes(self):
        """Test simple version with 'yes' input."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        mock_console = MagicMock()
        mock_console.input.return_value = "yes"

        cleared, count = clear_command_simple(messages, console=mock_console)

        assert cleared is True
        assert count == 1
        assert len(messages) == 1

    def test_simple_confirm_y(self):
        """Test simple version with 'y' input."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi!"},
        ]
        mock_console = MagicMock()
        mock_console.input.return_value = "y"

        cleared, count = clear_command_simple(messages, console=mock_console)

        assert cleared is True
        assert count == 2

    def test_simple_confirm_default(self):
        """Test simple version with empty input (default to yes)."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        mock_console = MagicMock()
        mock_console.input.return_value = ""  # Empty string = default

        cleared, count = clear_command_simple(messages, console=mock_console)

        assert cleared is True
        assert count == 1

    def test_simple_decline_no(self):
        """Test simple version with 'no' input."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi!"},
        ]
        original_count = len(messages)
        mock_console = MagicMock()
        mock_console.input.return_value = "no"

        cleared, count = clear_command_simple(messages, console=mock_console)

        assert cleared is False
        assert count == 0
        assert len(messages) == original_count

    def test_simple_decline_n(self):
        """Test simple version with 'n' input."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        mock_console = MagicMock()
        mock_console.input.return_value = "n"

        cleared, count = clear_command_simple(messages, console=mock_console)

        assert cleared is False
        assert count == 0

    def test_simple_keyboard_interrupt(self):
        """Test simple version with Ctrl+C."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        original_count = len(messages)
        mock_console = MagicMock()
        mock_console.input.side_effect = KeyboardInterrupt()

        cleared, count = clear_command_simple(messages, console=mock_console)

        assert cleared is False
        assert count == 0
        assert len(messages) == original_count


class TestClearIntegration:
    """Integration tests for clear command."""

    def test_multiple_clears(self):
        """Test that multiple clears work correctly."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi!"},
        ]
        mock_console = MagicMock()

        with patch.object(clear_module, 'clear_terminal_screen'):
            # First clear
            cleared, count = clear_command(messages, console=mock_console, force=True)
            assert cleared is True
            assert count == 2
            assert len(messages) == 1

            # Add more messages
            messages.append({"role": "user", "content": "How are you?"})
            messages.append({"role": "assistant", "content": "I'm good!"})

            # Second clear
            cleared, count = clear_command(messages, console=mock_console, force=True)
            assert cleared is True
            assert count == 2
            assert len(messages) == 1

    def test_system_message_always_preserved(self):
        """Test that system message is always preserved after clear."""
        system_msg = {"role": "system", "content": "You are a coding assistant."}
        messages = [
            system_msg,
            {"role": "user", "content": "Hello!"},
        ]
        mock_console = MagicMock()

        with patch.object(clear_module, 'clear_terminal_screen'):
            clear_command(messages, console=mock_console, force=True)

        assert len(messages) == 1
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a coding assistant."

    def test_messages_list_modified_in_place(self):
        """Test that the original messages list is modified in place."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "User message"},
        ]
        messages_id = id(messages)
        mock_console = MagicMock()

        with patch.object(clear_module, 'clear_terminal_screen'):
            clear_command(messages, console=mock_console, force=True)

        # Same list object should be modified
        assert id(messages) == messages_id
        assert len(messages) == 1


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
