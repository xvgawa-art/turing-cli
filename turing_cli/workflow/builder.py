"""
工作流构建器

提供声明式 API 来构建工作流定义。
"""

from typing import Any, Optional

from turing_cli.workflow.groups import (
    ConditionalGroup,
    ExecutionGroup,
    LoopGroup,
    ParallelGroup,
    SequentialGroup,
)
from turing_cli.workflow.models import ErrorHandler, WorkflowDefinition


class WorkflowBuilder:
    """工作流构建器

    使用声明式 API 组装执行组，最终 build() 为 WorkflowDefinition。

    用法示例::

        workflow = WorkflowBuilder("full_audit")

        with workflow.sequential_group("system_analysis") as g:
            g.add_agent("business_architecture_agent")
            g.add_agent("version_diff_agent")

        with workflow.parallel_group("code_audit") as g:
            g.add_agent("sql_injection_agent")
            g.add_agent("command_injection_agent")

        workflow.on_error("retry", max_retries=3)
        engine = workflow.build()
    """

    def __init__(self, name: str):
        self.name = name
        self._groups: list[ExecutionGroup] = []
        self._error_handler: Optional[ErrorHandler] = None

    def sequential_group(self, name: str) -> SequentialGroup:
        """创建并注册串行执行组"""
        group = SequentialGroup(name)
        self._groups.append(group)
        return group

    def parallel_group(self, name: str) -> ParallelGroup:
        """创建并注册并行执行组"""
        group = ParallelGroup(name)
        self._groups.append(group)
        return group

    def conditional_group(self, name: str) -> ConditionalGroup:
        """创建并注册条件执行组"""
        group = ConditionalGroup(name)
        self._groups.append(group)
        return group

    def loop_group(self, name: str) -> LoopGroup:
        """创建并注册循环执行组"""
        group = LoopGroup(name)
        self._groups.append(group)
        return group

    def on_error(self, strategy: str, **kwargs: Any) -> "WorkflowBuilder":
        """配置全局错误处理策略

        Args:
            strategy: "retry", "skip", 或 "abort"
            max_retries: 最大重试次数（strategy="retry" 时有效）
            backoff: 重试退避系数
        """
        self._error_handler = ErrorHandler(
            strategy=strategy,
            max_retries=kwargs.get("max_retries", 3),
            backoff=kwargs.get("backoff", 1.0),
        )
        return self

    def build(self) -> "WorkflowDefinition":
        """构建 WorkflowDefinition，传递给 WorkflowEngine 执行"""
        return WorkflowDefinition(
            name=self.name,
            groups=list(self._groups),
            error_handler=self._error_handler,
        )
