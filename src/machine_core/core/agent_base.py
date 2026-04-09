"""Base agent infrastructure and execution patterns.

This module defines:
- AgentCore: Core infrastructure (MCP tools, model, validation)
- BaseAgent: Abstract base for all agent types with execution patterns
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union, Any
from pydantic_ai import ImageUrl, AgentRunResult
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

    def _reset_toolset_state(self):
        """Reset async state on all MCP toolsets for the current event loop.

        MCPServer objects cache an asyncio.Lock (_enter_lock) that is bound to
        the event loop that was active when the lock was created.  Callers like
        Streamlit create a fresh event loop for every request; without resetting,
        the old lock is invalid and causes 'Session terminated' errors.
        """
        for ts in self.toolsets:
            inner = getattr(ts, "wrapped_toolset", ts)
            if hasattr(inner, "__post_init__"):
                inner.__post_init__()

    async def _remove_bad_toolsets_and_rebuild(self, error) -> bool:
        """Inspect an MCP error, remove the offending toolset, and rebuild.

        Returns True if a toolset was removed and the agent was rebuilt,
        False if nothing could be done (caller should propagate the error).
        """
        if not self.toolsets:
            return False

        # Try to identify which server(s) failed by probing each one
        bad_toolsets = []
        for ts in self.toolsets:
            inner = getattr(ts, "wrapped_toolset", ts)
            if hasattr(inner, "__post_init__"):
                inner.__post_init__()
            try:
                async with ts:
                    pass  # connect + disconnect; just testing
            except Exception as probe_err:
                server_url = getattr(getattr(ts, "wrapped_toolset", ts), "url", str(ts))
                logger.warning(
                    f"MCP server {server_url} is unhealthy, removing: {probe_err}"
                )
                bad_toolsets.append(ts)

        if not bad_toolsets:
            return False

        remaining = [ts for ts in self.toolsets if ts not in bad_toolsets]
        if len(remaining) == len(self.toolsets):
            return False  # nothing removed

        logger.info(
            f"Removed {len(bad_toolsets)} unhealthy MCP server(s), "
            f"{len(remaining)} remaining"
        )
        self.rebuild_agent(toolsets=remaining)
        # Reset async state on the surviving toolsets
        self._reset_toolset_state()
        return True

    async def run_query(
        self,
        query: str,
        image_paths: Optional[Union[str, Path, list[Union[str, Path]]]] = None,
    ) -> Union[dict, AgentRunResult]:
        """Execute a single query with retry logic.

        Use this for:
        - CLI agents
        - Cron jobs
        - One-shot tasks
        - Non-streaming contexts

        Returns:
            AgentRunResult or dict with agent result
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
                        return {
                            "output": f"Error: Failed to process image {img_path}: {e}"
                        }

            logger.info(f"Processed {len(processed_images)} image(s)")

            # Build message content
            if processed_images:
                message_content = [query] + [
                    ImageUrl(url=img) for img in processed_images
                ]
            else:
                message_content = query

            # Execute with pydantic-ai's internal error handling
            # pydantic-ai has its own retry logic for tool calls, configured via the 'retries' parameter
            # We should let it handle tool errors and pass them to the LLM for adjustment
            # Only catch critical errors that prevent execution entirely
            try:
                self._reset_toolset_state()
                result = await self.agent.run(
                    message_content, message_history=self.message_history
                )
                if result:
                    self.usage = result.usage()
                    self.message_history = result.all_messages()
                    return result
                else:
                    logger.warning("Empty result from agent execution")
                    return {"output": "Error: Agent returned empty result."}
            except Exception as e:
                # If an MCP server is down, remove it and retry once
                error_str = str(e).lower()
                is_mcp_error = any(
                    indicator in error_str
                    for indicator in [
                        "session terminated",
                        "mcperror",
                        "connection closed",
                    ]
                )
                if is_mcp_error and await self._remove_bad_toolsets_and_rebuild(e):
                    logger.info("Retrying query after removing unhealthy MCP server(s)")
                    try:
                        result = await self.agent.run(
                            message_content,
                            message_history=self.message_history,
                        )
                        if result:
                            self.usage = result.usage()
                            self.message_history = result.all_messages()
                            return result
                    except Exception as retry_err:
                        logger.error(f"Retry also failed: {retry_err}")
                        return {"output": f"Error: {str(retry_err)}"}

                logger.error(f"Critical error during agent execution: {e}")
                return {"output": f"Error: {str(e)}"}

        except Exception as e:
            error_msg = f"Critical error during query execution: {str(e)}"
            logger.error(error_msg)
            return {"output": error_msg}

    async def run_query_stream(
        self,
        query: str,
        image_paths: Optional[Union[str, Path, list[Union[str, Path]]]] = None,
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
                        yield {
                            "type": "error",
                            "content": f"Error: Failed to process image {img_path}: {e}",
                        }
                        return

            logger.info(f"Processed {len(processed_images)} image(s)")

            # Build message content
            if processed_images:
                message_content = [query] + [
                    ImageUrl(url=img) for img in processed_images
                ]
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

                self._reset_toolset_state()
                async for event in self.agent.run_stream_events(
                    message_content, message_history=self.message_history
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
                                    logger.debug(
                                        f"Streaming thinking delta: {len(thinking_chunk)} chars"
                                    )
                                    yield {
                                        "type": "thinking_delta",
                                        "content": thinking_chunk,
                                    }

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
                                result_content = getattr(
                                    event.result, "content", str(event.result)
                                )
                                yield {
                                    "type": "tool_result",
                                    "tool_name": getattr(event, "tool_name", "unknown"),
                                    "content": result_content,
                                }
                            except Exception as tool_error:
                                logger.error(
                                    f"Error processing tool result: {tool_error}",
                                    exc_info=True,
                                )

                        elif isinstance(event, FinalResultEvent):
                            logger.debug("Final result event received")

                        elif isinstance(event, PartStartEvent):
                            logger.debug(
                                f"Starting part {event.index}: {type(event.part).__name__}"
                            )

                        elif isinstance(event, PartEndEvent):
                            logger.debug(
                                f"Ending part {event.index}: {type(event.part).__name__}"
                            )

                        else:
                            logger.debug(
                                f"Unhandled event type: {type(event).__name__}"
                            )

                    except Exception as event_error:
                        logger.error(
                            f"Error processing event {type(event).__name__}: {event_error}",
                            exc_info=True,
                        )
                        continue

                # Send final message
                yield {
                    "type": "final",
                    "content": full_text,
                    "thinking": full_thinking if full_thinking else None,
                    "usage": {
                        "input_tokens": self.usage.total_tokens
                        if hasattr(self.usage, "total_tokens")
                        else 0,
                        "output_tokens": self.usage.total_tokens
                        if hasattr(self.usage, "total_tokens")
                        else 0,
                    },
                }

            except Exception as stream_error:
                # Extract actual error from potential TaskGroup wrapper
                actual_error = stream_error
                error_traceback = ""

                import traceback
                import sys

                # Handle ExceptionGroup (from TaskGroup)
                if hasattr(stream_error, "exceptions") and isinstance(
                    getattr(stream_error, "exceptions"), (list, tuple)
                ):
                    exceptions_list = getattr(stream_error, "exceptions")
                    logger.debug(
                        f"Caught ExceptionGroup with {len(exceptions_list)} exceptions"
                    )
                    for idx, exc in enumerate(exceptions_list):
                        logger.error(
                            f"  Sub-exception {idx}: {type(exc).__name__}: {exc}"
                        )
                        try:
                            tb_lines = traceback.format_exception(
                                type(exc), exc, exc.__traceback__
                            )
                            error_traceback += f"\n\n--- Sub-exception {idx} Traceback ---\n{''.join(tb_lines)}"
                        except:
                            error_traceback += (
                                f"\n\n--- Sub-exception {idx} ---\n{str(exc)}"
                            )
                    actual_error = (
                        exceptions_list[0] if exceptions_list else stream_error
                    )

                error_msg = (
                    f"Stream error: {type(actual_error).__name__}: {str(actual_error)}"
                )
                logger.error(error_msg)
                if error_traceback:
                    logger.error(f"Full error details:{error_traceback}")
                else:
                    logger.error(f"Stream traceback:", exc_info=True)

                # If this looks like an MCP connection error, try to remove
                # the bad server(s) and retry the stream once.
                actual_str = str(actual_error).lower()
                is_mcp_error = any(
                    indicator in actual_str
                    for indicator in [
                        "session terminated",
                        "mcperror",
                        "connection closed",
                    ]
                )
                if is_mcp_error and await self._remove_bad_toolsets_and_rebuild(
                    actual_error
                ):
                    logger.info(
                        "Retrying stream after removing unhealthy MCP server(s)"
                    )
                    try:
                        self._reset_toolset_state()
                        async for event in self.agent.run_stream_events(
                            message_content,
                            message_history=self.message_history,
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
                                            yield {
                                                "type": "text_delta",
                                                "content": text_chunk,
                                            }
                                    elif isinstance(event.delta, ThinkingPartDelta):
                                        thinking_chunk = event.delta.content_delta
                                        if thinking_chunk:
                                            full_thinking += thinking_chunk
                                            yield {
                                                "type": "thinking_delta",
                                                "content": thinking_chunk,
                                            }
                                elif isinstance(event, FunctionToolCallEvent):
                                    yield {
                                        "type": "tool_call",
                                        "tool_name": event.part.tool_name,
                                        "tool_args": event.part.args,
                                    }
                                elif isinstance(event, FunctionToolResultEvent):
                                    result_content = getattr(
                                        event.result,
                                        "content",
                                        str(event.result),
                                    )
                                    yield {
                                        "type": "tool_result",
                                        "tool_name": getattr(
                                            event, "tool_name", "unknown"
                                        ),
                                        "content": result_content,
                                    }
                            except Exception:
                                continue

                        yield {
                            "type": "final",
                            "content": full_text,
                            "thinking": full_thinking or None,
                            "usage": {
                                "input_tokens": self.usage.total_tokens
                                if hasattr(self.usage, "total_tokens")
                                else 0,
                                "output_tokens": self.usage.total_tokens
                                if hasattr(self.usage, "total_tokens")
                                else 0,
                            },
                        }
                        return  # retry succeeded, skip the error yield
                    except Exception as retry_err:
                        logger.error(f"Retry stream also failed: {retry_err}")
                        yield {
                            "type": "error",
                            "content": f"Stream error (retry failed): {retry_err}",
                        }
                        return

                yield {"type": "error", "content": error_msg}

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
    # Iteration Pattern - Step-by-step execution with custom processing
    # ========================================================================

    async def run_query_iter(
        self,
        query: str,
    ):
        """Execute a query using agent.iter() for step-by-step control.

        Use this for:
        - Per-step logging (tool calls, tool results, retries)
        - Custom processing of each agent step
        - Fine-grained monitoring of agent execution
        - Agents with dynamic tools that need detailed observability

        This is an async generator that yields (node, step_num) tuples.
        After the generator is exhausted, access the result via the returned value.

        Example:
            result = None
            async for node, step_num in self.run_query_iter(query):
                if isinstance(node, CallToolsNode):
                    # log tool calls
                    pass
            # result is available via agent_run.result after iteration

        Yields:
            Tuple of (node, step_num) where node is a pydantic-ai graph node
            and step_num is the 1-indexed step number.

        Returns:
            The agent run result (accessible after iteration completes).
        """
        try:
            async with self.agent.iter(query) as agent_run:
                step = 0
                async for node in agent_run:
                    step += 1
                    yield node, step

                # Update usage and history from the completed run
                if agent_run.result:
                    result = agent_run.result
                    if hasattr(result, "usage"):
                        self.usage = result.usage()
                    if hasattr(result, "all_messages"):
                        self.message_history = result.all_messages()

        except Exception as e:
            logger.error(f"Error during agent iteration: {e}", exc_info=True)
            raise

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _process_image(self, image_path: Union[str, Path]) -> Optional[str]:
        """Process an image path/URL and return a data URL.

        Delegates to FileProcessor.prepare_for_vlm() for the actual work.
        """
        from .file_processor import FileProcessor

        return await FileProcessor.prepare_for_vlm(image_path)

    async def get_server_info(self) -> list[dict]:
        """Get information about connected MCP servers and their tools."""
        from pydantic_ai.mcp import (
            MCPServerSSE,
            MCPServerStreamableHTTP,
            MCPServerStdio,
        )

        self._reset_toolset_state()
        server_info = []

        for toolset in self.toolsets:
            # Unwrap ToolFilterWrapper to get at the actual MCP server
            inner = getattr(toolset, "wrapped_toolset", toolset)

            logger.info(f"Gathering info for toolset: {type(inner).__name__}")
            info = {
                "server_type": type(inner).__name__.replace("MCPServer", "").lower(),
                "server_id": None,
                "tools": [],
            }

            if isinstance(inner, MCPServerStdio):
                info["server_id"] = (
                    f"{inner.command} {' '.join(inner.args) if inner.args else ''}"
                )
            elif isinstance(inner, (MCPServerSSE, MCPServerStreamableHTTP)):
                info["server_id"] = inner.url

            try:
                tools = await toolset.list_tools()

                for tool in tools:
                    info["tools"].append(
                        {
                            "name": tool.name,
                            "description": tool.description
                            or "No description available",
                        }
                    )

                logger.info(f"Found {len(tools)} tools for {info['server_id']}")
            except Exception as e:
                logger.warning(
                    f"Could not retrieve tools from {info['server_id']}: {e}"
                )
                info["tools"] = [{"name": "Error", "description": str(e)}]

            server_info.append(info)

        return server_info
