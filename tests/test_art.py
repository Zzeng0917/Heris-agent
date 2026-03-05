from rich.console import Console
from rich.text import Text

console = Console()
console.clear()

art = """
  ▄▀▀▀▄ ▄▀▀▀▄    ██   ██  ███████  ██████   ███████  ███████
  █████▀█████    ██   ██  ██       ██   ██    ██     ██     
  ████   ████    ███████  █████    ██████     ██     ███████
  ████▄▄▄████    ██   ██  ██       ██   ██    ██          ██
   ▀███████▀     ██   ██  ███████  ██   ██  ███████  ███████
                                                          v0.1.0
"""

console.print(f"[cyan]{art}[/cyan]")
console.print("  [dim]" + "─" * 55 + "[/dim]")
