"""Tests for upgraded subagent module v2.0"""

import pytest
from pathlib import Path

from heris.subagent import (
    SubagentDefinition,
    SubagentType,
    Thoroughness,
    PermissionMode,
    MemoryScope,
    SubagentRegistry,
    SubagentRunner,
    SubagentTool,
    load_subagent_definition,
    save_subagent_definition,
    scan_directory,
    parse_frontmatter,
    SubagentLoadError,
    get_builtin_definition,
    get_all_builtin_definitions,
    list_builtin_types,
    BUILTIN_SUBAGENTS,
)


class TestTypes:
    """Test type definitions"""

    def test_subagent_type_enum(self):
        assert SubagentType.EXPLORE.value == "explore"
        assert SubagentType.PLAN.value == "plan"
        assert SubagentType.GENERAL.value == "general"

    def test_thoroughness_enum(self):
        assert Thoroughness.QUICK.value == "quick"
        assert Thoroughness.MEDIUM.value == "medium"
        assert Thoroughness.VERY_THOROUGH.value == "very_thorough"

    def test_permission_mode_enum(self):
        assert PermissionMode.DEFAULT.value == "default"
        assert PermissionMode.ACCEPT_EDITS.value == "acceptEdits"
        assert PermissionMode.PLAN.value == "plan"

    def test_memory_scope_enum(self):
        assert MemoryScope.USER.value == "user"
        assert MemoryScope.PROJECT.value == "project"
        assert MemoryScope.LOCAL.value == "local"


class TestSubagentDefinition:
    """Test SubagentDefinition model"""

    def test_basic_creation(self):
        defn = SubagentDefinition(
            name="test-agent",
            description="A test agent",
            system_prompt="You are a test agent.",
        )
        assert defn.name == "test-agent"
        assert defn.description == "A test agent"
        assert defn.model == "inherit"  # default

    def test_name_validation(self):
        with pytest.raises(ValueError):
            SubagentDefinition(name="", description="test")

        with pytest.raises(ValueError):
            SubagentDefinition(name="Invalid Name", description="test")

        with pytest.raises(ValueError):
            SubagentDefinition(name="-invalid", description="test")

    def test_is_builtin_type(self):
        defn = SubagentDefinition(name="explore", description="test", system_prompt="test")
        assert defn.is_builtin_type()

        defn2 = SubagentDefinition(name="custom-agent", description="test", system_prompt="test")
        assert not defn2.is_builtin_type()

    def test_get_memory_path_user(self):
        defn = SubagentDefinition(
            name="test-agent",
            description="test",
            memory=MemoryScope.USER,
            system_prompt="test",
        )
        path = defn.get_memory_path()
        assert path is not None
        assert ".heris/agent-memory/test-agent" in str(path)

    def test_get_memory_path_project(self):
        defn = SubagentDefinition(
            name="test-agent",
            description="test",
            memory=MemoryScope.PROJECT,
            system_prompt="test",
        )
        path = defn.get_memory_path(Path("/project"))
        assert path is not None
        assert "/project/.heris/agent-memory/test-agent" in str(path)


class TestLoader:
    """Test loader functions"""

    def test_parse_frontmatter_valid(self):
        content = """---
name: test-agent
description: A test agent
tools: Read, Write
---

You are a test agent.
"""
        frontmatter, body = parse_frontmatter(content)
        assert frontmatter["name"] == "test-agent"
        assert frontmatter["description"] == "A test agent"
        assert frontmatter["tools"] == "Read, Write"
        assert body == "You are a test agent."

    def test_parse_frontmatter_invalid(self):
        with pytest.raises(SubagentLoadError):
            parse_frontmatter("No frontmatter here")

    def test_load_and_save_definition(self, tmp_path):
        defn = SubagentDefinition(
            name="test-agent",
            description="A test agent",
            tools=["Read", "Write"],
            model="sonnet",
            system_prompt="You are a test agent.",
        )

        file_path = tmp_path / "test-agent.md"
        save_subagent_definition(defn, file_path)
        assert file_path.exists()

        loaded = load_subagent_definition(file_path)
        assert loaded.name == defn.name
        assert loaded.description == defn.description
        assert loaded.tools == defn.tools
        assert loaded.model == defn.model

    def test_scan_directory(self, tmp_path):
        # Create test files
        (tmp_path / "agent1.md").write_text("""---
name: agent-1
description: First agent
---
System prompt 1
""")
        (tmp_path / "agent2.md").write_text("""---
name: agent-2
description: Second agent
---
System prompt 2
""")
        (tmp_path / "not-an-agent.txt").write_text("not an agent")

        definitions = scan_directory(tmp_path)
        assert len(definitions) == 2
        names = {d.name for d in definitions}
        assert names == {"agent-1", "agent-2"}


class TestBuiltin:
    """Test builtin agents"""

    def test_get_builtin_definition(self):
        defn = get_builtin_definition(SubagentType.EXPLORE)
        assert defn.name == "explore"
        assert defn.tools is not None
        assert "Read" in defn.tools
        assert "Grep" in defn.tools

    def test_get_all_builtin_definitions(self):
        definitions = get_all_builtin_definitions()
        assert len(definitions) == len(SubagentType)
        names = {d.name for d in definitions}
        assert "explore" in names
        assert "plan" in names
        assert "general-purpose" in names

    def test_list_builtin_types(self):
        types = list_builtin_types()
        assert "explore" in types
        assert "plan" in types
        assert "code-review" in types


class TestRegistry:
    """Test SubagentRegistry"""

    def test_basic_registry(self):
        registry = SubagentRegistry()
        # Registry auto-discovers on first access
        names = registry.list_names()
        assert len(names) >= len(SubagentType)  # At least builtins

    def test_discover_includes_builtins(self):
        registry = SubagentRegistry()
        count = registry.discover()
        assert count >= len(SubagentType)  # At least builtins

        names = registry.list_names()
        assert "explore" in names
        assert "plan" in names

    def test_get_builtin(self):
        registry = SubagentRegistry()
        defn = registry.get_builtin(SubagentType.DEBUG)
        assert defn.name == "debug"

    def test_register_custom(self):
        registry = SubagentRegistry()
        defn = SubagentDefinition(
            name="custom-agent",
            description="Custom agent",
            system_prompt="You are custom.",
        )
        registry.register(defn)
        assert "custom-agent" in registry.list_names()

        retrieved = registry.get("custom-agent")
        assert retrieved is not None
        assert retrieved.name == "custom-agent"

    def test_unregister(self):
        registry = SubagentRegistry()
        defn = SubagentDefinition(
            name="temp-agent",
            description="Temp agent",
            system_prompt="test",
        )
        registry.register(defn)
        assert "temp-agent" in registry.list_names()

        assert registry.unregister("temp-agent")
        assert "temp-agent" not in registry.list_names()
        assert not registry.unregister("temp-agent")  # Already removed


class TestSubagentRunner:
    """Test SubagentRunner"""

    def test_from_builtin(self):
        runner = SubagentRunner.from_builtin(
            agent_type=SubagentType.EXPLORE,
            llm_client=None,
            tools=[],
        )
        assert runner.definition is not None
        assert runner.definition.name == "explore"
        assert runner.thoroughness == Thoroughness.MEDIUM

    def test_from_builtin_with_thoroughness(self):
        runner = SubagentRunner.from_builtin(
            agent_type=SubagentType.EXPLORE,
            llm_client=None,
            tools=[],
            thoroughness=Thoroughness.VERY_THOROUGH,
        )
        assert runner.thoroughness == Thoroughness.VERY_THOROUGH

    def test_from_definition(self):
        defn = SubagentDefinition(
            name="test-agent",
            description="Test",
            max_turns=25,
            system_prompt="test",
        )
        runner = SubagentRunner.from_definition(
            definition=defn,
            llm_client=None,
            tools=[],
        )
        assert runner.definition == defn
        assert runner.max_steps == 25

    def test_tool_filtering(self):
        from heris.tools.base import Tool, ToolResult

        class MockTool(Tool):
            @property
            def name(self):
                return "mock_tool"

            @property
            def description(self):
                return "Mock tool"

            @property
            def parameters(self):
                return {"type": "object", "properties": {}}

            async def execute(self, **kwargs):
                return ToolResult(success=True, content="ok")

        tools = [MockTool()]

        # With allowed tools
        defn = SubagentDefinition(
            name="test",
            description="test",
            tools=["mock_tool"],
            system_prompt="test",
        )
        runner = SubagentRunner.from_definition(
            definition=defn,
            llm_client=None,
            tools=tools,
        )
        assert "mock_tool" in runner.tools

        # With disallowed tools
        defn2 = SubagentDefinition(
            name="test",
            description="test",
            disallowed_tools=["mock_tool"],
            system_prompt="test",
        )
        runner2 = SubagentRunner.from_definition(
            definition=defn2,
            llm_client=None,
            tools=tools,
        )
        assert "mock_tool" not in runner2.tools

    def test_get_stats(self):
        runner = SubagentRunner.from_builtin(
            agent_type=SubagentType.GENERAL,
            llm_client=None,
            tools=[],
        )
        stats = runner.get_stats()
        assert "executed_steps" in stats
        assert "max_steps" in stats
        assert "available_tools" in stats


class TestSubagentTool:
    """Test SubagentTool"""

    def test_tool_properties(self):
        tool = SubagentTool(llm_client=None)
        assert tool.name == "spawn_subagent"
        assert "delegate" in tool.description.lower()

    def test_tool_parameters(self):
        tool = SubagentTool(llm_client=None)
        params = tool.parameters
        assert params["type"] == "object"
        assert "prompt" in params["properties"]
        assert "agent_name" in params["properties"]
        assert "thoroughness" in params["properties"]

    def test_with_tools(self):
        from heris.tools.base import Tool, ToolResult

        class MockTool(Tool):
            @property
            def name(self):
                return "mock_tool"

            @property
            def description(self):
                return "Mock"

            @property
            def parameters(self):
                return {"type": "object", "properties": {}}

            async def execute(self, **kwargs):
                return ToolResult(success=True, content="ok")

        tool = SubagentTool(llm_client=None)
        new_tool = tool.with_tools([MockTool()])
        assert len(new_tool.tools) == 1

    def test_with_registry(self):
        registry = SubagentRegistry()
        tool = SubagentTool(llm_client=None)
        new_tool = tool.with_registry(registry)
        assert new_tool.registry is registry

    def test_list_available(self):
        tool = SubagentTool(llm_client=None)
        available = tool.list_available()
        assert "builtin" in available
        assert "registry" in available
        assert "explore" in available["builtin"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
