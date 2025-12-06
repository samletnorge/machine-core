"""RAG-enabled chat agent with Neo4j knowledge graph."""

from core.agent_base import BaseAgent
from loguru import logger


class RAGChatAgent(BaseAgent):
    """RAG-enabled chat agent with Neo4j knowledge graph.
    
    Chat agent with access to company knowledge base.
    Perfect for: Customer support, internal Q&A, knowledge retrieval
    """
    
    def __init__(self):
        super().__init__(
            system_prompt="""You are a knowledgeable assistant with access to our company knowledge graph.
Use the Neo4j tools to retrieve relevant information before answering.
Always cite your sources and be accurate.""",
            mcp_config_path="mcp_neo4j.json"  # Neo4j memory tools
        )
    
    async def run(self, query: str):
        """Run RAG chat query with streaming."""
        logger.info(f"RAG chat query: {query}")
        
        # Stream response with RAG
        async for event in self.run_query_stream(query):
            # The agent will automatically use Neo4j tools for retrieval
            yield event
