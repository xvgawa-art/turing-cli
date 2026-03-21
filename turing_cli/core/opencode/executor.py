"""Agent executor for running AI agents with OpenCode."""

from pathlib import Path
from typing import Dict

from turing_cli.models.audit import Vulnerability


class AgentExecutor:
    """Executes AI agents with vulnerability context using OpenCode."""

    def __init__(self, client, session_mgr):
        """Initialize agent executor.

        Args:
            client: OpenCode client instance
            session_mgr: Session manager instance
        """
        self.client = client
        self.session_mgr = session_mgr

    def execute(
        self,
        agent_name: str,
        vulnerability: Vulnerability,
        code_path: Path,
        prompt_template: str,
    ) -> Dict:
        """Execute an agent with vulnerability context.

        Args:
            agent_name: Name of the agent to execute
            vulnerability: Vulnerability context
            code_path: Path to code files
            prompt_template: Prompt template string

        Returns:
            Execution result dictionary
        """
        session_id = self.session_mgr.create_agent_session(agent_name)

        providers = self.client.get_providers()
        if not providers:
            raise RuntimeError("No providers available")

        provider = providers[0]
        provider_id = provider.id
        model_id = list(provider.models.keys())[0]

        prompt = self._build_prompt(vulnerability, code_path, prompt_template)

        response = self.client.chat(
            session_id=session_id,
            prompt=prompt,
            model_id=model_id,
            provider_id=provider_id,
        )

        return self._parse_response(response)

    def _build_prompt(
        self,
        vulnerability: Vulnerability,
        code_path: Path,
        template: str,
    ) -> str:
        """Build prompt from template and vulnerability context.

        Args:
            vulnerability: Vulnerability context
            code_path: Path to code files
            template: Prompt template string

        Returns:
            Formatted prompt string
        """
        return template.format(
            vuln_type=vulnerability.type,
            bug_class=vulnerability.bugClass,
            bug_method=vulnerability.bugMethod,
            code_path=str(code_path),
            calltree=vulnerability.callTree,
        )

    def _parse_response(self, response) -> Dict:
        """Parse OpenCode response into standardized format.

        Args:
            response: Raw response from OpenCode

        Returns:
            Parsed result dictionary
        """
        return {
            "status": "completed",
            "response": response,
        }
