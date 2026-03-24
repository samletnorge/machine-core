# Machine Core Documentation

**A framework for building AI agents with MCP tools, OpenAPI integration, RAG-based tool filtering, and multi-provider LLM support.**

Machine Core is the shared engine behind multiple AI projects. It handles LLM/embedding provider abstraction, MCP (Model Context Protocol) tool integration, OpenAPI-to-tool generation, vector search, file processing, and agent lifecycle management -- so your project only needs to define domain-specific logic.

Current version: **v0.4.1**

## Documentation Map

### Getting Started

- [Getting Started](getting-started.md) -- Installation, first agent, and a working example in under 5 minutes.

### Core Concepts

- [Architecture](architecture.md) -- Inheritance chain, tool modes, provider abstraction, and how the pieces fit together.
- [Agents](agents.md) -- BaseAgent, built-in agents, creating custom agents, streaming vs non-streaming execution.
- [Providers](providers.md) -- LLM and embedding provider registry, supported backends, switching providers.
- [Configuration](configuration.md) -- All environment variables, AgentConfig, MCPServerModel, and runtime overrides.

### Tools

- [MCP Toolsets](tools/mcp-toolsets.md) -- Loading MCP servers from config, validation, ToolFilterWrapper.
- [OpenAPI Tools](tools/openapi-tools.md) -- Generating pydantic-ai Tools from any OpenAPI spec.
- [Tool Filtering](tools/tool-filtering.md) -- RAG-based filtering with ToolFilterManager, mixed-mode (OpenAPI + MCP) filtering.

### Data & Files

- [Vector Store](vector-store.md) -- Embedder, multi-table LanceDB VectorStore, DocumentStore facade.
- [File Processing](file-processing.md) -- PDF extraction, OCR, VLM preparation, batch uploads.

### Reference

- [API Reference](api-reference.md) -- Complete class, method, and function reference.
- [Examples](examples.md) -- Real-world usage from production projects (deep-research, mcp-client-chat, multi-agent-dev, ai-accounting-agent).
- [Deployment](deployment.md) -- Docker, production setup, Prometheus monitoring.
- [Changelog](changelog.md) -- Version history and migration notes.

## Quick Overview

```
model-providers          External package: 7 LLM + 3 embedding providers
    |
machine-core             This package: agent framework + tools + RAG + file processing
    |
    +-- deep-research          Multi-agent research (MCP toolsets mode)
    +-- multi-agent-dev        Coding + review agents (MCP toolsets mode)
    +-- mcp-client-chat        Streamlit chat client (MCP toolsets mode)
    +-- ai-accounting-agent    Tripletex accounting (dynamic tools + rebuild_agent)
```

## License

[Royalty-Share Open-Source License (RSOSL) v1.0](../LICENSE.md) -- Free to use until $100K USD revenue, then 1% royalty.
