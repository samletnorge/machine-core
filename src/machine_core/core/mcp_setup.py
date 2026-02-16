"""MCP server configuration and validation utilities."""

import json
import os
from pathlib import Path
from loguru import logger
from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP, MCPServerStdio


async def validate_and_fix_toolsets(toolsets: list) -> tuple[list, list[str]]:
    """Validate MCP toolsets and exclude tools with malformed schemas.
    
    This prevents crashes from malformed tool schemas, particularly:
    - Empty Type arrays in parameter definitions (causes gpt-oss template crash)
    - Missing required schema fields
    
    Tools with issues are automatically excluded to prevent crashes.
    
    Args:
        toolsets: List of MCP toolset objects
        
    Returns:
        Tuple of (validated_toolsets, warning_messages)
    """
    validated_toolsets = []
    all_warnings = []
    
    for toolset in toolsets:
        try:
            # Get tools from the toolset to validate their schemas
            if hasattr(toolset, 'list_tools'):
                tools_response = await toolset.list_tools()
                logger.debug(f"tools_response type: {type(tools_response)}, value: {tools_response}")
                
                # Handle different response formats
                if hasattr(tools_response, 'tools'):
                    tools = tools_response.tools
                elif isinstance(tools_response, list):
                    tools = tools_response
                else:
                    tools = []
                
                logger.debug(f"Validating {len(tools)} tools from {toolset.__class__.__name__}")
                
                # Check each tool's schema
                issues_found = []
                for tool in tools:
                    logger.debug(f"Checking tool: {tool.name}")
                    if hasattr(tool, 'inputSchema') and tool.inputSchema:
                        schema = tool.inputSchema
                        logger.debug(f"Tool {tool.name} schema: {schema}")
                        
                        # Check for properties with empty Type arrays
                        if 'properties' in schema:
                            for prop_name, prop_def in schema['properties'].items():
                                logger.debug(f"  Property {prop_name}: {prop_def}")
                                # Check if type is missing or empty
                                if 'type' not in prop_def or not prop_def['type']:
                                    issues_found.append(f"{tool.name}.{prop_name}: missing/empty type")
                                    logger.debug(f"    ❌ Missing/empty type!")
                                # Check if type is an empty array
                                elif isinstance(prop_def['type'], list) and len(prop_def['type']) == 0:
                                    issues_found.append(f"{tool.name}.{prop_name}: empty type array")
                                    logger.debug(f"    ❌ Empty type array!")
                    else:
                        logger.debug(f"Tool {tool.name} has no inputSchema")
                
                if issues_found:
                    warning_msg = (
                        f"⚠️  EXCLUDING toolset {toolset.__class__.__name__} due to schema issues:\n  " + 
                        "\n  ".join(issues_found) +
                        "\n  These issues cause crashes with LLM models (e.g., gpt-oss template bug)."
                        "\n  Fix: Update the MCP server to use concrete types (str) instead of Optional[str]"
                        "\n  This toolset will NOT be available until fixed."
                    )
                    logger.error(warning_msg)
                    all_warnings.append(warning_msg)
                    # DO NOT add this toolset - skip it entirely
                    continue
                else:
                    # Schema is valid, add the toolset
                    logger.debug(f"✓ Toolset {toolset.__class__.__name__} passed validation")
                    validated_toolsets.append(toolset)
            else:
                # If can't validate, add it anyway (might be a different toolset type)
                logger.debug(f"Toolset {toolset.__class__.__name__} has no list_tools method, adding anyway")
                validated_toolsets.append(toolset)
                
        except Exception as e:
            logger.error(f"Error validating toolset {toolset.__class__.__name__}: {e}", exc_info=True)
            # Skip toolsets that can't be validated - safer to exclude than crash
            warning_msg = f"Excluding {toolset.__class__.__name__} due to validation error: {e}"
            logger.warning(warning_msg)
            all_warnings.append(warning_msg)
            continue
    
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
        logger.warning(f"MCP config file not found at {config_path}, using empty server list")
        return []
    
    try:
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        servers = []
        mcp_servers = config_data.get('servers', {})
        
        for server_name, server_config in mcp_servers.items():
            transport = server_config.get('type', 'http')
            
            if transport == 'stdio':
                # For stdio, construct command from 'command' and 'args' fields
                command = server_config.get('command', '')
                args = server_config.get('args', [])
                env = server_config.get('env', None)
                
                # If args exist, join command and args into a single command string
                if args:
                    full_command = ' '.join([command] + args)
                    servers.append(MCPServerModel(url=full_command, type='stdio', env=env))
                elif command:
                    servers.append(MCPServerModel(url=command, type='stdio', env=env))
                else:
                    logger.warning(f"Server {server_name} missing command, skipping")
            else:
                # For http/sse, use 'url' field
                url = server_config.get('url', '')
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


def setup_mcp_toolsets(tools_urls: list, timeout: float = 604800.0, max_retries: int = 15, allow_sampling: bool = False) -> list:
    """Set up MCP toolsets from server configurations.
    
    Args:
        tools_urls: List of MCP server configurations
        timeout: Timeout for MCP connections in seconds
        max_retries: Maximum retries for MCP operations
        allow_sampling: Allow sampling in MCP operations
        
    Returns:
        List of configured MCP toolsets
    """
    import httpx
    
    type_map = {"sse": MCPServerSSE, "http": MCPServerStreamableHTTP}
    toolsets = []
    
    # Create custom httpx client with keepalive_expiry=0 (disable keepalive)
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        limits=httpx.Limits(keepalive_expiry=0)
    )
    
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
                logger.info(f"Added stdio tool: {command} {' '.join(args)} with env vars: {list(tool.env.keys()) if tool.env else 'none'}")
            else:
                # Handle http and sse type tools
                if tool.type in type_map:
                    server = type_map[tool.type](
                        url=tool.url,
                        timeout=timeout,
                        max_retries=max_retries,
                        allow_sampling=allow_sampling,
                        read_timeout=timeout,
                        http_client=http_client
                    )
                    toolsets.append(server)
                    logger.info(f"Added {tool.type} tool: {tool.url}")
                else:
                    logger.warning(f"Unknown tool type: {tool.type}")
        except Exception as e:
            logger.error(f"Failed to setup tool {tool.url}: {e}")
    
    return toolsets
