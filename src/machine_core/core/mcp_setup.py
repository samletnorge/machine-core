"""MCP server configuration and validation utilities."""

import json
import os
from pathlib import Path
from loguru import logger
from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP, MCPServerStdio
from pydantic_ai.toolsets import AbstractToolset


class ToolFilterWrapper(AbstractToolset):
    """Wraps an MCP toolset and filters out problematic tools on-the-fly.

    This allows the MCP server to still load and function with valid tools,
    even if some tools have malformed schemas.
    """

    def __init__(self, wrapped_toolset, problematic_tool_names: set | None = None):
        """Initialize the wrapper.

        Args:
            wrapped_toolset: The MCP toolset to wrap
            problematic_tool_names: Set of tool names to filter out
        """
        self.wrapped_toolset = wrapped_toolset
        self.problematic_tool_names = problematic_tool_names or set()
        self._original_class_name = wrapped_toolset.__class__.__name__

    @property
    def id(self) -> str:
        """Return the ID of the wrapped toolset."""
        # Get ID from wrapped toolset if it has one
        try:
            wrapped_id = self.wrapped_toolset.id
            if wrapped_id:
                return f"filtered-{wrapped_id}"
        except:
            pass

        # Fallback to class name
        return f"filtered-{self._original_class_name}"

    def __getattr__(self, name):
        """Delegate all other attributes to the wrapped toolset."""
        return getattr(self.wrapped_toolset, name)

    async def get_tools(self, ctx) -> dict:
        """Get tools, filtering out problematic ones.

        Args:
            ctx: The run context

        Returns:
            Dict of tool name to ToolsetTool
        """
        tools_dict = await self.wrapped_toolset.get_tools(ctx)

        # Filter out problematic tools from the dict
        if isinstance(tools_dict, dict):
            filtered_tools = {
                name: tool
                for name, tool in tools_dict.items()
                if name not in self.problematic_tool_names
            }
            if len(filtered_tools) < len(tools_dict):
                filtered_count = len(tools_dict) - len(filtered_tools)
                logger.warning(
                    f"Filtered out {filtered_count} problematic tool(s) from "
                    f"{self._original_class_name}: {self.problematic_tool_names}"
                )
            return filtered_tools

        # Fallback if not a dict
        return tools_dict

    async def call_tool(self, name: str, tool_args: dict, ctx, tool):
        """Call a tool, rejecting filtered-out tools.

        Args:
            name: Name of the tool to call
            tool_args: Input parameters for the tool
            ctx: The run context
            tool: The tool definition

        Returns:
            The tool result

        Raises:
            ValueError: If the tool is filtered out
        """
        if name in self.problematic_tool_names:
            error_msg = f"Tool '{name}' has been filtered out due to schema issues"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Delegate to the wrapped toolset with correct signature
        return await self.wrapped_toolset.call_tool(name, tool_args, ctx, tool)


async def validate_and_fix_toolsets(toolsets: list) -> tuple[list, list[str]]:
    """Validate MCP toolsets and filter problematic tools.

    This prevents crashes from malformed tool schemas by filtering out individual
    problematic tools, while keeping the MCP server and other valid tools operational.

    Args:
        toolsets: List of MCP toolset objects

    Returns:
        Tuple of (validated_toolsets_with_filters, warning_messages)
    """
    validated_toolsets = []
    all_warnings = []

    for toolset in toolsets:
        try:
            # Get tools from the toolset to validate their schemas
            if hasattr(toolset, "list_tools"):
                tools_response = await toolset.list_tools()
                logger.debug(
                    f"tools_response type: {type(tools_response)}, value: {tools_response}"
                )

                # Handle different response formats
                if hasattr(tools_response, "tools"):
                    tools = tools_response.tools
                elif isinstance(tools_response, list):
                    tools = tools_response
                else:
                    tools = []

                logger.debug(
                    f"Validating {len(tools)} tools from {toolset.__class__.__name__}"
                )

                # Check each tool's schema and collect problematic tool names
                problematic_tools = set()
                issues_found = []

                for tool in tools:
                    logger.debug(f"Checking tool: {tool.name}")
                    if hasattr(tool, "inputSchema") and tool.inputSchema:
                        schema = tool.inputSchema
                        logger.debug(f"Tool {tool.name} schema: {schema}")

                        # Check for properties with empty Type arrays
                        if "properties" in schema:
                            tool_has_issues = False
                            for prop_name, prop_def in schema["properties"].items():
                                logger.debug(f"  Property {prop_name}: {prop_def}")
                                # Check if type is missing or empty
                                if "type" not in prop_def or not prop_def["type"]:
                                    issues_found.append(
                                        f"  {tool.name}.{prop_name}: missing/empty type"
                                    )
                                    logger.debug(f"    ❌ Missing/empty type!")
                                    tool_has_issues = True
                                # Check if type is an empty array
                                elif (
                                    isinstance(prop_def["type"], list)
                                    and len(prop_def["type"]) == 0
                                ):
                                    issues_found.append(
                                        f"  {tool.name}.{prop_name}: empty type array"
                                    )
                                    logger.debug(f"    ❌ Empty type array!")
                                    tool_has_issues = True

                            if tool_has_issues:
                                problematic_tools.add(tool.name)
                    else:
                        logger.debug(f"Tool {tool.name} has no inputSchema")

                if problematic_tools:
                    # Wrap the toolset to filter out problematic tools
                    wrapped_toolset = ToolFilterWrapper(toolset, problematic_tools)
                    validated_toolsets.append(wrapped_toolset)

                    warning_msg = (
                        f"⚠️  Filtering problematic tools from {toolset.__class__.__name__}:\n"
                        + "\n".join(issues_found)
                        + "\n  These tools will be excluded from the available tools.\n"
                        "  Fix: Update the MCP server to use concrete types (str) instead of Optional[str]"
                    )
                    logger.warning(warning_msg)
                    all_warnings.append(warning_msg)
                else:
                    # Schema is valid, add the toolset as-is
                    logger.debug(
                        f"✓ Toolset {toolset.__class__.__name__} passed validation"
                    )
                    validated_toolsets.append(toolset)
            else:
                # If can't validate, add it anyway (might be a different toolset type)
                logger.debug(
                    f"Toolset {toolset.__class__.__name__} has no list_tools method, adding anyway"
                )
                validated_toolsets.append(toolset)

        except Exception as e:
            logger.error(
                f"Error validating toolset {toolset.__class__.__name__}: {e}",
                exc_info=True,
            )
            # Still add the toolset - it might work despite validation errors
            logger.info(f"Adding {toolset.__class__.__name__} despite validation error")
            validated_toolsets.append(toolset)
            warning_msg = f"⚠️  {toolset.__class__.__name__} could not be validated: {e}"
            logger.warning(warning_msg)
            all_warnings.append(warning_msg)

    return validated_toolsets, all_warnings


def load_mcp_servers_from_config(config_path: str = "mcp.json") -> list:
    """Load MCP server configurations from a JSON file.

    Expected format (VS Code style):
    {
      "servers": {
        "server-name": {
          "type": "http",  // or "sse" or "stdio"
          "url": "https://example.com/mcp"
        },
        "stdio-server": {
          "type": "stdio",
          "command": "uv",
          "args": ["run", "python", "path/to/server.py"]
        }
      },
      "inputs": []  // optional
    }

    Args:
        config_path: Path to the mcp.json configuration file

    Returns:
        List of MCPServerModel instances
    """
    from .config import MCPServerModel

    config_file = Path(config_path)

    if not config_file.exists():
        logger.warning(
            f"MCP config file not found at {config_path}, using empty server list"
        )
        return []

    try:
        with open(config_file, "r") as f:
            config_data = json.load(f)

        servers = []
        mcp_servers = config_data.get("servers", {})

        for server_name, server_config in mcp_servers.items():
            transport = server_config.get("type", "http")

            if transport == "stdio":
                # For stdio, construct command from 'command' and 'args' fields
                command = server_config.get("command", "")
                args = server_config.get("args", [])
                env = server_config.get("env", None)

                # If args exist, join command and args into a single command string
                if args:
                    full_command = " ".join([command] + args)
                    servers.append(
                        MCPServerModel(url=full_command, type="stdio", env=env)
                    )
                elif command:
                    servers.append(MCPServerModel(url=command, type="stdio", env=env))
                else:
                    logger.warning(f"Server {server_name} missing command, skipping")
            else:
                # For http/sse, use 'url' field
                url = server_config.get("url", "")
                if url:
                    servers.append(MCPServerModel(url=url, type=transport))
                else:
                    logger.warning(f"Server {server_name} missing url, skipping")

        logger.info(f"Loaded {len(servers)} MCP server(s) from {config_path}")
        return servers

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse {config_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error loading MCP config: {e}")
        return []


def setup_mcp_toolsets(
    tools_urls: list,
    timeout: float = 604800.0,
    max_retries: int = 15,
    allow_sampling: bool = False,
) -> list:
    """Set up MCP toolsets from server configurations.

    Args:
        tools_urls: List of MCP server configurations
        timeout: Timeout for MCP connections in seconds
        max_retries: Maximum retries for MCP operations
        allow_sampling: Allow sampling in MCP operations

    Returns:
        List of configured MCP toolsets
    """
    type_map = {"sse": MCPServerSSE, "http": MCPServerStreamableHTTP}
    toolsets = []

    for tool in tools_urls:
        try:
            if tool.type == "stdio":
                # Parse command and args from url field
                parts = tool.url.split()
                command = parts[0]
                args = parts[1:] if len(parts) > 1 else []

                # Prepare environment variables
                env_vars = os.environ.copy() if tool.env else None
                if env_vars and tool.env:
                    env_vars.update(tool.env)
                elif tool.env:
                    env_vars = tool.env

                stdio_tool = MCPServerStdio(
                    command,
                    args=args,
                    env=env_vars,
                    timeout=timeout,
                    read_timeout=timeout,
                    max_retries=max_retries,
                    allow_sampling=allow_sampling,
                )

                toolsets.append(stdio_tool)
                logger.info(
                    f"Added stdio tool: {command} {' '.join(args)} with env vars: {list(tool.env.keys()) if tool.env else 'none'}"
                )
            else:
                # Handle http and sse type tools
                if tool.type in type_map:
                    server = type_map[tool.type](
                        url=tool.url,
                        timeout=timeout,
                        max_retries=max_retries,
                        allow_sampling=allow_sampling,
                        read_timeout=timeout,
                    )
                    toolsets.append(server)
                    logger.info(f"Added {tool.type} tool: {tool.url}")
                else:
                    logger.warning(f"Unknown tool type: {tool.type}")
        except Exception as e:
            logger.error(f"Failed to setup tool {tool.url}: {e}")

    return toolsets
