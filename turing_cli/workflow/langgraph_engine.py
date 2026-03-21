"""
基于 LangGraph 的工作流编排器

使用 LangGraph 替代自定义的 DAG 编排逻辑。
"""

from typing import Annotated, Any, Dict, List, TypedDict

from langgraph.graph import StateGraph, END

from turing_cli.config.logging_config import get_logger
from turing_cli.models.workflow import WorkflowConfig, TaskNode
from turing_cli.models.agent import AgentState

logger = get_logger(__name__)


def _merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """合并两个字典，供并行节点状态归约使用"""
    return {**a, **b}


class WorkflowState(TypedDict):
    """工作流状态"""
    task_results: Annotated[Dict[str, Any], _merge_dicts]
    completed_tasks: Annotated[List[str], lambda a, b: a + b]
    current_task: str
    error: str | None


class LangGraphWorkflowEngine:
    """基于 LangGraph 的工作流引擎"""

    def __init__(self, config: WorkflowConfig, agent_factory: callable):
        """初始化工作流引擎

        Args:
            config: 工作流配置
            agent_factory: Agent 工厂函数
        """
        self.config = config
        self.agent_factory = agent_factory
        self.graph = self._build_graph()

        logger.info(f"LangGraph 工作流引擎初始化: name={config.name}")

    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 图"""
        graph = StateGraph(WorkflowState)

        # 添加所有任务节点
        for task in self.config.tasks:
            if task.enabled:
                graph.add_node(task.id, self._create_task_node(task))

        # 添加边（依赖关系）
        for task in self.config.tasks:
            if not task.enabled:
                continue

            if not task.dependencies:
                # 无依赖的任务从 START 开始
                graph.set_entry_point(task.id)
            else:
                # 有依赖的任务从依赖任务连接
                for dep_id in task.dependencies:
                    graph.add_edge(dep_id, task.id)

        # 找到所有终端节点（没有被依赖的节点）
        dependent_tasks = set()
        for task in self.config.tasks:
            dependent_tasks.update(task.dependencies)

        terminal_tasks = [
            task.id for task in self.config.tasks
            if task.enabled and task.id not in dependent_tasks
        ]

        for task_id in terminal_tasks:
            graph.add_edge(task_id, END)

        return graph.compile()

    def _create_task_node(self, task: TaskNode):
        """创建任务节点函数

        Args:
            task: 任务配置

        Returns:
            任务执行函数
        """
        def task_node(state: WorkflowState) -> Dict[str, Any]:
            """执行单个任务"""
            logger.info(f"执行任务: {task.id}")

            try:
                agent = self.agent_factory(task.agent_type)
                input_data = {**task.input_data}
                context = {
                    "previous_outputs": state.get("task_results", {}),
                    "current_task": task.model_dump(),
                }

                output = agent.run(input_data, context)

                task_output = output.output_data if output.state == AgentState.COMPLETED else {"error": output.error_message}
                return {
                    "task_results": {task.id: task_output},
                    "completed_tasks": [task.id],
                }

            except Exception as e:
                error_msg = f"任务执行异常: {str(e)}"
                logger.error(error_msg, exc_info=True)

                return {
                    "task_results": {task.id: {"error": str(e)}},
                    "completed_tasks": [task.id],
                    "error": error_msg,
                }

        return task_node

    def run_single_agent(self, task_id: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """单独执行一个 Agent（不经过完整工作流）

        Args:
            task_id: 任务 ID
            context: 可选上下文

        Returns:
            包含 agent、output、error 的字典
        """
        task = next((t for t in self.config.tasks if t.id == task_id), None)
        if task is None:
            return {"agent": task_id, "output": None, "error": f"Task not found: {task_id}"}

        initial_state: WorkflowState = {
            "task_results": context or {},
            "completed_tasks": [],
            "current_task": task_id,
            "error": None,
        }

        node_fn = self._create_task_node(task)
        result = node_fn(initial_state)

        task_output = result.get("task_results", {}).get(task_id)
        return {"agent": task_id, "output": task_output, "error": result.get("error")}

    def run(self, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """运行工作流

        Args:
            context: 初始上下文

        Returns:
            所有任务的执行结果
        """
        initial_state = {
            "task_results": {},
            "completed_tasks": [],
            "current_task": "",
            "error": None,
        }

        logger.info(f"开始执行工作流: {self.config.name}")

        result = self.graph.invoke(initial_state)

        logger.info(f"工作流执行完成: {self.config.name}")

        return result.get("task_results", {})

