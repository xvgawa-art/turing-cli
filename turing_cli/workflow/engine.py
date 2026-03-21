"""
工作流执行引擎

接收 WorkflowDefinition，按顺序执行各执行组，处理错误。
"""

import time
from typing import Any, Callable, Dict, Optional

from turing_cli.config.logging_config import get_logger
from turing_cli.workflow.models import (
    ErrorHandler,
    ExecutionContext,
    WorkflowDefinition,
    WorkflowResult,
)

logger = get_logger(__name__)


class WorkflowEngine:
    """工作流执行引擎

    接收 WorkflowDefinition 并执行，支持 retry/skip 错误策略。

    用法::

        definition = workflow_builder.build()
        engine = WorkflowEngine(definition, agent_runner=my_runner)
        result = engine.run({"project_id": "proj-001"})
    """

    def __init__(
        self,
        definition: WorkflowDefinition,
        agent_runner: Optional[Callable] = None,
    ):
        self.definition = definition
        self._agent_runner = agent_runner or self._default_agent_runner

    def run(self, context_data: Optional[Dict[str, Any]] = None) -> WorkflowResult:
        """执行工作流

        Args:
            context_data: 初始上下文数据，必须包含 project_id

        Returns:
            WorkflowResult
        """
        data = context_data or {}
        context = ExecutionContext(
            project_id=data.get("project_id", ""),
            project_metadata=data.get("project_metadata", {}),
        )
        for key, value in data.items():
            if key not in ("project_id", "project_metadata"):
                context.set(key, value)

        start_time = time.time()
        logger.info(f"工作流 '{self.definition.name}' 开始执行")

        try:
            for group in self.definition.groups:
                group.execute(context, self._make_safe_runner(context))
        except Exception as e:
            error_msg = f"工作流执行失败: {e}"
            logger.error(error_msg, exc_info=True)
            execution_time = time.time() - start_time
            return WorkflowResult(
                success=False,
                task_results=context.task_results,
                error=error_msg,
                execution_time=execution_time,
            )

        execution_time = time.time() - start_time
        logger.info(f"工作流 '{self.definition.name}' 执行完成，耗时 {execution_time:.2f}s")

        return WorkflowResult(
            success=True,
            task_results=context.task_results,
            execution_time=execution_time,
        )

    def _make_safe_runner(self, context: ExecutionContext) -> Callable:
        """包装 agent_runner，添加错误处理逻辑"""
        error_handler = self.definition.error_handler

        def safe_runner(agent_name: str, ctx: ExecutionContext) -> Dict[str, Any]:
            if error_handler.strategy == ErrorHandler.STRATEGY_RETRY:
                return self._run_with_retry(agent_name, ctx, error_handler)
            try:
                return self._agent_runner(agent_name, ctx)
            except Exception as e:
                if error_handler.strategy == ErrorHandler.STRATEGY_SKIP:
                    logger.warning(f"Agent '{agent_name}' 失败，跳过: {e}")
                    return {"error": str(e), "skipped": True}
                raise

        return safe_runner

    def _run_with_retry(
        self,
        agent_name: str,
        context: ExecutionContext,
        error_handler: ErrorHandler,
    ) -> Dict[str, Any]:
        last_error = None
        for attempt in range(error_handler.max_retries + 1):
            try:
                return self._agent_runner(agent_name, context)
            except Exception as e:
                last_error = e
                if attempt < error_handler.max_retries:
                    wait = error_handler.backoff * (2 ** attempt)
                    logger.warning(f"Agent '{agent_name}' 第 {attempt + 1} 次重试（等待 {wait:.1f}s）: {e}")
                    time.sleep(wait)

        raise RuntimeError(f"Agent '{agent_name}' 重试 {error_handler.max_retries} 次后仍失败: {last_error}")

    @staticmethod
    def _default_agent_runner(agent_name: str, context: ExecutionContext) -> Dict[str, Any]:
        """默认 agent_runner，供测试时替换"""
        raise NotImplementedError(f"未提供 agent_runner，无法执行 Agent '{agent_name}'")
