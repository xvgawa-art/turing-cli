from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from turing_cli.config.loader import ConfigLoader


@dataclass(frozen=True)
class MCPToolSpec:
    """MCP 工具定义。

    Attributes:
        key: 工具的逻辑名称。
            这是业务代码里使用的稳定 key，例如：
            - method_source
            - class_source
            - call_chain

            Agent 和 Service 应依赖这个 key，而不是直接依赖真实 tool_name。

        tool_name: MCP Server 侧真实暴露的工具名。
            这一层通常会因不同项目、不同服务端实现而变化，
            所以应该放配置里，而不是散落在业务代码中。

        description: 工具描述，用于可读性和调试。
    """

    key: str
    tool_name: str
    description: str = ""


class MCPToolRegistry:
    """MCP 工具注册中心。

    这个类承担两个职责：
    1. 作为运行时内存中的工具索引
    2. 负责从配置文件把 MCP 工具定义加载进来

    设计目标：
    - 业务层只依赖逻辑 key，不直接写 tool_name
    - tool_name、描述等元数据集中管理
    - 后续可以平滑扩展参数 schema、返回 schema、权限控制等能力
    """

    def __init__(self, tools: Optional[Dict[str, MCPToolSpec]] = None):
        self._tools: Dict[str, MCPToolSpec] = tools or {}

    def register(self, spec: MCPToolSpec) -> None:
        """注册单个工具定义。"""
        self._tools[spec.key] = spec

    def register_many(self, specs: Dict[str, MCPToolSpec]) -> None:
        """批量注册工具定义。"""
        self._tools.update(specs)

    def get(self, key: str) -> Optional[MCPToolSpec]:
        """按逻辑 key 获取工具定义。"""
        return self._tools.get(key)

    def require(self, key: str) -> MCPToolSpec:
        """按逻辑 key 获取工具定义，不存在则抛错。"""
        tool = self.get(key)
        if tool is None:
            raise KeyError(f"未注册的 MCP 工具: {key}")
        return tool

    def to_dict(self) -> Dict[str, MCPToolSpec]:
        """导出当前注册表内容。"""
        return dict(self._tools)

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "MCPToolRegistry":
        """从配置字典创建注册表。

        支持两种结构：

        结构 A：
        {
          "tools": {
            "method_source": {
              "tool_name": "java_method_source",
              "description": "根据方法签名返回源码"
            }
          }
        }

        结构 B：
        {
          "mcp": {
            "tools": {
              "method_source": {
                "tool_name": "java_method_source",
                "description": "根据方法签名返回源码"
              }
            }
          }
        }

        这样做是为了让它既能单独复用，也能嵌入更大的配置文件结构中。
        """
        tools_section = config.get("tools")
        if tools_section is None and isinstance(config.get("mcp"), dict):
            tools_section = config["mcp"].get("tools")

        if not isinstance(tools_section, dict):
            raise ValueError("MCP 配置缺少 tools 字段，或 tools 不是字典类型")

        registry = cls()
        for key, raw_spec in tools_section.items():
            if not isinstance(raw_spec, dict):
                raise ValueError(f"MCP 工具配置格式错误: {key}")

            tool_name = raw_spec.get("tool_name")
            if not tool_name:
                raise ValueError(f"MCP 工具 [{key}] 缺少 tool_name 配置")

            registry.register(
                MCPToolSpec(
                    key=key,
                    tool_name=tool_name,
                    description=raw_spec.get("description", ""),
                )
            )

        return registry

    @classmethod
    def from_yaml_file(cls, filepath: Path) -> "MCPToolRegistry":
        """从指定 YAML 文件创建注册表。"""
        loader = ConfigLoader(filepath.parent)
        config = loader.load_yaml(filepath.name)
        return cls.from_config(config)

    @classmethod
    def from_config_dir(cls, config_dir: Path, filename: str = "mcp_tools.yaml") -> "MCPToolRegistry":
        """从配置目录加载 MCP 注册表。

        默认读取 ``config_dir/mcp_tools.yaml``。
        这是推荐入口，适合工程中的标准目录结构。
        """
        loader = ConfigLoader(config_dir)
        config = loader.load_yaml(filename)
        return cls.from_config(config)


DEFAULT_MCP_TOOLS = MCPToolRegistry()
