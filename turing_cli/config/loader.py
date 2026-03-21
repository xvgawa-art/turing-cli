from pathlib import Path
import yaml


class ConfigLoader:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir

    def load_agent_config(self) -> dict:
        config_path = self.config_dir / "agents.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)

    def load_prompt(self, prompt_name: str) -> str:
        prompt_path = self.config_dir / "prompts" / f"{prompt_name}.md"
        with open(prompt_path) as f:
            return f.read()
