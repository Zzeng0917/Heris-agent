"""Subagent module for Heris - spawn specialized subagents with isolated context.

This module provides a comprehensive subagent system compatible with Claude Code's
agent specification, supporting:
- YAML frontmatter-based agent definitions
- Built-in specialized agent types (Explore, Plan, General, etc.)
- Agent registry with priority-based discovery
- Tool filtering and permission modes
- Persistent memory support

## Quick Start

### Using Built-in Agents

```python
from heris import LLMClient
from heris.subagent import SubagentRunner, SubagentType

client = LLMClient(api_key="...")

# Use explore agent for codebase exploration
runner = SubagentRunner.from_builtin(
    agent_type=SubagentType.EXPLORE,
    llm_client=client,
    thoroughness="medium"
)
result = await runner.run("Find all API endpoints in this project")
```

### Using the Registry

```python
from heris.subagent import SubagentRegistry, SubagentTool

# Discover all available subagents
registry = SubagentRegistry()
registry.set_project_directory("./my-project")
registry.discover()

# List available subagents
print(registry.list_names())

# Get a specific subagent
code_reviewer = registry.get("code-reviewer")
runner = code_reviewer.create_runner(llm_client=client)
result = await runner.run("Review the auth module")
```

### Creating Custom Subagents

Create a file at `.heris/agents/my-agent.md`:

```markdown
---
name: my-agent
description: Custom agent for specific tasks
tools: Read, Grep, Bash
model: inherit
---

You are a specialized agent for...
```

## Architecture

```
heris/subagent/
├── types.py       # Data models (SubagentDefinition, etc.)
├── loader.py      # YAML frontmatter parser
├── registry.py    # Agent discovery and registry
├── builtin.py     # Built-in agent types
├── runner.py      # Execution engine
└── tool.py        # Tool integration
```

## Compatibility

This module follows Claude Code's agent specification:
- YAML frontmatter format is compatible
- Built-in agent types match Claude Code's
- Priority-based discovery follows same rules
"""

from .types import (
    SubagentDefinition,
    SubagentType,
    Thoroughness,
    PermissionMode,
    MemoryScope,
    SubagentConfig,
    SubagentSearchPath,
)
from .loader import (
    load_subagent_definition,
    save_subagent_definition,
    scan_directory,
    parse_frontmatter,
    SubagentLoadError,
)
from .registry import (
    SubagentRegistry,
    create_default_registry,
)
from .builtin import (
    get_builtin_definition,
    get_all_builtin_definitions,
    list_builtin_types,
    BUILTIN_SUBAGENTS,
)
from .runner import (
    SubagentRunner,
    run_subagent,
    SUBAGENT_SYSTEM_PROMPT,
)
from .tool import SubagentTool

__all__ = [
    # Types
    "SubagentDefinition",
    "SubagentType",
    "Thoroughness",
    "PermissionMode",
    "MemoryScope",
    "SubagentConfig",
    "SubagentSearchPath",
    # Loader
    "load_subagent_definition",
    "save_subagent_definition",
    "scan_directory",
    "parse_frontmatter",
    "SubagentLoadError",
    # Registry
    "SubagentRegistry",
    "create_default_registry",
    # Builtin
    "get_builtin_definition",
    "get_all_builtin_definitions",
    "list_builtin_types",
    "BUILTIN_SUBAGENTS",
    # Runner
    "SubagentRunner",
    "run_subagent",
    "SUBAGENT_SYSTEM_PROMPT",
    # Tool
    "SubagentTool",
]

__version__ = "2.0.0"
