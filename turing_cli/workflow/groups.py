"""
工作流执行组

定义不同执行模式的组：串行、并行、条件执行。
"""

import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from turing_cli.config.logging_config import get_logger
from turing_cli.workflow.models import ExecutionContext, TaskNode

logger = get_logger(__name__)


class ExecutionGroup(ABC):
    """执行组基类"""

    def __init__(self, name: str):
        self.name = name
        self.tasks: List[TaskNode] = []
        self.subgroups: List["ExecutionGroup"] = []

    def add_agent(self, agent_name: str, config: Optional[Dict[str, Any]] = None) -> "ExecutionGroup":
        """添加 Agent 任务到组"""
        self.tasks.append(TaskNode(agent_name=agent_name, config=config or {}))
        return self

    def add_group(self, group: "ExecutionGroup") -> "ExecutionGroup":
        """添加子组"""
        self.subgroups.append(group)
        return self

    @abstractmethod
    def execute(self, context: ExecutionContext, agent_runner: Callable) -> None:
        """执行组内所有任务

        Args:
            context: 执行上下文
            agent_runner: callable(agent_name, context) -> Dict
        """

    def __enter__(self) -> "ExecutionGroup":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class SequentialGroup(ExecutionGroup):
    """串行执行组 - 按顺序依次执行所有任务"""

    def execute(self, context: ExecutionContext, agent_runner: Callable) -> None:
        logger.info(f"串行组 '{self.name}' 开始执行，共 {len(self.tasks)} 个任务")

        for task in self.tasks:
            context.current_task = task.agent_name
            logger.info(f"执行任务: {task.agent_name}")
            result = agent_runner(task.agent_name, context)
            context.record_task_result(task.agent_name, result)

        for group in self.subgroups:
            group.execute(context, agent_runner)


class ParallelGroup(ExecutionGroup):
    """并行执行组 - 并发执行所有任务"""

    def __init__(self, name: str, max_concurrency: int = 5):
        super().__init__(name)
        self._max_concurrency = max_concurrency
        self._dynamic_agents_fn: Optional[Callable[[ExecutionContext], List[str]]] = None

    def max_concurrency(self, n: int) -> "ParallelGroup":
        """设置最大并发数"""
        self._max_concurrency = n
        return self

    def dynamic_agents(self, fn: Callable[[ExecutionContext], List[str]]) -> "ParallelGroup":
        """设置动态 Agent 列表函数，运行时根据上下文决定执行哪些 Agent"""
        self._dynamic_agents_fn = fn
        return self

    def execute(self, context: ExecutionContext, agent_runner: Callable) -> None:
        tasks = self._resolve_tasks(context)
        logger.info(f"并行组 '{self.name}' 开始执行，共 {len(tasks)} 个任务")

        with ThreadPoolExecutor(max_workers=self._max_concurrency) as executor:
            futures = {
                executor.submit(agent_runner, task.agent_name, context): task.agent_name
                for task in tasks
            }
            for future in as_completed(futures):
                agent_name = futures[future]
                try:
                    result = future.result()
                    context.record_task_result(agent_name, result)
                except Exception as e:
                    logger.error(f"并行任务 '{agent_name}' 失败: {e}")
                    context.record_task_result(agent_name, {"error": str(e)})

        for group in self.subgroups:
            group.execute(context, agent_runner)

    def _resolve_tasks(self, context: ExecutionContext) -> List[TaskNode]:
        if self._dynamic_agents_fn is not None:
            agent_names = self._dynamic_agents_fn(context)
            return [TaskNode(agent_name=name) for name in agent_names]
        return self.tasks


class ConditionalGroup(ExecutionGroup):
    """条件执行组 - 满足条件时才执行"""

    def __init__(self, name: str):
        super().__init__(name)
        self._condition: Optional[Callable[[ExecutionContext], bool]] = None
        self._else_group: Optional[ExecutionGroup] = None

    def condition(self, fn: Callable[[ExecutionContext], bool]) -> "ConditionalGroup":
        """设置执行条件函数"""
        self._condition = fn
        return self

    def else_group(self) -> SequentialGroup:
        """创建 else 分支组"""
        group = SequentialGroup(f"{self.name}_else")
        self._else_group = group
        return group

    def execute(self, context: ExecutionContext, agent_runner: Callable) -> None:
        condition_met = self._condition is None or self._condition(context)

        if condition_met:
            logger.info(f"条件组 '{self.name}' 条件满足，开始执行")
            for task in self.tasks:
                context.current_task = task.agent_name
                result = agent_runner(task.agent_name, context)
                context.record_task_result(task.agent_name, result)
            for group in self.subgroups:
                group.execute(context, agent_runner)
        else:
            logger.info(f"条件组 '{self.name}' 条件不满足，跳过")
            if self._else_group is not None:
                self._else_group.execute(context, agent_runner)


class LoopGroup(ExecutionGroup):
    """循环执行组 - 循环执行直到条件不满足或达到最大迭代次数"""

    def __init__(self, name: str, max_iterations: int = 10):
        super().__init__(name)
        self._condition: Optional[Callable[[ExecutionContext], bool]] = None
        self._max_iterations = max_iterations

    def condition(self, fn: Callable[[ExecutionContext], bool]) -> "LoopGroup":
        """设置循环继续条件"""
        self._condition = fn
        return self

    def max_iterations(self, n: int) -> "LoopGroup":
        """设置最大迭代次数"""
        self._max_iterations = n
        return self

    def execute(self, context: ExecutionContext, agent_runner: Callable) -> None:
        iteration = 0

        while iteration < self._max_iterations:
            should_continue = self._condition is None or self._condition(context)
            if not should_continue:
                break

            logger.info(f"循环组 '{self.name}' 第 {iteration + 1} 次迭代")
            for task in self.tasks:
                context.current_task = task.agent_name
                result = agent_runner(task.agent_name, context)
                context.record_task_result(task.agent_name, result)

            iteration += 1

        if iteration >= self._max_iterations:
            logger.warning(f"循环组 '{self.name}' 达到最大迭代次数 {self._max_iterations}")
