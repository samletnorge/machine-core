"""CLI agent for command-line usage."""

from pathlib import Path
from typing import Optional, Union
from core.agent_base import BaseAgent
from ..core.config import AgentConfig


class CLIAgent(BaseAgent):
    """CLI agent for command-line usage.
    
    Uses non-streaming execution for simple CLI output.
    Perfect for: Terminal commands, cron jobs, scripts
    """
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        mcp_config_path: str = "mcp.json",
        agent_config: Optional[AgentConfig] = None
    ):
        super().__init__(
            model_name=model_name,
            system_prompt="You are a helpful AI assistant.",
            mcp_config_path=mcp_config_path,
            agent_config=agent_config
        )
    
    async def run(self, query: str, image_paths: Optional[Union[str, Path, list]] = None):
        """Run a single CLI query.
        
        Returns complete result after execution.
        """
        result = await self.run_query(query, image_paths)
        return result
