"""交付件验证器包。

提供 Agent 交付件的验证机制。
"""

from turing_cli.validators.base import (
    DeliverableValidator,
    DefaultValidator,
    ValidationResult,
    register_validator,
    get_validator,
    validate_deliverable,
)
from turing_cli.validators.audit_validators import (
    CodeAuditValidator,
    SQLInjectionValidator,
    XSSValidator,
    AuthBypassValidator,
    CommandInjectionValidator,
)

__all__ = [
    # 基类和工具
    "DeliverableValidator",
    "DefaultValidator",
    "ValidationResult",
    "register_validator",
    "get_validator",
    "validate_deliverable",
    # 具体验证器
    "CodeAuditValidator",
    "SQLInjectionValidator",
    "XSSValidator",
    "AuthBypassValidator",
    "CommandInjectionValidator",
]
