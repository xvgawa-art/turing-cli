from pathlib import Path
from typing import Any, Dict

import yaml


class ConfigLoader:
    """统一配置加载器。

    目前负责加载：
    1. agents.yaml：Agent 相关配置
    2. prompts/*.md：Prompt 模板
    3. mcp_tools.yaml：MCP 工具注册配置

    之所以把 MCP 配置也放进这里，而不是让调用方自行读 YAML，
    是为了让整个工程的配置读取入口保持一致，后续你要增加：
    - 多环境配置
    - 配置校验
    - 默认值合并
    - 配置热切换
    都可以在这一层统一处理。
    """

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir

    def load_yaml(self, filename: str) -> Dict[str, Any]:
        """加载指定 YAML 文件。

        Args:
            filename: 配置文件名，例如 ``agents.yaml`` 或 ``mcp_tools.yaml``

        Returns:
            解析后的字典；如果 YAML 为空，则返回空字典。
        """
        config_path = self.config_dir / filename
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def load_agent_config(self) -> Dict[str, Any]:
        """加载 Agent 配置。"""
        return self.load_yaml("agents.yaml")

    def load_mcp_config(self) -> Dict[str, Any]:
        """加载 MCP 工具配置。

        约定文件名为 ``mcp_tools.yaml``。
        """
        return self.load_yaml("mcp_tools.yaml")

    def load_prompt(self, prompt_name: str) -> str:
        """加载 Prompt 模板。"""
        prompt_path = self.config_dir / "prompts" / f"{prompt_name}.md"
        with open(prompt_path, encoding="utf-8") as f:
            return f.read()
