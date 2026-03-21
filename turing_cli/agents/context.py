"""Agent 执行上下文。

提供 Agent 执行过程中的上下文信息，包括：
- 项目信息和配置
- 跨阶段数据传递
- 任务特定数据
- 重试反馈机制
- OpenCode 连接获取
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from turing_cli.core.opencode.client import OpenCodeClient


class TaskData(BaseModel):
    """任务数据"""

    vulnerability: Optional[Dict[str, Any]] = None
    scan_result: Optional[Dict[str, Any]] = None
    target_file: Optional[str] = None
    target_function: Optional[str] = None
    custom_data: Dict[str, Any] = {}

    model_config = {"extra": "allow"}


class AgentContext:
    """Agent 执行上下文

    每个 Agent 执行时都会收到一个 AgentContext 实例，提供：
    1. 项目级信息（code_path, deliverables_dir 等）
    2. 跨阶段数据获取（get_phase_result）
    3. OpenCode 连接获取（get_opencode_client）
    4. 任务数据（get_vulnerability, get_task_data）
    5. 重试反馈（set_feedback, get_feedback）

    Example:
        def execute(self, context: AgentContext) -> Deliverable:
            # 获取项目信息
            code_path = context.get_code_path()

            # 获取 OpenCode 连接
            client = context.get_opencode_client()

            # 获取上一阶段结果
            threat_result = context.get_phase_result("threat_analysis")

            # 获取当前任务数据
            vuln = context.get_vulnerability()

            # 处理重试反馈
            if context.get_feedback():
                # 根据反馈调整策略
                ...
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        phase: str,
        shared_context: Dict[str, Any],
        task_data: Optional[TaskData] = None,
    ):
        """初始化 Agent 上下文

        Args:
            agent_id: Agent 唯一标识符
            agent_type: Agent 类型
            phase: 当前阶段
            shared_context: 共享上下文（跨 Agent 共享）
            task_data: 任务特定数据
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.phase = phase
        self._shared = shared_context
        self._task_data = task_data or TaskData()
        self._local: Dict[str, Any] = {}
        self._feedback: Optional[str] = None
        self._retry_count: int = 0

    # ============================================================
    # 项目级信息
    # ============================================================

    @property
    def project_id(self) -> str:
        """项目 ID"""
        return self._shared.get("project_id", "")

    @property
    def code_path(self) -> Path:
        """代码路径"""
        return Path(self._shared.get("code_path", "."))

    @property
    def deliverables_dir(self) -> Path:
        """交付件目录"""
        return Path(self._shared.get("deliverables_dir", "./deliverables"))

    @property
    def config_dir(self) -> Path:
        """配置目录"""
        return Path(self._shared.get("config_dir", "./config"))

    def get_project_info(self) -> Dict[str, Any]:
        """获取项目信息"""
        return self._shared.get("project_info", {})

    # ============================================================
    # OpenCode 连接获取
    # ============================================================

    def get_opencode_client(self) -> Optional["OpenCodeClient"]:
        """获取 OpenCode 客户端

        客户端由 AgentRunner 统一管理和注入。

        Returns:
            OpenCodeClient 实例，如果未注入则返回 None
        """
        return self._shared.get("__opencode_client__")

    def get_session_id(self) -> Optional[str]:
        """获取当前 Agent 的 Session ID

        Returns:
            Session ID，如果尚未创建则返回 None
        """
        sessions = self._shared.get("__sessions__", {})
        return sessions.get(self.agent_id)

    def set_session_id(self, session_id: str) -> None:
        """设置当前 Agent 的 Session ID

        Args:
            session_id: Session ID
        """
        if "__sessions__" not in self._shared:
            self._shared["__sessions__"] = {}
        self._shared["__sessions__"][self.agent_id] = session_id

    def create_session(self) -> str:
        """创建新的 OpenCode Session

        Returns:
            新创建的 Session ID
        """
        client = self.get_opencode_client()
        if client:
            session_id = client.create_session()
            self.set_session_id(session_id)
            return session_id
        raise RuntimeError("OpenCode client not available")

    # ============================================================
    # 跨阶段数据获取
    # ============================================================

    def get_phase_result(self, phase: str, agent_name: Optional[str] = None) -> Dict:
        """获取指定阶段的结果

        Args:
            phase: 阶段名称（system_analysis, threat_analysis, code_audit）
            agent_name: Agent 名称，None 则返回整个阶段的结果

        Returns:
            阶段结果字典
        """
        phase_results = self._shared.get("phase_results", {})
        phase_data = phase_results.get(phase, {})

        if agent_name:
            return phase_data.get(agent_name, {})
        return phase_data

    def get_all_phase_results(self) -> Dict[str, Dict]:
        """获取所有阶段的结果

        Returns:
            所有阶段结果
        """
        return self._shared.get("phase_results", {})

    def get_previous_phase_results(self) -> Dict[str, Dict]:
        """获取上一阶段的所有结果

        Returns:
            上一阶段的结果
        """
        phases_order = ["system_analysis", "threat_analysis", "code_audit"]

        try:
            current_idx = phases_order.index(self.phase)
        except ValueError:
            return {}

        if current_idx > 0:
            prev_phase = phases_order[current_idx - 1]
            return self.get_phase_result(prev_phase)
        return {}

    def set_result(self, result: Dict[str, Any]) -> None:
        """设置当前 Agent 的结果

        Args:
            result: 结果字典
        """
        if "phase_results" not in self._shared:
            self._shared["phase_results"] = {}

        if self.phase not in self._shared["phase_results"]:
            self._shared["phase_results"][self.phase] = {}

        self._shared["phase_results"][self.phase][self.agent_id] = result

    # ============================================================
    # 任务数据
    # ============================================================

    def get_task_data(self) -> TaskData:
        """获取任务数据"""
        return self._task_data

    def set_task_data(self, data: Dict[str, Any]) -> None:
        """设置任务数据"""
        self._task_data = TaskData(**data)

    def get_vulnerability(self) -> Optional[Dict[str, Any]]:
        """获取漏洞数据（代码审计阶段）"""
        return self._task_data.vulnerability

    def set_vulnerability(self, vuln: Dict[str, Any]) -> None:
        """设置漏洞数据"""
        self._task_data.vulnerability = vuln

    def get_scan_result(self) -> Optional[Dict[str, Any]]:
        """获取扫描结果"""
        return self._task_data.scan_result

    def get_target_file(self) -> Optional[str]:
        """获取目标文件"""
        return self._task_data.target_file

    def get_target_function(self) -> Optional[str]:
        """获取目标函数"""
        return self._task_data.target_function

    # ============================================================
    # 本地存储（Agent 内部使用）
    # ============================================================

    def get_local(self, key: str, default: Any = None) -> Any:
        """获取本地存储的值"""
        return self._local.get(key, default)

    def set_local(self, key: str, value: Any) -> None:
        """设置本地存储的值"""
        self._local[key] = value

    # ============================================================
    # 反馈机制
    # ============================================================

    def set_feedback(self, feedback: str) -> None:
        """设置验证反馈

        验证失败时调用，Agent 在下次重试时可以获取此反馈。

        Args:
            feedback: 反馈信息
        """
        self._feedback = feedback
        self._retry_count += 1

    def get_feedback(self) -> Optional[str]:
        """获取上次的验证反馈

        Returns:
            反馈信息，如果是首次执行则返回 None
        """
        return self._feedback

    def get_retry_count(self) -> int:
        """获取重试次数

        Returns:
            重试次数（0 表示首次执行）
        """
        return self._retry_count

    def is_retry(self) -> bool:
        """是否是重试"""
        return self._retry_count > 0

    def clear_feedback(self) -> None:
        """清除反馈"""
        self._feedback = None

    # ============================================================
    # 工具方法
    # ============================================================

    def get_deliverable_path(self, extension: str = ".json") -> Path:
        """获取交付件保存路径

        Args:
            extension: 文件扩展名

        Returns:
            交付件路径
        """
        filename = f"{self.agent_id}-{self.agent_type}{extension}"
        return self.deliverables_dir / self.phase / filename

    def get_deliverable_dir(self) -> Path:
        """获取当前阶段的交付件目录"""
        deliverable_dir = self.deliverables_dir / self.phase
        deliverable_dir.mkdir(parents=True, exist_ok=True)
        return deliverable_dir

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于调试）"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "phase": self.phase,
            "project_id": self.project_id,
            "code_path": str(self.code_path),
            "retry_count": self._retry_count,
            "has_feedback": self._feedback is not None,
        }
