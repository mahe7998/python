#!/bin/bash

# Start MLX-Whisper backend with Apple Silicon acceleration
# This script starts the backend on the host Mac (not in Docker)

cd "$(dirname "$0")"

# Source environment variables from ~/.zshrc
source ~/.zshrc 2>/dev/null || true

# Activate virtual environment
source venv/bin/activate

# Replace env vars in .env file
export DATABASE_URL="postgresql+asyncpg://whisper:${WHISPER_DB_PASSWORD}@localhost:5432/whisper"

# Export WHISPER_MODEL from .env
export WHISPER_MODEL="mlx-community/whisper-tiny"

# Set HuggingFace Hub timeout to 10 minutes (600 seconds) for large model downloads
# Default is 10 seconds which is too short for 1.5GB Medium model
export HF_HUB_ETAG_TIMEOUT=600
export HF_HUB_DOWNLOAD_TIMEOUT=600

echo "========================================="
echo "Starting MLX-Whisper Backend"
echo "========================================="
echo "Apple Silicon GPU Acceleration: Enabled"
echo "Model: ${WHISPER_MODEL}"
echo "Port: 8000"
echo "Database: localhost:5432/whisper"
echo "========================================="
echo ""

# Start the backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
