# Heris Subagent Module v2.0

An advanced subagent system compatible with Claude Code's agent specification.

## Features

### 1. YAML Frontmatter-Based Definitions

Define subagents using Markdown files with YAML frontmatter:

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Grep, Glob, Bash
model: inherit
permission_mode: acceptEdits
max_turns: 30
---

You are a senior code reviewer...
```

### 2. Built-in Agent Types

- **explore** - Fast codebase exploration with thoroughness levels
- **plan** - Software architect for implementation planning
- **general-purpose** - Complex multi-step tasks
- **code-reviewer** - Expert code review
- **debug** - Debugging specialist
- **db-reader** - Read-only database queries

### 3. Subagent Registry

Priority-based agent discovery:
1. CLI-specified directories (`--agents`)
2. Project agents (`.heris/agents/`)
3. User agents (`~/.heris/agents/`)
4. Built-in agents

### 4. Tool Filtering

Control which tools each subagent can access:
- `tools`: Allowlist of permitted tools
- `disallowed_tools`: Blocklist of forbidden tools

### 5. Permission Modes

- `default` - Standard permission checks
- `acceptEdits` - Auto-accept file edits
- `dontAsk` - Auto-reject permission prompts
- `bypassPermissions` - Skip all checks
- `plan` - Read-only exploration mode

### 6. Persistent Memory

Cross-session knowledge accumulation:
- `user` scope: `~/.heris/agent-memory/<name>/`
- `project` scope: `.heris/agent-memory/<name>/`
- `local` scope: `.heris/agent-memory-local/<name>/`

## Quick Start

### Using Built-in Agents

```python
from heris import LLMClient
from heris.subagent import SubagentRunner, SubagentType

client = LLMClient(api_key="...")

# Explore agent
runner = SubagentRunner.from_builtin(
    agent_type=SubagentType.EXPLORE,
    llm_client=client,
    thoroughness="medium"
)
result = await runner.run("Find all API endpoints")
```

### Using the Registry

```python
from heris.subagent import SubagentRegistry, SubagentTool

# Setup registry
registry = SubagentRegistry()
registry.set_project_directory("./my-project")
registry.discover()

# Use in tool
subagent_tool = SubagentTool(
    llm_client=client,
    registry=registry,
)
```

### Creating Custom Agents

Create `.heris/agents/my-agent.md`:

```markdown
---
name: my-agent
description: Custom agent for specific tasks
tools: Read, Grep, Bash
---

Your system prompt here...
```

## CLI Commands

- `/agents` - List available subagents

## API Reference

### Core Classes

- `SubagentDefinition` - Agent configuration model
- `SubagentRegistry` - Agent discovery and management
- `SubagentRunner` - Execution engine
- `SubagentTool` - Tool integration

### Enums

- `SubagentType` - Built-in agent types
- `Thoroughness` - Exploration levels
- `PermissionMode` - Permission behaviors
- `MemoryScope` - Memory storage scopes

## Compatibility

This module follows Claude Code's agent specification for:
- YAML frontmatter format
- Built-in agent types
- Discovery priority order
- Configuration options
