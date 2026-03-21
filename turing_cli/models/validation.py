"""交付件验证模型（兼容层）。

此文件保持向后兼容，实际实现已移动到 validators 包。
"""

# 重新导出 validators 包中的类
from turing_cli.validators.base import (
    ValidationResult,
    DeliverableValidator,
    DefaultValidator,
    CodeAuditValidator,
    register_validator,
    get_validator,
    validate_deliverable,
)

__all__ = [
    "ValidationResult",
    "DeliverableValidator",
    "DefaultValidator",
    "CodeAuditValidator",
    "register_validator",
    "get_validator",
    "validate_deliverable",
]
