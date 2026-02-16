# Stage 1: Install dependencies
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS deps
WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    openssh-client \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Add GitHub to known hosts
RUN mkdir -p /root/.ssh && \
    ssh-keyscan github.com >> /root/.ssh/known_hosts

# Copy only dependency definitions first (for better caching)
COPY pyproject.toml uv.lock* ./

ARG GITHUB_TOKEN
# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    echo "machine github.com login ${GITHUB_TOKEN} password x-oauth-basic" > /root/.netrc \
    && chmod 600 /root/.netrc \
    && uv sync --frozen --no-install-project --no-dev \
    && rm /root/.netrc

# Stage 2: Build the application image
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /workspace/
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy application files first
COPY . ./

# Add the pyproject.toml file and uv.lock file
COPY pyproject.toml uv.lock* ./

# Copy only the site-packages from the deps stage (not the whole venv with symlinks)
COPY --from=deps /workspace/.venv/lib/python3.12/site-packages /workspace/.venv/lib/python3.12/site-packages

# Create a fresh venv in this stage and sync to ensure correct Python linking
ARG GITHUB_TOKEN
RUN --mount=type=cache,target=/root/.cache/uv \
    python3.12 -m venv /workspace/.venv \
    && /workspace/.venv/bin/pip install --upgrade pip \
    && echo "machine github.com login ${GITHUB_TOKEN} password x-oauth-basic" > /root/.netrc \
    && chmod 600 /root/.netrc \
    && uv sync --frozen --no-dev \
    && rm /root/.netrc

# Set the path to include the virtual environment
ENV PATH="/workspace/.venv/bin:$PATH"

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose the application port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "src.main:app", "--host=0.0.0.0", "--port=8000"]
