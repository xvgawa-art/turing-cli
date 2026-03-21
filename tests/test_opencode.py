"""Tests for OpenCode client integration."""

from unittest.mock import Mock, MagicMock
from pathlib import Path

from turing_cli.core.opencode.client import OpenCodeClient
from turing_cli.core.opencode.session_manager import SessionManager
from turing_cli.core.opencode.executor import AgentExecutor
from turing_cli.models.audit import Vulnerability


def test_client_init():
    """Test OpenCode client initialization."""
    client = OpenCodeClient("http://localhost:4097")
    assert client is not None
    assert client.client is not None


def test_client_create_session():
    """Test session creation."""
    mock_opencode = Mock()
    mock_session = Mock()
    mock_session.id = "test-session-id"
    mock_opencode.session.create.return_value = mock_session

    client = OpenCodeClient()
    client.client = mock_opencode

    session_id = client.create_session()

    assert session_id == "test-session-id"
    mock_opencode.session.create.assert_called_once_with(extra_body={})


def test_client_get_providers():
    """Test getting providers."""
    mock_opencode = Mock()
    mock_response = Mock()
    mock_provider = Mock()
    mock_provider.id = "test-provider"
    mock_provider.models = {"model1": Mock()}
    mock_response.providers = [mock_provider]
    mock_opencode.app.providers.return_value = mock_response

    client = OpenCodeClient()
    client.client = mock_opencode

    providers = client.get_providers()

    assert len(providers) == 1
    assert providers[0].id == "test-provider"
    mock_opencode.app.providers.assert_called_once()


def test_client_chat():
    """Test sending chat message."""
    mock_opencode = Mock()
    mock_response = Mock()
    mock_opencode.client.session.chat.return_value = mock_response

    client = OpenCodeClient()
    client.client = mock_opencode

    response = client.chat(
        session_id="test-session",
        prompt="Hello",
        model_id="model1",
        provider_id="provider1",
    )

    assert response == mock_response
    mock_opencode.client.session.chat.assert_called_once_with(
        "test-session",
        model_id="model1",
        provider_id="provider1",
        parts=[{"type": "text", "text": "Hello"}],
        tools={"file_operations": True, "code_execution": True},
    )


def test_session_manager():
    """Test session manager."""
    client = Mock()
    client.create_session.return_value = "test-session-id"

    mgr = SessionManager(client)
    sid = mgr.create_agent_session("test-agent")

    assert sid == "test-session-id"
    assert mgr.get_session("test-agent") == "test-session-id"
    assert mgr.get_session("non-existent") is None

    mgr.close_session("test-agent")
    assert mgr.get_session("test-agent") is None


def test_executor_execute():
    """Test agent executor."""
    client = Mock()
    client.create_session.return_value = "test-session-id"

    mock_provider = Mock()
    mock_provider.id = "test-provider"
    mock_provider.models = {"model1": Mock()}
    client.get_providers.return_value = [mock_provider]

    mock_response = Mock()
    client.chat.return_value = mock_response

    session_mgr = SessionManager(client)
    executor = AgentExecutor(client, session_mgr)

    vulnerability = Vulnerability(
        type="sql_injection",
        bugClass="Injection",
        bugMethod="executeQuery",
        bugLine=42,
        bugSig="executeQuery(Ljava/lang/String;)V",
        sinkClass="Statement",
        sinkMethod="execute",
        sinkSig="execute(Ljava/lang/String;)Z",
        callTree={"main": ["process", "executeQuery"]},
    )

    result = executor.execute(
        agent_name="test-agent",
        vulnerability=vulnerability,
        code_path=Path("/test/code"),
        prompt_template="Analyze {vuln_type} in {bug_method}",
    )

    assert result["status"] == "completed"
    assert result["response"] == mock_response

    client.create_session.assert_called_once()
    client.get_providers.assert_called_once()
    client.chat.assert_called_once()


def test_executor_build_prompt():
    """Test prompt building."""
    client = Mock()
    session_mgr = Mock()
    executor = AgentExecutor(client, session_mgr)

    vulnerability = Vulnerability(
        type="sql_injection",
        bugClass="Injection",
        bugMethod="executeQuery",
        bugLine=42,
        bugSig="executeQuery(Ljava/lang/String;)V",
        sinkClass="Statement",
        sinkMethod="execute",
        sinkSig="execute(Ljava/lang/String;)Z",
        callTree={"main": ["process", "executeQuery"]},
    )

    prompt = executor._build_prompt(
        vulnerability,
        Path("/test/code"),
        "Type: {vuln_type}, Class: {bug_class}, Method: {bug_method}",
    )

    assert "sql_injection" in prompt
    assert "Injection" in prompt
    assert "executeQuery" in prompt


def test_executor_no_providers():
    """Test executor when no providers available."""
    client = Mock()
    client.get_providers.return_value = []

    session_mgr = Mock()
    executor = AgentExecutor(client, session_mgr)

    vulnerability = Vulnerability(
        type="sql_injection",
        bugClass="Injection",
        bugMethod="executeQuery",
        bugLine=42,
        bugSig="executeQuery(Ljava/lang/String;)V",
        sinkClass="Statement",
        sinkMethod="execute",
        sinkSig="execute(Ljava/lang/String;)Z",
        callTree={"main": ["process", "executeQuery"]},
    )

    try:
        executor.execute(
            agent_name="test-agent",
            vulnerability=vulnerability,
            code_path=Path("/test/code"),
            prompt_template="Test prompt",
        )
        assert False, "Should have raised RuntimeError"
    except RuntimeError as e:
        assert "No providers available" in str(e)
