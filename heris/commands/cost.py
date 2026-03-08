"""
/cost command for Heris CLI.

Displays API token usage and cost statistics for the current session.
"""

from typing import Optional
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.columns import Columns

# Command metadata for registration
COST_COMMAND_INFO = {
    "name": "cost",
    "description": "Display API token usage and costs",
    "category": "session",
    "icon": "💰",
    "aliases": ["/cost"],
}


# Model pricing (per 1M tokens in USD)
MODEL_PRICING = {
    # Anthropic models
    "claude-4-opus": {"input": 15.00, "output": 75.00},
    "claude-4-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    # OpenAI models
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    # MiniMax models (estimated pricing)
    "minimax-m2.5": {"input": 2.00, "output": 8.00},
    "minimax": {"input": 2.00, "output": 8.00},
}


def get_model_pricing(model_name: str) -> dict:
    """Get pricing for a specific model.

    Args:
        model_name: The model name/identifier

    Returns:
        Dict with input and output pricing per 1M tokens
    """
    model_lower = model_name.lower()

    # Try exact match first
    if model_lower in MODEL_PRICING:
        return MODEL_PRICING[model_lower]

    # Try partial match
    for model_key, pricing in MODEL_PRICING.items():
        if model_key in model_lower or model_lower in model_key:
            return pricing

    # Default pricing if model not found
    return {"input": 2.00, "output": 8.00}


def calculate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model_name: str
) -> tuple[float, float, float]:
    """Calculate API cost based on token usage.

    Args:
        prompt_tokens: Number of input/prompt tokens
        completion_tokens: Number of output/completion tokens
        model_name: The model name/identifier

    Returns:
        Tuple of (input_cost, output_cost, total_cost) in USD
    """
    pricing = get_model_pricing(model_name)

    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost

    return input_cost, output_cost, total_cost


def format_number(num: int) -> str:
    """Format number with thousand separators."""
    return f"{num:,}"


def format_cost(cost: float) -> str:
    """Format cost with appropriate precision."""
    if cost >= 0.01:
        return f"${cost:.4f}"
    elif cost >= 0.0001:
        return f"${cost:.6f}"
    else:
        return f"${cost:.8f}"


def cost_command(
    agent,
    console: Optional[Console] = None,
    session_start: Optional[datetime] = None,
    show_breakdown: bool = True
) -> None:
    """Display API token usage and cost statistics.

    Args:
        agent: The Agent instance with usage statistics
        console: Rich console instance (creates new one if None)
        session_start: Session start datetime for duration calculation
        show_breakdown: Whether to show detailed token breakdown
    """
    if console is None:
        console = Console()

    # Get model name from agent's LLM client
    model_name = getattr(agent, 'llm', None)
    if model_name and hasattr(model_name, 'model'):
        model_name = model_name.model
    else:
        model_name = "unknown"

    # Calculate session duration
    duration_str = ""
    if session_start:
        duration = datetime.now() - session_start
        hours, remainder = divmod(int(duration.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # Get message counts
    user_msgs = sum(1 for m in agent.messages if m.role == "user")
    assistant_msgs = sum(1 for m in agent.messages if m.role == "assistant")
    tool_msgs = sum(1 for m in agent.messages if m.role == "tool")

    # Get token usage
    api_usage = getattr(agent, 'api_total_tokens', 0)

    console.print()

    # Create main stats panel
    if api_usage > 0:
        # Estimate prompt vs completion tokens (typical ratio is about 70/30)
        # In a real implementation, you would track these separately
        estimated_prompt = int(api_usage * 0.7)
        estimated_completion = api_usage - estimated_prompt

        # Calculate cost
        input_cost, output_cost, total_cost = calculate_cost(
            estimated_prompt, estimated_completion, model_name
        )

        # Main summary table
        summary_table = Table(show_header=False, box=None, padding=(0, 2))
        summary_table.add_column(style="cyan", justify="right")
        summary_table.add_column(style="white")

        summary_table.add_row("Model:", model_name)
        summary_table.add_row("Session Duration:", duration_str)
        summary_table.add_row("Total Messages:", f"{len(agent.messages)} (User: {user_msgs}, Assistant: {assistant_msgs}, Tool: {tool_msgs})")

        # Token usage row with highlight
        summary_table.add_row(
            "Total Tokens:",
            f"[bold yellow]{format_number(api_usage)}[/bold yellow]"
        )

        # Cost row
        summary_table.add_row(
            "Estimated Cost:",
            f"[bold green]{format_cost(total_cost)}[/bold green]"
        )

        summary_panel = Panel(
            summary_table,
            title="[bold]Session Cost Summary[/bold]",
            border_style="cyan",
            box=box.ROUNDED
        )

        # Detailed breakdown panel
        if show_breakdown:
            breakdown_table = Table(show_header=True, box=None, padding=(0, 1))
            breakdown_table.add_column("Metric", style="dim", width=20)
            breakdown_table.add_column("Tokens", style="cyan", justify="right", width=15)
            breakdown_table.add_column("Price/1M", style="dim", justify="right", width=12)
            breakdown_table.add_column("Cost", style="green", justify="right", width=15)

            pricing = get_model_pricing(model_name)

            # Input tokens
            breakdown_table.add_row(
                "Input Tokens",
                format_number(estimated_prompt),
                f"${pricing['input']:.2f}",
                format_cost(input_cost)
            )

            # Output tokens
            breakdown_table.add_row(
                "Output Tokens",
                format_number(estimated_completion),
                f"${pricing['output']:.2f}",
                format_cost(output_cost)
            )

            # Total
            breakdown_table.add_row(
                "[bold]Total[/bold]",
                f"[bold]{format_number(api_usage)}[/bold]",
                "",
                f"[bold]{format_cost(total_cost)}[/bold]"
            )

            breakdown_panel = Panel(
                breakdown_table,
                title="[bold]Cost Breakdown[/bold]",
                border_style="bright_black",
                box=box.ROUNDED
            )

            # Display panels side by side if terminal is wide enough
            console.print(Columns([summary_panel, breakdown_panel]))
        else:
            console.print(summary_panel)

        # Note about pricing
        console.print()
        console.print(
            f"[dim]Note: Pricing estimates are based on standard rates for {model_name}. "
            f"Actual costs may vary based on your API plan and any applicable discounts.[/dim]"
        )
    else:
        # No API usage yet
        info_table = Table(show_header=False, box=None, padding=(0, 2))
        info_table.add_column(style="cyan", justify="right")
        info_table.add_column(style="white")

        info_table.add_row("Model:", model_name)
        if duration_str:
            info_table.add_row("Session Duration:", duration_str)
        info_table.add_row("Total Messages:", str(len(agent.messages)))
        info_table.add_row("API Tokens:", "[dim]No API calls yet[/dim]")

        console.print(Panel(
            info_table,
            title="[bold]Session Cost Summary[/bold]",
            border_style="bright_black",
            box=box.ROUNDED
        ))
        console.print()
        console.print("[dim]Start a conversation to see token usage and cost estimates.[/dim]")

    console.print()


def cost_command_simple(
    agent,
    console: Optional[Console] = None
) -> None:
    """Simple version of cost command with basic output.

    Args:
        agent: The Agent instance with usage statistics
        console: Rich console instance (creates new one if None)
    """
    if console is None:
        console = Console()

    # Get model name
    model_name = getattr(agent, 'llm', None)
    if model_name and hasattr(model_name, 'model'):
        model_name = model_name.model
    else:
        model_name = "unknown"

    # Get token usage
    api_usage = getattr(agent, 'api_total_tokens', 0)

    if api_usage > 0:
        # Estimate prompt vs completion tokens
        estimated_prompt = int(api_usage * 0.7)
        estimated_completion = api_usage - estimated_prompt

        # Calculate cost
        _, _, total_cost = calculate_cost(
            estimated_prompt, estimated_completion, model_name
        )

        console.print()
        console.print(f"[cyan]Model:[/cyan] {model_name}")
        console.print(f"[cyan]Tokens:[/cyan] {format_number(api_usage)}")
        console.print(f"[cyan]Estimated Cost:[/cyan] [green]{format_cost(total_cost)}[/green]")
        console.print()
    else:
        console.print()
        console.print("[dim]No API usage yet.[/dim]")
        console.print()


# For direct CLI usage
if __name__ == "__main__":
    # Test with mock data
    class MockLLM:
        model = "claude-3-sonnet"

    class MockAgent:
        llm = MockLLM()
        api_total_tokens = 15000
        messages = [
            type('obj', (object,), {'role': 'system'})(),
            type('obj', (object,), {'role': 'user'})(),
            type('obj', (object,), {'role': 'assistant'})(),
            type('obj', (object,), {'role': 'tool'})(),
        ]

    console = Console()
    cost_command(MockAgent(), console, datetime.now())
