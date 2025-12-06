"""
CUDA Whisper Backend - Main FastAPI Application
Optimized for NVIDIA RTX 4090 GPU acceleration
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, close_db
from app.whisper_service import get_whisper_service
from app.routers import transcription, websocket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager

    Handles startup and shutdown events
    """
    # Startup
    logger.info("Starting CUDA Whisper Backend...")

    try:
        # Initialize database (optional - will continue without it if connection fails)
        logger.info("Initializing database...")
        try:
            await init_db()
            logger.info("Database initialized")
        except Exception as db_error:
            logger.warning(f"Database initialization failed (will run without database): {db_error}")
            logger.info("Continuing without database - transcription history will not be saved")

        # Initialize Whisper service (load models)
        logger.info("Loading Whisper models with CUDA acceleration...")
        whisper_service = get_whisper_service()
        logger.info("Whisper models loaded on CUDA")

        logger.info("CUDA Whisper Backend started successfully")

    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down CUDA Whisper Backend...")

    try:
        await close_db()
        logger.info("Database connections closed")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

    logger.info("CUDA Whisper Backend shut down")


# Create FastAPI app
app = FastAPI(
    title="CUDA Whisper Backend",
    description="Audio transcription API with NVIDIA RTX 4090 GPU acceleration",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(transcription.router)
app.include_router(websocket.router)


@app.get("/")
async def root():
    """
    Root endpoint - health check
    """
    return {
        "service": "CUDA Whisper Backend",
        "version": "0.1.0",
        "status": "running",
        "acceleration": "NVIDIA CUDA (RTX 4090)",
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint

    Returns service status and component availability
    """
    from app.ollama_client import get_ollama_client
    import torch

    ollama_client = get_ollama_client()
    ollama_available = await ollama_client.is_available()

    # Check CUDA availability
    cuda_available = torch.cuda.is_available()
    cuda_device = torch.cuda.get_device_name(0) if cuda_available else "N/A"

    return {
        "status": "healthy",
        "database": "connected",
        "whisper": "loaded",
        "ollama": "available" if ollama_available else "unavailable",
        "cuda": "available" if cuda_available else "unavailable",
        "cuda_device": cuda_device,
    }


@app.get("/api/info")
async def api_info():
    """
    Get API information and available models
    """
    from app.whisper_service import whisper_service
    import torch

    cuda_available = torch.cuda.is_available()
    cuda_device = torch.cuda.get_device_name(0) if cuda_available else "N/A"
    cuda_memory = f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB" if cuda_available else "N/A"

    return {
        "whisper_model": whisper_service.model_name if whisper_service else "not loaded",
        "device": whisper_service.device if whisper_service else "unknown",
        "compute_type": whisper_service.compute_type if whisper_service else "unknown",
        "cuda_device": cuda_device,
        "cuda_memory": cuda_memory,
        "speaker_diarization": whisper_service.diarize_model is not None if whisper_service else False,
        "endpoints": {
            "rest_api": "/api/transcriptions",
            "websocket": "/ws/transcribe",
            "health": "/health",
        },
    }


@app.get("/api/audio/{filename}")
async def serve_audio_file(filename: str, request: Request):
    """
    Serve audio files (WebM recordings) with range request support for seeking
    """
    from pathlib import Path
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse
    import os

    # Audio directory
    audio_dir = Path.home() / "projects" / "python" / "cuda_whisper" / "audio"
    file_path = audio_dir / filename

    # Security: ensure file is within audio directory
    if not file_path.resolve().is_relative_to(audio_dir.resolve()):
        raise HTTPException(status_code=403, detail="Access denied")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    # Get file size
    file_size = os.path.getsize(file_path)

    # Parse Range header
    range_header = request.headers.get("range")

    if range_header:
        # Parse range header (e.g., "bytes=0-1023")
        range_match = range_header.replace("bytes=", "").split("-")
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if len(range_match) > 1 and range_match[1] else file_size - 1

        # Validate range
        if start >= file_size or end >= file_size or start > end:
            raise HTTPException(status_code=416, detail="Range not satisfiable")

        chunk_size = end - start + 1

        def file_iterator():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    chunk = min(8192, remaining)
                    data = f.read(chunk)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "audio/webm",
        }

        return StreamingResponse(
            file_iterator(),
            status_code=206,
            headers=headers,
            media_type="audio/webm"
        )
    else:
        # No range request - serve entire file
        def file_iterator():
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": "audio/webm",
        }

        return StreamingResponse(
            file_iterator(),
            headers=headers,
            media_type="audio/webm"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
