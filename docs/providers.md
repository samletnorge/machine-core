# Providers

Machine Core delegates all LLM and embedding provider logic to the external `model-providers` package. This page documents every supported provider, how they work, and how to switch between them.

## How Providers Work

The provider system uses a **registry + factory** pattern:

1. A dictionary maps string keys (`"ollama"`, `"google"`, etc.) to provider classes.
2. `LLMProviderConfig.from_env()` reads environment variables to build a config.
3. `get_llm_provider(config)` does a registry lookup and calls `provider_cls.create(config)`.
4. Each provider's `create()` returns a `ResolvedProvider` containing a **fully-constructed pydantic-ai model object**.
5. Machine Core passes that model directly to `pydantic_ai.Agent(model=...)`.

```python
# This is what happens inside AgentCore.__init__():
from model_providers import get_llm_provider, LLMProviderConfig

cfg = LLMProviderConfig.from_env()    # reads LLM_PROVIDER, LLM_MODEL, etc.
resolved = get_llm_provider(cfg)      # registry lookup + create()

# resolved.model is OpenAIChatModel, GoogleModel, or AnthropicModel
# resolved.model_name is e.g. "gemini-2.5-flash"
# resolved.provider_type is "openai", "google", or "anthropic"
```

Machine Core never imports model-specific classes. All provider knowledge lives in `model-providers`.

## LLM Providers

### Ollama

**Key:** `ollama` | **Type:** `openai` | **Default model:** `gpt-oss:latest`

Local or remote Ollama instance. Uses the OpenAI-compatible API.

```bash
LLM_PROVIDER=ollama
LLM_MODEL=gpt-oss:latest          # any model pulled in Ollama
OLLAMA_BASE_URL=http://localhost:11434/v1  # default: https://ollama.valiantlynx.com/v1
```

Automatically sets `think: true` (chain-of-thought reasoning) and `keep_alive: 0` (release GPU after request). Returns `OpenAIChatModel`.

### Azure OpenAI

**Key:** `azure` | **Type:** `openai` | **Default model:** `gpt-4o-2` (deployment name)

Supports two auth modes:

**Token auth (default):**

```bash
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_USE_TOKEN_AUTH=true  # default
# Uses DefaultAzureCredential (managed identity, CLI, etc.)
```

**API key auth:**

```bash
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_USE_TOKEN_AUTH=false
AZURE_OPENAI_API_KEY=your-key
# Or fetch from Key Vault:
# AZURE_OPENAI_KEYVAULT_URL=https://your-kv.vault.azure.net/
# AZURE_OPENAI_SECRET_NAME=azure-openai-api-key
```

### Grok (x.ai)

**Key:** `grok` | **Type:** `openai` | **Default model:** `grok-2-latest`

```bash
LLM_PROVIDER=grok
GROK_API_KEY=your-xai-api-key  # required
```

Uses the OpenAI-compatible API at `https://api.x.ai/v1`.

### Groq

**Key:** `groq` | **Type:** `openai` | **Default model:** `llama-3.3-70b-versatile`

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key  # required
```

Uses the OpenAI-compatible API at `https://api.groq.com/openai/v1`.

### Google Gemini

**Key:** `google` | **Type:** `google` | **Default model:** `gemini-2.5-flash`

Direct API access with an API key.

```bash
LLM_PROVIDER=google
GCP_API_KEY=your-google-api-key  # required
```

Returns `GoogleModel`. Does not pass `ModelSettings` -- Gemini handles settings through its own API.

### Vertex AI (Gemini)

**Key:** `vertex-gemini` | **Type:** `google` | **Default model:** `gemini-2.5-flash`

Gemini through Google Cloud Vertex AI. Uses service account or application default credentials.

```bash
LLM_PROVIDER=vertex-gemini
GCP_PROJECT=your-project-id     # required
GCP_LOCATION=us-central1        # default
```

### Vertex AI (Claude)

**Key:** `vertex-claude` | **Type:** `anthropic` | **Default model:** `claude-sonnet-4-20250514`

Anthropic Claude through Google Cloud Vertex AI.

```bash
LLM_PROVIDER=vertex-claude
GCP_PROJECT=your-project-id     # required
GCP_LOCATION=us-east5           # default (Claude availability)
```

Returns `AnthropicModel` via `AsyncAnthropicVertex`.

## Provider Type Summary

| Key | Returns | Auth | Base URL |
|-----|---------|------|----------|
| `ollama` | `OpenAIChatModel` | None (local) | `OLLAMA_BASE_URL` |
| `azure` | `OpenAIChatModel` | Token or API key | `AZURE_OPENAI_ENDPOINT` |
| `grok` | `OpenAIChatModel` | API key | `https://api.x.ai/v1` |
| `groq` | `OpenAIChatModel` | API key | `https://api.groq.com/openai/v1` |
| `google` | `GoogleModel` | API key | Google API |
| `vertex-gemini` | `GoogleModel` | GCP credentials | Vertex AI |
| `vertex-claude` | `AnthropicModel` | GCP credentials | Vertex AI |

## Embedding Providers

Embedding providers work slightly differently: they return an **instance** with an `embed()` method, not a pydantic-ai model.

### Ollama Embeddings

**Key:** `ollama` | **Default model:** `nomic-embed-text`

```bash
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://localhost:11434/v1
```

Calls `/v1/embeddings` endpoint. Handles both OpenAI-style and Ollama-native response formats.

### Azure Embeddings

**Key:** `azure` | **Default model:** `text-embedding-3-large`

```bash
EMBEDDING_PROVIDER=azure
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-large
# Uses same AZURE_OPENAI_ENDPOINT and auth as LLM
```

### Google Embeddings

**Key:** `google` | **Default model:** `gemini-embedding-001`

```bash
EMBEDDING_PROVIDER=google
GCP_API_KEY=your-api-key  # same as LLM
EMBEDDING_DIMENSIONS=3072  # default for gemini-embedding-001
```

Uses the `google-genai` SDK with `embed_content()`.

## Switching Providers

Switching providers requires only environment variable changes. No code changes needed.

```bash
# From Ollama (local)...
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1

# ...to Google Gemini (cloud)
LLM_PROVIDER=google
GCP_API_KEY=your-key

# ...to Azure OpenAI
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
```

All downstream code (`BaseAgent`, `AgentCore`, etc.) works identically regardless of provider.

## Discovery Functions

For building dynamic UIs (e.g., mcp-client-chat's Streamlit sidebar):

```python
from model_providers import (
    get_available_llm_providers,       # -> ["ollama", "azure", "grok", ...]
    get_available_llm_models,          # -> ["gemini-2.5-flash", ...] for a given provider
    get_available_embedding_providers, # -> ["ollama", "azure", "google"]
    get_available_embedding_models,    # -> ["nomic-embed-text", ...] for a given provider
)

# Populate a dropdown
providers = get_available_llm_providers()
models = get_available_llm_models("google")  # ["gemini-2.5-flash", "gemini-2.5-pro", ...]
```

Ollama's `get_available_llm_models("ollama")` makes a live HTTP query to discover pulled models. Other providers return static lists.

## Adding New Providers

In `model-providers`, subclass `BaseLLMProvider` or `BaseEmbeddingProvider` and add to the registry:

```python
# In model_providers/llm.py

class MyCustomProvider(BaseLLMProvider):
    @classmethod
    def create(cls, cfg: LLMProviderConfig) -> ResolvedProvider:
        # Construct a pydantic-ai model
        provider = OpenAIProvider(api_key=os.getenv("MY_API_KEY"), base_url="https://my-api.com/v1")
        model = OpenAIChatModel(cfg.model_name, provider=provider)
        return ResolvedProvider(model=model, model_name=cfg.model_name, provider_type="openai")

# Add to registry
LLM_PROVIDERS["my-custom"] = MyCustomProvider
```

Then use it: `LLM_PROVIDER=my-custom LLM_MODEL=my-model-name`.
