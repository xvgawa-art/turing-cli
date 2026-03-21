"""OpenCode client wrapper for AI code execution.

提供与 OpenCode server 交互的客户端功能。
"""

from typing import Any, Dict, List, Optional, Union

# Optional import - opencode_ai is only needed for actual OpenCode integration
try:
    from opencode_ai import (
        Opencode,
        APIConnectionError,
        APIError,
        APIStatusError,
        NotFoundError,
        BadRequestError,
    )
    OPENCODE_AVAILABLE = True
except ImportError:
    Opencode = None
    OPENCODE_AVAILABLE = False


class OpenCodeClient:
    """Wrapper around OpenCode SDK for AI code execution."""

    def __init__(self, base_url: str = "http://localhost:4097"):
        """Initialize OpenCode client.

        Args:
            base_url: Base URL of the OpenCode service
        Raises:
            ImportError: If opencode_ai is not installed
        """
        self.base_url = base_url.rstrip("/")
        self._client: Optional["Opencode"] = None

        if not OPENCODE_AVAILABLE:
            raise ImportError(
                "opencode-ai package is required for OpenCode integration. "
                "Install it with: pip install opencode-ai"
            )

    def initialize(self) -> bool:
        """初始化 OpenCode 客户端

        Returns:
            bool: 是否成功初始化
        """
        try:
            import httpx
            self._client = Opencode(
                base_url=self.base_url,
                timeout=httpx.Timeout(300.0),
            )
            return True
        except Exception as e:
            from turing_cli.config.logging_config import get_logger
            logger = get_logger(__name__)
            logger.warning(f"OpenCode 初始化失败: {e}")
            return False

    def get_client(self) -> Optional["Opencode"]:
        """获取 OpenCode 客户端

        Returns:
            Opencode 客户端实例
        """
        if self._client is None:
            self.initialize()
        return self._client

    def is_available(self) -> bool:
        """检查 OpenCode 是否可用"""
        return OPENCODE_AVAILABLE

    def get_providers(self) -> List[Dict[str, Any]]:
        """获取可用的 AI 提供商

        Returns:
            Provider 列表，如果不可用则返回空列表
        """
        if not self.is_available():
            return []

        client = self.get_client()
        if not client:
            return []

        try:
            providers_resp = client.app.providers()
            # 转换为统一的 Provider 字典格式
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.api or "",
                    "models": {model.id: model.name for model in p.models.values()},
                }
                for p in providers_resp.providers
            ]
        except APIConnectionError:
            # 连接失败，返回空列表
            return []
        except APIError:
            # API 调用失败
            return []

    def get_provider(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 Provider

        Args:
            provider_id: Provider ID

        Returns:
            Provider 信息字典，如果不存在则返回 None
        """
        providers = self.get_providers()
        for provider in providers:
            if provider["id"] == provider_id:
                return provider
        return None

    def get_default_model(self) -> Optional[Dict[str, Any]]:
        """获取默认的 Model

        Returns:
            默认的 Model 信息，如果未设置则返回 None
        """
        providers = self.get_providers()
        if not providers:
            return None

        provider = providers[0]
        models = provider.get("models", {})
        if models:
            first_model_id = list(models.keys())[0]
            return {
                "id": first_model_id,
                "name": provider.get("name", ""),
                "provider_id": provider["id"],
            }
        return None

    def create_session(self) -> str:
        """创建新的 OpenCode Session

        Returns:
            Session ID
        """
        if not self.is_available():
            raise RuntimeError("OpenCode client 不可用")

        client = self.get_client()
        session = client.session.create(extra_body={})
        return session.id

    def chat(
        self,
        session_id: str,
        prompt: str,
        model_id: str,
        provider_id: str,
        enable_tools: bool = False,
    ) -> Any:
        """发送 chat 消息到 OpenCode session

        Args:
            session_id: Session ID
            prompt: User prompt/message
            model_id: Model identifier
            provider_id: Provider identifier
            enable_tools: 是否启用文件操作和代码执行工具

        Returns:
            OpenCode 响应（AssistantMessage）
        """
        if not self.is_available():
            raise RuntimeError("OpenCode client 不可用")

        client = self.get_client()

        # 构建 parts（使用字典格式）
        parts = [{"type": "text", "text": prompt}]

        # 构建工具参数 - 只有在启用时才传递
        kwargs = {}
        if enable_tools:
            kwargs["tools"] = {"file_operations": True, "code_execution": True}

        try:
            return client.session.chat(
                session_id,
                model_id=model_id,
                provider_id=provider_id,
                parts=parts,
                **kwargs,
            )
        except APIConnectionError as e:
            from turing_cli.config.logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(f"OpenCode 连接失败: {e}")
            raise
        except APIStatusError as e:
            from turing_cli.config.logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(f"OpenCode API 错误: {e.status_code} - {e}")
            raise

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取 Session 信息

        Args:
            session_id: Session ID

        Returns:
            Session 信息字典，如果不存在则返回 None
        """
        if not self.is_available():
            return None

        client = self.get_client()
        if not client:
            return None

        try:
            # 获取所有 session 列表
            sessions_resp = client.session.list()
            for session in sessions_resp:
                if session.id == session_id:
                    return {
                        "id": session.id,
                        "created_at": session.created_at,
                        "app_id": session.app_id,
                    }
            return None
        except APIError:
            return None

    def get_sessions(self) -> List[Dict[str, Any]]:
        """获取所有 Session 信息

        Returns:
            Session 列表
        """
        if not self.is_available():
            return []

        client = self.get_client()
        if not client:
            return []

        try:
            sessions_resp = client.session.list()
            return [
                {
                    "id": session.id,
                    "created_at": session.created_at,
                    "app_id": session.app_id,
                }
                for session in sessions_resp
            ]
        except APIError:
            return []

    def get_app(self) -> Optional[Dict[str, Any]]:
        """获取 App 信息

        Returns:
            App 信息字典，如果不可用则返回 None
        """
        if not self.is_available():
            return None

        client = self.get_client()
        if not client:
            return None

        try:
            app = client.app.get()
            return {
                "id": "app",
                "git": app.git,
                "hostname": app.hostname,
                "path": app.path.model_dump(),
                "time": app.time.model_dump(),
            }
        except APIError:
            return None


# ========================================
# 测试用 Mock 客户端
# ========================================


class MockClient:
    """Mock OpenCode 客户端（仅用于测试）"""

    def __init__(self):
        self._providers = {
            "mock-provider": {
                "id": "mock-provider",
                "name": "Mock Provider",
                "description": "Mock AI provider for testing",
                "models": {
                    "mock-model-1": {"id": "mock-model-1", "name": "Mock Model 1"},
                    "mock-model-2": {"id": "mock-model-2", "name": "Mock Model 2"},
                    "mock-model-3": {"id": "mock-model-3", "name": "Mock Model 3"},
                },
            }
        }
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def initialize(self) -> bool:
        """Mock 初始化"""
        return True

    def is_available(self) -> bool:
        """Mock 总是可用的"""
        return True

    def get_providers(self) -> List[Dict[str, Any]]:
        """获取可用的 Provider"""
        return [self._providers["mock-provider"]]

    def get_provider(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 Provider"""
        if provider_id == "mock-provider":
            return self._providers["mock-provider"]
        return None

    def create_session(self) -> str:
        """创建新的 Session"""
        import uuid
        session_id = f"mock-session-{uuid.uuid4().hex[:8]}"
        self._sessions[session_id] = {
            "id": session_id,
            "created_at": None,
            "app_id": "mock-app",
        }
        return session_id

    def chat(
        self,
        session_id: str,
        prompt: str,
        model_id: str,
        provider_id: str,
        enable_tools: bool = False,
    ) -> Dict[str, Any]:
        """发送 chat 消息（Mock 版本）"""
        return {
            "id": f"msg-{session_id}",
            "session_id": session_id,
            "role": "assistant",
            "content": f"Mock response for: {prompt[:50]}...",
        }

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取 Session 信息（Mock 版本）"""
        return self._sessions.get(session_id)

    def get_sessions(self) -> List[Dict[str, Any]]:
        """获取所有 Session 信息（Mock 版本）"""
        return list(self._sessions.values())

    def get_app(self) -> Dict[str, Any]:
        """获取 App 信息（Mock 版本）"""
        return {
            "id": "mock-app",
            "name": "Mock Application",
            "providers": self._providers,
        }


# ========================================
# 工厂函数
# ========================================


def get_opencode_client(url: str = "http://localhost:4097") -> Union[OpenCodeClient, MockClient]:
    """获取 OpenCode 客户端

    Args:
        url: OpenCode 服务地址

    Returns:
        OpenCodeClient 实例，如果不可用则返回 MockClient
    """
    try:
        return OpenCodeClient(base_url=url)
    except ImportError:
        from turing_cli.config.logging_config import get_logger
        logger = get_logger(__name__)
        logger.warning("opencode-ai 未安装，使用 Mock Client")
        return MockClient()


def is_opencode_available() -> bool:
    """检查 opencode-ai 是否可用"""
    return OPENCODE_AVAILABLE


def get_mock_client(url: str = "http://localhost:4097") -> MockClient:
    """获取 Mock 客户端（用于测试）"""
    return MockClient()
