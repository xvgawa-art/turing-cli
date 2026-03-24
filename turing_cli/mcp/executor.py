from __future__ import annotations

from typing import Any, Dict

from turing_cli.clients.mcp_client import run_mcp_tool_sync
from turing_cli.mcp.registry import MCPToolRegistry


class MCPExecutor:
    """MCP 工具执行器。"""

    def __init__(self, server_command: str, registry: MCPToolRegistry):
        self.server_command = server_command
        self.registry = registry

    def call(self, tool_key: str, arguments: Dict[str, Any]) -> Any:
        spec = self.registry.require(tool_key)
        return run_mcp_tool_sync(
            server_command=self.server_command,
            tool_name=spec.tool_name,
            arguments=arguments,
        )
