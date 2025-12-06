"""Chat agent for interactive conversations."""

from pathlib import Path
from typing import Optional, Union
from core.agent_base import BaseAgent
from ..core.config import AgentConfig


class ChatAgent(BaseAgent):
    """Chat agent for interactive conversations.
    
    Uses streaming for real-time responses with thinking display.
    Perfect for: Streamlit UI, web chat, real-time interfaces
    """
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        mcp_config_path: str = "mcp.json",
        agent_config: Optional[AgentConfig] = None
    ):
        super().__init__(
            model_name=model_name,
            system_prompt="You are a helpful AI assistant with access to various tools and a knowledge base.",
            mcp_config_path=mcp_config_path,
            agent_config=agent_config
        )
    
    async def run(self, query: str, image_paths: Optional[Union[str, Path, list]] = None):
        """Run a streaming chat query.
        
        Yields streaming events for real-time UI updates.
        """
        async for event in self.run_query_stream(query, image_paths):
            yield event
