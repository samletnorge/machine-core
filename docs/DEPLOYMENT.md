# Deployment Guide

This guide explains how to deploy the Machine Core API with the documentation frontend.

## Local Development

### Prerequisites

- Python 3.12+
- uv or pip for dependency management

### Running Locally

1. Install dependencies:
```bash
uv sync
# or
pip install -e .
```

2. Set up environment variables (optional):
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Run the server:
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

4. Access the application:
- Frontend: http://localhost:8000/
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- API Info: http://localhost:8000/api/info
- Metrics: http://localhost:8000/metrics

## Docker Deployment

### Prerequisites

- Docker
- Docker Compose
- GitHub Token (for private dependencies)

### Using Docker Compose

1. Set your GitHub token:
```bash
export GITHUB_TOKEN=your_github_token_here
```

2. Build and run:
```bash
docker-compose up -d
```

3. Check health:
```bash
curl http://localhost:8000/health
```

4. View logs:
```bash
docker-compose logs -f
```

5. Stop the service:
```bash
docker-compose down
```

### Building Docker Image Manually

```bash
docker build \
  --build-arg GITHUB_TOKEN=your_token \
  -t machine-core:latest \
  .
```

### Running Docker Container

```bash
docker run -d \
  -p 8000:8000 \
  -e AGENT_MAX_ITERATIONS=10 \
  -e LLM_PROVIDER=ollama \
  -e LLM_MODEL=gpt-oss:latest \
  --name machine-core \
  machine-core:latest
```

## Environment Variables

### Agent Configuration

- `AGENT_MAX_ITERATIONS` (default: 10) - Maximum number of tool iterations
- `AGENT_TIMEOUT` (default: 604800.0) - Timeout in seconds
- `AGENT_MAX_TOOL_RETRIES` (default: 15) - Maximum tool retry attempts
- `AGENT_ALLOW_SAMPLING` (default: true) - Allow response sampling

### LLM Configuration

- `LLM_PROVIDER` (default: ollama) - LLM provider name
- `LLM_MODEL` (default: gpt-oss:latest) - LLM model name

### Embedding Configuration

- `EMBEDDING_PROVIDER` (default: ollama) - Embedding provider name
- `EMBEDDING_MODEL` (default: nomic-embed-text) - Embedding model name

### CORS Configuration

- `ALLOWED_ORIGINS` (default: http://localhost:5173,http://localhost:8000,http://localhost:3000) - Comma-separated list of allowed origins

## Production Deployment

### Reverse Proxy with Nginx

Example nginx configuration:

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
    }
}
```

### SSL with Let's Encrypt

```bash
certbot --nginx -d machine-core.example.com
```

## Monitoring

The application exposes Prometheus metrics at `/metrics`:

```bash
curl http://localhost:8000/metrics
```

You can configure Prometheus to scrape these metrics:

```yaml
scrape_configs:
  - job_name: 'machine-core'
    static_configs:
      - targets: ['localhost:8000']
```

## Troubleshooting

### Port Already in Use

If port 8000 is already in use:

```bash
# Find the process
lsof -i :8000

# Kill the process
kill <PID>
```

Or use a different port:

```bash
uvicorn src.main:app --port 8001
```

### Frontend Not Loading

Check that the `frontend` directory exists and contains:
- `index.html`
- `styles.css`
- `script.js`

### Dependencies Not Installing

Make sure you have access to the private `model-providers` repository:

```bash
# Test access
git clone https://github.com/samletnorge/model-providers.git
```

## Security Considerations

1. **CORS**: Configure `ALLOWED_ORIGINS` appropriately for your deployment
2. **Secrets**: Never commit sensitive data like API keys to the repository
3. **GitHub Token**: Use read-only tokens for deployment
4. **Health Checks**: Monitor `/health` endpoint for service availability
5. **Updates**: Keep dependencies up-to-date for security patches

## Support

For issues and questions:
- GitHub Issues: https://github.com/samletnorge/machine-core/issues
- Documentation: See `docs/README.md`
