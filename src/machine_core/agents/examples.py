"""Example usage of different agent types.

This module demonstrates how to use the various agent implementations.
Import agents from their individual modules or from agents/__init__.py
"""

import asyncio
from agents import (
    ChatAgent,
    CLIAgent,
    ReceiptProcessorAgent,
    TwitterBotAgent,
    RAGChatAgent,
    MemoryMasterAgent,
)


# Example: Run an agent
if __name__ == "__main__":
    import asyncio
    
    async def main():
        # Example 1: Chat agent
        chat_agent = ChatAgent()
        async for event in chat_agent.run("What is the capital of France?"):
            if event['type'] == 'text_delta':
                print(event['content'], end='', flush=True)
        print()
        
        # Example 2: CLI agent
        cli_agent = CLIAgent()
        result = await cli_agent.run("What is 2+2?")
        print(f"Result: {result.output if hasattr(result, 'output') else result}")
        
        # Example 3: Receipt processor (runs continuously)
        # receipt_agent = ReceiptProcessorAgent()
        # await receipt_agent.run()
        
        # Example 4: Twitter bot (runs on schedule)
        # twitter_agent = TwitterBotAgent()
        # await twitter_agent.run()
        
        # Example 5: Memory master (runs continuously)
        # memory_agent = MemoryMasterAgent()
        # await memory_agent.run()
    
    asyncio.run(main())
