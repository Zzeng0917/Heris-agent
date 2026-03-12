"""Subagent definition loader - parses YAML frontmatter from Markdown files.

Supports Claude Code compatible agent definition format:
    ---
    name: agent-name
    description: When to use this agent
    tools: Read, Grep, Glob
    ---

    System prompt content here...
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from .types import SubagentDefinition, PermissionMode, MemoryScope


# Regex to match YAML frontmatter in markdown
FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)$",
    re.DOTALL | re.MULTILINE,
)


class SubagentLoadError(Exception):
    """Error loading subagent definition."""
    pass


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: Markdown content with optional YAML frontmatter

    Returns:
        Tuple of (frontmatter dict, markdown body)

    Raises:
        SubagentLoadError: If frontmatter is invalid
    """
    if yaml is None:
        raise SubagentLoadError("PyYAML is required to parse agent definitions")

    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        raise SubagentLoadError(
            "Invalid agent definition format. Expected YAML frontmatter between '---' markers."
        )

    yaml_content = match.group(1)
    markdown_body = match.group(2).strip()

    try:
        frontmatter = yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError as e:
        raise SubagentLoadError(f"Invalid YAML in frontmatter: {e}")

    if not isinstance(frontmatter, dict):
        raise SubagentLoadError("Frontmatter must be a YAML dictionary")

    return frontmatter, markdown_body


def load_subagent_definition(path: Path) -> SubagentDefinition:
    """Load a subagent definition from a Markdown file.

    Args:
        path: Path to the .md file

    Returns:
        SubagentDefinition instance

    Raises:
        SubagentLoadError: If file cannot be loaded or is invalid
        FileNotFoundError: If file does not exist
    """
    if not path.exists():
        raise FileNotFoundError(f"Agent definition file not found: {path}")

    if not path.suffix == ".md":
        raise SubagentLoadError(f"Agent definition must be a .md file: {path}")

    content = path.read_text(encoding="utf-8")

    try:
        frontmatter, body = parse_frontmatter(content)
    except SubagentLoadError as e:
        raise SubagentLoadError(f"Failed to parse {path}: {e}")

    # Validate required fields
    if "name" not in frontmatter:
        raise SubagentLoadError(f"Missing required field 'name' in {path}")
    if "description" not in frontmatter:
        raise SubagentLoadError(f"Missing required field 'description' in {path}")

    # Parse enum fields
    permission_mode = frontmatter.get("permission_mode", "default")
    if isinstance(permission_mode, str):
        try:
            permission_mode = PermissionMode(permission_mode)
        except ValueError:
            valid_modes = [m.value for m in PermissionMode]
            raise SubagentLoadError(
                f"Invalid permission_mode '{permission_mode}'. "
                f"Must be one of: {', '.join(valid_modes)}"
            )

    memory = frontmatter.get("memory")
    if isinstance(memory, str):
        try:
            memory = MemoryScope(memory)
        except ValueError:
            valid_scopes = [m.value for m in MemoryScope]
            raise SubagentLoadError(
                f"Invalid memory scope '{memory}'. "
                f"Must be one of: {', '.join(valid_scopes)}"
            )

    # Parse tools - handle both string and list formats
    tools = frontmatter.get("tools")
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]

    disallowed_tools = frontmatter.get("disallowed_tools") or frontmatter.get("disallowedTools")
    if isinstance(disallowed_tools, str):
        disallowed_tools = [t.strip() for t in disallowed_tools.split(",") if t.strip()]

    # Build definition
    definition = SubagentDefinition(
        name=frontmatter["name"],
        description=frontmatter["description"],
        tools=tools,
        disallowed_tools=disallowed_tools,
        model=frontmatter.get("model", "inherit"),
        permission_mode=permission_mode,
        max_turns=frontmatter.get("max_turns") or frontmatter.get("maxTurns"),
        skills=frontmatter.get("skills"),
        mcp_servers=frontmatter.get("mcp_servers") or frontmatter.get("mcpServers"),
        memory=memory,
        background=frontmatter.get("background", False),
        isolation=frontmatter.get("isolation"),
        system_prompt=body,
        source_path=path,
    )

    return definition


def save_subagent_definition(definition: SubagentDefinition, path: Path) -> None:
    """Save a subagent definition to a Markdown file.

    Args:
        definition: Subagent definition to save
        path: Path to save to

    Raises:
        SubagentLoadError: If yaml is not available
    """
    if yaml is None:
        raise SubagentLoadError("PyYAML is required to save agent definitions")

    # Build frontmatter
    frontmatter_data: dict[str, Any] = {
        "name": definition.name,
        "description": definition.description,
    }

    if definition.tools is not None:
        frontmatter_data["tools"] = definition.tools
    if definition.disallowed_tools is not None:
        frontmatter_data["disallowed_tools"] = definition.disallowed_tools
    if definition.model != "inherit":
        frontmatter_data["model"] = definition.model
    if definition.permission_mode != PermissionMode.DEFAULT:
        frontmatter_data["permission_mode"] = definition.permission_mode.value
    if definition.max_turns is not None:
        frontmatter_data["max_turns"] = definition.max_turns
    if definition.skills is not None:
        frontmatter_data["skills"] = definition.skills
    if definition.mcp_servers is not None:
        frontmatter_data["mcp_servers"] = definition.mcp_servers
    if definition.memory is not None:
        frontmatter_data["memory"] = definition.memory.value
    if definition.background:
        frontmatter_data["background"] = True
    if definition.isolation is not None:
        frontmatter_data["isolation"] = definition.isolation

    # Convert to YAML
    yaml_content = yaml.dump(
        frontmatter_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    # Build full content
    content = f"---\n{yaml_content}---\n\n{definition.system_prompt}\n"

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    path.write_text(content, encoding="utf-8")


def scan_directory(directory: Path) -> list[SubagentDefinition]:
    """Scan a directory for subagent definition files.

    Args:
        directory: Directory to scan

    Returns:
        List of loaded subagent definitions
    """
    if not directory.exists():
        return []

    definitions = []
    for file_path in directory.glob("*.md"):
        try:
            definition = load_subagent_definition(file_path)
            definitions.append(definition)
        except SubagentLoadError:
            # Skip invalid definitions
            continue
        except Exception:
            # Skip files that can't be loaded
            continue

    return definitions
