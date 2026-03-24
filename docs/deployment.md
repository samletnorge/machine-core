# Deployment

How to run machine-core locally, in Docker, and in production.

## Local Development

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Access to the private `model-providers` Git repository

### Setup

```bash
git clone https://github.com/samletnorge/machine-core.git
cd machine-core
uv sync
```

### Running the FastAPI Service

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `/` | Static frontend (if `frontend/` directory exists) |
| `/docs` | Swagger UI (auto-generated API docs) |
| `/health` | Health check — returns `{"status": "healthy"}` |
| `/api/info` | Service metadata and available agent list |
| `/metrics` | Prometheus metrics (auto-instrumented) |

### Environment Setup

Copy the example and edit:

```bash
cp .env.example .env
```

Minimal `.env` for local development with Ollama:

```bash
LLM_PROVIDER=ollama
LLM_MODEL=gpt-oss:latest
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
```

See [Configuration](configuration.md) for the full environment variable reference.

---

## Docker

### Build Arguments

The Dockerfile requires `GITHUB_TOKEN` at build time to clone the private `model-providers` dependency:

```bash
export GITHUB_TOKEN=your_github_personal_access_token
```

### Docker Compose

```bash
docker-compose up -d
```

The `docker-compose.yml` defines a single service:

```yaml
services:
  machine-core:
    build:
      context: .
      args:
        GITHUB_TOKEN: ${GITHUB_TOKEN}
    expose:
      - "8000"
    environment:
      - AGENT_MAX_ITERATIONS=10
      - AGENT_TIMEOUT=604800.0
      - LLM_PROVIDER=ollama
      - LLM_MODEL=gpt-oss:latest
      - EMBEDDING_PROVIDER=ollama
      - EMBEDDING_MODEL=nomic-embed-text
      - ALLOWED_ORIGINS=http://localhost:5173,http://localhost:8000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: always
```

### Manual Docker Build

```bash
docker build \
  --build-arg GITHUB_TOKEN=$GITHUB_TOKEN \
  -t machine-core:latest \
  .

docker run -d \
  -p 8000:8000 \
  -e LLM_PROVIDER=ollama \
  -e LLM_MODEL=gpt-oss:latest \
  --name machine-core \
  machine-core:latest
```

### Dockerfile Details

Multi-stage build with two stages:

1. **Dependencies stage** — installs build tools (git, gcc, libffi, libssl), uses `.netrc` with `GITHUB_TOKEN` for private Git dependencies, runs `uv sync --frozen --no-install-project --no-dev`
2. **Runtime stage** — installs runtime dependencies (curl, Azure CLI, OpenCV libs), copies `.venv` from stage 1, runs final `uv sync --frozen --no-dev`

Base image: `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`

---

## Downstream Project Deployment

All downstream projects follow similar Docker patterns. Key differences:

| Project | Port | Base Image | CMD |
|---------|------|------------|-----|
| machine-core | 8000 | `uv:python3.13-bookworm-slim` | `uvicorn src.main:app --host 0.0.0.0 --port 8000` |
| deep-research | 8000 | `python:3.13-slim` | `uv run python src/server.py` |
| mcp-client-chat | 8501 | `uv:python3.12-bookworm-slim` | `uv run streamlit run ./src/mcp_client_chat/app.py` |
| multi-agent-dev | 8000 | `python:3.14-slim` | `uvicorn src.multi_agent_dev.server:app --host 0.0.0.0 --port 8000` |
| ai-accounting-agent | 8080 | `python:3.13-slim` | `uvicorn src.ai_accounting_agent.http_server:app --host 0.0.0.0 --port 8080` |

### Private Dependency Access

All projects that depend on `machine-core` (which transitively depends on `model-providers`) need the `GITHUB_TOKEN` at build time. The token is injected via `.netrc` in multi-stage builds:

```dockerfile
RUN echo "machine github.com login x-access-token password ${GITHUB_TOKEN}" > /root/.netrc \
    && chmod 600 /root/.netrc
```

---

## Production

### Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name machine-core.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support (for streaming)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }
}
```

### SSL with Let's Encrypt

```bash
certbot --nginx -d machine-core.example.com
```

### CORS

Configure allowed origins via the `ALLOWED_ORIGINS` environment variable:

```bash
ALLOWED_ORIGINS=https://your-frontend.example.com,https://admin.example.com
```

Default: `http://localhost:5173,http://localhost:8000,http://localhost:3000`

### Resource Limits

For production containers, set resource limits. Example from `multi-agent-dev`:

```yaml
deploy:
  resources:
    limits:
      cpus: "2"
      memory: 4G
    reservations:
      cpus: "0.5"
      memory: 1G
```

### Log Rotation

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

---

## Monitoring

### Prometheus

machine-core auto-instruments all FastAPI routes via `prometheus-fastapi-instrumentator`. Metrics are exposed at `/metrics`.

Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: 'machine-core'
    static_configs:
      - targets: ['machine-core:8000']
    scrape_interval: 30s
```

Available metrics include:
- `http_request_duration_seconds` — request latency histogram
- `http_requests_total` — request count by method, path, status
- `http_request_size_bytes` — request body sizes
- `http_response_size_bytes` — response body sizes

### Health Checks

All projects expose a `/health` endpoint. Docker Compose health checks:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

---

## Troubleshooting

### Port Already in Use

```bash
lsof -i :8000
kill <PID>
# Or use a different port:
uvicorn src.main:app --port 8001
```

### Private Dependency Access Fails

Verify your token has repo read access:

```bash
git clone https://github.com/samletnorge/model-providers.git
```

If using Docker, ensure `GITHUB_TOKEN` is set before `docker-compose up`:

```bash
export GITHUB_TOKEN=ghp_...
docker-compose up -d
```

### Frontend Not Loading

The frontend is served from a `frontend/` directory at the project root. Check that it contains `index.html`, `styles.css`, and `script.js`.

### Lock File Outdated After machine-core Update

After updating machine-core, downstream projects must refresh their lock files:

```bash
uv lock --upgrade-package machine-core
uv sync
```

This forces uv to re-fetch machine-core from Git rather than using a cached version.

### Azure CLI Issues in Docker

The Dockerfile installs Azure CLI for token-based authentication. If you're not using Azure providers, this dependency is harmless but adds image size. To use Azure providers in Docker, ensure the container has valid Azure credentials (managed identity, service principal, etc.).
