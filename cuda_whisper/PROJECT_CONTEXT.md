# CUDA Whisper Project Context

## Overview
This is a CUDA-optimized port of the MLX Whisper backend (from `../mlx_whisper`), designed for NVIDIA RTX 4090 GPU acceleration using `faster-whisper` (CTranslate2).

## Key Differences from MLX Version
- Uses `faster-whisper` instead of `mlx_whisper`
- Device: `cuda` with `float16` compute type (optimized for RTX 4090)
- Model names map from MLX-style (`mlx-community/whisper-base-mlx`) to faster-whisper sizes (`base`)

## Project Structure
```
cuda_whisper/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI entry point
│   ├── database.py          # PostgreSQL async connection
│   ├── models.py            # SQLAlchemy ORM + Pydantic schemas
│   ├── whisper_service.py   # CUDAWhisperService (faster-whisper)
│   ├── wav_utils.py         # WAV file utilities
│   ├── ollama_client.py     # Ollama AI client
│   ├── diff_service.py      # Edit history/versioning
│   └── routers/
│       ├── transcription.py # REST API endpoints
│       └── websocket.py     # WebSocket streaming
├── requirements.txt
├── start.bat                # Windows startup script
└── PROJECT_CONTEXT.md       # This file
```

## Environment Variables Required
| Variable | Description |
|----------|-------------|
| `WHISPER_DB_PASSWORD` | PostgreSQL password |
| `TAILSCALE_URL` | Tailscale domain (e.g., `tail1234.ts.net`) |

## Database Connection
- Host: `jacques-m4-macboo-pro-max.${TAILSCALE_URL}` (Mac via Tailscale)
- Port: 5432
- Database: `whisper`
- User: `whisper`

## Model Options
- `tiny`, `base`, `small`, `medium`, `large-v3`
- `distil-large-v2`, `distil-large-v3` (faster variants)

## Key APIs
- REST: `/api/transcriptions`
- WebSocket: `/ws/transcribe`
- Health: `/health`
- Info: `/api/info`

## WebSocket Protocol
```json
{"type": "set_model", "model": "base"}
{"type": "set_channel", "channel": "left|right|both"}
{"type": "set_language", "language": "en|null"}
{"type": "audio_chunk", "data": "<base64>", "duration": 0.5}
{"type": "end_recording"}
```

## Setup Steps
1. Create venv: `python -m venv venv`
2. Activate: `venv\Scripts\activate`
3. Install PyTorch CUDA: `pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121`
4. Install deps: `pip install -r requirements.txt`
5. Set env vars (WHISPER_DB_PASSWORD, TAILSCALE_URL)
6. Run: `start.bat` or `uvicorn app.main:app --reload`
