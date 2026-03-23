"""Base agent infrastructure and execution patterns.

This module defines:
- AgentCore: Core infrastructure (MCP tools, model, validation)
- BaseAgent: Abstract base for all agent types with execution patterns
"""

from __future__ import annotations
from typing import Optional, List
from pydantic_ai import Agent, Tool
from pydantic_ai.usage import RequestUsage
from loguru import logger


class AgentCore:
    """Core agent infrastructure - handles MCP setup, model config, validation.

    This is the low-level infrastructure that all agents share:
    - MCP toolset loading and validation
    - Model/provider configuration
    - Embedding backend
    - Agent instance creation

    Supports two tool modes:
    - MCP toolsets: loaded from mcp.json (original pattern)
    - Dynamic tools: pydantic-ai Tool objects passed directly (new pattern)
    - Both: combine MCP toolsets + dynamic tools

    Don't subclass this directly - use BaseAgent instead.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        tools_urls: Optional[list] = None,
        tools: Optional[List[Tool]] = None,
        mcp_config_path: str = "mcp.json",
        system_prompt: str = "",
        agent_config: Optional["AgentConfig"] = None,
    ):
        """Initialize core agent infrastructure.

        Args:
            model_name: Override model from config
            tools_urls: List of MCP server configs
            tools: List of pydantic-ai Tool objects (alternative to MCP toolsets).
                   When provided, these are passed directly to the Agent.
                   Can be combined with MCP toolsets.
            mcp_config_path: Path to mcp.json (ignored if tools_urls is provided
                            or if tools is provided without MCP)
            system_prompt: System prompt for the agent
            agent_config: AgentConfig instance for runtime configuration.
                         If None, loads from environment variables.
        """
        from .config import AgentConfig

        # Use provided config or load from environment
        if agent_config is None:
            agent_config = AgentConfig.from_env()

        self.agent_config = agent_config
        self.system_prompt = system_prompt

        # |----------------------------------------------------------|
        # |-----------------------Set up tools-----------------------|
        # |----------------------------------------------------------|
        # Dynamic tools (pydantic-ai Tool objects)
        self.tools = tools or []

        # MCP toolsets: skip loading if only dynamic tools are provided
        self.toolsets = []
        self.validation_warnings = []

        if tools and not tools_urls:
            # Pure dynamic tools mode: skip MCP entirely
            logger.info(f"Using {len(self.tools)} dynamic tool(s), skipping MCP setup")
        else:
            # MCP mode (original behavior) or hybrid mode
            from .mcp_setup import (
                load_mcp_servers_from_config,
                setup_mcp_toolsets,
                validate_and_fix_toolsets,
            )

            if tools_urls is None:
                tools_urls = load_mcp_servers_from_config(mcp_config_path)

            self.toolsets = setup_mcp_toolsets(
                tools_urls,
                timeout=self.agent_config.timeout,
                max_retries=self.agent_config.max_tool_retries,
                allow_sampling=self.agent_config.allow_sampling,
            )

            # Validate toolsets
            try:
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                    logger.info(
                        "Running toolset validation in existing event loop context"
                    )
                    import concurrent.futures

                    def validate_in_thread():
                        """Validate toolsets in a separate thread with its own event loop."""
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            result = new_loop.run_until_complete(
                                validate_and_fix_toolsets(self.toolsets)
                            )
                            return result
                        finally:
                            new_loop.close()

                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=1
                    ) as executor:
                        future = executor.submit(validate_in_thread)
                        self.toolsets, self.validation_warnings = future.result(
                            timeout=30
                        )
                        logger.info(f"Validated {len(self.toolsets)} toolset(s)")

                except RuntimeError:
                    # No running loop, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        self.toolsets, self.validation_warnings = (
                            loop.run_until_complete(
                                validate_and_fix_toolsets(self.toolsets)
                            )
                        )
                        logger.info(f"Validated {len(self.toolsets)} toolset(s)")
                    finally:
                        loop.close()
            except Exception as e:
                logger.warning(f"Could not validate toolsets: {e}", exc_info=True)

        # |----------------------------------------------------------|
        # |-----------------------Set up model-----------------------|
        # |----------------------------------------------------------|
        from model_providers import get_llm_provider, LLMProviderConfig
        from model_providers import get_embedding_provider, EmbeddingProviderConfig

        cfg = LLMProviderConfig.from_env()
        if model_name and model_name != cfg.model_name:
            cfg.model_name = model_name
        resolved = get_llm_provider(cfg)

        # model-providers now returns a fully-constructed pydantic-ai model
        # (OpenAIChatModel, GoogleModel, or AnthropicModel) with settings baked in.
        self.model = resolved.model
        self.provider_type = resolved.provider_type

        # |----------------------------------------------------------|
        # |-------------------Set up embedding backend---------------|
        # |----------------------------------------------------------|
        try:
            emb_cfg = EmbeddingProviderConfig.from_env()
            resolved_embedding = get_embedding_provider(emb_cfg)
            self.embedding = resolved_embedding.provider
            self.embedding_model_name = resolved_embedding.model_name
        except Exception as e:
            logger.warning(f"Embedding backend unavailable: {e}")
            self.embedding = None
            self.embedding_model_name = None

        # |----------------------------------------------------------|
        # |-----------------------Create agent-----------------------|
        # |----------------------------------------------------------|
        self._build_agent()

        # Print total tools loaded
        tool_count = len(self.tools)
        toolset_count = len(self.toolsets)
        if tool_count and toolset_count:
            print(f"Total tools: {tool_count} dynamic + {toolset_count} MCP toolset(s)")
        elif tool_count:
            print(f"Total tools: {tool_count} dynamic tool(s)")
        else:
            print(f"Total toolsets: {toolset_count}")

        # Validate tools after agent creation
        self._validate_agent_tools()

    def _build_agent(self):
        """Build the pydantic-ai Agent from current model, tools, and toolsets."""
        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            toolsets=self.toolsets,
            system_prompt=self.system_prompt,
            retries=self.agent_config.max_tool_retries,
        )
        self.usage = RequestUsage()
        self.message_history = []

    def rebuild_agent(
        self,
        tools: Optional[List[Tool]] = None,
        system_prompt: Optional[str] = None,
        retries: Optional[int] = None,
    ):
        """Recreate the agent with new tools and/or system prompt.

        Reuses the same model and MCP toolsets. Useful for per-request
        tool sets (e.g., RAG-filtered tools that change per query).

        Args:
            tools: New list of dynamic tools. If None, keeps existing self.tools.
            system_prompt: New system prompt. If None, keeps existing.
            retries: Override retry count. If None, uses agent_config default.
        """
        if tools is not None:
            self.tools = tools
        if system_prompt is not None:
            self.system_prompt = system_prompt

        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            toolsets=self.toolsets,
            system_prompt=self.system_prompt,
            retries=retries or self.agent_config.max_tool_retries,
        )
        self.usage = RequestUsage()
        # Preserve message_history across rebuilds (caller can reset if needed)
        logger.info(
            f"Agent rebuilt with {len(self.tools)} dynamic tool(s) "
            f"and {len(self.toolsets)} MCP toolset(s)"
        )

    def _validate_agent_tools(self):
        """Validate tools in the created agent."""
        try:
            if hasattr(self.agent, "_function_tools") and self.agent._function_tools:
                issues_found = []

                for tool_name, tool_def in self.agent._function_tools.items():
                    logger.debug(f"Validating agent tool: {tool_name}")

                    if hasattr(tool_def, "parameters_json_schema"):
                        schema = tool_def.parameters_json_schema
                        logger.debug(f"Tool {tool_name} schema: {schema}")

                        if isinstance(schema, dict) and "properties" in schema:
                            for prop_name, prop_def in schema["properties"].items():
                                if "type" not in prop_def or not prop_def["type"]:
                                    issues_found.append(
                                        f"{tool_name}.{prop_name}: missing/empty type"
                                    )
                                elif (
                                    isinstance(prop_def["type"], list)
                                    and len(prop_def["type"]) == 0
                                ):
                                    issues_found.append(
                                        f"{tool_name}.{prop_name}: empty type array"
                                    )

                if issues_found:
                    logger.error(
                        f"⚠️  WARNING: Agent has tools with schema issues:\n  "
                        + "\n  ".join(issues_found)
                        + "\n  These WILL cause crashes with some LLM models (e.g., gpt-oss template bug)!"
                        "\n  Fix: Update MCP servers to use concrete types (str) instead of Optional[str]"
                        "\n  Consider using a different model or fixing the MCP server."
                    )
                else:
                    logger.info("✓ All agent tools passed schema validation")
            else:
                logger.debug("No function tools found in agent to validate")
        except Exception as e:
            logger.warning(f"Could not validate agent tools: {e}")

    def get_validation_warnings(self) -> list[str]:
        """Get validation warnings from MCP server initialization."""
        return self.validation_warnings
