"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_server.api.routes import router as api_router
from data_server.api.tracking import router as tracking_router
from data_server.db.database import init_db, close_db
from data_server.workers.scheduler import start_scheduler, stop_scheduler
from data_server.ws.manager import manager as ws_manager
from data_server.ws.handlers import router as ws_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting data server...")
    await init_db()
    await start_scheduler()
    logger.info("Data server started successfully")

    yield

    # Shutdown
    logger.info("Shutting down data server...")
    await stop_scheduler()
    await ws_manager.disconnect_all()
    await close_db()
    logger.info("Data server shutdown complete")


app = FastAPI(
    title="Data Server",
    description="EODHD caching proxy server with real-time updates",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router, prefix="/api")
app.include_router(tracking_router, prefix="/tracking")
app.include_router(ws_router)  # WebSocket router (no prefix, uses /ws)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Data Server",
        "version": "0.1.0",
        "description": "EODHD caching proxy server",
    }
