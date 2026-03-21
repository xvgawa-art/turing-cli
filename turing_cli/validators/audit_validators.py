"""代码审计相关验证器。

提供针对不同漏洞类型的验证逻辑。
"""

from typing import List

from turing_cli.validators.base import (
    DeliverableValidator,
    ValidationResult,
    register_validator,
)


class CodeAuditValidator(DeliverableValidator):
    """代码审计验证器基类

    提供代码审计类 Agent 的通用验证逻辑。
    """

    # 合法的置信度值
    VALID_CONFIDENCES = ["confirmed", "likely", "unlikely", "false-positive"]

    @classmethod
    def validate(cls, deliverable) -> ValidationResult:
        content = deliverable.content

        # 1. 检查置信度
        confidence = content.get("confidence")
        if not confidence:
            return ValidationResult.failure("缺少 confidence 字段")

        if confidence not in cls.VALID_CONFIDENCES:
            return ValidationResult.failure(
                f"无效的置信度: {confidence}，有效值为: {cls.VALID_CONFIDENCES}"
            )

        # 2. 检查分析内容
        analysis = content.get("analysis", "")
        if len(analysis) < 50:
            return ValidationResult.failure(
                f"分析内容过短（{len(analysis)} 字符），可能不完整，请提供更详细的分析"
            )

        return ValidationResult.success()

    @classmethod
    def get_required_fields(cls) -> List[str]:
        return ["confidence", "analysis"]


@register_validator("sql_injection")
class SQLInjectionValidator(CodeAuditValidator):
    """SQL 注入漏洞验证器"""

    @classmethod
    def validate(cls, deliverable) -> ValidationResult:
        content = deliverable.content

        # 1. 基础验证
        base_result = super().validate(deliverable)
        if not base_result.is_valid:
            return base_result

        # 2. 检查 SQL 注入特有字段
        required = cls._get_required_fields()
        missing = [f for f in required if not content.get(f)]
        if missing:
            return ValidationResult.failure(
                f"SQL注入分析缺少必要字段: {', '.join(missing)}"
            )

        # 3. 检查 sink 信息完整性
        sink_class = content.get("sink_class")
        sink_method = content.get("sink_method")
        if not sink_class or not sink_method:
            return ValidationResult.failure(
                "SQL注入分析必须包含 sink_class 和 sink_method"
            )

        return ValidationResult.success()

    @classmethod
    def _get_required_fields(cls) -> List[str]:
        return ["vuln_type", "sink_class", "sink_method", "confidence"]


@register_validator("xss")
class XSSValidator(CodeAuditValidator):
    """XSS 漏洞验证器"""

    @classmethod
    def validate(cls, deliverable) -> ValidationResult:
        content = deliverable.content

        # 1. 基础验证
        base_result = super().validate(deliverable)
        if not base_result.is_valid:
            return base_result

        # 2. 检查 XSS 特有字段
        xss_type = content.get("xss_type")
        if xss_type and xss_type not in ["reflected", "stored", "dom"]:
            return ValidationResult.failure(
                f"无效的 XSS 类型: {xss_type}，有效值为: reflected, stored, dom"
            )

        # 3. 检查 sink 信息
        sink = content.get("sink")
        if not sink:
            return ValidationResult.failure("XSS 分析必须包含 sink 信息")

        return ValidationResult.success()


@register_validator("auth_bypass")
class AuthBypassValidator(CodeAuditValidator):
    """权限绕过漏洞验证器"""

    @classmethod
    def validate(cls, deliverable) -> ValidationResult:
        content = deliverable.content

        # 1. 基础验证
        base_result = super().validate(deliverable)
        if not base_result.is_valid:
            return base_result

        # 2. 检查权限绕过特有字段
        bypass_type = content.get("bypass_type")
        if not bypass_type:
            return ValidationResult.failure("权限绕过分析必须包含 bypass_type")

        # 3. 检查绕过路径
        bypass_path = content.get("bypass_path")
        if bypass_type == "confirmed" and not bypass_path:
            return ValidationResult.failure(
                "确认的权限绕过必须包含 bypass_path（绕过路径）"
            )

        return ValidationResult.success()


@register_validator("command_injection")
class CommandInjectionValidator(CodeAuditValidator):
    """命令注入漏洞验证器"""

    @classmethod
    def validate(cls, deliverable) -> ValidationResult:
        content = deliverable.content

        # 1. 基础验证
        base_result = super().validate(deliverable)
        if not base_result.is_valid:
            return base_result

        # 2. 检查命令注入特有字段
        sink_function = content.get("sink_function")
        if not sink_function:
            return ValidationResult.failure("命令注入分析必须包含 sink_function")

        # 3. 检查输入来源
        user_input = content.get("user_input_source")
        if not user_input:
            return ValidationResult.failure(
                "命令注入分析必须包含 user_input_source（用户输入来源）"
            )

        return ValidationResult.success()


@register_validator("deserialization")
class DeserializationValidator(CodeAuditValidator):
    """反序列化漏洞验证器"""

    @classmethod
    def validate(cls, deliverable) -> ValidationResult:
        content = deliverable.content

        # 1. 基础验证
        base_result = super().validate(deliverable)
        if not base_result.is_valid:
            return base_result

        # 2. 检查反序列化特有字段
        gadget_chain = content.get("gadget_chain")
        if content.get("confidence") == "confirmed" and not gadget_chain:
            return ValidationResult.failure(
                "确认的反序列化漏洞必须包含 gadget_chain 信息"
            )

        return ValidationResult.success()


@register_validator("ssrf")
class SSRFValidator(CodeAuditValidator):
    """SSRF 漏洞验证器"""

    @classmethod
    def validate(cls, deliverable) -> ValidationResult:
        content = deliverable.content

        # 1. 基础验证
        base_result = super().validate(deliverable)
        if not base_result.is_valid:
            return base_result

        # 2. 检查 SSRF 特有字段
        target_url_param = content.get("target_url_param")
        if not target_url_param:
            return ValidationResult.failure("SSRF 分析必须包含 target_url_param")

        return ValidationResult.success()


@register_validator("path_traversal")
class PathTraversalValidator(CodeAuditValidator):
    """路径遍历漏洞验证器"""

    @classmethod
    def validate(cls, deliverable) -> ValidationResult:
        content = deliverable.content

        # 1. 基础验证
        base_result = super().validate(deliverable)
        if not base_result.is_valid:
            return base_result

        # 2. 检查路径遍历特有字段
        file_operation = content.get("file_operation")
        if not file_operation:
            return ValidationResult.failure("路径遍历分析必须包含 file_operation")

        return ValidationResult.success()


# ============================================================
# 通用系统分析验证器
# ============================================================


@register_validator("business_architecture")
class BusinessArchitectureValidator(DeliverableValidator):
    """业务架构分析验证器"""

    @classmethod
    def validate(cls, deliverable) -> ValidationResult:
        content = deliverable.content

        # 检查必要字段
        required = ["architecture_overview", "core_modules", "tech_stack"]
        missing = [f for f in required if not content.get(f)]
        if missing:
            return ValidationResult.failure(
                f"业务架构分析缺少: {', '.join(missing)}"
            )

        # 检查核心模块数量
        modules = content.get("core_modules", [])
        if len(modules) < 1:
            return ValidationResult.failure("必须识别至少一个核心模块")

        return ValidationResult.success()


@register_validator("risk_assessment")
class RiskAssessmentValidator(DeliverableValidator):
    """风险评估验证器"""

    @classmethod
    def validate(cls, deliverable) -> ValidationResult:
        content = deliverable.content

        # 检查必要字段
        required = ["high_risk_modules", "risk_matrix"]
        missing = [f for f in required if not content.get(f)]
        if missing:
            return ValidationResult.failure(f"风险评估缺少: {', '.join(missing)}")

        return ValidationResult.success()
