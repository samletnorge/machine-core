"""Memory master agent for knowledge graph maintenance."""

import asyncio
from core.agent_base import BaseAgent
from loguru import logger


class MemoryMasterAgent(BaseAgent):
    """Memory master that maintains knowledge graph.
    
    Reads chats, extracts entities/relations, updates knowledge graph.
    Perfect for: Knowledge extraction, graph maintenance, memory consolidation
    """
    
    def __init__(self):
        super().__init__(
            system_prompt="""You are a knowledge graph maintainer.
Extract entities, relationships, and facts from conversations.
Update the Neo4j knowledge graph with new information.
Identify connections between existing knowledge.""",
            mcp_config_path="mcp_neo4j.json"
        )
    
    async def run(self):
        """Process conversations and update knowledge graph."""
        logger.info("Memory master started")
        
        while True:
            try:
                # Get unprocessed conversations
                conversations = await self._get_unprocessed_chats()
                
                if not conversations:
                    logger.info("No new conversations to process")
                    break
                
                for conv in conversations:
                    logger.info(f"Processing conversation: {conv['id']}")
                    
                    # Extract knowledge
                    result = await self.run_query(
                        f"""Analyze this conversation and extract:
1. Entities (people, places, concepts)
2. Relationships between entities
3. Key facts and information

Conversation: {conv['text']}

Then update the knowledge graph using the Neo4j tools."""
                    )
                    
                    # Mark as processed
                    await self._mark_processed(conv['id'])
                
                # Wait before next batch
                await asyncio.sleep(300)  # 5 minutes
                
            except Exception as e:
                logger.error(f"Error processing conversations: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def _get_unprocessed_chats(self):
        """Get conversations that haven't been processed."""
        # TODO: Query your chat DB
        return []
    
    async def _mark_processed(self, conv_id: str):
        """Mark conversation as processed."""
        # TODO: Update your DB
        pass
    
    async def cleanup(self):
        """Cleanup before shutdown."""
        logger.info("Memory master shutting down")
        # Close any open connections
        await super().cleanup()
