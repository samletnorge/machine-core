# Stage 1: Install dependencies
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS deps
WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON=python3.13

RUN apt-get update && apt-get install -y \
	git \
	build-essential \
	gcc \
	g++ \
	libffi-dev \
	libssl-dev \
	python3-dev \
    openssh-client \
	&& rm -rf /var/lib/apt/lists/*
# Add GitHub to known hosts
RUN mkdir -p /root/.ssh && \
    ssh-keyscan github.com >> /root/.ssh/known_hosts
# Copy only dependency definitions first (for better caching)
COPY pyproject.toml uv.lock* ./

# Install only the dependencies
ARG GITHUB_TOKEN
RUN --mount=type=cache,target=/root/.cache/uv \
    echo "machine github.com login ${GITHUB_TOKEN} password x-oauth-basic" > /root/.netrc \
    && chmod 600 /root/.netrc \
    && uv sync --frozen --no-install-project --no-dev \
    && rm /root/.netrc

# Stage 2: Build the application image
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /workspace/
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON=python3.13

# Install curl, Azure CLI, and OpenCV dependencies
RUN apt-get update && apt-get install -y \
	curl \
	apt-transport-https \
	git \
	lsb-release \
	gnupg \
	libgl1-mesa-glx \
	libglib2.0-0 \
	libsm6 \
	libxext6 \
	libxrender-dev \
	libgomp1 \
	&& curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
	&& apt-get clean \
	&& rm -rf /var/lib/apt/lists/*

# Copy the dependencies from the previous stage
COPY --from=deps /workspace/.venv/ /workspace/.venv/

# Copy application code
COPY . ./

# Ensure dependency files are present (should already be there from COPY . ./)
# But explicitly copy them for clarity
ADD pyproject.toml uv.lock* ./

# Install the project (dependencies are already installed)
RUN --mount=type=cache,target=/root/.cache/uv \
	uv sync --frozen --no-dev

# Set the path to include the virtual environment
ENV PATH="/workspace/.venv/bin:$PATH"

# Expose port
EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]