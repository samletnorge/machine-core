"""Base agent infrastructure and execution patterns.

This module defines:
- AgentCore: Core infrastructure (MCP tools, model, validation)
- BaseAgent: Abstract base for all agent types with execution patterns
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union
from pydantic_ai import ImageUrl
from loguru import logger
from .agent_core import AgentCore

class BaseAgent(AgentCore, ABC):
    """Base class for all agent types.
    
    Combines core infrastructure (from AgentCore) with execution patterns.
    
    Usage:
        class MyAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    system_prompt="You are a helpful assistant",
                    mcp_config_path="mcp.json"
                )
            
            async def run(self, query: str):
                # Use self.run_query() or self.run_query_stream()
                result = await self.run_query(query)
                return result
    """
    
    @abstractmethod
    async def run(self, *args, **kwargs):
        """Main execution loop for the agent.
        
        Override this in subclasses to define agent-specific behavior.
        Use self.run_query() or self.run_query_stream() within this method.
        """
        pass
    
    async def cleanup(self):
        """Cleanup resources before shutdown.
        
        Override if your agent needs to clean up resources (close connections, save state, etc.)
        """
        pass
    
    # ========================================================================
    # Execution Patterns - Use these in your run() method
    # ========================================================================
    
    async def run_query(
        self,
        query: str,
        image_paths: Optional[Union[str, Path, list[Union[str, Path]]]] = None
    ) -> dict:
        """Execute a single query with retry logic.
        
        Use this for:
        - CLI agents
        - Cron jobs
        - One-shot tasks
        - Non-streaming contexts
        
        Returns:
            dict with agent result
        """
        from .config import Config
        agent_config = Config.Agent()
        
        try:
            if not query:
                logger.error("No query provided.")
                return {"output": "Error: No query provided."}
            
            # Process images if provided
            processed_images = []
            if image_paths:
                if not isinstance(image_paths, list):
                    image_paths = [image_paths]
                
                for img_path in image_paths:
                    try:
                        data_url = await self._process_image(img_path)
                        if data_url:
                            processed_images.append(data_url)
                    except Exception as e:
                        logger.error(f"Failed to process image {img_path}: {e}")
                        return {"output": f"Error: Failed to process image {img_path}: {e}"}
            
            logger.info(f"Processed {len(processed_images)} image(s)")
            
            # Run with retries
            max_retries = agent_config.MAX_ITERATIONS
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    # Build message content
                    if processed_images:
                        message_content = [query] + [ImageUrl(url=img) for img in processed_images]
                    else:
                        message_content = query
                    
                    # Execute
                    result = await self.agent.run(message_content, message_history=self.message_history)
                    if result:
                        self.usage = result.usage()
                        self.message_history = result.all_messages()
                        return result
                    else:
                        logger.warning(f"Empty result on attempt {retry_count + 1}")
                        retry_count += 1
                except Exception as inner_e:
                    logger.warning(f"Error on attempt {retry_count + 1}: {inner_e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        import asyncio
                        await asyncio.sleep(1)
            
            return {
                "output": "Error: Maximum retries reached. Some tools failed to respond properly."
            }
        
        except Exception as e:
            error_msg = f"Critical error during query execution: {str(e)}"
            logger.error(error_msg)
            return {"output": error_msg}
    
    async def run_query_stream(
        self,
        query: str,
        image_paths: Optional[Union[str, Path, list[Union[str, Path]]]] = None
    ):
        """Execute a query with streaming support.
        
        Use this for:
        - Chat interfaces
        - Real-time UIs
        - Progress monitoring
        - Thinking/reasoning display
        
        Yields:
            dict with keys:
                - 'type': 'text_delta' | 'thinking_delta' | 'tool_call' | 'tool_result' | 'final' | 'error'
                - 'content': the actual content
                - 'tool_name': (if type is tool_call/tool_result)
                - 'tool_args': (if type is tool_call)
        """
        try:
            if not query:
                logger.error("No query provided.")
                yield {"type": "error", "content": "Error: No query provided."}
                return
            
            # Process images
            processed_images = []
            if image_paths:
                if not isinstance(image_paths, list):
                    image_paths = [image_paths]
                
                for img_path in image_paths:
                    try:
                        data_url = await self._process_image(img_path)
                        if data_url:
                            processed_images.append(data_url)
                    except Exception as e:
                        logger.error(f"Failed to process image {img_path}: {e}")
                        yield {"type": "error", "content": f"Error: Failed to process image {img_path}: {e}"}
                        return
            
            logger.info(f"Processed {len(processed_images)} image(s)")
            
            # Build message content
            if processed_images:
                message_content = [query] + [ImageUrl(url=img) for img in processed_images]
            else:
                message_content = query
            
            # Stream the response
            full_text = ""
            full_thinking = ""
            
            try:
                from pydantic_ai.messages import (
                    ThinkingPartDelta,
                    TextPartDelta,
                    PartStartEvent,
                    PartDeltaEvent,
                    PartEndEvent,
                )
                from pydantic_ai import (
                    AgentRunResultEvent,
                    FunctionToolCallEvent,
                    FunctionToolResultEvent,
                    FinalResultEvent,
                )
                
                async for event in self.agent.run_stream_events(
                    message_content,
                    message_history=self.message_history
                ):
                    try:
                        if isinstance(event, AgentRunResultEvent):
                            self.usage = event.result.usage()
                            self.message_history = event.result.all_messages()
                            continue
                        
                        if isinstance(event, PartDeltaEvent):
                            if isinstance(event.delta, TextPartDelta):
                                text_chunk = event.delta.content_delta
                                if text_chunk:
                                    full_text += text_chunk
                                    yield {"type": "text_delta", "content": text_chunk}
                            
                            elif isinstance(event.delta, ThinkingPartDelta):
                                thinking_chunk = event.delta.content_delta
                                if thinking_chunk:
                                    full_thinking += thinking_chunk
                                    logger.debug(f"Streaming thinking delta: {len(thinking_chunk)} chars")
                                    yield {"type": "thinking_delta", "content": thinking_chunk}
                        
                        elif isinstance(event, FunctionToolCallEvent):
                            logger.debug(f"Tool call: {event.part.tool_name}")
                            yield {
                                "type": "tool_call",
                                "tool_name": event.part.tool_name,
                                "tool_args": event.part.args,
                            }
                        
                        elif isinstance(event, FunctionToolResultEvent):
                            try:
                                logger.debug(f"Tool result for {event.tool_call_id}")
                                result_content = getattr(event.result, 'content', str(event.result))
                                yield {
                                    "type": "tool_result",
                                    "tool_name": getattr(event, 'tool_name', 'unknown'),
                                    "content": result_content,
                                }
                            except Exception as tool_error:
                                logger.error(f"Error processing tool result: {tool_error}", exc_info=True)
                        
                        elif isinstance(event, FinalResultEvent):
                            logger.debug("Final result event received")
                        
                        elif isinstance(event, PartStartEvent):
                            logger.debug(f"Starting part {event.index}: {type(event.part).__name__}")
                        
                        elif isinstance(event, PartEndEvent):
                            logger.debug(f"Ending part {event.index}: {type(event.part).__name__}")
                        
                        else:
                            logger.debug(f"Unhandled event type: {type(event).__name__}")
                    
                    except Exception as event_error:
                        logger.error(f"Error processing event {type(event).__name__}: {event_error}", exc_info=True)
                        continue
                
                # Send final message
                yield {
                    "type": "final",
                    "content": full_text,
                    "thinking": full_thinking if full_thinking else None,
                    "usage": {
                        "input_tokens": self.usage.total_tokens if hasattr(self.usage, 'total_tokens') else 0,
                        "output_tokens": self.usage.total_tokens if hasattr(self.usage, 'total_tokens') else 0
                    }
                }
            
            except Exception as stream_error:
                logger.error(f"Stream error: {stream_error}", exc_info=True)
                yield {"type": "error", "content": str(stream_error)}
        
        except KeyError as e:
            error_msg = (
                f"KeyError during streaming: {str(e)}\n\n"
                "This often happens when:\n"
                "1. MCP server tools have malformed schemas (e.g., Optional[] types creating empty Type arrays)\n"
                "2. The LLM model template has bugs (e.g., gpt-oss template crashes on empty Type arrays)\n\n"
                "Solutions:\n"
                "- Fix the MCP server to use concrete types (str instead of Optional[str])\n"
                "- Use a different LLM model\n"
                "- Check the validation warnings above for specific tool schema issues"
            )
            logger.error(error_msg, exc_info=True)
            yield {"type": "error", "content": error_msg}
        except Exception as e:
            error_msg = f"Critical error during streaming: {str(e)}"
            logger.error(error_msg, exc_info=True)
            yield {"type": "error", "content": error_msg}
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    async def _process_image(self, image_path: Union[str, Path]) -> str:
        """Process an image path/URL and return a data URL."""
        import base64
        
        if not image_path:
            return None
        
        image_path = str(image_path)
        
        # Already a data URL
        if image_path.startswith("data:image/"):
            logger.info(f"Using provided data URL (first 100 chars): {image_path[:100]}...")
            return image_path
        
        # HTTP/HTTPS URL
        if image_path.startswith("http://") or image_path.startswith("https://"):
            logger.info(f"Fetching image from URL: {image_path}")
            try:
                import httpx
                async with httpx.AsyncClient() as http_client:
                    response = await http_client.get(image_path)
                    response.raise_for_status()
                    image_bytes = response.content
                    
                    content_type = response.headers.get('content-type', '')
                    if 'png' in content_type or image_path.endswith('.png'):
                        img_format = 'png'
                    elif 'jpeg' in content_type or 'jpg' in content_type or image_path.endswith(('.jpg', '.jpeg')):
                        img_format = 'jpeg'
                    elif 'gif' in content_type or image_path.endswith('.gif'):
                        img_format = 'gif'
                    elif 'webp' in content_type or image_path.endswith('.webp'):
                        img_format = 'webp'
                    else:
                        img_format = 'png'
                    
                    encoded_image = base64.b64encode(image_bytes).decode('utf-8')
                    data_url = f"data:image/{img_format};base64,{encoded_image}"
                    logger.info(f"Fetched and encoded image from URL")
                    return data_url
            except Exception as e:
                logger.error(f"Failed to fetch image: {e}")
                raise
        
        # Local file path
        try:
            image_path_obj = Path(image_path)
            if not image_path_obj.exists():
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            with open(image_path_obj, "rb") as f:
                encoded_image = base64.b64encode(f.read()).decode('utf-8')
            
            img_format = image_path_obj.suffix[1:] or 'png'
            data_url = f"data:image/{img_format};base64,{encoded_image}"
            logger.info(f"Encoded local image to base64")
            return data_url
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            raise
    
    async def get_server_info(self) -> list[dict]:
        """Get information about connected MCP servers and their tools."""
        from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP, MCPServerStdio
        
        server_info = []
        
        for toolset in self.toolsets:
            logger.info(f"Gathering info for toolset: {type(toolset).__name__}")
            info = {
                'server_type': type(toolset).__name__.replace('MCPServer', '').lower(),
                'server_id': None,
                'tools': []
            }
            
            if isinstance(toolset, MCPServerStdio):
                info['server_id'] = f"{toolset.command} {' '.join(toolset.args) if toolset.args else ''}"
            elif isinstance(toolset, (MCPServerSSE, MCPServerStreamableHTTP)):
                info['server_id'] = toolset.url
            
            try:
                tools = await toolset.list_tools()
                
                for tool in tools:
                    info['tools'].append({
                        'name': tool.name,
                        'description': tool.description or 'No description available'
                    })
                
                logger.info(f"Found {len(tools)} tools for {info['server_id']}")
            except Exception as e:
                logger.warning(f"Could not retrieve tools from {info['server_id']}: {e}")
                info['tools'] = [{'name': 'Error', 'description': str(e)}]
            
            server_info.append(info)
        
        return server_info
