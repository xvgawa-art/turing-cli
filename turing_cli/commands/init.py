"""Init command - Create workflow scaffolding."""

from pathlib import Path

import click


WORKFLOW_TEMPLATE = '''#!/usr/bin/env python3
"""
{workflow_name} - {description}

使用方法:
    python {workflow_file}.py
"""

import sys
from pathlib import Path

# 添加项目路径（如果需要）
# project_root = Path(__file__).parent.parent
# sys.path.insert(0, str(project_root))

from turing_cli.workflow.builder import WorkflowBuilder
from turing_cli.workflow.engine import WorkflowEngine
from turing_cli.workflow.models import ExecutionContext


# ============================================================
# 1. 定义 Agent Runner（Agent 执行器）
# ============================================================

def my_agent_runner(agent_name: str, context: ExecutionContext) -> dict:
    """
    Agent 执行器 - 实际执行 Agent 任务的地方

    Args:
        agent_name: Agent 名称
        context: 执行上下文，包含项目信息和之前的执行结果

    Returns:
        dict: Agent 执行结果
    """
    print(f"  [执行] Agent: {{agent_name}}")

    # TODO: 在这里实现你的 Agent 逻辑
    # 例如：调用 LLM、执行代码扫描、生成报告等

    # 获取共享上下文
    project_id = context.project_id
    custom_data = context.get("custom_data")

    # 获取其他 Agent 的结果
    # prev_result = context.get_agent_result("previous_agent_name")

    # 返回执行结果
    return {{
        "status": "success",
        "agent_name": agent_name,
        "result": "TODO: 实现你的逻辑",
    }}


# ============================================================
# 2. 定义 Workflow
# ============================================================

def create_workflow():
    """创建工作流定义"""
    builder = WorkflowBuilder("{workflow_id}")

    # TODO: 根据你的需求添加执行组

    # 示例 1: 串行执行组
    # with builder.sequential_group("phase1") as group:
    #     group.add_agent("agent_a")
    #     group.add_agent("agent_b")

    # 示例 2: 并行执行组
    # with builder.parallel_group("phase2") as group:
    #     group.add_agent("agent_x")
    #     group.add_agent("agent_y")
    #     group.add_agent("agent_z")
    #     group.max_concurrency(3)

    # 示例 3: 动态 Agent 列表
    # with builder.parallel_group("dynamic_phase") as group:
    #     group.dynamic_agents(lambda ctx: ctx.get("task_list", []))
    #     group.max_concurrency(5)

    # 错误处理策略: "retry", "skip", "abort"
    builder.on_error("retry", max_retries=3)

    return builder.build()


# ============================================================
# 3. 主函数
# ============================================================

def main():
    """主函数"""
    print("=" * 60)
    print("{workflow_name}")
    print("=" * 60)

    # 创建工作流
    definition = create_workflow()
    print(f"\\n创建工作流: {{definition.name}}")

    # 创建引擎
    engine = WorkflowEngine(definition, agent_runner=my_agent_runner)

    # 执行工作流
    print("\\n开始执行工作流...")
    result = engine.run({{
        "project_id": "{workflow_id}-001",
        "custom_data": {{}},
    }})

    # 输出结果
    print("\\n" + "=" * 60)
    print("执行结果:")
    print(f"  成功: {{result.success}}")
    print(f"  耗时: {{result.execution_time:.2f}}s")

    if result.task_results:
        print("  任务结果:")
        for agent_name, task_result in result.task_results.items():
            status = task_result.get("status", "unknown")
            print(f"    - {{agent_name}}: {{status}}")

    if result.error:
        print(f"  错误: {{result.error}}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
'''

AGENT_TEMPLATE = '''"""Custom Agent implementation."""

from pathlib import Path
from typing import Any, Dict

from turing_cli.agents.runner import BaseAgentRunner, AgentContext


class {agent_class_name}(BaseAgentRunner):
    """自定义 Agent

    实现特定的任务逻辑。
    """

    def __init__(
        self,
        deliverables_path: Path,
        code_path: Path,
        **kwargs,
    ):
        super().__init__(deliverables_path, code_path)
        # TODO: 初始化你的 Agent
        self.custom_config = kwargs.get("custom_config", {{}})

    def _execute(self, context: AgentContext) -> Dict[str, Any]:
        """执行 Agent 任务

        Args:
            context: Agent 执行上下文

        Returns:
            执行结果字典
        """
        agent_id = context.agent_id
        task_data = context.task_data

        # TODO: 实现你的 Agent 逻辑

        return {{
            "status": "completed",
            "agent_id": agent_id,
            "result": "TODO: 实现你的逻辑",
        }}
'''

CONFIG_TEMPLATE = '''# {workflow_name} Configuration

# Agent 类型定义
agent_types:
  # 示例 Agent 类型
  example_agent:
    description: "示例 Agent"
    prompt_template: "example_agent.md"

# 错误处理配置
error_handling:
  max_retries: 3
  backoff: 1.0
  strategy: "retry"  # retry, skip, abort

# 并发配置
concurrency:
  max_workers: 5
  timeout: 300
'''

README_TEMPLATE = '''# {workflow_name}

{description}

## 使用方法

```bash
# 进入项目目录
cd {workflow_dir}

# 运行工作流
python {workflow_file}.py
```

## 工作流结构

```
{workflow_name}/
├── {workflow_file}.py    # 主工作流文件
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
        return {{"status": "completed"}}
```

## 配置

编辑 `config/config.yaml` 来配置 Agent 和工作流参数。
'''


def create_scaffold(
    project_name: str,
    description: str = "A custom workflow",
    output: str = ".",
    with_agent: bool = False,
) -> int:
    """创建工作流脚手架（核心函数）

    Args:
        project_name: 项目名称
        description: 项目描述
        output: 输出目录
        with_agent: 是否创建自定义 Agent 模板

    Returns:
        0 成功，1 失败
    """
    output_path = Path(output)
    workflow_dir = output_path / project_name
    workflow_file = f"{project_name}_workflow"
    workflow_id = project_name.lower().replace("-", "_").replace(" ", "_")
    workflow_class = "".join(word.capitalize() for word in workflow_id.split("_"))

    # 检查目录是否存在
    if workflow_dir.exists():
        print(f"错误: 目录 {workflow_dir} 已存在")
        return 1

    # 创建目录结构
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "agents").mkdir(exist_ok=True)
    (workflow_dir / "config").mkdir(exist_ok=True)

    # 生成工作流文件
    workflow_content = WORKFLOW_TEMPLATE.format(
        workflow_name=project_name,
        workflow_id=workflow_id,
        workflow_file=workflow_file,
        description=description,
    )

    workflow_path = workflow_dir / f"{workflow_file}.py"
    workflow_path.write_text(workflow_content)
    workflow_path.chmod(0o755)

    # 生成配置文件
    config_content = CONFIG_TEMPLATE.format(
        workflow_name=project_name,
    )
    (workflow_dir / "config" / "config.yaml").write_text(config_content)

    # 生成 README
    readme_content = README_TEMPLATE.format(
        workflow_name=project_name,
        description=description,
        workflow_dir=project_name,
        workflow_file=workflow_file,
    )
    (workflow_dir / "README.md").write_text(readme_content)

    # 可选：生成自定义 Agent
    if with_agent:
        agent_class_name = f"{workflow_class}Agent"
        agent_content = AGENT_TEMPLATE.format(
            agent_class_name=agent_class_name,
        )
        (workflow_dir / "agents" / "custom_agent.py").write_text(agent_content)

    # 输出结果
    print(f"\n✓ 创建工作流脚手架: {workflow_dir}")
    print("\n目录结构:")
    print(f"  {project_name}/")
    print(f"  ├── {workflow_file}.py    # 主工作流文件")
    if with_agent:
        print("  ├── agents/")
        print("  │   └── custom_agent.py   # 自定义 Agent")
    print("  ├── config/")
    print("  │   └── config.yaml       # 配置文件")
    print("  └── README.md")

    print("\n开始使用:")
    print(f"  cd {project_name}")
    print(f"  python {workflow_file}.py")

    return 0


# Click 命令包装
@click.command("init")
@click.argument("project_name", default="my_workflow")
@click.option("--description", "-d", default="A custom workflow", help="工作流描述")
@click.option("--output", "-o", default=".", help="输出目录")
@click.option("--with-agent", "-a", is_flag=True, help="同时创建自定义 Agent 模板")
def init_cmd(project_name: str, description: str, output: str, with_agent: bool):
    """创建工作流脚手架

    快速生成一个新的工作流项目结构，包含必要的文件和示例代码。

    示例:
        turing init my_audit
        turing init my_audit -d "我的审计工作流" -o ./workflows
        turing init my_audit --with-agent
    """
    return create_scaffold(project_name, description, output, with_agent)


# 为了兼容 argparse 的 main.py 调用
init = create_scaffold
