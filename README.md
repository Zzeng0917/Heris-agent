# Heris

**Heris** is a personal AI agent project. A minimal yet professional framework for building agents with the MiniMax M2.5 model. Leveraging an Anthropic-compatible API, it fully supports interleaved thinking to unlock M2's powerful reasoning capabilities for long, complex tasks.

This project comes packed with features designed for a robust and intelligent agent development experience:

*   ✅ **Full Agent Execution Loop**: A complete and reliable foundation with a basic toolset for file system and shell operations.
*   ✅ **Persistent Memory**: An active **Session Note Tool** ensures the agent retains key information across multiple sessions.
*   ✅ **Intelligent Context Management**: Automatically summarizes conversation history to handle contexts up to a configurable token limit, enabling infinitely long tasks.
*   ✅ **Claude Skills Integration**: Comes with 15 professional skills for documents, design, testing, and development.
*   ✅ **MCP Tool Integration**: Natively supports MCP for tools like knowledge graph access and web search.
*   ✅ **Comprehensive Logging**: Detailed logs for every request, response, and tool execution for easy debugging.
*   ✅ **Clean & Simple Design**: A beautiful CLI and a codebase that is easy to understand, making it the perfect starting point for building advanced agents.

## Quick Start

### 1. Get API Key

MiniMax provides both global and China platforms. Choose based on your network environment:

| Version    | Platform                                                       | API Base                   |
| ---------- | -------------------------------------------------------------- | -------------------------- |
| **Global** | [https://platform.minimax.io](https://platform.minimax.io)     | `https://api.minimax.io`   |
| **China**  | [https://platform.minimaxi.com](https://platform.minimaxi.com) | `https://api.minimaxi.com` |

**Steps to get API Key:**
1. Visit the corresponding platform to register and login
2. Go to **Account Management > API Keys**
3. Click **"Create New Key"**
4. Copy and save it securely (key is only shown once)

> 💡 **Tip**: Remember the API Base address corresponding to your chosen platform, you'll need it for configuration

### 2. Installation

**Prerequisites: Install uv**

```bash
# macOS/Linux/WSL
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Development Mode:**

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd heris

# 2. Sync dependencies
uv sync

# 3. Copy config template
cp heris/config/config-example.yaml heris/config/config.yaml

# 4. Edit config file
vim heris/config/config.yaml  # Or use your preferred editor
```

Fill in your API Key and corresponding API Base:

```yaml
api_key: "YOUR_API_KEY_HERE"          # API Key from step 1
api_base: "https://api.minimax.io"  # Global
# api_base: "https://api.minimaxi.com"  # China
model: "MiniMax-M2.5"
max_steps: 100
workspace_dir: "./workspace"
```

**Run Methods:**

```bash
# Method 1: Run as module directly (good for debugging)
uv run python -m heris.cli

# Method 2: Install in editable mode (recommended)
uv tool install -e .
# After installation, run from anywhere and code changes take effect immediately
heris
heris --workspace /path/to/your/project
```

## Usage Examples

```bash
# Interactive mode
heris

# Non-interactive mode
heris --task "create a simple HTML page"

# Specify workspace
heris --workspace /path/to/project

# View logs
heris log
```

## Project Structure

```
heris/
├── heris/                    # Main package
│   ├── config/              # Configuration files
│   ├── llm/                 # LLM client implementations
│   ├── tools/               # Tool implementations
│   ├── skills/              # Claude skills
│   ├── cli.py               # CLI entry point
│   └── agent.py             # Core agent implementation
├── workspace/               # Default workspace directory
└── pyproject.toml          # Project configuration
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run core functionality tests
pytest tests/test_agent.py tests/test_note_tool.py -v
```

## License

This project is licensed under the [MIT License](LICENSE).

---

**Heris** - Your personal AI assistant
