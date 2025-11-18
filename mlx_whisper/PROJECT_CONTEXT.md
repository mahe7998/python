# WhisperX Transcription Project - Context

**Last Updated**: 2025-11-18

## Project Overview

A real-time audio transcription system with AI-powered review capabilities. The system consists of a FastAPI backend, React frontend, and PostgreSQL database, all containerized with Docker.

## Architecture

### Stack
- **Backend**: FastAPI (Python) - Real-time WebSocket transcription + REST API
- **Frontend**: React + Vite + TipTap editor - Web interface at https://whisper.tail60cd1d.ts.net
- **Database**: PostgreSQL - Transcriptions with soft delete and edit history
- **AI Services**:
  - WhisperX (via Tailscale) - Audio transcription
  - Ollama (via Tailscale) - Text processing (grammar, rephrasing, summarization)

### Key Components

1. **Backend API** (`app/`)
   - `main.py` - FastAPI application entry point
   - `routers/transcription.py` - CRUD endpoints for transcriptions
   - `routers/websocket.py` - Real-time transcription WebSocket
   - `models.py` - SQLAlchemy database models
   - `database.py` - Database connection and session management
   - `whisper_service.py` - WhisperX integration
   - `diff_service.py` - Edit history tracking

2. **Frontend** (`whisper-project/whisper-frontend/src/`)
   - `App.jsx` - Main application component
   - `components/AudioRecorder.jsx` - Recording controls
   - `components/TranscriptionEditor.jsx` - TipTap rich text editor
   - `components/TranscriptionSelector.jsx` - Dropdown to load saved transcriptions

3. **Management Scripts**
   - `manage_deleted.py` - List and restore deleted transcriptions
   - `start.sh` - Backend startup script

## Recent Changes (November 2025)

### UI Improvements
- **Dark Theme**: Updated TranscriptionSelector with dark grey background, white text
- **Compact Layout**: Reduced Audio Recording window height, aligned controls horizontally
- **Append Mode**: New recordings append to existing selected transcriptions instead of replacing
- **Duplication Fix**: Prevented stale data from duplicating when switching transcriptions
- **Dropdown Refresh**: Transcription list auto-refreshes after save/delete operations

### Backend Fixes
- **Delete Button**: Fixed always-disabled state by tracking programmatic vs user edits
- **Deletion Logic**: Fixed circular FK constraint issues with proper diff cleanup
- **Soft Delete**: Only saves latest content to deleted_transcriptions, not full history
- **Summarize Removal**: Removed standalone Summarize button (now only in save flow)

### New Features
- **AI-Powered Titles**: Automatic summary generation when saving transcriptions
- **Summary Modal**: User can review/edit AI-generated title before saving
- **Deleted Management**: New `manage_deleted.py` script to list and restore deleted records

## Database Schema

### Tables

**transcriptions** (Main active records)
- `id` (PK) - Unique identifier
- `title` - User-friendly title/summary
- `content_md` - Original transcription content
- `current_content_md` - Latest edited content
- `current_diff_id` (FK) - Reference to latest diff
- `created_at`, `updated_at`, `last_modified_at` - Timestamps
- `audio_file_path` - Path to audio file
- `duration_seconds` - Audio duration
- `speaker_map` - Speaker identification data
- `extra_metadata` - Additional metadata
- `is_reviewed` - Review flag

**deleted_transcriptions** (Soft delete storage)
- Same fields as transcriptions
- `deleted_at` - Deletion timestamp
- `deleted_reason` - Optional deletion reason
- Only stores latest content, not edit history

**transcription_diffs** (Edit history)
- `id` (PK)
- `transcription_id` (FK) - Parent transcription
- `content_md` - Content at this version
- `created_at` - When edit was made

### Soft Delete Behavior

When deleting a transcription:
1. Latest content saved to `deleted_transcriptions`
2. `current_diff_id` cleared to avoid FK constraint issues
3. All `transcription_diffs` records permanently deleted
4. Record removed from `transcriptions` table

Restoring a transcription:
1. Creates new record in `transcriptions` with same ID
2. No diff history restored (starts fresh)
3. Removes from `deleted_transcriptions`

## Important Workflows

### Recording and Saving
1. User selects existing transcription (optional) or starts fresh
2. Clicks "Start Recording" - audio streams to WhisperX via WebSocket
3. Transcription appears in editor in real-time (appended if existing transcription loaded)
4. User can edit content using TipTap editor
5. Clicks "Save" → AI generates summary → User reviews/edits summary → Saves to database
6. Dropdown refreshes to show new/updated transcription

### AI Review
- **Fix Grammar**: Corrects grammatical errors
- **Rephrase**: Rewords for clarity
- **Improve**: Enhances overall quality
- Summary generation happens automatically on save

### Managing Deleted Records
```bash
# List all deleted transcriptions
python manage_deleted.py list

# Restore a specific transcription
python manage_deleted.py restore <ID>
```

## Environment Setup

### Required Environment Variables
- `WHISPER_DB_PASSWORD` - PostgreSQL password (must be set on local machine)

### Database Connection
- **From Docker**: `postgresql+asyncpg://whisper:${WHISPER_DB_PASSWORD}@whisper-db:5432/whisper`
- **From Host**: `postgresql+asyncpg://whisper:${WHISPER_DB_PASSWORD}@localhost:5432/whisper`

### Docker Services
- `whisper-db` - PostgreSQL on port 5432
- `whisper-frontend` - React app (served via Traefik)
- `whisper-traefik` - Reverse proxy with Tailscale HTTPS
- `whisper-tailscale` - Tailscale sidecar for networking

## Key Design Decisions

### Programmatic Update Tracking
The frontend uses `isProgrammaticUpdateRef` to distinguish between:
- **Programmatic updates**: Loading saved transcriptions, receiving WebSocket data
- **User edits**: Typing in the editor

This prevents false "modified" states and enables proper delete button behavior.

### Sliding Window Transcription
Backend sends deduplicated text chunks to frontend. Frontend appends new content without re-sending entire transcription each time.

### Stale Data Prevention
`justLoadedTranscriptionRef` flag prevents processing stale WebSocket data immediately after loading a saved transcription.

## Known Considerations

1. **Edit History Not Restored**: When restoring deleted transcriptions, diff history is lost
2. **ID Conflicts**: Restore fails if transcription ID already exists in main table
3. **No Audio Persistence**: Audio files are not managed by deletion/restore system
4. **Single User**: No authentication or multi-user support currently

## Common Commands

```bash
# Start backend server
cd /Users/jmahe/projects/python/mlx_whisper
./start.sh

# Rebuild frontend (force no cache)
cd /Users/jmahe/projects/docker/n8n-compose
docker-compose build --no-cache whisper-frontend
docker-compose up -d --force-recreate whisper-frontend

# List deleted transcriptions
cd /Users/jmahe/projects/python/mlx_whisper
source venv/bin/activate
python manage_deleted.py list

# Access application
# https://whisper.tail60cd1d.ts.net (from other devices on Tailscale network)
```

## Repository Structure

```
/Users/jmahe/projects/
├── python/mlx_whisper/              # Backend Python code
│   ├── app/                         # FastAPI application
│   ├── manage_deleted.py            # Deleted transcription management
│   ├── start.sh                     # Backend startup script
│   ├── requirements.txt             # Python dependencies
│   └── README.md                    # Project documentation
│
└── docker/n8n-compose/              # Docker deployment
    ├── whisper-project/
    │   ├── whisper-frontend/        # React frontend
    │   │   └── src/
    │   │       ├── components/      # React components
    │   │       └── services/        # API clients
    │   └── init-db.sql              # Database schema
    └── docker-compose.yml           # Service orchestration
```

## Next Session Tips

1. **Browser Cache**: When frontend changes don't appear, use `docker-compose build --no-cache` and hard refresh (Cmd+Shift+R)
2. **Database Password**: Always use `WHISPER_DB_PASSWORD` environment variable, never hardcode
3. **Testing Deletions**: Remember to check both main table and deleted_transcriptions table
4. **Frontend State**: Watch for `isProgrammaticUpdateRef` when modifying editor behavior
5. **Background Processes**: Multiple background bash shells may be running - check with BashOutput tool if needed

## Success Metrics

✅ Real-time transcription working
✅ Append mode functional
✅ AI-powered summaries on save
✅ Soft delete with restore capability
✅ Dark theme UI implemented
✅ No content duplication bugs
✅ Dropdown refreshes after operations
✅ Delete button properly enabled/disabled

## Future Enhancements (Ideas)

- Audio file management in soft delete system
- Multi-user authentication
- Export to Obsidian integration
- Speaker diarization improvements
- Real-time collaboration
- Transcription templates
- Search and filtering capabilities
