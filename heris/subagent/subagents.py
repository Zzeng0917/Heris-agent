"""
Subagent Module - 子智能体设计指南

## 核心设计原则

tip 1 "大任务拆小, 每个小任务干净的上下文" -- 子智能体用独立 messages[], 不污染主对话。
子智能体以 fresh messages=[] 启动，只有最终结果返回给父智能体。

tip 2 "智能体工作越久, messages 数组越胖。" 每次读文件、跑命令的输出都永久留在上下文里。
"这个项目用什么测试框架?" 可能要读 5 个文件, 但父智能体只需要一个词: "pytest"。

tip 3 "工作空间要隔离。" 子智能体在独立 workspace/ 下干活, 别污染主对话的文件。

tip 4 "记得善后。" 子智能体完事后清理自己的 workspace/, 别留垃圾。使用 runner.cleanup() 或上下文管理器。

tip 5 "保持清醒。" 子智能体别自己给自己改 todo list, 让父智能体统一管理。

## 父智能体与子智能体的工具差异

父智能体有 task 工具，可以生成子智能体（禁止递归生成）。
子智能体拥有除 task 外的所有基础工具。

## 使用方式

### 1. 直接使用 Runner (推荐)

```python
from heris import LLMClient
from heris.subagent import SubagentRunner

client = LLMClient(api_key="...")
runner = SubagentRunner(llm_client=client)

result = await runner.run("分析 /src 目录下的所有 Python 文件")
print(result)

# 清理 workspace
runner.cleanup()
```

### 2. 使用便利函数

```python
from heris import LLMClient
from heris.subagent import run_subagent

client = LLMClient(api_key="...")
result = await run_subagent(
    prompt="列出当前目录的所有文件",
    llm_client=client,
    max_steps=20,
)
```

### 3. 作为 Tool 使用

```python
from heris import LLMClient
from heris.agents import Agent
from heris.subagent import SubagentTool
from heris.tools import BashTool, ReadTool

client = LLMClient(api_key="...")

# 创建带工具的 subagent
tools = [BashTool(), ReadTool(workspace_dir="./workspace")]
subagent_tool = SubagentTool(
    llm_client=client,
    tools=tools,
)

# 在 Agent 中使用
agent = Agent(
    llm_client=client,
    system_prompt="...",
    tools=[subagent_tool, ...],
)
```

### 4. 使用上下文管理器

```python
async with SubagentRunner(llm_client=client) as runner:
    result = await runner.run("执行某些任务")
    # 自动清理 workspace
```

## 模块结构

- `__init__.py` - 模块导出
- `runner.py` - SubagentRunner 类，核心执行逻辑
- `tool.py` - SubagentTool 类，作为工具集成到 Agent
- `subagents.py` - 本文件，设计文档和参考指南

## 实现参考 (旧版伪代码)

```python
# 父智能体有一个 task 工具。子智能体拥有除 task 外的所有基础工具 (禁止递归生成)。
PARENT_TOOLS = CHILD_TOOLS + [
    {"name": "task",
     "description": "Spawn a subagent with fresh context.",
     "input_schema": {
         "type": "object",
         "properties": {"prompt": {"type": "string"}},
         "required": ["prompt"],
     }},
]

# 子智能体以 messages=[] 启动, 运行自己的循环。只有最终文本返回给父智能体。
def run_subagent(prompt: str) -> str:
    sub_messages = [{"role": "user", "content": prompt}]
    for _ in range(30):  # safety limit
        response = client.messages.create(
            model=MODEL, system=SUBAGENT_SYSTEM,
            messages=sub_messages,
            tools=CHILD_TOOLS, max_tokens=8000,
        )
        sub_messages.append({"role": "assistant",
                             "content": response.content})
        if response.stop_reason != "tool_use":
            break
        results = []
        for block in response.content:
            if block.type == "tool_use":
                handler = TOOL_HANDLERS.get(block.name)
                output = handler(**block.input)
                results.append({"type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output)[:50000]})
        sub_messages.append({"role": "user", "content": results})
    return "".join(
        b.text for b in response.content if hasattr(b, "text")
    ) or "(no summary)"
```

新版实现参见 `runner.py` 和 `tool.py`。
"""

# 导出主要组件，保持向后兼容
from .runner import SubagentRunner, run_subagent, SUBAGENT_SYSTEM_PROMPT
from .tool import SubagentTool

__all__ = [
    "SubagentRunner",
    "run_subagent",
    "SubagentTool",
    "SUBAGENT_SYSTEM_PROMPT",
]
