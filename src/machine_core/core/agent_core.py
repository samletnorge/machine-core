"""Base agent infrastructure and execution patterns.

This module defines:
- AgentCore: Core infrastructure (MCP tools, model, validation)
- BaseAgent: Abstract base for all agent types with execution patterns
"""

from __future__ import annotations
from typing import Optional
from pydantic_ai import Agent
from pydantic_ai.usage import RequestUsage
from loguru import logger


class AgentCore:
    """Core agent infrastructure - handles MCP setup, model config, validation.

    This is the low-level infrastructure that all agents share:
    - MCP toolset loading and validation
    - Model/provider configuration
    - Embedding backend
    - Agent instance creation

    Don't subclass this directly - use BaseAgent instead.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        tools_urls: Optional[list] = None,
        mcp_config_path: str = "mcp.json",
        system_prompt: str = "",
        agent_config: Optional["AgentConfig"] = None,
    ):
        """Initialize core agent infrastructure.

        Args:
            model_name: Override model from config
            tools_urls: List of MCP server configs
            mcp_config_path: Path to mcp.json
            system_prompt: System prompt for the agent
            agent_config: AgentConfig instance for runtime configuration.
                         If None, loads from environment variables.
        """
        from .config import AgentConfig

        # Use provided config or load from environment
        if agent_config is None:
            agent_config = AgentConfig.from_env()

        self.agent_config = agent_config

        from .mcp_setup import (
            load_mcp_servers_from_config,
            setup_mcp_toolsets,
            validate_and_fix_toolsets,
        )

        # |----------------------------------------------------------|
        # |-----------------------Set up tools-----------------------|
        # |----------------------------------------------------------|
        if tools_urls is None:
            tools_urls = load_mcp_servers_from_config(mcp_config_path)

        self.toolsets = setup_mcp_toolsets(
            tools_urls,
            timeout=self.agent_config.timeout,
            max_retries=self.agent_config.max_tool_retries,
            allow_sampling=self.agent_config.allow_sampling,
        )

        # Validate toolsets
        self.validation_warnings = []
        try:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                # Even in a running loop, we need to validate the toolsets
                # Use asyncio.run in a thread if necessary
                logger.info("Running toolset validation in existing event loop context")
                import concurrent.futures
                import threading

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

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(validate_in_thread)
                    self.toolsets, self.validation_warnings = future.result(timeout=30)
                    logger.info(f"Validated {len(self.toolsets)} toolset(s)")

            except RuntimeError:
                # No running loop, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    self.toolsets, self.validation_warnings = loop.run_until_complete(
                        validate_and_fix_toolsets(self.toolsets)
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
        self.agent = Agent(
            model=self.model,
            toolsets=self.toolsets,
            system_prompt=system_prompt,
            retries=self.agent_config.max_tool_retries,
        )
        self.usage = RequestUsage()
        self.message_history = []

        # Print total tools loaded
        print(f"📦 Total toolsets: {len(self.toolsets)}")

        # Validate tools after agent creation
        self._validate_agent_tools()

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
