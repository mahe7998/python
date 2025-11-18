# WhisperX Transcription Service

A real-time audio transcription service using WhisperX with AI-powered review capabilities, built with FastAPI and PostgreSQL.

## Features

- Real-time audio transcription via WebSocket
- AI-powered text review (grammar fixing, rephrasing, improvement, summarization)
- Transcription history with edit tracking
- Soft delete with restore capability
- Web interface with TipTap rich text editor
- RESTful API for transcription management

## Architecture

- **Backend**: FastAPI with async SQLAlchemy
- **Frontend**: React with Vite
- **Database**: PostgreSQL
- **AI**: Ollama for text processing
- **Transcription**: WhisperX via Tailscale network

## Getting Started

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- WHISPER_DB_PASSWORD environment variable set

### Environment Setup

```bash
# Set database password
export WHISPER_DB_PASSWORD='your_secure_password'

# Install Python dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Running the Service

```bash
# Start backend API server
./start.sh

# The API will be available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

## API Endpoints

### Transcriptions

- `GET /api/transcriptions` - List all transcriptions (with pagination)
- `GET /api/transcriptions/{id}` - Get specific transcription
- `POST /api/transcriptions` - Create new transcription
- `PUT /api/transcriptions/{id}` - Update transcription
- `DELETE /api/transcriptions/{id}` - Delete transcription (soft delete)

### AI Review

- `POST /api/transcriptions/ai-review` - Review text with AI
  - Actions: `fix_grammar`, `rephrase`, `improve`, `summarize`

### WebSocket

- `WS /ws/transcribe` - Real-time transcription stream

## Managing Deleted Transcriptions

The `manage_deleted.py` script allows you to view and restore deleted transcriptions.

### Usage

```bash
# List all deleted transcriptions
python manage_deleted.py list

# Restore a specific transcription by ID
python manage_deleted.py restore <ID>
```

### Example Output

```
================================================================================
DELETED TRANSCRIPTIONS
================================================================================

ID: 1
Title: Meeting Notes - Project Discussion
Content Preview: We discussed the new features for the upcoming release. The team agreed on...
Created: 2025-11-13 08:15:04
Deleted: 2025-11-17 02:15:34
Reason: Accidentally deleted
--------------------------------------------------------------------------------

Total deleted transcriptions: 1
```

### Restoring Transcriptions

When you restore a transcription:
- It moves back from `deleted_transcriptions` to `transcriptions` table
- The original ID is preserved
- Edit history (diffs) is not restored
- The transcription appears in the main list again

**Note**: If the ID already exists in the main table, the restore will fail. You'll need to delete the existing record or choose a different action.

## Database Schema

### Main Tables

- **transcriptions** - Active transcription records
- **deleted_transcriptions** - Soft-deleted transcriptions (for recovery)
- **transcription_diffs** - Edit history tracking

### Soft Delete Behavior

When a transcription is deleted:
1. Only the latest content is saved to `deleted_transcriptions`
2. Edit history (diffs) is permanently removed
3. The record can be restored using `manage_deleted.py`

## Development

### Project Structure

```
mlx_whisper/
├── app/
│   ├── models.py           # SQLAlchemy models
│   ├── database.py         # Database configuration
│   ├── routers/
│   │   └── transcription.py  # API endpoints
│   └── main.py             # FastAPI application
├── manage_deleted.py       # Deleted transcription management
├── start.sh               # Backend startup script
└── requirements.txt       # Python dependencies
```

### Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run tests (if available)
pytest
```

## Configuration

### Environment Variables

- `WHISPER_DB_PASSWORD` - PostgreSQL password (required)
- `OLLAMA_URL` - Ollama API endpoint (default: via Tailscale)
- `WHISPERX_URL` - WhisperX service endpoint (default: via Tailscale)

### Database Connection

The service connects to PostgreSQL at `localhost:5432` using credentials:
- Database: `whisper`
- User: `whisper`
- Password: From `WHISPER_DB_PASSWORD` environment variable

## License

Private project - All rights reserved
