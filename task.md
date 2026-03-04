第一步：新增 heris/tools/mode_tool.py
        - SetModeTool
        - GetCurrentModeTool

第二步：新增 heris/modes.py（或 heris/config/modes.py）
        - ModeType 枚举
        - UrgencyLevel 枚举
        - AgentMode 数据类（含 build_prompt_injection() 方法）
        - 四种模式的 Prompt 片段

第三步：修改 heris/config/system_prompt.md
        - 添加 {MODE_PROMPT} 占位符

第四步：修改 heris/cli.py
        - 新增 select_mode_interactive() 函数（启动时的模式选择 UI）
        - run_agent() 中注入模式 Prompt
        - 注册 SetModeTool 到工具列表
        - 添加 /mode 交互命令
        - 添加 --mode CLI 参数

第五步：修改 heris/agent.py
        - 添加 update_persona() 方法，支持运行时修改人格片段