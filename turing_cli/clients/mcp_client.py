"""
MCP 客户端 - 用于调用 MCP 服务器上的工具
"""
import asyncio
import json
import subprocess
import sys
from typing import Any, Dict, List, Optional

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


class MCPClient:
    """MCP 客户端"""

    def __init__(self, server_command: str = "python -u /opt/server.py"):
        """
        初始化 MCP 客户端

        Args:
            server_command: MCP 服务器启动命令
        """
        self.server_command = server_command
        self._session: Optional[ClientSession] = None
        self._initialized = False

    def is_available(self) -> bool:
        """检查 MCP 是否可用"""
        return MCP_AVAILABLE

    async def _ensure_session(self) -> ClientSession:
        """确保会话已初始化"""
        if self._session is None or not self._initialized:
            await self.connect()
        return self._session

    async def connect(self) -> None:
        """连接到 MCP 服务器"""
        if not MCP_AVAILABLE:
            raise ImportError("mcp 包未安装，请运行: pip install mcp")

        # 解析服务器命令
        parts = self.server_command.split()
        command = parts[0]
        args = parts[1:] if len(parts) > 1 else []

        # 创建服务器参数
        server_params = StdioServerParameters(
            command=command,
            args=args,
        )

        # 创建 stdio 客户端
        stdio_transport = await stdio_client(server_params)

        # 创建会话
        self._session = ClientSession(stdio_transport[0], stdio_transport[1])

        # 初始化会话
        await self._session.initialize()
        self._initialized = True

    async def disconnect(self) -> None:
        """断开连接"""
        if self._session and self._initialized:
            await self._session.close()
            self._initialized = False
            self._session = None

    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有可用工具"""
        session = await self._ensure_session()
        response = await session.list_tools()
        return response.tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Any:
        """
        调用工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        session = await self._ensure_session()
        response = await session.call_tool(tool_name, arguments)
        return response

    async def get_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """获取指定工具的信息"""
        tools = await self.list_tools()
        for tool in tools:
            if tool.name == tool_name:
                return tool
        return None

    def call_tool_sync(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Any:
        """
        同步调用工具（在 asyncio 事件循环中运行）

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在事件循环中，创建新的事件循环
                import nest_asyncio
                nest_asyncio.apply()
        except RuntimeError:
            pass

        return asyncio.run(self.call_tool(tool_name, arguments))


def run_mcp_tool_sync(
    server_command: str,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Any:
    """
    便捷函数：同步调用 MCP 工具

    Args:
        server_command: MCP 服务器启动命令
        tool_name: 工具名称
        arguments: 工具参数

    Returns:
        工具执行结果
    """
    client = MCPClient(server_command)
    try:
        return client.call_tool_sync(tool_name, arguments)
    finally:
        # 注意：由于 call_tool_sync 使用 asyncio.run，会话会自动关闭
        pass