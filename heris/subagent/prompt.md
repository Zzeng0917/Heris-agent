# Claude Code Subagent 技术指南

## 核心概念

Subagent 是处理特定类型任务的专门 AI 助手，在自己的 context window 中运行，具有自定义系统提示、特定的工具访问权限和独立的权限。

**主要作用：**
- 保留上下文：将探索和实现保持在主对话之外
- 强制执行约束：限制 subagent 可以使用的工具
- 跨项目重用配置：使用用户级 subagents
- 专门化行为：为特定领域使用专注的系统提示
- 控制成本：将任务路由到更快、更便宜的模型（如 Haiku）

## 内置 Subagents

| Agent | 模型 | 工具 | 用途 |
|-------|------|------|------|
| **Explore** | Haiku | 只读工具 | 文件发现、代码搜索、代码库探索 |
| **Plan** | 继承 | 只读工具 | 规划阶段的代码库研究 |
| **General-purpose** | 继承 | 所有工具 | 复杂研究、多步骤操作、代码修改 |

**调用 Explore 时的彻底程度级别：** quick（快速查找）、medium（平衡探索）、very thorough（全面分析）

## 创建 Subagent

### 文件格式
Subagent 是带有 YAML frontmatter 的 Markdown 文件：

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Glob, Grep
model: sonnet
---

You are a code reviewer. When invoked, analyze the code and provide
specific, actionable feedback on quality, security, and best practices.
```

### 存储位置（优先级从高到低）

| 位置 | 范围 | 优先级 |
|------|------|--------|
| `--agents` CLI 标志 | 当前会话 | 1（最高） |
| `.claude/agents/` | 当前项目 | 2 |
| `~/.claude/agents/` | 所有项目 | 3 |
| 插件的 `agents/` 目录 | 启用插件的位置 | 4（最低） |

### Frontmatter 字段

| 字段 | 必需 | 说明 |
|------|------|------|
| `name` | 是 | 小写字母和连字符的唯一标识符 |
| `description` | 是 | Claude 何时应委托给此 subagent |
| `tools` | 否 | 允许使用的工具列表 |
| `disallowedTools` | 否 | 拒绝使用的工具列表 |
| `model` | 否 | sonnet / opus / haiku / inherit（默认） |
| `permissionMode` | 否 | default / acceptEdits / dontAsk / bypassPermissions / plan |
| `maxTurns` | 否 | 最大代理轮数 |
| `skills` | 否 | 启动时加载的技能列表 |
| `mcpServers` | 否 | 可用的 MCP 服务器 |
| `hooks` | 否 | 生命周期 hooks |
| `memory` | 否 | 持久内存范围：user / project / local |
| `background` | 否 | 是否始终作为后台任务运行 |
| `isolation` | 否 | worktree - 在临时 git worktree 中运行 |

## 权限模式

| 模式 | 行为 |
|------|------|
| `default` | 标准权限检查与提示 |
| `acceptEdits` | 自动接受文件编辑 |
| `dontAsk` | 自动拒绝权限提示 |
| `bypassPermissions` | 跳过所有权限检查（慎用） |
| `plan` | Plan mode（只读探索） |

## 工具访问控制

### 限制可生成的 subagents
在 `tools` 字段中使用 `Agent(agent_type)` 语法：

```yaml
tools: Agent(worker, researcher), Read, Bash
```

- `Agent(agent_type)` - 只允许生成指定的 subagent 类型
- `Agent` - 允许生成任何 subagent
- 省略 `Agent` - 无法生成任何 subagents

## 持久内存

启用 memory 后，subagent 获得持久目录用于跨会话积累知识：

| 范围 | 位置 | 用途 |
|------|------|------|
| `user` | `~/.claude/agent-memory/<name>/` | 跨项目记住学习 |
| `project` | `.claude/agent-memory/<name>/` | 项目特定，可版本控制 |
| `local` | `.claude/agent-memory-local/<name>/` | 项目特定，不版本控制 |

启用内存时自动启用 Read、Write、Edit 工具。

## Hooks

### Subagent 内部 Hooks（frontmatter 中定义）

| 事件 | 触发时机 |
|------|----------|
| `PreToolUse` | subagent 使用工具之前 |
| `PostToolUse` | subagent 使用工具之后 |
| `Stop` | subagent 完成时（转换为 SubagentStop） |

示例：
```yaml
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-command.sh"
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "./scripts/run-linter.sh"
```

### 项目级 Hooks（settings.json 中定义）

| 事件 | 触发时机 |
|------|----------|
| `SubagentStart` | subagent 开始执行时 |
| `SubagentStop` | subagent 完成时 |

## 使用模式

### 前台 vs 后台运行

- **前台**：阻塞主对话直到完成，权限提示传递给用户
- **后台**：并发运行，启动前提示工具权限，自动拒绝未预先批准的内容

切换方式：
- 要求 "run this in the background"
- 按 Ctrl+B 将运行中的任务放在后台

### 何时使用 Subagent

**使用主对话：**
- 任务需要频繁的来回或迭代细化
- 多个阶段共享重要上下文
- 快速、有针对性的更改
- 延迟很重要

**使用 Subagent：**
- 任务产生详细输出但只需要摘要
- 想强制执行特定的工具限制或权限
- 工作是自包含的

### 恢复 Subagent

每个 subagent 调用创建新实例。要恢复现有工作：

```
Continue that code review and now analyze the authorization logic
```

转录文件位置：`~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl`

## 示例 Subagents

### 代码审查者

```markdown
---
name: code-reviewer
description: Expert code review specialist. Proactively reviews code for quality, security, and maintainability. Use immediately after writing or modifying code.
tools: Read, Grep, Glob, Bash
model: inherit
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
- No exposed secrets or API keys
- Input validation implemented
- Good test coverage
- Performance considerations addressed

Provide feedback organized by priority:
- Critical issues (must fix)
- Warnings (should fix)
- Suggestions (consider improving)

Include specific examples of how to fix issues.
```

### 调试器

```markdown
---
name: debugger
description: Debugging specialist for errors, test failures, and unexpected behavior. Use proactively when encountering any issues.
tools: Read, Edit, Bash, Grep, Glob
---

You are an expert debugger specializing in root cause analysis.

When invoked:
1. Capture error message and stack trace
2. Identify reproduction steps
3. Isolate the failure location
4. Implement minimal fix
5. Verify solution works

Debugging process:
- Analyze error messages and logs
- Check recent code changes
- Form and test hypotheses
- Add strategic debug logging
- Inspect variable states

For each issue, provide:
- Root cause explanation
- Evidence supporting the diagnosis
- Specific code fix
- Testing approach
- Prevention recommendations

Focus on fixing the underlying issue, not the symptoms.
```

### 只读数据库查询

```markdown
---
name: db-reader
description: Execute read-only database queries. Use when analyzing data or generating reports.
tools: Bash
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-readonly-query.sh"
---

You are a database analyst with read-only access. Execute SELECT queries to answer questions about the data.

When asked to analyze data:
1. Identify which tables contain the relevant data
2. Write efficient SELECT queries with appropriate filters
3. Present results clearly with context

You cannot modify data. If asked to INSERT, UPDATE, DELETE, or modify schema, explain that you only have read access.
```

配合的验证脚本 `scripts/validate-readonly-query.sh`：

```bash
#!/bin/bash
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [ -z "$COMMAND" ]; then
  exit 0
fi

# 阻止写操作（不区分大小写）
if echo "$COMMAND" | grep -iE '\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE)\b' > /dev/null; then
  echo "Blocked: Write operations not allowed. Use SELECT queries only." >&2
  exit 2
fi

exit 0
```

## 最佳实践

- **设计专注的 subagents：** 每个 subagent 应该在一个特定任务中表现出色
- **编写详细的描述：** Claude 使用描述来决定何时委托
- **限制工具访问：** 仅授予安全和专注所需的权限
- **检入版本控制：** 与团队共享项目 subagents
