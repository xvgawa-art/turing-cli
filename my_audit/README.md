# my_audit

我的审计工作流

## 使用方法

```bash
# 进入项目目录
cd my_audit

# 运行工作流
python my_audit_workflow.py
```

## 工作流结构

```
my_audit/
├── my_audit_workflow.py    # 主工作流文件
├── agents/
│   └── custom_agent.py   # 自定义 Agent
├── config/
│   └── config.yaml       # 配置文件
└── README.md
```

## 自定义 Agent

在 `agents/` 目录下创建新的 Agent 类：

```python
from turing_cli.agents.runner import BaseAgentRunner, AgentContext

class MyAgent(BaseAgentRunner):
    def _execute(self, context: AgentContext) -> dict:
        # 实现你的逻辑
        return {"status": "completed"}
```

## 配置

编辑 `config/config.yaml` 来配置 Agent 和工作流参数。
