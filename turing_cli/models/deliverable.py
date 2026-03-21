"""Agent 执行交付件模型。

定义 Agent 执行过程中产生和交换的数据结构。
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DeliverableStatus(str, Enum):
    """交付件状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class Confidence(str, Enum):
    """漏洞置信度"""

    CONFIRMED = "confirmed"  # 已确认
    LIKELY = "likely"  # 可能存在
    UNLIKELY = "unlikely"  # 不太可能
    FALSE_POSITIVE = "false-positive"  # 误报


class Deliverable(BaseModel):
    """Agent 执行交付件

    每个 Agent 执行完成后产生的结构化输出，包含分析结果、
    验证状态、重试信息等。

    Attributes:
        agent_id: Agent 唯一标识符
        agent_type: Agent 类型（如 sql_injection, auth_bypass）
        phase: 所属阶段（system_analysis, threat_analysis, code_audit）
        status: 交付件状态
        confidence: 置信度（仅代码审计阶段）
        content: 具体内容字典
        file_path: 保存的文件路径
        created_at: 创建时间
        validated_at: 验证时间
        validation_errors: 验证错误列表
        retry_count: 重试次数
        execution_time: 执行耗时（秒）
    """

    agent_id: str = Field(..., description="Agent 唯一标识符")
    agent_type: str = Field(..., description="Agent 类型")
    phase: str = Field(..., description="所属阶段")
    status: DeliverableStatus = Field(
        default=DeliverableStatus.PENDING, description="交付件状态"
    )
    confidence: Optional[Confidence] = Field(
        default=None, description="置信度（代码审计阶段）"
    )
    content: Dict[str, Any] = Field(
        default_factory=dict, description="具体内容字典"
    )
    file_path: Optional[Path] = Field(default=None, description="保存的文件路径")
    created_at: datetime = Field(
        default_factory=datetime.now, description="创建时间"
    )
    validated_at: Optional[datetime] = Field(
        default=None, description="验证时间"
    )
    validation_errors: List[str] = Field(
        default_factory=list, description="验证错误列表"
    )
    retry_count: int = Field(default=0, description="重试次数")
    execution_time: float = Field(default=0.0, description="执行耗时（秒）")

    model_config = {
        "arbitrary_types_allowed": True,
        "use_enum_values": True,
    }

    def mark_completed(self) -> "Deliverable":
        """标记为完成"""
        self.status = DeliverableStatus.COMPLETED
        return self

    def mark_failed(self, error: str) -> "Deliverable":
        """标记为失败"""
        self.status = DeliverableStatus.FAILED
        self.validation_errors.append(error)
        return self

    def mark_retrying(self, feedback: str) -> "Deliverable":
        """标记为重试中"""
        self.status = DeliverableStatus.RETRYING
        self.retry_count += 1
        self.validation_errors.append(feedback)
        return self

    def mark_validated(self) -> "Deliverable":
        """标记为已验证"""
        self.validated_at = datetime.now()
        return self

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 JSON 序列化）"""
        # 处理 confidence，可能是枚举或字符串
        confidence_str = None
        if self.confidence:
            if isinstance(self.confidence, Confidence):
                confidence_str = self.confidence.value
            else:
                confidence_str = str(self.confidence)

        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "phase": self.phase,
            "status": self.status.value if isinstance(self.status, DeliverableStatus) else self.status,
            "confidence": confidence_str,
            "content": self.content,
            "file_path": str(self.file_path) if self.file_path else None,
            "created_at": self.created_at.isoformat(),
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
            "validation_errors": self.validation_errors,
            "retry_count": self.retry_count,
            "execution_time": self.execution_time,
        }

    def save(self, output_dir: Path) -> Path:
        """保存交付件到文件

        Args:
            output_dir: 输出目录

        Returns:
            保存的文件路径
        """
        import json

        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self.agent_id}-{self.agent_type}.json"
        self.file_path = output_dir / filename

        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

        return self.file_path

    @classmethod
    def load(cls, file_path: Path) -> "Deliverable":
        """从文件加载交付件

        Args:
            file_path: 文件路径

        Returns:
            Deliverable 实例
        """
        import json

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        # 处理时间字段
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("validated_at"), str):
            data["validated_at"] = datetime.fromisoformat(data["validated_at"])

        # 处理路径字段
        if data.get("file_path"):
            data["file_path"] = Path(data["file_path"])

        return cls(**data)


class AgentResult(BaseModel):
    """Agent 执行结果

    AgentRunner.run() 的返回值，包含执行状态和交付件。

    Attributes:
        success: 是否成功
        agent_id: Agent ID
        deliverable: 交付件（成功时）
        error: 错误信息（失败时）
        attempts: 尝试次数
    """

    success: bool = Field(..., description="是否成功")
    agent_id: str = Field(..., description="Agent ID")
    deliverable: Optional[Deliverable] = Field(
        default=None, description="交付件"
    )
    error: Optional[str] = Field(default=None, description="错误信息")
    attempts: int = Field(default=1, description="尝试次数")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "agent_id": self.agent_id,
            "deliverable": self.deliverable.to_dict() if self.deliverable else None,
            "error": self.error,
            "attempts": self.attempts,
        }
