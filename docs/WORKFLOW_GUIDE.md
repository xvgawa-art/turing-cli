# Workflow 使用指南

本指南介绍如何使用 turing-cli 的工作流系统来调度 Agent 完成任务。

## 核心概念

### 1. WorkflowBuilder（工作流构建器）

使用声明式 API 构建工作流定义：

```python
from turing_cli.workflow.builder import WorkflowBuilder

builder = WorkflowBuilder("my_workflow")
```

### 2. ExecutionGroup（执行组）

四种执行组类型：

| 类型 | 说明 | 使用场景 |
|------|------|----------|
| `SequentialGroup` | 串行执行 | 有依赖关系的任务，需要按顺序执行 |
| `ParallelGroup` | 并行执行 | 独立任务，可同时执行提高效率 |
| `ConditionalGroup` | 条件执行 | 根据上下文决定是否执行 |
| `LoopGroup` | 循环执行 | 重复执行直到条件不满足 |

### 3. WorkflowEngine（工作流引擎）

执行工作流定义，管理上下文和错误处理：

```python
from turing_cli.workflow.engine import WorkflowEngine

engine = WorkflowEngine(definition, agent_runner=my_runner)
result = engine.run({"project_id": "proj-001"})
```

## 快速开始

### 步骤 1: 定义 Agent Runner

Agent Runner 是实际执行任务的地方：

```python
from turing_cli.workflow.models import ExecutionContext

def my_agent_runner(agent_name: str, context: ExecutionContext) -> dict:
    """执行 Agent 任务"""

    if agent_name == "scanner":
        # 执行扫描逻辑
        return {"status": "success", "findings": [...]}

    elif agent_name == "analyzer":
        # 获取之前的结果
        scan_result = context.get_agent_result("scanner")
        # 执行分析逻辑
        return {"status": "success", "analysis": "..."}

    return {"status": "unknown_agent"}
```

### 步骤 2: 构建工作流

```python
builder = WorkflowBuilder("security_audit")

# 串行阶段
with builder.sequential_group("preparation") as group:
    group.add_agent("initializer")
    group.add_agent("collector")

# 并行阶段
with builder.parallel_group("scanning") as group:
    group.add_agent("sql_scanner")
    group.add_agent("xss_scanner")
    group.add_agent("auth_scanner")
    group.max_concurrency(3)

# 报告阶段
with builder.sequential_group("reporting") as group:
    group.add_agent("aggregator")
    group.add_agent("reporter")

# 错误处理
builder.on_error("retry", max_retries=3)
```

### 步骤 3: 执行工作流

```python
definition = builder.build()
engine = WorkflowEngine(definition, agent_runner=my_agent_runner)

result = engine.run({
    "project_id": "my-project",
    "project_metadata": {"language": "Python"}
})

print(f"成功: {result.success}")
print(f"结果: {result.task_results}")
```

## 执行组详解

### SequentialGroup（串行执行）

```python
with builder.sequential_group("phase1") as group:
    group.add_agent("agent_a")  # 先执行
    group.add_agent("agent_b")  # agent_a 完成后执行
    group.add_agent("agent_c")  # agent_b 完成后执行
```

### ParallelGroup（并行执行）

```python
with builder.parallel_group("phase2") as group:
    group.add_agent("agent_x")  # 同时执行
    group.add_agent("agent_y")  # 同时执行
    group.add_agent("agent_z")  # 同时执行
    group.max_concurrency(5)    # 最大并发数
```

**动态 Agent 列表**：

```python
with builder.parallel_group("dynamic_scan") as group:
    # 运行时根据上下文决定执行哪些 Agent
    group.dynamic_agents(lambda ctx: ctx.get("vulnerability_types", []))
    group.max_concurrency(10)
```

### ConditionalGroup（条件执行）

```python
with builder.conditional_group("high_risk") as group:
    # 只有条件满足时才执行
    group.condition(lambda ctx: ctx.get("risk_level") == "high")
    group.add_agent("deep_analyzer")
    group.add_agent("exploit_checker")
```

### LoopGroup（循环执行）

```python
with builder.loop_group("iteration") as group:
    # 循环直到条件不满足或达到最大次数
    group.condition(lambda ctx: ctx.get("needs_more_work", True))
    group.max_iterations(5)
    group.add_agent("refiner")
```

## 上下文管理

`ExecutionContext` 提供工作流执行过程中的状态管理：

```python
def my_agent_runner(agent_name: str, context: ExecutionContext) -> dict:
    # 获取项目 ID
    project_id = context.project_id

    # 获取项目元数据
    metadata = context.project_metadata

    # 获取/设置自定义数据
    context.set("custom_key", "value")
    value = context.get("custom_key", default=None)

    # 获取其他 Agent 的结果
    prev_result = context.get_agent_result("previous_agent")

    # 获取已完成的任务列表
    completed = context.completed_tasks
```

## 错误处理

三种错误处理策略：

| 策略 | 说明 |
|------|------|
| `"retry"` | 失败时重试，支持指数退避 |
| `"skip"` | 跳过失败的任务，继续执行 |
| `"abort"` | 失败时立即停止整个工作流 |

```python
# 重试策略
builder.on_error("retry", max_retries=3, backoff=1.0)

# 跳过策略
builder.on_error("skip")

# 中止策略（默认）
builder.on_error("abort")
```

## 完整示例

参见 `examples/demo_workflow.py`，包含：
- 简单串行工作流
- 并行工作流
- 条件执行工作流
- 动态 Agent 工作流

运行示例：

```bash
cd ~/turing-cli
source venv/bin/activate
python examples/demo_workflow.py
```

## 最佳实践

1. **合理分组**：将相关任务放在同一组，便于管理和调试
2. **并发控制**：设置合理的 `max_concurrency`，避免资源耗尽
3. **错误处理**：根据任务重要性选择合适的错误策略
4. **上下文传递**：使用 `context.set()` / `context.get()` 传递中间结果
5. **幂等设计**：Agent 执行应尽量幂等，便于重试
