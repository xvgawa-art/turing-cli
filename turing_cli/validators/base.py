"""交付件验证器基类和注册表。"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """交付件验证结果

    验证器对交付件进行验证后的返回结果。

    Attributes:
        is_valid: 是否通过验证
        feedback: 反馈信息（验证失败时提供给 Agent 用于改进）
        errors: 错误列表
        warnings: 警告列表
    """

    is_valid: bool = Field(..., description="是否通过验证")
    feedback: Optional[str] = Field(
        default=None, description="反馈信息，用于指导 Agent 改进"
    )
    errors: List[str] = Field(default_factory=list, description="错误列表")
    warnings: List[str] = Field(default_factory=list, description="警告列表")

    @classmethod
    def success(cls) -> "ValidationResult":
        """创建成功的验证结果"""
        return cls(is_valid=True)

    @classmethod
    def failure(
        cls,
        feedback: str,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
    ) -> "ValidationResult":
        """创建失败的验证结果

        Args:
            feedback: 反馈信息
            errors: 错误列表
            warnings: 警告列表

        Returns:
            ValidationResult 实例
        """
        return cls(
            is_valid=False,
            feedback=feedback,
            errors=errors or [],
            warnings=warnings or [],
        )

    def add_error(self, error: str) -> "ValidationResult":
        """添加错误"""
        self.errors.append(error)
        return self

    def add_warning(self, warning: str) -> "ValidationResult":
        """添加警告"""
        self.warnings.append(warning)
        return self


class DeliverableValidator(ABC):
    """交付件验证器基类

    所有验证器必须继承此类并实现 validate 方法。

    Example:
        class SQLInjectionValidator(DeliverableValidator):
            @classmethod
            def validate(cls, deliverable: Deliverable) -> ValidationResult:
                content = deliverable.content
                if not content.get("sink_class"):
                    return ValidationResult.failure("缺少 sink_class 字段")
                return ValidationResult.success()
    """

    @classmethod
    @abstractmethod
    def validate(cls, deliverable: "Deliverable") -> ValidationResult:
        """验证交付件

        Args:
            deliverable: 要验证的交付件

        Returns:
            ValidationResult 验证结果
        """
        pass

    @classmethod
    def get_required_fields(cls) -> List[str]:
        """获取必填字段列表（子类可重写）"""
        return []

    @classmethod
    def check_required_fields(
        cls, deliverable: "Deliverable", fields: Optional[List[str]] = None
    ) -> Optional[str]:
        """检查必填字段

        Args:
            deliverable: 交付件
            fields: 字段列表，默认使用 get_required_fields()

        Returns:
            None 如果全部存在，否则返回缺失字段描述
        """
        fields = fields or cls.get_required_fields()
        content = deliverable.content
        missing = [f for f in fields if not content.get(f)]

        if missing:
            return f"缺少必要字段: {', '.join(missing)}"
        return None


class DefaultValidator(DeliverableValidator):
    """默认验证器

    执行基本的结构验证：
    - 检查 status 字段
    - 检查 content 不为空
    """

    @classmethod
    def validate(cls, deliverable: "Deliverable") -> ValidationResult:
        # 检查状态
        if not deliverable.status:
            return ValidationResult.failure("缺少 status 字段")

        # 检查内容
        if not deliverable.content:
            return ValidationResult.failure("content 不能为空")

        return ValidationResult.success()

    @classmethod
    def get_required_fields(cls) -> List[str]:
        return ["status"]


class CodeAuditValidator(DeliverableValidator):
    """代码审计验证器基类

    代码审计类的通用验证逻辑。
    """

    # 合法的置信度值
    VALID_CONFIDENCES = ["confirmed", "likely", "unlikely", "false-positive"]

    @classmethod
    def validate(cls, deliverable: "Deliverable") -> ValidationResult:
        content = deliverable.content

        # 检查置信度
        confidence = content.get("confidence")
        if confidence and confidence not in cls.VALID_CONFIDENCES:
            return ValidationResult.failure(
                f"无效的置信度: {confidence}，有效值为: {cls.VALID_CONFIDENCES}"
            )

        # 检查分析内容长度
        analysis = content.get("analysis", "")
        if len(analysis) < 20:
            return ValidationResult.failure("分析内容过短，可能不完整")

        return ValidationResult.success()

    @classmethod
    def get_required_fields(cls) -> List[str]:
        return ["confidence", "analysis"]


# ============================================================
# 验证器注册表
# ============================================================

_VALIDATOR_REGISTRY: Dict[str, Type[DeliverableValidator]] = {
    "default": DefaultValidator,
    "code_audit": CodeAuditValidator,
}


def register_validator(agent_type: str) -> callable:
    """注册验证器装饰器

    Example:
        @register_validator("sql_injection")
        class SQLInjectionValidator(DeliverableValidator):
            ...
    """

    def decorator(cls: Type[DeliverableValidator]) -> Type[DeliverableValidator]:
        _VALIDATOR_REGISTRY[agent_type] = cls
        return cls

    return decorator


def get_validator(agent_type: str) -> Type[DeliverableValidator]:
    """获取验证器

    Args:
        agent_type: Agent 类型

    Returns:
        对应的验证器类，如果未注册则返回 DefaultValidator
    """
    return _VALIDATOR_REGISTRY.get(agent_type, DefaultValidator)


def validate_deliverable(
    deliverable: "Deliverable", validator_type: Optional[str] = None
) -> ValidationResult:
    """验证交付件

    Args:
        deliverable: 交付件
        validator_type: 验证器类型，默认使用 deliverable.agent_type

    Returns:
        ValidationResult
    """
    validator_type = validator_type or deliverable.agent_type
    validator = get_validator(validator_type)
    return validator.validate(deliverable)
