# Heris Subagent 升级设计文档

基于 Claude Code Subagent 技术指南的架构升级

## 当前实现分析

### 现有组件
- `SubagentRunner`: 子agent执行器，管理独立的message上下文
- `SubagentTool`: 作为Tool集成到父Agent
- `SUBAGENT_SYSTEM_PROMPT`: 简单的系统提示词

### 当前局限性
1. 缺乏标准化的subagent定义格式
2. 没有内置的专业化subagent类型
3. 工具访问无法精细控制
4. 不支持持久内存
5. 没有subagent发现和注册机制

---

## 目标架构

```
heris/subagent/
├── __init__.py          # 模块导出
├── types.py             # 数据类型定义 (Pydantic models)
├── loader.py            # Subagent定义文件加载器
├── registry.py          # Subagent注册表
├── builtin.py           # 内置subagent类型
├── runner.py            # 执行器（升级现有）
├── tool.py              # Tool集成（升级现有）
├── prompts/             # 内置提示词模板
│   ├── explore.md
│   ├── plan.md
│   └── general.md
└── DESIGN.md            # 本文档
```

---

## 核心类型定义

### 1. SubagentDefinition (subagent定义)

```python
class SubagentDefinition(BaseModel):
    """Subagent定义 - 对应YAML frontmatter配置"""
    name: str                          # 唯一标识符
    description: str                   # Claude何时委托给此subagent
    tools: list[str] | None = None     # 允许的工具列表
    disallowed_tools: list[str] | None = None  # 禁止的工具列表
    model: str = "inherit"             # sonnet/opus/haiku/inherit
    permission_mode: str = "default"   # default/acceptEdits/dontAsk/bypassPermissions/plan
    max_turns: int | None = None       # 最大代理轮数
    skills: list[str] | None = None    # 启动时加载的技能
    memory: str | None = None          # 内存范围: user/project/local
    background: bool = False           # 是否始终后台运行
    isolation: str | None = None       # worktree - 在临时git worktree中运行
    system_prompt: str                 # 系统提示词内容
```

### 2. SubagentType (内置类型枚举)

```python
class SubagentType(str, Enum):
    """内置subagent类型"""
    EXPLORE = "explore"           # 只读探索
    PLAN = "plan"                 # 规划阶段研究
    GENERAL = "general"           # 通用复杂任务
    CODE_REVIEW = "code-review"   # 代码审查
    DEBUG = "debug"               # 调试专家
```

---

## Subagent定义文件格式

基于Markdown + YAML frontmatter的标准格式：

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices. Use immediately after writing or modifying code.
tools: Read, Grep, Glob, Bash
model: inherit
permission_mode: acceptEdits
max_turns: 30
---

You are a senior code reviewer ensuring high standards of code quality and security.

When invoked:
1. Run git diff to see recent changes
2. Focus on modified files
3. Begin review immediately

Review checklist:
- Code is clear and readable
- Functions and variables are well-named
- No duplicated code
- Proper error handling
```

---

## 搜索路径优先级

| 位置 | 范围 | 优先级 |
|------|------|--------|
| `--agents` CLI 标志 | 当前会话 | 1（最高） |
| `.heris/agents/` | 当前项目 | 2 |
| `~/.heris/agents/` | 所有项目 | 3 |
| 包内置 agents | 全局 | 4（最低） |

---

## 内置Subagent类型

### 1. Explore Agent (探索型)

```yaml
name: explore
description: Fast agent for exploring codebases. Use for file discovery, code search, and answering questions about the codebase.
tools: Read, Grep, Glob  # 只读工具
model: haiku            # 使用更快更便宜的模型
---
# 探索专用系统提示词...
```

**彻底程度级别**: quick / medium / very thorough

### 2. Plan Agent (规划型)

```yaml
name: plan
description: Software architect agent for designing implementation plans. Use when planning the implementation strategy for a task.
tools: Read, Grep, Glob  # 只读工具
permission_mode: plan    # Plan mode
---
# 规划专用系统提示词...
```

### 3. General-purpose Agent (通用型)

```yaml
name: general-purpose
description: General-purpose agent for complex, multi-step tasks. Use for researching complex questions, searching for code, and executing multi-step operations.
model: inherit
---
# 通用系统提示词...
```

---

## 使用方式升级

### 1. 使用内置Subagent

```python
from heris.subagent import SubagentRunner, SubagentType

# 使用内置explore agent
runner = SubagentRunner.from_builtin(
    agent_type=SubagentType.EXPLORE,
    llm_client=client,
    thoroughness="medium"  # quick/medium/very_thorough
)
result = await runner.run("Find all API endpoints in this project")
```

### 2. 从定义文件加载

```python
from heris.subagent import SubagentRegistry

# 加载所有可用的subagent
registry = SubagentRegistry()
registry.discover()

# 获取特定subagent
code_reviewer = registry.get("code-reviewer")
runner = code_reviewer.create_runner(llm_client=client)
result = await runner.run("Review the auth module")
```

### 3. 作为Tool使用（增强版）

```python
from heris.subagent import SubagentTool, SubagentRegistry

# 创建带所有subagent的tool
registry = SubagentRegistry()
registry.discover()

subagent_tool = SubagentTool(
    llm_client=client,
    registry=registry,  # 使用注册表
)

# 在Agent中使用
agent = Agent(
    llm_client=client,
    system_prompt="...",
    tools=[subagent_tool, ...],
)
```

---

## 权限模式

| 模式 | 行为 |
|------|------|
| `default` | 标准权限检查与提示 |
| `acceptEdits` | 自动接受文件编辑 |
| `dontAsk` | 自动拒绝权限提示 |
| `bypassPermissions` | 跳过所有权限检查（慎用） |
| `plan` | Plan mode（只读探索） |

---

## 持久内存

启用memory后，subagent获得持久目录用于跨会话积累知识：

| 范围 | 位置 | 用途 |
|------|------|------|
| `user` | `~/.heris/agent-memory/<name>/` | 跨项目记住学习 |
| `project` | `.heris/agent-memory/<name>/` | 项目特定，可版本控制 |
| `local` | `.heris/agent-memory-local/<name>/` | 项目特定，不版本控制 |

---

## 实施计划

### Phase 1: 核心类型和加载器
- [x] 创建 `types.py` - 定义数据模型
- [x] 创建 `loader.py` - YAML frontmatter解析

### Phase 2: 注册表和内置类型
- [x] 创建 `registry.py` - Subagent发现和注册
- [x] 创建 `builtin.py` - 内置subagent类型
- [x] 创建 `prompts/` - 内置提示词模板

### Phase 3: 升级执行器
- [x] 升级 `runner.py` - 支持新配置选项
- [x] 升级 `tool.py` - 集成注册表

### Phase 4: 高级功能
- [ ] 持久内存支持
- [ ] 权限模式实现
- [ ] Git worktree隔离

---

## 与Claude Code的兼容性

本设计参考Claude Code的subagent规范，但做了以下适配：

1. **路径适配**: `.claude/agents/` → `.heris/agents/`
2. **配置简化**: 移除部分高级hooks（可在未来版本添加）
3. **工具命名**: 适配Heris现有的工具命名规范
