"""Session manager for OpenCode sessions."""

from typing import Dict, Optional


class SessionManager:
    """Manages OpenCode sessions for different agents.

    Each agent gets its own isolated session to prevent cross-contamination.
    """

    def __init__(self, client: "OpenCodeClient"):
        """Initialize session manager.

        Args:
            client: OpenCode client instance
        """
        self.client = client
        self._sessions: Dict[str, str] = {}

    def create_agent_session(self, agent_name: str) -> str:
        """Create a new session for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Session ID
        """
        session_id = self.client.create_session()
        self._sessions[agent_name] = session_id
        return session_id

    def get_session(self, agent_name: str) -> Optional[str]:
        """Get existing session for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Session ID or None if not found
        """
        return self._sessions.get(agent_name)

    def close_session(self, agent_name: str):
        """Close a session for an agent.

        Args:
            agent_name: Name of the agent
        """
        if agent_name in self._sessions:
            del self._sessions[agent_name]
