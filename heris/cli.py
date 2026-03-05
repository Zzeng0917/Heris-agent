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
from prompt_toolkit.shortcuts import radiolist_dialog, message_dialog, input_dialog
from prompt_toolkit.application import get_app

from heris import LLMClient
from heris.agent import Agent
from heris.config import Config
from heris.schema import LLMProvider
from heris.tools.base import Tool
from heris.tools.bash_tool import BashKillTool, BashOutputTool, BashTool
from heris.tools.file_tools import EditTool, ReadTool, WriteTool
from heris.tools.mcp_loader import cleanup_mcp_connections, load_mcp_tools_async, set_mcp_timeout_config
from heris.tools.note_tool import SessionNoteTool
from heris.tools.skill_tool import create_skill_tools


# Slash command definitions for interactive picker
SLASH_COMMANDS = [
    ("/about", "Show version information"),
    ("/help", "Display help information"),
    ("/clear", "Clear the terminal screen"),
    ("/history", "Show message count"),
    ("/stats", "Show session statistics"),
    ("/log", "View log directory"),
    ("/model", "Show current model"),
    ("/model set <model>", "Set model to use"),
    ("/tools", "List available tools"),
    ("/tools desc", "List tools with descriptions"),
    ("/mcp list", "List configured MCP servers"),
    ("/mcp refresh", "Refresh MCP connections"),
    ("/chat save <tag>", "Save conversation"),
    ("/chat load <tag>", "Load conversation"),
    ("/chat list", "List saved conversations"),
    ("/exit", "Exit Heris"),
]


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
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    console = Console()

    # Main commands table with border
    table = Table(show_header=False, box=box.ROUNDED, border_style="bright_black", padding=(0, 2))
    table.add_column(style="cyan", width=20)
    table.add_column(style="white")

    # Basic commands
    table.add_row("/about", "Show version information")
    table.add_row("/help", "Display this help message")
    table.add_row("/clear", "Clear the terminal screen")
    table.add_row("/exit, /quit", "Exit Heris")
    table.add_row("")

    # Model commands
    table.add_row("/model", "Show current model")
    table.add_row("/model set <model>", "Set model to use")
    table.add_row("")

    # Tool commands
    table.add_row("/tools", "List available tools")
    table.add_row("/tools desc", "List tools with descriptions")
    table.add_row("")

    # MCP commands
    table.add_row("/mcp list", "List configured MCP servers")
    table.add_row("/mcp refresh", "Refresh MCP connections")
    table.add_row("")

    # Session commands
    table.add_row("/chat save <tag>", "Save conversation")
    table.add_row("/chat load <tag>", "Load conversation")
    table.add_row("/chat list", "List saved conversations")
    table.add_row("")

    # Stats & Info
    table.add_row("/history", "Show message count")
    table.add_row("/stats", "Show session statistics")
    table.add_row("/log", "View log directory")

    console.print(Panel(table, title="[bold cyan]Heris Commands[/bold cyan]", border_style="bright_black", box=box.ROUNDED))

    # Shortcuts table with border
    shortcuts = Table(show_header=False, box=box.ROUNDED, border_style="bright_black", padding=(0, 2))
    shortcuts.add_column(style="cyan", width=20)
    shortcuts.add_column(style="white")
    shortcuts.add_row("Esc", "Cancel current task")
    shortcuts.add_row("Ctrl+C", "Exit program")
    shortcuts.add_row("Ctrl+U", "Clear input line")
    shortcuts.add_row("Ctrl+L", "Clear screen")
    shortcuts.add_row("Ctrl+J", "New line")
    shortcuts.add_row("↑/↓", "Browse history")

    console.print(Panel(shortcuts, title="[bold cyan]Keyboard Shortcuts[/bold cyan]", border_style="bright_black", box=box.ROUNDED))
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
        """Completer for slash commands with descriptions."""

        def get_completions(self, document, complete_event):
            text = document.text
            if not text.startswith('/'):
                return

            for cmd, desc in SLASH_COMMANDS:
                if cmd.startswith(text):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=cmd,
                        display_meta=desc
                    )

    # Style for the interface
    style = Style.from_dict({
        'prompt': '#00aaaa bold',
        'completion-menu': 'bg:#1a1a1a',
        'completion-menu.completion': '#ffffff',
        'completion-menu.completion.current': 'bg:#4285f4 #ffffff bold',
        'completion-menu.meta': '#888888',
        'completion-menu.meta.current': '#aaaaaa',
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
                    old_count = len(agent.messages)
                    agent.messages = [agent.messages[0]]
                    from rich.console import Console
                    Console().print("[dim]Cleared {} messages[/dim]\n".format(old_count - 1))

                elif command == "/history":
                    print(f"\n{Colors.SECONDARY}  当前消息数: {len(agent.messages)}{Colors.RESET}\n")

                elif command == "/stats":
                    print_stats(agent, session_start)

                elif command == "/log" or command.startswith("/log "):
                    parts2 = user_input.split(maxsplit=1)
                    if len(parts2) == 1:
                        show_log_directory(open_file_manager=True)
                    else:
                        read_log_file(parts2[1].strip("\"'"))

                elif command == "/model":
                    if subcommand is None:
                        print_model_info(config)
                    elif subcommand == "set" and arg:
                        config.llm.model = arg
                        llm_client.model = arg
                        from rich.console import Console
                        from rich.panel import Panel
                        Console().print(Panel(f"Model set to [cyan]{arg}[/cyan]", border_style="green"))
                    else:
                        print(f"{Colors.WARNING}Usage: /model or /model set <model>{Colors.RESET}")

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
