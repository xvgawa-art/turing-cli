"""内置 Agent 包。

提供开箱即用的 Agent 实现：
- 系统分析 Agent
- 威胁分析 Agent
- 代码审计 Agent
"""

from turing_cli.agents.builtin.base import OpenCodeAgent
from turing_cli.agents.builtin.code_audit import (
    SQLInjectionAgent,
    XSSAgent,
    AuthBypassAgent,
    CommandInjectionAgent,
    DeserializationAgent,
)

__all__ = [
    # 基类
    "OpenCodeAgent",
    # 代码审计
    "SQLInjectionAgent",
    "XSSAgent",
    "AuthBypassAgent",
    "CommandInjectionAgent",
    "DeserializationAgent",
]
