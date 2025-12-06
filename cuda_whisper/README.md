# CUDA Whisper Backend

Real-time audio transcription API optimized for **NVIDIA RTX 4090** GPU acceleration using `faster-whisper` (CTranslate2).

## Features

- Real-time streaming transcription via WebSocket
- REST API for batch transcription
- CUDA-accelerated inference with FP16 precision
- PostgreSQL storage for transcription history
- AI-powered text review via Ollama integration
- Audio concatenation for resumed recordings

## Requirements

- Windows 10/11 with NVIDIA RTX 4090
- Python 3.10+
- CUDA 12.1+
- FFmpeg (for audio processing)
- PostgreSQL database (remote via Tailscale)

## Installation

### 1. Create Virtual Environment

```powershell
cd cuda_whisper
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install PyTorch with CUDA

```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Set Environment Variables

Add these to your Windows User Environment Variables:

| Variable | Value |
|----------|-------|
| `WHISPER_DB_PASSWORD` | Your PostgreSQL password |
| `TAILSCALE_URL` | Your Tailscale domain (e.g., `tail1234.ts.net`) |

### 5. Install FFmpeg

Download from https://ffmpeg.org/download.html and add to PATH.

## Running

```powershell
.\start.bat
# or
.\start.ps1
```

The server starts at `http://localhost:8000`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health` | GET | Detailed health status |
| `/api/info` | GET | API and GPU info |
| `/api/transcriptions` | GET/POST | List/create transcriptions |
| `/api/transcriptions/{id}` | GET/PATCH/DELETE | CRUD operations |
| `/api/transcriptions/transcribe` | POST | Upload and transcribe file |
| `/ws/transcribe` | WebSocket | Real-time streaming transcription |

## WebSocket Protocol

Connect to `/ws/transcribe` and send JSON messages:

```javascript
// Select model
ws.send(JSON.stringify({type: "set_model", model: "base"}));

// Set audio channel (optional)
ws.send(JSON.stringify({type: "set_channel", channel: "both"}));

// Set language (optional, null = auto-detect)
ws.send(JSON.stringify({type: "set_language", language: "en"}));

// Send audio chunks (base64 WebM)
ws.send(JSON.stringify({
  type: "audio_chunk",
  data: base64AudioData,
  duration: 0.5
}));

// End recording
ws.send(JSON.stringify({type: "end_recording"}));
```

## Model Options

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `tiny` | 75MB | Fastest | Basic |
| `base` | 150MB | Fast | Good |
| `small` | 500MB | Medium | Better |
| `medium` | 1.5GB | Slower | Great |
| `large-v3` | 3GB | Slowest | Best |
| `distil-large-v3` | 1.5GB | Fast | Great |

Set via `WHISPER_MODEL` environment variable in `start.bat`.

## Configuration

Edit `start.bat` or `start.ps1` to change:

- `WHISPER_MODEL` - Model size
- `CUDA_VISIBLE_DEVICES` - GPU selection
- Database connection string

## Differences from MLX Version

This is a port of `../mlx_whisper` optimized for Windows/CUDA:

| Feature | MLX Version | CUDA Version |
|---------|-------------|--------------|
| Backend | mlx_whisper | faster-whisper |
| Device | Apple Silicon (MPS) | NVIDIA CUDA |
| Precision | Default | FP16 |
| Platform | macOS | Windows |

## Troubleshooting

### CUDA not detected

```powershell
python -c "import torch; print(torch.cuda.is_available())"
```

Should print `True`. If not, reinstall PyTorch with CUDA.

### Model download fails

Set longer timeouts:
```powershell
$env:HF_HUB_ETAG_TIMEOUT = "600"
$env:HF_HUB_DOWNLOAD_TIMEOUT = "600"
```

### Database connection fails

Verify Tailscale is connected and environment variables are set:
```powershell
echo $env:WHISPER_DB_PASSWORD
echo $env:TAILSCALE_URL
```
