#!/usr/bin/env python3
"""
my_audit - 我的审计工作流

使用方法:
    python my_audit_workflow.py
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
    print(f"  [执行] Agent: {agent_name}")

    # TODO: 在这里实现你的 Agent 逻辑
    # 例如：调用 LLM、执行代码扫描、生成报告等

    # 获取共享上下文
    project_id = context.project_id
    custom_data = context.get("custom_data")

    # 获取其他 Agent 的结果
    # prev_result = context.get_agent_result("previous_agent_name")

    # 返回执行结果
    return {
        "status": "success",
        "agent_name": agent_name,
        "result": "TODO: 实现你的逻辑",
    }


# ============================================================
# 2. 定义 Workflow
# ============================================================

def create_workflow():
    """创建工作流定义"""
    builder = WorkflowBuilder("my_audit")

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
    print("my_audit")
    print("=" * 60)

    # 创建工作流
    definition = create_workflow()
    print(f"\n创建工作流: {definition.name}")

    # 创建引擎
    engine = WorkflowEngine(definition, agent_runner=my_agent_runner)

    # 执行工作流
    print("\n开始执行工作流...")
    result = engine.run({
        "project_id": "my_audit-001",
        "custom_data": {},
    })

    # 输出结果
    print("\n" + "=" * 60)
    print("执行结果:")
    print(f"  成功: {result.success}")
    print(f"  耗时: {result.execution_time:.2f}s")

    if result.task_results:
        print("  任务结果:")
        for agent_name, task_result in result.task_results.items():
            status = task_result.get("status", "unknown")
            print(f"    - {agent_name}: {status}")

    if result.error:
        print(f"  错误: {result.error}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
