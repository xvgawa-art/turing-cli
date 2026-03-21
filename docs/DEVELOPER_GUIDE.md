# Workflow 开发指南

本指南介绍如何使用 turing-cli 框架开发自定义工作流。

## 快速开始

### 创建脚手架

使用 `turing init` 命令快速创建工作流脚手架：

```bash
# 基础脚手架
turing init my_workflow

# 带自定义 Agent 模板
turing init my_workflow --with-agent

# 指定描述和输出目录
turing init my_audit -d "安全审计工作流" -o ./workflows
```

生成的目录结构：

```
my_workflow/
├── my_workflow_workflow.py    # 主工作流文件
├── agents/
│   └── custom_agent.py        # 自定义 Agent（可选）
├── config/
│   └── config.yaml            # 配置文件
└── README.md
```

## 核心概念

### 1. Agent Runner

Agent Runner 是实际执行任务的地方。每个 Agent 接收上下文，执行任务，返回结果。

```python
from turing_cli.workflow.models import ExecutionContext

def my_agent_runner(agent_name: str, context: ExecutionContext) -> dict:
    """Agent 执行器"""

    # 获取上下文信息
    project_id = context.project_id
    custom_data = context.get("custom_key")

    # 获取其他 Agent 的结果
    prev_result = context.get_agent_result("previous_agent")

    # 执行任务...
    result = do_something(agent_name, custom_data)

    return {
        "status": "success",  # 或 "failed"
        "result": result,
    }
```

### 2. Workflow Builder

使用声明式 API 构建工作流：

```python
from turing_cli.workflow.builder import WorkflowBuilder

builder = WorkflowBuilder("my_workflow")

# 串行执行
with builder.sequential_group("phase1") as group:
    group.add_agent("agent_a")
    group.add_agent("agent_b")

# 并行执行
with builder.parallel_group("phase2") as group:
    group.add_agent("agent_x")
    group.add_agent("agent_y")
    group.max_concurrency(3)

# 错误处理
builder.on_error("retry", max_retries=3)
```

### 3. Workflow Engine

执行工作流：

```python
from turing_cli.workflow.engine import WorkflowEngine

engine = WorkflowEngine(builder.build(), agent_runner=my_agent_runner)

result = engine.run({
    "project_id": "my-project",
    "custom_key": "value",
})

print(f"成功: {result.success}")
print(f"结果: {result.task_results}")
```

## 执行组详解

### SequentialGroup（串行执行）

按顺序依次执行，适用于有依赖关系的任务：

```python
with builder.sequential_group("data_pipeline") as group:
    group.add_agent("collector")    # 1. 收集数据
    group.add_agent("processor")    # 2. 处理数据
    group.add_agent("reporter")     # 3. 生成报告
```

### ParallelGroup（并行执行）

同时执行多个任务，提高效率：

```python
with builder.parallel_group("parallel_scan") as group:
    group.add_agent("sql_scanner")
    group.add_agent("xss_scanner")
    group.add_agent("auth_scanner")
    group.max_concurrency(5)  # 最大并发数
```

**动态 Agent 列表**：运行时决定执行哪些 Agent

```python
def get_agents(ctx):
    # 根据上下文返回 Agent 列表
    vulns = ctx.get("vulnerabilities", [])
    return [f"vuln-{i}" for i in range(len(vulns))]

with builder.parallel_group("dynamic") as group:
    group.dynamic_agents(get_agents)
    group.max_concurrency(10)
```

### ConditionalGroup（条件执行）

满足条件时才执行：

```python
with builder.conditional_group("high_risk_check") as group:
    group.condition(lambda ctx: ctx.get("risk_level") == "high")
    group.add_agent("deep_analyzer")
```

### LoopGroup（循环执行）

重复执行直到条件不满足：

```python
with builder.loop_group("iteration") as group:
    group.condition(lambda ctx: ctx.get("needs_more_work", True))
    group.max_iterations(5)
    group.add_agent("refiner")
```

## 自定义 Agent

### 继承 BaseAgentRunner

```python
from pathlib import Path
from turing_cli.agents.runner import BaseAgentRunner, AgentContext

class MyCustomAgent(BaseAgentRunner):
    """自定义 Agent"""

    def __init__(self, deliverables_path: Path, code_path: Path, **kwargs):
        super().__init__(deliverables_path, code_path)
        self.config = kwargs.get("config", {})

    def _execute(self, context: AgentContext) -> dict:
        """实现执行逻辑"""
        agent_id = context.agent_id
        task_data = context.task_data

        # 你的逻辑...

        return {
            "status": "completed",
            "result": "...",
        }
```

### 在工作流中使用

```python
from my_agent import MyCustomAgent

def my_agent_runner(agent_name: str, context: ExecutionContext) -> dict:
    agent = MyCustomAgent(
        deliverables_path=Path("./deliverables"),
        code_path=Path("./src"),
    )

    agent_context = AgentContext(
        agent_id=agent_name,
        task_data=context.get("tasks", {}).get(agent_name, {}),
        shared_context=context._data,
    )

    return agent.run(agent_name, {
        "task_data": agent_context.task_data,
        "shared_context": agent_context.shared_context,
    })
```

## 错误处理

### 策略选择

| 策略 | 适用场景 |
|------|----------|
| `retry` | 临时性错误，重试可能成功 |
| `skip` | 非关键任务，跳过不影响整体 |
| `abort` | 关键任务，失败需要停止 |

```python
# 重试策略
builder.on_error("retry", max_retries=3, backoff=1.0)

# 跳过策略
builder.on_error("skip")

# 中止策略
builder.on_error("abort")
```

### Agent 内部错误处理

```python
def my_agent_runner(agent_name: str, context: ExecutionContext) -> dict:
    try:
        result = do_risky_operation()
        return {"status": "success", "result": result}
    except TemporaryError as e:
        # 返回 failed 会触发 retry
        return {"status": "failed", "error": str(e)}
    except CriticalError as e:
        # 返回 skipped 会跳过
        return {"status": "skipped", "error": str(e)}
```

## Git 集成

### 自动分支管理

框架自动为每个 Agent 创建独立分支：

```python
from turing_cli.git_ops.manager import GitManager
from turing_cli.agents.runner import BaseAgentRunner

class MyAgent(BaseAgentRunner):
    def _execute(self, context):
        # Git 管理器会自动：
        # 1. 创建 agent-{agent_id} 分支
        # 2. 成功后合并到审计分支
        # 3. 失败时回滚并删除分支

        # 你可以手动操作
        if self.git_mgr:
            self.git_mgr.commit_changes("中间结果")

        return {"status": "completed"}
```

### 手动 Git 操作

```python
from turing_cli.git_ops.manager import GitManager
from turing_cli.git_ops.rollback import RollbackManager

git_mgr = GitManager(Path("./repo"))
rollback_mgr = RollbackManager(git_mgr, Path("./deliverables"))

# 初始化审计
audit_branch = git_mgr.init_audit("my-audit")

# 创建 Agent 分支
agent_branch = git_mgr.create_agent_branch("agent-1")

# 执行任务...

# 成功：提交并合并
git_mgr.commit_result("agent-1", report_path, state_path)
git_mgr.merge_agent_branch(agent_branch)

# 失败：回滚
rollback_mgr.handle_failure("agent-1", agent_branch)
```

## 完整示例

参见 `examples/` 目录：

- `demo_workflow.py` - 基础工作流示例
- `parallel_audit.py` - 并行审计示例
- `custom_agent.py` - 自定义 Agent 示例

## 调试技巧

### 1. 打印上下文

```python
def my_agent_runner(agent_name: str, context: ExecutionContext) -> dict:
    print(f"Agent: {agent_name}")
    print(f"Project: {context.project_id}")
    print(f"Completed: {context.completed_tasks}")
    print(f"Data: {context._data}")
    # ...
```

### 2. 使用简单 Agent 测试

```python
def debug_runner(agent_name: str, context: ExecutionContext) -> dict:
    print(f"[DEBUG] Running: {agent_name}")
    return {"status": "success", "debug": True}

engine = WorkflowEngine(definition, agent_runner=debug_runner)
```

### 3. 检查工作流定义

```python
definition = builder.build()
print(f"Groups: {len(definition.groups)}")
for group in definition.groups:
    print(f"  - {group.name}: {len(group.tasks)} tasks")
```

## 最佳实践

1. **合理分组**：相关任务放在同一组
2. **并发控制**：设置合理的 `max_concurrency`
3. **幂等设计**：Agent 执行应该幂等
4. **状态传递**：使用 `context.set()` / `context.get()`
5. **错误恢复**：选择合适的错误处理策略
6. **日志记录**：记录关键操作便于调试
