# Heris

Heris 是一个极简但专业的 AI Agent 框架，兼容 Anthropic API 格式，支持交错思维能力。

## 特点

- **完整的 Agent 执行循环** - 可靠的执行框架，内置文件系统和 Shell 操作工具
- **持久化记忆** - Session Note Tool 实现跨会话信息保留
- **智能上下文管理** - 自动摘要处理，支持长上下文任务
- **多模型支持** - 支持多种 LLM Provider
- **Claude Skills** - 内置多种专业技能（文档处理、设计、测试等）
- **MCP 工具** - 原生支持 Model Context Protocol，可扩展知识图谱、网页搜索等工具

## 项目结构

```
heris/
├── cli.py              # 命令行入口
├── agents/             # Agent 执行核心
├── tools/              # 基础工具集
│   ├── file_tools.py   # 文件读写编辑
│   ├── bash_tool.py    # Shell 命令执行
│   └── note_tool.py    # 会话笔记
├── skills/             # Claude Skills 技能库
├── llm/                # LLM 客户端
├── mcp/                # MCP 工具支持
├── acp/                # Agent Communication Protocol
└── config/             # 配置文件
```

## 快速使用

### 安装

```bash
# 使用 uv 安装
uv tool install git+https://github.com/Zzeng0917/Heris-agent.git

# 或克隆开发
git clone https://github.com/Zzeng0917/Heris-agent.git
cd Heris-agent
uv sync
```

### 配置

复制配置文件：

```bash
cp heris/config/config-example.yaml heris/config/config.yaml
```

编辑 `config.yaml`，填写你的 API Key 和配置：

```yaml
api_key: "YOUR_API_KEY"
api_base: "YOUR_API_BASE"
model: "YOUR_MODEL_NAME"
provider: "anthropic"
```

### 运行

```bash
heris                              # 启动交互式 CLI
heris --workspace ./my-project     # 指定工作目录
```

### MCP 配置（可选）

在 `~/.heris/config/mcp.json` 配置 MCP 工具：

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

## 许可证

MIT
