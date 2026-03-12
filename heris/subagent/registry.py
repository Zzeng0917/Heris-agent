"""Subagent registry - discovery and management of subagent definitions.

Provides centralized management for subagents from multiple sources:
- Built-in subagents
- Project-specific agents (.heris/agents/)
- User-level agents (~/.heris/agents/)
- CLI-specified agent directories
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

from .types import SubagentDefinition, SubagentSearchPath
from .builtin import get_all_builtin_definitions, get_builtin_definition, SubagentType
from .loader import scan_directory, load_subagent_definition

logger = logging.getLogger(__name__)


class SubagentRegistry:
    """Registry for subagent definitions.

    Manages subagents from multiple sources with priority-based resolution.
    Higher priority definitions override lower priority ones with the same name.

    Priority order (1 = highest):
    1. CLI-specified directories (--agents flag)
    2. Project-specific agents (.heris/agents/)
    3. User-level agents (~/.heris/agents/)
    4. Built-in agents (package)
    """

    # Default search paths
    DEFAULT_SEARCH_PATHS: list[SubagentSearchPath] = [
        SubagentSearchPath(
            path=Path.home() / ".heris" / "agents",
            scope="user",
            priority=3,
        ),
    ]

    def __init__(self):
        """Initialize empty registry."""
        self._definitions: dict[str, SubagentDefinition] = {}
        self._search_paths: list[SubagentSearchPath] = []
        self._project_dir: Path | None = None
        self._cli_path: Path | None = None

    def set_project_directory(self, project_dir: Path | str) -> None:
        """Set the project directory for project-scoped agents.

        Args:
            project_dir: Path to project root
        """
        self._project_dir = Path(project_dir)
        # Invalidate cached definitions
        self._definitions.clear()

    def set_cli_directory(self, cli_path: Path | str) -> None:
        """Set the CLI-specified agent directory (highest priority).

        Args:
            cli_path: Path to agent directory
        """
        self._cli_path = Path(cli_path)
        # Invalidate cached definitions
        self._definitions.clear()

    def _build_search_paths(self) -> list[SubagentSearchPath]:
        """Build the complete list of search paths with correct priorities.

        Returns:
            List of search paths sorted by priority (highest first)
        """
        paths: list[SubagentSearchPath] = []

        # Priority 1: CLI-specified directory
        if self._cli_path:
            paths.append(SubagentSearchPath(
                path=self._cli_path,
                scope="cli",
                priority=1,
            ))

        # Priority 2: Project-specific directory
        if self._project_dir:
            paths.append(SubagentSearchPath(
                path=self._project_dir / ".heris" / "agents",
                scope="project",
                priority=2,
            ))

        # Priority 3+: Default search paths
        paths.extend(self.DEFAULT_SEARCH_PATHS)

        # Sort by priority (lower number = higher priority)
        paths.sort(key=lambda p: p.priority)
        return paths

    def discover(self) -> int:
        """Discover and load all subagent definitions from search paths.

        Loads definitions from all sources, with higher priority sources
        overriding lower priority ones for agents with the same name.

        Returns:
            Number of subagent definitions loaded
        """
        self._definitions.clear()
        search_paths = self._build_search_paths()

        # Track loaded names and their sources
        loaded: dict[str, tuple[SubagentDefinition, int]] = {}

        # Load from each search path
        for search_path in search_paths:
            if not search_path.path.exists():
                logger.debug(f"Skipping non-existent search path: {search_path.path}")
                continue

            try:
                definitions = scan_directory(search_path.path)
                for definition in definitions:
                    existing = loaded.get(definition.name)
                    if existing:
                        existing_defn, existing_priority = existing
                        if search_path.priority < existing_priority:
                            logger.debug(
                                f"Overriding '{definition.name}' from {existing_defn.source_path} "
                                f"with version from {search_path.path} (higher priority)"
                            )
                            loaded[definition.name] = (definition, search_path.priority)
                        else:
                            logger.debug(
                                f"Skipping '{definition.name}' from {search_path.path} "
                                f"(lower priority than existing)"
                            )
                    else:
                        loaded[definition.name] = (definition, search_path.priority)
            except Exception as e:
                logger.warning(f"Error scanning {search_path.path}: {e}")

        # Load built-in agents (lowest priority)
        for definition in get_all_builtin_definitions():
            if definition.name not in loaded:
                loaded[definition.name] = (definition, 999)

        # Store final definitions
        self._definitions = {name: defn for name, (defn, _) in loaded.items()}

        return len(self._definitions)

    def get(self, name: str) -> SubagentDefinition | None:
        """Get a subagent definition by name.

        Args:
            name: Subagent name

        Returns:
            SubagentDefinition or None if not found
        """
        # Auto-discover if not loaded
        if not self._definitions:
            self.discover()
        return self._definitions.get(name)

    def get_builtin(self, agent_type: SubagentType) -> SubagentDefinition:
        """Get a built-in subagent definition.

        Args:
            agent_type: Built-in subagent type

        Returns:
            SubagentDefinition
        """
        return get_builtin_definition(agent_type)

    def list_all(self) -> list[SubagentDefinition]:
        """List all available subagent definitions.

        Returns:
            List of all subagent definitions
        """
        if not self._definitions:
            self.discover()
        return list(self._definitions.values())

    def list_names(self) -> list[str]:
        """List names of all available subagents.

        Returns:
            List of subagent names
        """
        if not self._definitions:
            self.discover()
        return list(self._definitions.keys())

    def register(self, definition: SubagentDefinition) -> None:
        """Register a custom subagent definition.

        Args:
            definition: Subagent definition to register
        """
        self._definitions[definition.name] = definition

    def unregister(self, name: str) -> bool:
        """Unregister a subagent definition.

        Args:
            name: Name of subagent to unregister

        Returns:
            True if was registered, False otherwise
        """
        if name in self._definitions:
            del self._definitions[name]
            return True
        return False

    def __contains__(self, name: str) -> bool:
        """Check if a subagent is registered."""
        return name in self._definitions

    def __iter__(self) -> Iterator[SubagentDefinition]:
        """Iterate over all registered subagents."""
        return iter(self._definitions.values())

    def __len__(self) -> int:
        """Number of registered subagents."""
        return len(self._definitions)

    def reload(self) -> int:
        """Reload all subagent definitions from disk.

        Returns:
            Number of subagent definitions loaded
        """
        return self.discover()


def create_default_registry(
    project_dir: Path | str | None = None,
    cli_path: Path | str | None = None,
) -> SubagentRegistry:
    """Create a default registry with standard configuration.

    Args:
        project_dir: Optional project directory
        cli_path: Optional CLI-specified agent directory

    Returns:
        Configured SubagentRegistry
    """
    registry = SubagentRegistry()

    if project_dir:
        registry.set_project_directory(project_dir)
    if cli_path:
        registry.set_cli_directory(cli_path)

    registry.discover()
    return registry
