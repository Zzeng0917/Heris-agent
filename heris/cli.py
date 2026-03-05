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


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BRAND = "\033[33m"
    BRIGHT_BRAND = "\033[93m"
    PRIMARY = "\033[36m"
    SECONDARY = "\033[90m"
    SUCCESS = "\033[32m"
    ERROR = "\033[31m"
    WARNING = "\033[33m"
    USER = "\033[37m"
    ASSISTANT = "\033[36m"
    TOOL = "\033[35m"
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
"""
    print(help_text)


def print_session_info(agent: Agent, workspace_dir: Path, model: str):
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    
    info_text = f"[cyan]模型 (Model):[/cyan] {model}\n[cyan]位置 (Workspace):[/cyan] {workspace_dir}"
    console.print(Panel(info_text, border_style="cyan", expand=False))
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

    # 构建 prompt_toolkit session
    command_completer = WordCompleter(
        ["/help", "/clear", "/history", "/stats", "/log", "/exit", "/quit", "/q"],
        ignore_case=True, sentence=True,
    )
    prompt_style = Style.from_dict({
        "prompt": "#00aaaa bold",
        "separator": "#666666",
    })
    kb = KeyBindings()

    @kb.add("c-u")
    def _(event):
        event.current_buffer.reset()

    @kb.add("c-l")
    def _(event):
        event.app.renderer.clear()

    @kb.add("c-j")
    def _(event):
        event.current_buffer.insert_text("\n")

    history_file = Path.home() / ".heris" / ".history"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=command_completer,
        style=prompt_style,
        key_bindings=kb,
    )

    # 交互循环
    while True:
        try:
            user_input = await session.prompt_async(
                [("class:prompt", ">"), ("", " ")],
                multiline=False,
                enable_history_search=True,
            )
            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                command = user_input.lower()

                if command in ["/exit", "/quit", "/q"]:
                    print(f"\n{Colors.BRAND}  再见!{Colors.RESET}\n")
                    print_stats(agent, session_start)
                    break

                elif command == "/help":
                    print_help()

                elif command == "/clear":
                    old_count = len(agent.messages)
                    agent.messages = [agent.messages[0]]
                    print(f"{Colors.SECONDARY}  已清除 {old_count - 1} 条消息{Colors.RESET}\n")

                elif command == "/history":
                    print(f"\n{Colors.SECONDARY}  当前消息数: {len(agent.messages)}{Colors.RESET}\n")

                elif command == "/stats":
                    print_stats(agent, session_start)

                elif command == "/log" or command.startswith("/log "):
                    parts = user_input.split(maxsplit=1)
                    if len(parts) == 1:
                        show_log_directory(open_file_manager=True)
                    else:
                        read_log_file(parts[1].strip("\"'"))

                else:
                    print(f"{Colors.WARNING}  未知命令: {user_input}，输入 /help 查看帮助{Colors.RESET}\n")
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print(f"\n{Colors.BRAND}  再见!{Colors.RESET}\n")
                print_stats(agent, session_start)
                break

            print(f"\n{Colors.SECONDARY}  思考中... (按 Esc 取消){Colors.RESET}")
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
    import os
    import time
    from rich.console import Console
    from rich.progress import Progress, BarColumn, TextColumn

    console = Console()
    console.clear()

    art = """
  ██   ██  ███████  ██████   ███████  ███████
  ██   ██  ██       ██   ██    ██     ██     
  ███████  █████    ██████     ██     ███████
  ██   ██  ██       ██   ██    ██          ██
  ██   ██  ███████  ██   ██  ███████  ███████
                                           v0.1.0"""
    
    console.print()
    for line in art.strip('\n').split('\n'):
        console.print(f"  [cyan]{line}[/cyan]")
        
    console.print("  [dim]" + "─" * 50 + "[/dim]\n")

    # 渲染进度条
    with Progress(
        TextColumn("  "),
        BarColumn(bar_width=50, complete_style="cyan", finished_style="cyan"),
        TextColumn(" [dim]{task.percentage:>3.0f}%[/dim]"),
        TextColumn("  [dim]初始化中...[/dim]"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("加载中", total=100)
        for i in range(0, 101, 5):
            progress.update(task, completed=i)
            time.sleep(0.02)
        progress.update(task, completed=100)

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
