"""
工作流执行模型

定义工作流执行过程中使用的数据结构。
"""

from typing import Any, Callable, Dict, List, Optional


class ExecutionContext:
    """工作流执行上下文

    保存工作流执行过程中的状态、中间结果和项目信息。
    """

    def __init__(
        self,
        project_id: str,
        project_metadata: Optional[Dict[str, Any]] = None,
    ):
        self.project_id = project_id
        self.project_metadata: Dict[str, Any] = project_metadata or {}
        self.task_results: Dict[str, Any] = {}
        self.completed_tasks: List[str] = []
        self.current_task: str = ""
        self.error: Optional[str] = None
        self._data: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """从上下文数据中获取值"""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """向上下文数据中设置值"""
        self._data[key] = value

    def get_agent_result(self, agent_name: str) -> Dict[str, Any]:
        """获取指定 Agent 的执行结果"""
        return self.task_results.get(agent_name, {})

    def record_task_result(self, agent_name: str, result: Dict[str, Any]) -> None:
        """记录 Agent 执行结果并更新完成列表"""
        self.task_results[agent_name] = result
        if agent_name not in self.completed_tasks:
            self.completed_tasks.append(agent_name)


class WorkflowResult:
    """工作流执行结果"""

    def __init__(
        self,
        success: bool,
        task_results: Dict[str, Any],
        error: Optional[str] = None,
        execution_time: float = 0.0,
    ):
        self.success = success
        self.task_results = task_results
        self.error = error
        self.execution_time = execution_time


class ErrorHandler:
    """错误处理配置"""

    STRATEGY_RETRY = "retry"
    STRATEGY_SKIP = "skip"
    STRATEGY_ABORT = "abort"

    def __init__(
        self,
        strategy: str = STRATEGY_ABORT,
        max_retries: int = 3,
        backoff: float = 1.0,
    ):
        self.strategy = strategy
        self.max_retries = max_retries
        self.backoff = backoff


class WorkflowDefinition:
    """工作流定义

    由 WorkflowBuilder.build() 生成，传递给 WorkflowEngine 执行。
    """

    def __init__(
        self,
        name: str,
        groups: List[Any],
        error_handler: Optional[ErrorHandler] = None,
    ):
        self.name = name
        self.groups = groups
        self.error_handler = error_handler or ErrorHandler()


class TaskNode:
    """任务节点

    代表工作流中一个具体的 Agent 执行任务。
    """

    def __init__(
        self,
        agent_name: str,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.agent_name = agent_name
        self.config: Dict[str, Any] = config or {}
