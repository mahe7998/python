# Start CUDA Whisper backend with NVIDIA RTX 4090 GPU acceleration
# PowerShell version for Windows

# Change to script directory
Set-Location $PSScriptRoot

# Activate virtual environment
& .\venv\Scripts\Activate.ps1

# Set database URL - connects to PostgreSQL on Mac via Tailscale
$env:DATABASE_URL = "postgresql+asyncpg://whisper:$env:WHISPER_DB_PASSWORD@jacques-m4-macboo-pro-max.$env:TAILSCALE_URL`:5432/whisper"

# Set Whisper model - Options: tiny, base, small, medium, large-v3, distil-large-v3
$env:WHISPER_MODEL = "base"

# CUDA settings for RTX 4090
$env:CUDA_VISIBLE_DEVICES = "0"
$env:CUDA_DEVICE_ORDER = "PCI_BUS_ID"

# HuggingFace Hub timeout settings for large model downloads
$env:HF_HUB_ETAG_TIMEOUT = "600"
$env:HF_HUB_DOWNLOAD_TIMEOUT = "600"

Write-Host "========================================="
Write-Host "Starting CUDA Whisper Backend"
Write-Host "========================================="
Write-Host "NVIDIA RTX 4090 GPU Acceleration: Enabled"
Write-Host "Model: $env:WHISPER_MODEL"
Write-Host "Port: 8000"
Write-Host "Database: jacques-m4-macboo-pro-max (via Tailscale)"
Write-Host "========================================="
Write-Host ""

# Start the backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
