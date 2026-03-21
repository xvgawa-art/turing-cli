"""代码审计 Agent 实现。

提供各种漏洞类型的审计 Agent。
"""

import json
import re
from typing import Any, Dict, Optional

from turing_cli.agents.builtin.base import OpenCodeAgent
from turing_cli.agents.context import AgentContext
from turing_cli.models.deliverable import Deliverable, Confidence
from turing_cli.models.validation import ValidationResult
from turing_cli.validators.audit_validators import (
    SQLInjectionValidator,
    XSSValidator,
    AuthBypassValidator,
    CommandInjectionValidator,
    DeserializationValidator,
)


class CodeAuditAgent(OpenCodeAgent):
    """代码审计 Agent 基类

    提供代码审计的通用功能。
    """

    def prepare_context(self, context: AgentContext) -> None:
        """准备上下文"""
        super().prepare_context(context)

        # 获取威胁分析阶段的结果
        threat_results = context.get_phase_result("threat_analysis")
        if threat_results:
            # 存储高风险模块信息
            risk_assessment = threat_results.get("risk_assessment", {})
            high_risk_modules = risk_assessment.get("high_risk_modules", [])
            context.set_local("high_risk_modules", high_risk_modules)

    def parse_response(self, response: Any, context: AgentContext) -> Dict[str, Any]:
        """解析响应，尝试提取 JSON"""
        content = str(response) if response else ""

        # 尝试提取 JSON
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                parsed["raw_response"] = content
                return parsed
            except json.JSONDecodeError:
                pass

        # 尝试提取置信度
        confidence = self._extract_confidence(content)

        return {
            "confidence": confidence,
            "analysis": content,
            "raw_response": content,
        }

    def _extract_confidence(self, content: str) -> str:
        """从内容中提取置信度"""
        content_lower = content.lower()

        if "confirmed" in content_lower or "已确认" in content_lower:
            return "confirmed"
        elif "likely" in content_lower or "可能存在" in content_lower:
            return "likely"
        elif "false-positive" in content_lower or "误报" in content_lower:
            return "false-positive"
        else:
            return "unlikely"


# ============================================================
# SQL 注入审计 Agent
# ============================================================


class SQLInjectionAgent(CodeAuditAgent):
    """SQL 注入审计 Agent"""

    agent_type = "sql_injection"
    description = "SQL 注入漏洞审计"

    def build_prompt(self, context: AgentContext) -> str:
        vuln = context.get_vulnerability() or {}
        code_path = context.code_path

        return f"""你是一个专业的安全审计专家，请分析以下潜在的 SQL 注入漏洞。

**项目路径**: {code_path}

**漏洞信息**:
- 类型: {vuln.get('type', 'N/A')}
- Sink 类: {vuln.get('sinkClass', 'N/A')}
- Sink 方法: {vuln.get('sinkMethod', 'N/A')}
- Sink 签名: {vuln.get('sinkSig', 'N/A')}
- Bug 类: {vuln.get('bugClass', 'N/A')}
- Bug 方法: {vuln.get('bugMethod', 'N/A')}
- Bug 行: {vuln.get('bugLine', 'N/A')}
- 调用链: {json.dumps(vuln.get('callTree', {}), ensure_ascii=False, indent=2)}

**请分析**:
1. 这个 SQL 注入是否可利用？
2. 用户输入如何到达 sink 点？
3. 是否存在有效的过滤或转义？

**请以 JSON 格式返回**:
{{
    "confidence": "confirmed|likely|unlikely|false-positive",
    "vuln_type": "sql_injection",
    "sink_class": "...",
    "sink_method": "...",
    "source": "用户输入来源",
    "analysis": "详细分析...",
    "exploit_path": "利用路径（如果存在）"
}}
"""

    def validate(self, deliverable: Deliverable) -> ValidationResult:
        return SQLInjectionValidator.validate(deliverable)


# ============================================================
# XSS 审计 Agent
# ============================================================


class XSSAgent(CodeAuditAgent):
    """XSS 漏洞审计 Agent"""

    agent_type = "xss"
    description = "XSS 漏洞审计"

    def build_prompt(self, context: AgentContext) -> str:
        vuln = context.get_vulnerability() or {}
        code_path = context.code_path

        return f"""你是一个专业的安全审计专家，请分析以下潜在的 XSS 漏洞。

**项目路径**: {code_path}

**漏洞信息**:
- 类型: {vuln.get('type', 'N/A')}
- Sink 类: {vuln.get('sinkClass', 'N/A')}
- Sink 方法: {vuln.get('sinkMethod', 'N/A')}
- 调用链: {json.dumps(vuln.get('callTree', {}), ensure_ascii=False, indent=2)}

**请分析**:
1. XSS 类型（Reflected/Stored/DOM）
2. 用户输入如何到达输出点
3. 是否存在有效的输出编码

**请以 JSON 格式返回**:
{{
    "confidence": "confirmed|likely|unlikely|false-positive",
    "xss_type": "reflected|stored|dom",
    "sink": "输出点",
    "source": "用户输入来源",
    "analysis": "详细分析..."
}}
"""

    def validate(self, deliverable: Deliverable) -> ValidationResult:
        return XSSValidator.validate(deliverable)


# ============================================================
# 权限绕过审计 Agent
# ============================================================


class AuthBypassAgent(CodeAuditAgent):
    """权限绕过审计 Agent"""

    agent_type = "auth_bypass"
    description = "权限绕过漏洞审计"

    def build_prompt(self, context: AgentContext) -> str:
        vuln = context.get_vulnerability() or {}
        code_path = context.code_path

        return f"""你是一个专业的安全审计专家，请分析以下潜在的权限绕过漏洞。

**项目路径**: {code_path}

**漏洞信息**:
- 类型: {vuln.get('type', 'N/A')}
- Bug 类: {vuln.get('bugClass', 'N/A')}
- Bug 方法: {vuln.get('bugMethod', 'N/A')}
- 调用链: {json.dumps(vuln.get('callTree', {}), ensure_ascii=False, indent=2)}

**请分析**:
1. 权限检查是否完整
2. 是否存在绕过路径
3. 是否可以利用参数或路径绕过

**请以 JSON 格式返回**:
{{
    "confidence": "confirmed|likely|unlikely|false-positive",
    "bypass_type": "参数绕过|路径绕过|逻辑绕过",
    "bypass_path": "绕过路径（如果存在）",
    "analysis": "详细分析..."
}}
"""

    def validate(self, deliverable: Deliverable) -> ValidationResult:
        return AuthBypassValidator.validate(deliverable)


# ============================================================
# 命令注入审计 Agent
# ============================================================


class CommandInjectionAgent(CodeAuditAgent):
    """命令注入审计 Agent"""

    agent_type = "command_injection"
    description = "命令注入漏洞审计"

    def build_prompt(self, context: AgentContext) -> str:
        vuln = context.get_vulnerability() or {}
        code_path = context.code_path

        return f"""你是一个专业的安全审计专家，请分析以下潜在的命令注入漏洞。

**项目路径**: {code_path}

**漏洞信息**:
- 类型: {vuln.get('type', 'N/A')}
- Sink 类: {vuln.get('sinkClass', 'N/A')}
- Sink 方法: {vuln.get('sinkMethod', 'N/A')}
- 调用链: {json.dumps(vuln.get('callTree', {}), ensure_ascii=False, indent=2)}

**请分析**:
1. 命令执行函数是什么
2. 用户输入如何进入命令
3. 是否存在有效的输入验证

**请以 JSON 格式返回**:
{{
    "confidence": "confirmed|likely|unlikely|false-positive",
    "sink_function": "命令执行函数",
    "user_input_source": "用户输入来源",
    "analysis": "详细分析..."
}}
"""

    def validate(self, deliverable: Deliverable) -> ValidationResult:
        return CommandInjectionValidator.validate(deliverable)


# ============================================================
# 反序列化审计 Agent
# ============================================================


class DeserializationAgent(CodeAuditAgent):
    """反序列化漏洞审计 Agent"""

    agent_type = "deserialization"
    description = "反序列化漏洞审计"

    def build_prompt(self, context: AgentContext) -> str:
        vuln = context.get_vulnerability() or {}
        code_path = context.code_path

        return f"""你是一个专业的安全审计专家，请分析以下潜在的反序列化漏洞。

**项目路径**: {code_path}

**漏洞信息**:
- 类型: {vuln.get('type', 'N/A')}
- Sink 类: {vuln.get('sinkClass', 'N/A')}
- Sink 方法: {vuln.get('sinkMethod', 'N/A')}
- 调用链: {json.dumps(vuln.get('callTree', {}), ensure_ascii=False, indent=2)}

**请分析**:
1. 反序列化方法是什么
2. 数据来源是否可控
3. 是否存在可利用的 Gadget Chain

**请以 JSON 格式返回**:
{{
    "confidence": "confirmed|likely|unlikely|false-positive",
    "deser_method": "反序列化方法",
    "data_source": "数据来源",
    "gadget_chain": "Gadget Chain（如果存在）",
    "analysis": "详细分析..."
}}
"""

    def validate(self, deliverable: Deliverable) -> ValidationResult:
        return DeserializationValidator.validate(deliverable)
