"""Agent 运行器和基类。

提供 Agent 执行的核心框架：
- AgentRunner: 管理连接池和 Agent 执行循环
- BaseAgent: Agent 基类，实现模板方法模式
- MCP 服务注入：为 Agent 提供工程化 MCP 工具能力
"""

import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from turing_cli.agents.context import AgentContext
from turing_cli.config.loader import ConfigLoader
from turing_cli.config.logging_config import get_logger
from turing_cli.core.opencode.client import OpenCodeClient
from turing_cli.core.opencode.session_manager import SessionManager
from turing_cli.git_ops.manager import GitManager
from turing_cli.git_ops.rollback import RollbackManager
from turing_cli.mcp.services.audit_service import AuditMCPService
from turing_cli.models.deliverable import AgentResult, Deliverable
from turing_cli.models.validation import ValidationResult, validate_deliverable

logger = get_logger(__name__)


# ============================================================
# Agent 基类
# ============================================================


class BaseAgent(ABC):
    """Agent 基类

    所有 Agent 必须继承此类并实现 execute 方法。
    框架会自动调用 prepare_context → execute → validate 循环。

    Example:
        class SQLInjectionAgent(BaseAgent):
            agent_type = "sql_injection"

            def execute(self, context: AgentContext) -> Deliverable:
                client = context.get_opencode_client()
                vuln = context.get_vulnerability()

                # 调用 OpenCode 分析
                response = client.chat(...)

                return Deliverable(
                    agent_id=context.agent_id,
                    agent_type=self.agent_type,
                    phase=context.phase,
                    content={"confidence": "confirmed", ...},
                )

            def validate(self, deliverable: Deliverable) -> ValidationResult:
                # 自定义验证逻辑
                ...
    """

    # 子类必须设置的类属性
    agent_type: str = "base"
    description: str = "Base Agent"

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def prepare_context(self, context: AgentContext) -> None:
        """准备上下文（可选重写）

        在执行前调用，可用于：
        - 处理重试反馈
        - 获取上一阶段结果
        - 准备 prompt 模板

        Args:
            context: Agent 执行上下文
        """
        feedback = context.get_feedback()
        if feedback:
            logger.info(
                f"Agent {context.agent_id} 重试 #{context.get_retry_count()}: {feedback}"
            )

    @abstractmethod
    def execute(self, context: AgentContext) -> Deliverable:
        pass

    def validate(self, deliverable: Deliverable) -> ValidationResult:
        return validate_deliverable(deliverable)

    def build_prompt(self, context: AgentContext) -> str:
        return ""

    def on_success(self, context: AgentContext, deliverable: Deliverable) -> None:
        pass

    def on_failure(self, context: AgentContext, error: str) -> None:
        pass


# ============================================================
# Agent Runner
# ============================================================


class AgentRunner:
    """Agent 运行器

    职责：
    1. 管理 OpenCode 连接池
    2. 管理 Agent 注册表
    3. 执行 Agent 循环（prepare → execute → validate → retry）
    4. 管理 Git 分支和回滚

    Example:
        runner = AgentRunner(
            opencode_url="http://localhost:4097",
            max_retries=3,
        )
        runner.initialize()

        # 注册 Agent
        runner.register_agent("vuln-0", SQLInjectionAgent())
        runner.register_agent("vuln-1", XSSAgent())

        # 执行
        result = runner.run("vuln-0", context)
    """

    def __init__(
        self,
        opencode_url: str = "http://localhost:4097",
        max_retries: int = 3,
        config_dir: Optional[Path] = None,
        deliverables_dir: Optional[Path] = None,
        mcp_service: Optional[AuditMCPService] = None,
    ):
        self.opencode_url = opencode_url
        self.max_retries = max_retries
        self.config_dir = config_dir
        self.deliverables_dir = deliverables_dir or Path("./deliverables")

        # 连接池
        self._client: Optional[OpenCodeClient] = None
        self._session_mgr: Optional[SessionManager] = None
        self._mcp_service: Optional[AuditMCPService] = mcp_service

        # Agent 注册表
        self._agents: Dict[str, BaseAgent] = {}

        # Git 管理
        self._git_mgr: Optional[GitManager] = None
        self._rollback_mgr: Optional[RollbackManager] = None

        # 配置加载器
        self._config_loader: Optional[ConfigLoader] = None
        if config_dir:
            self._config_loader = ConfigLoader(config_dir)

    def initialize(self) -> bool:
        """初始化连接池

        Returns:
            bool: 是否成功初始化 OpenCode 连接
        """
        try:
            self._client = OpenCodeClient(self.opencode_url)
            self._session_mgr = SessionManager(self._client)
            logger.info(f"AgentRunner 初始化完成，OpenCode URL: {self.opencode_url}")
            return True
        except ImportError as e:
            logger.warning(f"OpenCode 不可用: {e}")
            self._client = None
            self._session_mgr = None
            return False
        except Exception as e:
            logger.error(f"OpenCode 初始化失败: {e}")
            self._client = None
            self._session_mgr = None
            return False

    def get_client(self) -> Optional[OpenCodeClient]:
        """获取 OpenCode 客户端

        Returns:
            OpenCodeClient 实例，如果不可用则返回 None
        """
        if self._client is None:
            self.initialize()
        return self._client

    def get_mcp_service(self) -> Optional[AuditMCPService]:
        return self._mcp_service

    def set_mcp_service(self, mcp_service: Optional[AuditMCPService]) -> None:
        self._mcp_service = mcp_service

    def is_opencode_available(self) -> bool:
        """检查 OpenCode 是否可用"""
        return self._client is not None or self.initialize()

    def create_session(self, agent_id: str) -> str:
        """为 Agent 创建 Session"""
        if self._session_mgr is None:
            self.initialize()
        return self._session_mgr.create_agent_session(agent_id)

    def get_session(self, agent_id: str) -> Optional[str]:
        """获取 Agent 的 Session"""
        if self._session_mgr:
            return self._session_mgr.get_session(agent_id)
        return None

    # ============================================================
    # Agent 注册
    # ============================================================

    def register_agent(self, agent_id: str, agent: BaseAgent) -> None:
        """注册 Agent

        Args:
            agent_id: Agent 唯一标识符
            agent: Agent 实例
        """
        self._agents[agent_id] = agent
        logger.debug(f"注册 Agent: {agent_id} -> {agent.name}")

    def register_agents(self, agents: Dict[str, BaseAgent]) -> None:
        """批量注册 Agent

        Args:
            agents: {agent_id: agent_instance} 字典
        """
        for agent_id, agent in agents.items():
            self.register_agent(agent_id, agent)

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """获取已注册的 Agent"""
        return self._agents.get(agent_id)

    def has_agent(self, agent_id: str) -> bool:
        """检查 Agent 是否已注册"""
        return agent_id in self._agents

    # ============================================================
    # Git 管理
    # ============================================================

    def init_git(self, repo_path: Path) -> None:
        """初始化 Git 管理

        Args:
            repo_path: Git 仓库路径
        """
        self._git_mgr = GitManager(repo_path)
        self._rollback_mgr = RollbackManager(self._git_mgr, self.deliverables_dir)
        logger.info(f"Git 管理初始化完成: {repo_path}")

    # ============================================================
    # 执行循环
    # ============================================================

    def run(
        self,
        agent_id: str,
        context: AgentContext,
    ) -> AgentResult:
        """执行 Agent（模板方法）

        执行流程：
        1. 获取 Agent 实例
        2. 注入连接到 Context
        3. 循环执行：prepare → execute → validate
        4. 失败时设置 feedback 并重试

        Args:
            agent_id: Agent 唯一标识符
            context: Agent 执行上下文

        Returns:
            AgentResult 执行结果
        """
        # 1. 获取 Agent
        agent = self._agents.get(agent_id)
        if agent is None:
            return AgentResult(
                success=False,
                agent_id=agent_id,
                error=f"Unknown agent: {agent_id}",
            )

        # 2. 注入连接到 Context
        context._shared["__opencode_client__"] = self.get_client()
        context._shared["__mcp_service__"] = self.get_mcp_service()
        if self._session_mgr:
            context._shared["__sessions__"] = self._session_mgr._sessions

        # 3. 创建 Git 分支
        branch_name = None
        if self._git_mgr:
            try:
                branch_name = self._git_mgr.create_agent_branch(agent_id)
            except Exception as e:
                logger.warning(f"创建分支失败: {e}")

        # 4. 执行循环
        start_time = time.time()
        deliverable = None

        for attempt in range(self.max_retries + 1):
            try:
                # 4.1 准备上下文
                agent.prepare_context(context)

                # 4.2 执行
                deliverable = agent.execute(context)
                deliverable.retry_count = attempt
                deliverable.execution_time = time.time() - start_time

                # 4.3 验证
                validation = agent.validate(deliverable)

                if validation.is_valid:
                    # 验证通过
                    deliverable.mark_completed()
                    deliverable.mark_validated()

                    # 保存交付件
                    self._save_deliverable(deliverable)

                    # 设置结果到 Context
                    context.set_result(deliverable.to_dict())

                    # 提交 Git
                    if self._git_mgr and branch_name:
                        self._commit_and_merge(agent_id, branch_name)

                    # 成功回调
                    agent.on_success(context, deliverable)

                    return AgentResult(
                        success=True,
                        agent_id=agent_id,
                        deliverable=deliverable,
                        attempts=attempt + 1,
                    )

                deliverable.mark_retrying(validation.feedback or "")
                context.set_feedback(validation.feedback or "验证失败")
                logger.warning(
                    f"Agent {agent_id} 验证失败 (尝试 {attempt + 1}): {validation.feedback}"
                )

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Agent {agent_id} 执行失败 (尝试 {attempt + 1}): {error_msg}")
                context.set_feedback(error_msg)

                # 失败回调
                agent.on_failure(context, error_msg)

                # 回滚 Git
                if self._rollback_mgr and branch_name:
                    self._rollback_mgr.handle_failure(
                        agent_id=agent_id,
                        branch_name=branch_name,
                        clean_deliverables=True,
                    )
                    # 为下次重试创建新分支
                    if attempt < self.max_retries:
                        try:
                            branch_name = self._git_mgr.create_agent_branch(
                                f"{agent_id}-retry-{attempt + 1}"
                            )
                        except Exception:
                            branch_name = None

                # 最后一次尝试失败
                if attempt >= self.max_retries:
                    if deliverable:
                        deliverable.mark_failed(error_msg)
                    return AgentResult(
                        success=False,
                        agent_id=agent_id,
                        deliverable=deliverable,
                        error=error_msg,
                        attempts=attempt + 1,
                    )

        return AgentResult(
            success=False,
            agent_id=agent_id,
            error="Max retries exceeded",
            attempts=self.max_retries + 1,
        )

    def run_batch(
        self,
        tasks: List[Tuple[str, AgentContext]],
        max_workers: Optional[int] = None,
        show_progress: bool = True,
    ) -> List[AgentResult]:
        """并发执行多个 Agent

        每个任务使用独立的线程执行，共享连接池。

        Args:
            tasks: [(agent_id, context), ...] 任务列表
            max_workers: 最大并发数，默认为任务数
            show_progress: 是否显示进度

        Returns:
            List[AgentResult] 执行结果列表（顺序与 tasks 相同）
        """
        if max_workers is None:
            max_workers = len(tasks)

        results_map: Dict[int, AgentResult] = {}
        results_lock = threading.Lock()

        def _execute_task(idx: int, agent_id: str, context: AgentContext) -> Tuple[int, AgentResult]:
            """执行单个任务"""
            if show_progress:
                logger.info(f"开始执行 [{idx + 1}/{len(tasks)}] {agent_id}...")

            result = self.run(agent_id, context)

            if show_progress:
                status = "✓" if result.success else "✗"
                exec_time = result.deliverable.execution_time if result.deliverable else 0.0
                logger.info(
                    f"[{idx + 1}/{len(tasks)}] {agent_id} {status} "
                    f"(尝试: {result.attempts}, 耗时: {exec_time:.2f}s)"
                )

            return (idx, result)

        # 使用线程池并发执行
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_execute_task, idx, agent_id, ctx): (idx, agent_id)
                for idx, (agent_id, ctx) in enumerate(tasks)
            }

            for future in as_completed(futures):
                idx, agent_id = futures[future]
                try:
                    idx_result, result = future.result()
                    with results_lock:
                        results_map[idx_result] = result
                except Exception as e:
                    logger.error(f"Agent {agent_id} 执行异常: {e}")
                    with results_lock:
                        results_map[idx] = AgentResult(
                            success=False,
                            agent_id=agent_id,
                            error=str(e),
                            attempts=0,
                        )

        return [
            results_map.get(
                i,
                AgentResult(success=False, agent_id=tasks[i][0], error="未执行"),
            )
            for i in range(len(tasks))
        ]

    def _save_deliverable(self, deliverable: Deliverable) -> Path:
        """保存交付件

        Args:
            deliverable: 交付件

        Returns:
            保存的文件路径
        """
        phase_dir = self.deliverables_dir / deliverable.phase
        phase_dir.mkdir(parents=True, exist_ok=True)
        return deliverable.save(phase_dir)

    def _commit_and_merge(self, agent_id: str, branch_name: str) -> None:
        """提交并合并 Git 分支"""
        if not self._git_mgr:
            return

        try:
            # 添加更改
            self._git_mgr.repo.git.add("-A")

            # 提交
            if self._git_mgr.repo.is_dirty():
                self._git_mgr.commit_changes(f"agent-{agent_id}: completed")

            # 合并
            self._git_mgr.merge_agent_branch(branch_name)
        except Exception as e:
            logger.warning(f"Git 提交/合并失败: {e}")


# ============================================================
# 具体实现（兼容旧代码）
# ============================================================


class VulnAgentRunner:
    """漏洞分析 Agent Runner（兼容旧接口）

    这是一个兼容层，内部使用新的 AgentRunner。
    推荐直接使用 AgentRunner + BaseAgent。
    """

    def __init__(
        self,
        config_dir: Path,
        deliverables_path: Path,
        code_path: Path,
        opencode_url: str = "http://localhost:4097",
        mcp_service: Optional[AuditMCPService] = None,
    ):
        self.config_dir = config_dir
        self.deliverables_path = deliverables_path
        self.code_path = code_path
        self.opencode_url = opencode_url

        self._runner = AgentRunner(
            opencode_url=opencode_url,
            config_dir=config_dir,
            deliverables_dir=deliverables_path,
            mcp_service=mcp_service,
        )

    def init_git(self, repo_path: Optional[Path] = None) -> None:
        self._runner.init_git(repo_path or self.deliverables_path)

    def run(self, agent_id: str, context: Dict[str, object]) -> Dict[str, object]:
        task_data = context.get("task_data", context)
        shared_context = context.get("shared_context", {})

        agent_context = AgentContext(
            agent_id=agent_id,
            agent_type=context.get("agent_type", "unknown"),
            phase=context.get("phase", "code_audit"),
            shared_context=shared_context,
            task_data=task_data,
        )

        result = self._runner.run(agent_id, agent_context)
        return result.to_dict()


# ============================================================
# 工厂函数
# ============================================================


def create_agent_runner(
    agent_type: str,
    deliverables_path: Path,
    code_path: Path,
    **kwargs,
) -> AgentRunner:
    """工厂函数：创建 Agent Runner

    Args:
        agent_type: Agent 类型
        deliverables_path: 交付件目录
        code_path: 代码路径
        **kwargs: 其他参数

    Returns:
        AgentRunner 实例
    """
    runner = AgentRunner(
        opencode_url=kwargs.get("opencode_url", "http://localhost:4097"),
        max_retries=kwargs.get("max_retries", 3),
        config_dir=kwargs.get("config_dir"),
        deliverables_dir=deliverables_path,
        mcp_service=kwargs.get("mcp_service"),
    )
    return runner
