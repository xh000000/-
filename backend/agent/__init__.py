"""Agent 服务层：LangGraph 智能体基座。

分层
----
- config.py  模型配置：AGENT_* 环境变量优先，逐项回落到页面外部模型（AI_*）。
- memory.py  会话记忆：LangGraph SqliteSaver，独立于业务库（agent_memory.db）。
- tools.py   工具注册表：把平台引擎包装成 agent 可调用的工具，写操作复用平台处理器。
- graph.py   ReAct 智能体：create_react_agent + 持久记忆 + 平台系统提示词。
- service.py 运行服务：SSE 事件流、线程管理、后台任务队列。
- routes.py  API 路由：/api/agent/*，由 app.py 在启动时挂载。

依赖是可选的：没装 langchain 系列时 app.py 会跳过挂载，平台以无 Agent 模式运行。
"""
