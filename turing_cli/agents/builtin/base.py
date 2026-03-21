"""OpenCode Agent 基类。

提供集成 OpenCode 的 Agent 基类实现。
"""

import time
from abc import abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from turing_cli.agents.runner import BaseAgent
from turing_cli.agents.context import AgentContext
from turing_cli.models.deliverable import Deliverable, DeliverableStatus, Confidence
from turing_cli.models.validation import ValidationResult


class OpenCodeAgent(BaseAgent):
    """OpenCode Agent 基类

    集成 OpenCode 的 Agent 基类，子类只需实现：
    - build_prompt(): 构建 prompt
    - parse_response(): 解析响应

    Example:
        class SQLInjectionAgent(OpenCodeAgent):
            agent_type = "sql_injection"

            def build_prompt(self, context: AgentContext) -> str:
                vuln = context.get_vulnerability()
                return f"分析 SQL 注入: {vuln}"

            def parse_response(self, response: str) -> Dict[str, Any]:
                return {"confidence": "confirmed", "analysis": response}
    """

    def __init__(self):
        self._provider_id: Optional[str] = None
        self._model_id: Optional[str] = None

    def execute(self, context: AgentContext) -> Deliverable:
        """执行 Agent

        模板方法：
        1. 获取 OpenCode 客户端
        2. 创建/获取 Session
        3. 构建 Prompt
        4. 调用 OpenCode
        5. 解析响应
        6. 返回 Deliverable
        """
        start_time = time.time()

        # 1. 获取客户端
        client = context.get_opencode_client()
        if not client:
            return self._create_error_deliverable(
                context, "OpenCode client not available"
            )

        # 2. 获取或创建 Session
        session_id = context.get_session_id()
        if not session_id:
            session_id = context.create_session()

        # 3. 获取 Provider 和 Model
        if not self._provider_id:
            self._init_provider(client)

        # 4. 构建 Prompt
        prompt = self.build_prompt(context)

        # 5. 调用 OpenCode
        try:
            response = client.chat(
                session_id=session_id,
                prompt=prompt,
                model_id=self._model_id,
                provider_id=self._provider_id,
            )
        except Exception as e:
            return self._create_error_deliverable(context, str(e))

        # 6. 解析响应
        parsed = self.parse_response(response, context)

        # 7. 返回 Deliverable
        return Deliverable(
            agent_id=context.agent_id,
            agent_type=self.agent_type,
            phase=context.phase,
            status=DeliverableStatus.COMPLETED,
            confidence=self._get_confidence(parsed.get("confidence")),
            content=parsed,
            execution_time=time.time() - start_time,
        )

    def _init_provider(self, client) -> None:
        """初始化 Provider 和 Model"""
        providers = client.get_providers()
        if not providers:
            raise RuntimeError("No providers available")

        provider = providers[0]
        self._provider_id = provider.id
        models = list(provider.models.keys())
        self._model_id = models[0] if models else "default"

    def _get_confidence(self, value: Optional[str]) -> Optional[Confidence]:
        """转换置信度值"""
        if not value:
            return None
        try:
            return Confidence(value.lower())
        except ValueError:
            return None

    def _create_error_deliverable(
        self, context: AgentContext, error: str
    ) -> Deliverable:
        """创建错误 Deliverable"""
        return Deliverable(
            agent_id=context.agent_id,
            agent_type=self.agent_type,
            phase=context.phase,
            status=DeliverableStatus.FAILED,
            content={"error": error},
        )

    @abstractmethod
    def build_prompt(self, context: AgentContext) -> str:
        """构建 Prompt（子类必须实现）

        Args:
            context: Agent 执行上下文

        Returns:
            Prompt 字符串
        """
        pass

    def parse_response(self, response: Any, context: AgentContext) -> Dict[str, Any]:
        """解析 OpenCode 响应（子类可重写）

        Args:
            response: OpenCode 响应
            context: Agent 执行上下文

        Returns:
            解析后的内容字典
        """
        # 默认实现：尝试提取文本内容
        if hasattr(response, "content"):
            return {"analysis": response.content, "raw_response": str(response)}
        return {"analysis": str(response), "raw_response": str(response)}

    def get_prompt_template(self) -> str:
        """获取 Prompt 模板（子类可重写）"""
        return ""


class SimpleAgent(OpenCodeAgent):
    """简单 Agent

    通过 prompt_template 创建的简单 Agent。
    """

    def __init__(
        self,
        agent_type: str,
        prompt_template: str,
        required_fields: Optional[List[str]] = None,
    ):
        super().__init__()
        self._agent_type = agent_type
        self._prompt_template = prompt_template
        self._required_fields = required_fields or []

    @property
    def agent_type(self) -> str:
        return self._agent_type

    def build_prompt(self, context: AgentContext) -> str:
        """构建 Prompt"""
        # 收集模板变量
        variables = {
            "code_path": str(context.code_path),
            "agent_id": context.agent_id,
            "phase": context.phase,
        }

        # 添加漏洞信息
        vuln = context.get_vulnerability()
        if vuln:
            variables.update({
                "vuln_type": vuln.get("type", ""),
                "bug_class": vuln.get("bugClass", ""),
                "bug_method": vuln.get("bugMethod", ""),
                "bug_line": vuln.get("bugLine", ""),
            })

        # 添加上一阶段结果
        prev_results = context.get_previous_phase_results()
        if prev_results:
            variables["prev_results"] = str(prev_results)

        return self._prompt_template.format(**variables)

    def validate(self, deliverable: Deliverable) -> ValidationResult:
        """验证交付件"""
        content = deliverable.content

        # 检查必填字段
        for field in self._required_fields:
            if not content.get(field):
                return ValidationResult.failure(f"缺少必要字段: {field}")

        return ValidationResult.success()
