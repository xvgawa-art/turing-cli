from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from turing_cli.clients.mcp_client import MCPClient
from turing_cli.mcp.executor import MCPExecutor


class MCPToolExecutionError(RuntimeError):
    """MCP 工具执行失败。"""


class AuditMCPService:
    """面向代码审计场景的 MCP 服务封装。"""

    def __init__(
        self,
        server_command: str,
        executor: MCPExecutor,
    ) -> None:
        self.server_command = server_command
        self.executor = executor
        self._client = MCPClient(server_command)

    def is_available(self) -> bool:
        return self._client.is_available()

    def get_method_source(
        self,
        *,
        class_name: str,
        method_name: str,
        code_path: Optional[str] = None,
        signature: Optional[str] = None,
        tool_key: str = "method_source",
        extra_arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """根据类名/方法名/方法签名获取源码。"""
        arguments: Dict[str, Any] = {
            "class_name": class_name,
            "method_name": method_name,
        }
        if code_path:
            arguments["code_path"] = code_path
        if signature:
            arguments["signature"] = signature
        if extra_arguments:
            arguments.update(extra_arguments)

        raw = self.call_tool(tool_key, arguments)
        normalized = self._normalize_tool_result(raw)
        normalized.setdefault("class_name", class_name)
        normalized.setdefault("method_name", method_name)
        normalized.setdefault("signature", signature)
        return normalized

    def call_tool(self, tool_key: str, arguments: Dict[str, Any]) -> Any:
        try:
            return self.executor.call(tool_key, arguments)
        except Exception as exc:
            raise MCPToolExecutionError(f"MCP 工具调用失败 [{tool_key}]: {exc}") from exc

    def _normalize_tool_result(self, result: Any) -> Dict[str, Any]:
        content: Any = result

        if hasattr(result, "content"):
            content = result.content
        elif isinstance(result, list) and result:
            first = result[0]
            if hasattr(first, "text"):
                content = first.text
            elif hasattr(first, "content"):
                content = first.content
            else:
                content = first

        if isinstance(content, str):
            content = self._parse_string_content(content)

        if not isinstance(content, dict):
            content = {"raw_response": content}

        source_code = self._extract_source_code(content)
        file_path = self._extract_first_value(content, ["file_path", "path", "source_file"])
        start_line = self._extract_first_value(content, ["start_line", "line_start"])
        end_line = self._extract_first_value(content, ["end_line", "line_end"])

        return {
            "found": bool(source_code),
            "source_code": source_code or "",
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "raw_response": content,
        }

    def _parse_string_content(self, content: str) -> Dict[str, Any]:
        json_match = re.search(r"```json\s*\n([\s\S]*?)\n```", content)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        return {"source_code": content, "raw_text": content}

    def _extract_source_code(self, content: Dict[str, Any]) -> Optional[str]:
        for key in ["source_code", "source", "code", "method_source", "content", "text"]:
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    def _extract_first_value(self, content: Dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            if key in content and content[key] not in (None, ""):
                return content[key]
        return None
