"""
Heris - Interactive Runtime Example

Usage:
    heris [--workspace DIR] [--task TASK]

Examples:
    heris                              # Use current directory as workspace (interactive mode)
    heris --workspace /path/to/dir     # Use specific workspace directory (interactive mode)
    heris --task "create a file"       # Execute a task non-interactively
"""

import argparse
import asyncio
import platform
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import List

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

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


# ANSI color codes - 简化主题系统，参考 Kode Agent 设计风格
class Colors:
    """Terminal color definitions - simplified theme"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # 品牌色 - 金黄色 (类似 Kode 的 #FFC233)
    BRAND = "\033[33m"
    BRIGHT_BRAND = "\033[93m"

    # 语义化颜色
    PRIMARY = "\033[36m"      # 青色 - 主要信息
    SECONDARY = "\033[90m"    # 灰色 - 次要信息
    SUCCESS = "\033[32m"      # 绿色 - 成功
    ERROR = "\033[31m"        # 红色 - 错误
    WARNING = "\033[33m"      # 黄色 - 警告

    # 角色颜色
    USER = "\033[37m"         # 白色 - 用户
    ASSISTANT = "\033[36m"    # 青色 - 助手
    TOOL = "\033[35m"         # 洋红 - 工具

    # 兼容性别名
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
    """Get the log directory path."""
    return Path.home() / ".heris" / "log"


def show_log_directory(open_file_manager: bool = True) -> None:
    """Show log directory contents - simplified"""
    log_dir = get_log_directory()

    print(f"\n{Colors.PRIMARY}日志目录: {Colors.RESET}{log_dir}")

    if not log_dir.exists() or not log_dir.is_dir():
        print(f"{Colors.ERROR}目录不存在{Colors.RESET}\n")
        return

    log_files = list(log_dir.glob("*.log"))

    if not log_files:
        print(f"{Colors.WARNING}暂无日志文件{Colors.RESET}\n")
        return

    # Sort by modification time (newest first)
    log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    print(f"{Colors.SECONDARY}  最近日志文件:{Colors.RESET}")
    for i, log_file in enumerate(log_files[:5], 1):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        size = log_file.stat().st_size
        size_str = f"{size:,}" if size < 1024 else f"{size / 1024:.1f}K"
        print(f"  {Colors.PRIMARY}{i}.{Colors.RESET} {log_file.name} {Colors.SECONDARY}({mtime.strftime('%m-%d %H:%M')}, {size_str}){Colors.RESET}")

    if len(log_files) > 5:
        print(f"  {Colors.SECONDARY}... 还有 {len(log_files) - 5} 个文件{Colors.RESET}")

    # Open file manager
    if open_file_manager:
        _open_directory_in_file_manager(log_dir)

    print()


def _open_directory_in_file_manager(directory: Path) -> None:
    """Open directory in system file manager (cross-platform)."""
    system = platform.system()

    try:
        if system == "Darwin":
            subprocess.run(["open", str(directory)], check=False)
        elif system == "Windows":
            subprocess.run(["explorer", str(directory)], check=False)
        elif system == "Linux":
            subprocess.run(["xdg-open", str(directory)], check=False)
    except FileNotFoundError:
        print(f"{Colors.YELLOW}Could not open file manager. Please navigate manually.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.YELLOW}Error opening file manager: {e}{Colors.RESET}")


def read_log_file(filename: str) -> None:
    """Read and display a specific log file - simplified"""
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


def print_banner():
    """Print welcome banner - simplified style like Kode"""
    # ASCII Logo - Heris style
    logo = (
        f"{Colors.BRIGHT_BRAND}\n"
        "  _   _           _     \n"
        " | | | | ___  ___| |_   \n"
        " | |_| |/ _ \\/ __| __|  \n"
        " |  _  |  __/\\__ \\ |_   \n"
        " |_| |_|\\___||___/\\__|  \n"
        f"{Colors.RESET}"
    )
    print(logo)
    print(f"{Colors.SECONDARY}  Heris - AI 助手 · 输入 /help 查看帮助{Colors.RESET}")
    print()


def print_help():
    """Print help information - simplified Chinese version"""
    help_text = f"""
{Colors.BOLD}可用命令:{Colors.RESET}
  {Colors.PRIMARY}/help{Colors.RESET}      显示帮助信息
  {Colors.PRIMARY}/clear{Colors.RESET}     清除会话历史（保留系统提示）
  {Colors.PRIMARY}/history{Colors.RESET}   显示当前会话消息数
  {Colors.PRIMARY}/stats{Colors.RESET}     显示会话统计
  {Colors.PRIMARY}/log{Colors.RESET}       查看日志目录
  {Colors.PRIMARY}/log <file>{Colors.RESET} 读取指定日志文件
  {Colors.PRIMARY}/exit{Colors.RESET}      退出程序

{Colors.BOLD}快捷键:{Colors.RESET}
  {Colors.PRIMARY}Esc{Colors.RESET}       取消当前任务
  {Colors.PRIMARY}Ctrl+C{Colors.RESET}    退出程序
  {Colors.PRIMARY}Ctrl+U{Colors.RESET}    清空当前输入行
  {Colors.PRIMARY}Ctrl+L{Colors.RESET}    清屏
  {Colors.PRIMARY}Ctrl+J{Colors.RESET}    换行
  {Colors.PRIMARY}↑/↓{Colors.RESET}      浏览历史记录

{Colors.BOLD}使用提示:{Colors.RESET}
  · 直接输入任务描述，Agent 将协助完成
  · Agent 会记住会话中的对话内容
  · 使用 {Colors.PRIMARY}/clear{Colors.RESET} 开始新会话
"""
    print(help_text)


def print_session_info(agent: Agent, workspace_dir: Path, model: str):
    """Print session information - simplified style"""
    print(f"{Colors.SECONDARY}  模型: {Colors.RESET}{model}")
    print(f"{Colors.SECONDARY}  工作区: {Colors.RESET}{workspace_dir}")
    print(f"{Colors.SECONDARY}  工具: {Colors.RESET}{len(agent.tools)} 个")
    print()


def print_stats(agent: Agent, session_start: datetime):
    """Print session statistics - simplified"""
    duration = datetime.now() - session_start
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    # Count different types of messages
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
    """Parse command line arguments

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Heris - AI assistant with file tools and MCP support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  heris                              # Use current directory as workspace
  heris --workspace /path/to/dir     # Use specific workspace directory
  heris log                          # Show log directory and recent files
  heris log agent_run_xxx.log        # Read a specific log file
        """,
    )
    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory (default: current directory)",
    )
    parser.add_argument(
        "--task",
        "-t",
        type=str,
        default=None,
        help="Execute a task non-interactively and exit",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="heris 0.1.0",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # log subcommand
    log_parser = subparsers.add_parser("log", help="Show log directory or read log files")
    log_parser.add_argument(
        "filename",
        nargs="?",
        default=None,
        help="Log filename to read (optional, shows directory if omitted)",
    )

    return parser.parse_args()


async def initialize_base_tools(config: Config):
    """Initialize base tools (independent of workspace)

    These tools are loaded from package configuration and don't depend on workspace.
    Note: File tools are now workspace-dependent and initialized in add_workspace_tools()

    Args:
        config: Configuration object

    Returns:
        Tuple of (list of tools, skill loader if skills enabled)
    """

    tools = []
    skill_loader = None

    # 1. Bash auxiliary tools (output monitoring and kill)
    # Note: BashTool itself is created in add_workspace_tools() with workspace_dir as cwd
    if config.tools.enable_bash:
        bash_output_tool = BashOutputTool()
        tools.append(bash_output_tool)
        bash_kill_tool = BashKillTool()
        tools.append(bash_kill_tool)

    # 3. Claude Skills (loaded from package directory)
    if config.tools.enable_skills:
        try:
            # Resolve skills directory with priority search
            # Expand ~ to user home directory for portability
            skills_path = Path(config.tools.skills_dir).expanduser()
            if skills_path.is_absolute():
                skills_dir = str(skills_path)
            else:
                # Search in priority order:
                # 1. Current directory (dev mode: ./skills or ./heris/skills)
                # 2. Package directory (installed: site-packages/heris/skills)
                search_paths = [
                    skills_path,  # ./skills for backward compatibility
                    Path("heris") / skills_path,  # ./heris/skills
                    Config.get_package_dir() / skills_path,  # site-packages/heris/skills
                ]

                # Find first existing path
                skills_dir = str(skills_path)  # default
                for path in search_paths:
                    if path.exists():
                        skills_dir = str(path.resolve())
                        break

            skill_tools, skill_loader = create_skill_tools(skills_dir)
            if skill_tools:
                tools.extend(skill_tools)
        except Exception:
            pass

    # 4. MCP tools (loaded with priority search)
    if config.tools.enable_mcp:
        try:
            # Apply MCP timeout configuration from config.yaml
            mcp_config = config.tools.mcp
            set_mcp_timeout_config(
                connect_timeout=mcp_config.connect_timeout,
                execute_timeout=mcp_config.execute_timeout,
                sse_read_timeout=mcp_config.sse_read_timeout,
            )

            # Use priority search for mcp.json
            mcp_config_path = Config.find_config_file(config.tools.mcp_config_path)
            if mcp_config_path:
                mcp_tools = await load_mcp_tools_async(str(mcp_config_path))
                if mcp_tools:
                    tools.extend(mcp_tools)
        except Exception:
            pass
    return tools, skill_loader


def add_workspace_tools(tools: List[Tool], config: Config, workspace_dir: Path):
    """Add workspace-dependent tools

    These tools need to know the workspace directory.

    Args:
        tools: Existing tools list to add to
        config: Configuration object
        workspace_dir: Workspace directory path
    """
    # Ensure workspace directory exists
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Bash tool - needs workspace as cwd for command execution
    if config.tools.enable_bash:
        bash_tool = BashTool(workspace_dir=str(workspace_dir))
        tools.append(bash_tool)

    # File tools - need workspace to resolve relative paths
    if config.tools.enable_file_tools:
        tools.extend(
            [
                ReadTool(workspace_dir=str(workspace_dir)),
                WriteTool(workspace_dir=str(workspace_dir)),
                EditTool(workspace_dir=str(workspace_dir)),
            ]
        )

    # Session note tool - needs workspace to store memory file
    if config.tools.enable_note:
        tools.append(SessionNoteTool(memory_file=str(workspace_dir / ".agent_memory.json")))


async def _quiet_cleanup():
    """Clean up MCP connections, suppressing noisy asyncgen teardown tracebacks."""
    # Silence the asyncgen finalization noise that anyio/mcp emits when
    # stdio_client's task group is torn down across tasks.  The handler is
    # intentionally NOT restored: asyncgen finalization happens during
    # asyncio.run() shutdown (after run_agent returns), so restoring the
    # handler here would still let the noise through.  Since this runs
    # right before process exit, swallowing late exceptions is safe.
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(lambda _loop, _ctx: None)
    try:
        await cleanup_mcp_connections()
    except Exception:
        pass


async def run_agent(workspace_dir: Path, task: str = None):
    """Run Agent in interactive or non-interactive mode.

    Args:
        workspace_dir: Workspace directory path
        task: If provided, execute this task and exit (non-interactive mode)
    """
    session_start = datetime.now()

    # 1. Load configuration from package directory
    config_path = Config.get_default_config_path()

    if not config_path.exists():
        print(f"{Colors.ERROR}配置文件未找到{Colors.RESET}")
        print()
        print(f"{Colors.SECONDARY}搜索路径:{Colors.RESET}")
        print(f"  1) heris/config/config.yaml (开发)")
        print(f"  2) ~/.heris/config/config.yaml (用户)")
        print(f"  3) <package>/config/config.yaml (已安装)")
        print()
        print(f"{Colors.PRIMARY}快速设置:{Colors.RESET}")
        print(f"  复制 heris/config/config-example.yaml 到 heris/config/config.yaml 并编辑配置")
        print()
        return

    try:
        config = Config.from_yaml(config_path)
    except FileNotFoundError:
        print(f"{Colors.ERROR}配置文件未找到: {config_path}{Colors.RESET}")
        return
    except ValueError as e:
        print(f"{Colors.ERROR}配置错误: {e}{Colors.RESET}")
        print(f"{Colors.SECONDARY}请检查配置文件格式{Colors.RESET}")
        return
    except Exception as e:
        print(f"{Colors.ERROR}加载配置失败: {e}{Colors.RESET}")
        return

    # 2. Initialize LLM client
    from heris.retry import RetryConfig as RetryConfigBase

    # Convert configuration format
    retry_config = RetryConfigBase(
        enabled=config.llm.retry.enabled,
        max_retries=config.llm.retry.max_retries,
        initial_delay=config.llm.retry.initial_delay,
        max_delay=config.llm.retry.max_delay,
        exponential_base=config.llm.retry.exponential_base,
        retryable_exceptions=(Exception,),
    )

    # Create retry callback function to display retry information in terminal
    def on_retry(exception: Exception, attempt: int):
        """Retry callback function to display retry information"""
        next_delay = retry_config.calculate_delay(attempt - 1)
        print(f"\n{Colors.WARNING}  请求失败 ({attempt}/{retry_config.max_retries})，{next_delay:.1f}s 后重试...{Colors.RESET}")

    # Convert provider string to LLMProvider enum
    provider = LLMProvider.ANTHROPIC if config.llm.provider.lower() == "anthropic" else LLMProvider.OPENAI

    llm_client = LLMClient(
        api_key=config.llm.api_key,
        provider=provider,
        api_base=config.llm.api_base,
        model=config.llm.model,
        retry_config=retry_config if config.llm.retry.enabled else None,
    )

    # Set retry callback
    if config.llm.retry.enabled:
        llm_client.retry_callback = on_retry

    # 3. Initialize base tools (independent of workspace)
    tools, skill_loader = await initialize_base_tools(config)

    # 4. Add workspace-dependent tools
    add_workspace_tools(tools, config, workspace_dir)

    # 5. Load System Prompt (with priority search)
    system_prompt_path = Config.find_config_file(config.agent.system_prompt_path)
    if system_prompt_path and system_prompt_path.exists():
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = "You are Heris, an intelligent assistant powered by MiniMax M2.5 that can help users complete various tasks."

    # 6. Inject Skills Metadata into System Prompt
    if skill_loader:
        skills_metadata = skill_loader.get_skills_metadata_prompt()
        if skills_metadata:
            # Replace placeholder with actual metadata
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
        else:
            # Remove placeholder if no skills
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")
    else:
        # Remove placeholder if skills not enabled
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

    # 7. Create Agent
    agent = Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=tools,
        max_steps=config.agent.max_steps,
        workspace_dir=str(workspace_dir),
    )

    # 8. Display welcome information
    if not task:
        print_banner()
        print_session_info(agent, workspace_dir, config.llm.model)

    # 8.5 Non-interactive mode: execute task and exit
    if task:
        print(f"\n{Colors.SECONDARY}  执行任务...{Colors.RESET}\n")
        agent.add_user_message(task)
        try:
            await agent.run()
        except Exception as e:
            print(f"\n{Colors.ERROR}  错误: {e}{Colors.RESET}")
        finally:
            print_stats(agent, session_start)

        # Cleanup MCP connections
        await _quiet_cleanup()
        return

    # 9. Setup prompt_toolkit session
    # Command completer
    command_completer = WordCompleter(
        ["/help", "/clear", "/history", "/stats", "/log", "/exit", "/quit", "/q"],
        ignore_case=True,
        sentence=True,
    )

    # Custom style for prompt - Kode style: simple ">"
    prompt_style = Style.from_dict(
        {
            "prompt": "#00aaaa bold",  # Cyan for user prompt
            "separator": "#666666",    # Gray separator
        }
    )

    # Custom key bindings
    kb = KeyBindings()

    @kb.add("c-u")  # Ctrl+U: Clear current line
    def _(event):
        """Clear the current input line"""
        event.current_buffer.reset()

    @kb.add("c-l")  # Ctrl+L: Clear screen (optional bonus)
    def _(event):
        """Clear the screen"""
        event.app.renderer.clear()

    @kb.add("c-j")  # Ctrl+J (对应 Ctrl+Enter)
    def _(event):
        """Insert a newline"""
        event.current_buffer.insert_text("\n")

    # Create prompt session with history and auto-suggest
    # Use FileHistory for persistent history across sessions (stored in user's home directory)
    history_file = Path.home() / ".heris" / ".history"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=command_completer,
        style=prompt_style,
        key_bindings=kb,
    )

    # 10. Interactive loop
    while True:
        try:
            # Get user input using prompt_toolkit - Kode style: simple ">" prompt
            user_input = await session.prompt_async(
                [
                    ("class:prompt", ">"),
                    ("", " "),
                ],
                multiline=False,
                enable_history_search=True,
            )
            user_input = user_input.strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                command = user_input.lower()

                if command in ["/exit", "/quit", "/q"]:
                    print(f"\n{Colors.BRAND}  再见!{Colors.RESET}\n")
                    print_stats(agent, session_start)
                    break

                elif command == "/help":
                    print_help()
                    continue

                elif command == "/clear":
                    # Clear message history but keep system prompt
                    old_count = len(agent.messages)
                    agent.messages = [agent.messages[0]]  # Keep only system message
                    print(f"{Colors.SECONDARY}  已清除 {old_count - 1} 条消息{Colors.RESET}\n")
                    continue

                elif command == "/history":
                    print(f"\n{Colors.SECONDARY}  当前消息数: {len(agent.messages)}{Colors.RESET}\n")
                    continue

                elif command == "/stats":
                    print_stats(agent, session_start)
                    continue

                elif command == "/log" or command.startswith("/log "):
                    # Parse /log command
                    parts = user_input.split(maxsplit=1)
                    if len(parts) == 1:
                        # /log - show log directory
                        show_log_directory(open_file_manager=True)
                    else:
                        # /log <filename> - read specific log file
                        filename = parts[1].strip("\"'")
                        read_log_file(filename)
                    continue

                else:
                    print(f"{Colors.WARNING}  未知命令: {user_input}{Colors.RESET}")
                    print(f"{Colors.SECONDARY}  输入 /help 查看帮助{Colors.RESET}\n")
                    continue

            # Normal conversation - exit check
            if user_input.lower() in ["exit", "quit", "q"]:
                print(f"\n{Colors.BRAND}  再见!{Colors.RESET}\n")
                print_stats(agent, session_start)
                break

            # Run Agent with Esc cancellation support
            print(f"\n{Colors.SECONDARY}  思考中... (按 Esc 取消){Colors.RESET}")
            agent.add_user_message(user_input)

            # Create cancellation event
            cancel_event = asyncio.Event()
            agent.cancel_event = cancel_event

            # Esc key listener thread
            esc_listener_stop = threading.Event()
            esc_cancelled = [False]  # Mutable container for thread access

            def esc_key_listener():
                """Listen for Esc key in a separate thread."""
                if platform.system() == "Windows":
                    try:
                        import msvcrt

                        while not esc_listener_stop.is_set():
                            if msvcrt.kbhit():
                                char = msvcrt.getch()
                                if char == b"\x1b":  # Esc
                                    print(f"\n{Colors.WARNING}  取消中...{Colors.RESET}")
                                    esc_cancelled[0] = True
                                    cancel_event.set()
                                    break
                            esc_listener_stop.wait(0.05)
                    except Exception:
                        pass
                    return

                # Unix/macOS
                try:
                    import select
                    import termios
                    import tty

                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)

                    try:
                        tty.setcbreak(fd)
                        while not esc_listener_stop.is_set():
                            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                            if rlist:
                                char = sys.stdin.read(1)
                                if char == "\x1b":  # Esc
                                    print(f"\n{Colors.WARNING}  取消中...{Colors.RESET}")
                                    esc_cancelled[0] = True
                                    cancel_event.set()
                                    break
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass

            # Start Esc listener thread
            esc_thread = threading.Thread(target=esc_key_listener, daemon=True)
            esc_thread.start()

            # Run agent with periodic cancellation check
            try:
                agent_task = asyncio.create_task(agent.run())

                # Poll for cancellation while agent runs
                while not agent_task.done():
                    if esc_cancelled[0]:
                        cancel_event.set()
                    await asyncio.sleep(0.1)

                # Get result
                _ = agent_task.result()

            except asyncio.CancelledError:
                print(f"\n{Colors.WARNING}  已取消{Colors.RESET}")
            finally:
                agent.cancel_event = None
                esc_listener_stop.set()
                esc_thread.join(timeout=0.2)

            # Visual separation - simplified
            print()

        except KeyboardInterrupt:
            print(f"\n\n{Colors.BRAND}  再见!{Colors.RESET}\n")
            print_stats(agent, session_start)
            break

        except Exception as e:
            print(f"\n{Colors.ERROR}  错误: {e}{Colors.RESET}\n")

    # 11. Cleanup MCP connections
    await _quiet_cleanup()


def main():
    """Main entry point for CLI"""
    # Parse command line arguments
    args = parse_args()

    # Handle log subcommand
    if args.command == "log":
        if args.filename:
            read_log_file(args.filename)
        else:
            show_log_directory(open_file_manager=True)
        return

    # Determine workspace directory
    # Expand ~ to user home directory for portability
    if args.workspace:
        workspace_dir = Path(args.workspace).expanduser().absolute()
    else:
        # Use current working directory
        workspace_dir = Path.cwd()

    # Ensure workspace directory exists
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Run the agent (config always loaded from package directory)
    asyncio.run(run_agent(workspace_dir, task=args.task))


if __name__ == "__main__":
    main()
