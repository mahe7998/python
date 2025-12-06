@echo off
REM Start CUDA Whisper backend with NVIDIA RTX 4090 GPU acceleration
REM This script starts the backend on Windows

cd /d "%~dp0"

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Set database URL - connects to PostgreSQL on Mac via Tailscale
set DATABASE_URL=postgresql+asyncpg://whisper:%WHISPER_DB_PASSWORD%@jacques-m4-macbook-pro-max.%TAILSCALE_URL%:5432/whisper

REM Set Whisper model - Options: tiny, base, small, medium, large-v3, distil-large-v3
set WHISPER_MODEL=base

REM CUDA settings for RTX 4090
set CUDA_VISIBLE_DEVICES=0
set CUDA_DEVICE_ORDER=PCI_BUS_ID

REM HuggingFace Hub timeout settings for large model downloads
set HF_HUB_ETAG_TIMEOUT=600
set HF_HUB_DOWNLOAD_TIMEOUT=600

echo =========================================
echo Starting CUDA Whisper Backend
echo =========================================
echo NVIDIA RTX 4090 GPU Acceleration: Enabled
echo Model: %WHISPER_MODEL%
echo Port: 8000
echo Database: jacques-m4-macbook-pro-max (via Tailscale)
echo =========================================
echo.

REM Get Tailscale hostname for display
for /f "tokens=*" %%i in ('powershell -Command "(tailscale status --self --json | ConvertFrom-Json).Self.DNSName -replace '\.$', ''"') do set TAILSCALE_HOST=%%i

REM Ensure Tailscale Serve is running (provides HTTPS on port 443)
echo Configuring Tailscale Serve for HTTPS...
tailscale serve --bg 8000

echo.
echo Tailscale Hostname: %TAILSCALE_HOST%
echo Access backend at: https://%TAILSCALE_HOST%
echo (Tailscale Serve provides HTTPS, proxying to localhost:8000)
echo.

REM Start the backend on localhost (Tailscale Serve proxies to 127.0.0.1:8000)
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
