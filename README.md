# Heris / Heris

Heris 是一个极简但专业的 AI Agent 框架，兼容 Anthropic API 格式，支持交错思维能力。

Heris is a minimal yet professional AI Agent framework, compatible with Anthropic API format, supporting interleaved thinking.

## 特点 / Features

| 功能 | Feature |
|------|---------|
| 完整 Agent 执行循环，内置文件系统和 Shell 工具 | Full Agent execution loop with built-in file system and Shell tools |
| 持久化记忆，跨会话信息保留 | Persistent memory for cross-session information retention |
| 智能上下文管理，自动摘要处理 | Intelligent context management with automatic summarization |
| 多模型支持，多种 LLM Provider | Multi-model support across various LLM providers |
| Claude Skills 专业技能库 | Claude Skills professional skill library |
| MCP 原生支持 | Native MCP support |

## 技术栈 / Tech Stack

- **Runtime**: Python 3.11+
- **Package Manager**: uv
- **API**: Anthropic API / OpenAI API
- **Protocol**: MCP (Model Context Protocol)

## 项目结构 / Project Structure

```
heris/
├── cli.py           # CLI entry point
├── agents/          # Agent execution core
├── tools/           # Built-in tools (file, shell, memory)
├── llm/             # LLM client (Anthropic / OpenAI)
├── mcp/             # MCP support
├── skills/          # Claude Skills
└── config/          # Configuration
```

## 快速开始 / Quick Start

### 安装 / Install

```bash
# Install via uv
uv tool install git+https://github.com/Zzeng0917/Heris-agent.git

# Or clone for development
git clone https://github.com/Zzeng0917/Heris-agent.git
cd Heris-agent
uv sync
```

### 配置 / Configure

```bash
cp heris/config/config-example.yaml heris/config/config.yaml
```

Edit `config.yaml`:

```yaml
api_key: "YOUR_API_KEY"
api_base: "YOUR_API_BASE"
model: "YOUR_MODEL_NAME"
provider: "anthropic"
```

### 运行 / Run

```bash
heris                              # Start interactive CLI
heris --workspace ./my-project     # Specify workspace
```

### MCP 配置 / MCP Config (Optional)

```json
{
  "mcpServers": {
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    }
  }
}
```

## License

MIT
