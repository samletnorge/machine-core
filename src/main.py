"""
Machine Core FastAPI Service

A robust service for building AI agents with MCP (Model Context Protocol) integration.
This service provides API endpoints and serves documentation with SEO optimization.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup application resources."""
    logger.info("Starting Machine Core API...")
    yield
    logger.info("Shutting down Machine Core API...")


app = FastAPI(
    title="Machine Core API",
    description="""
A flexible agent framework for building AI agents with MCP (Model Context Protocol) integration.

## Features
- Clean Architecture - Separation of infrastructure and execution patterns
- Flexible Configuration - Environment variables, direct parameters, or runtime overrides
- MCP Integration - Easy integration with MCP servers and tools
- Multiple Agent Types - Chat, CLI, Receipt Processor, Twitter Bot, Memory Master, RAG Chat
""",
    version="0.1.2",
    lifespan=lifespan,
)

# CORS Middleware
allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:8000,http://localhost:3000"
).split(",")
logger.info(f"ALLOWED_ORIGINS: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "machine-core",
            "version": "0.1.2"
        }
    )


@app.get("/api/info")
async def get_info():
    """Get information about the Machine Core service."""
    return JSONResponse(
        content={
            "name": "Machine Core",
            "version": "0.1.2",
            "description": "A flexible agent framework for building AI agents with MCP integration",
            "features": [
                "Clean Architecture",
                "Flexible Configuration",
                "MCP Integration",
                "Multiple Agent Types",
                "Streaming Support",
                "Reusable Package"
            ],
            "agents": [
                {"name": "ChatAgent", "description": "Streaming chat", "use_case": "Streamlit UI, web chat"},
                {"name": "CLIAgent", "description": "Non-streaming", "use_case": "Terminal, cron jobs"},
                {"name": "ReceiptProcessorAgent", "description": "Vision + queue", "use_case": "Document analysis"},
                {"name": "TwitterBotAgent", "description": "Scheduled posting", "use_case": "Social media automation"},
                {"name": "RAGChatAgent", "description": "Knowledge graph", "use_case": "Q&A, support"},
                {"name": "MemoryMasterAgent", "description": "Knowledge extraction", "use_case": "Graph maintenance"}
            ]
        }
    )


# Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Mount static files for frontend at root (must be last to avoid overriding API routes)
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
    logger.info(f"Mounted frontend from {frontend_path}")
else:
    logger.warning(f"Frontend directory not found at {frontend_path}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
