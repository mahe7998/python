"""
REST API router for transcription CRUD operations
"""
from typing import List, Optional, Dict, Any
import logging
import asyncio
import uuid
import os
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, insert

from app.database import get_db
from app.models import (
    Transcription,
    TranscriptionDiff,
    DeletedTranscription,
    TranscriptionCreate,
    TranscriptionUpdate,
    TranscriptionResponse,
    TranscriptionListResponse,
    TranscriptionSummary,
    DiffResponse,
    AIReviewRequest,
)
from app.whisper_service import get_whisper_service, MLXWhisperService
from app.ollama_client import get_ollama_client, OllamaClient
from app.diff_service import DiffService

logger = logging.getLogger(__name__)


# ============================================================================
# Background Job System for AI Processing
# ============================================================================

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AIJobStore:
    """Simple in-memory store for AI processing jobs"""

    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def create_job(self, action: str, text: str, model: Optional[str] = None, context_words: Optional[int] = None) -> str:
        """Create a new job and return its ID"""
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            "id": job_id,
            "status": JobStatus.PENDING,
            "action": action,
            "text": text,
            "model": model,
            "context_words": context_words,
            "result": None,
            "error": None,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
        }
        logger.info(f"Created AI job {job_id} for action: {action} (context_words: {context_words})")
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID"""
        return self.jobs.get(job_id)

    def update_job(self, job_id: str, **kwargs):
        """Update job fields"""
        if job_id in self.jobs:
            self.jobs[job_id].update(kwargs)

    def cleanup_old_jobs(self, max_age_hours: int = 1):
        """Remove jobs older than max_age_hours"""
        now = datetime.utcnow()
        to_remove = []
        for job_id, job in self.jobs.items():
            created = datetime.fromisoformat(job["created_at"])
            age_hours = (now - created).total_seconds() / 3600
            if age_hours > max_age_hours:
                to_remove.append(job_id)

        for job_id in to_remove:
            del self.jobs[job_id]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old AI jobs")


# Global job store instance
ai_job_store = AIJobStore()

router = APIRouter(prefix="/api/transcriptions", tags=["transcriptions"])


@router.post("", response_model=TranscriptionResponse, status_code=201)
async def create_transcription(
    data: TranscriptionCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new transcription

    Args:
        data: Transcription data
        db: Database session

    Returns:
        Created transcription
    """
    try:
        # Set both content_md (original) and current_content_md (current) to the same initial value
        transcription_data = data.model_dump()
        transcription = Transcription(
            **transcription_data,
            current_content_md=transcription_data['content_md']  # Initialize current with original
        )
        db.add(transcription)
        await db.commit()
        await db.refresh(transcription)

        logger.info(f"Created transcription: {transcription.id}")

        # Return current_content_md as content_md (frontend expects current version)
        return TranscriptionResponse(
            id=transcription.id,
            title=transcription.title,
            content_md=transcription.current_content_md,  # Map current to content_md
            audio_file_path=transcription.audio_file_path,
            duration_seconds=transcription.duration_seconds,
            speaker_map=transcription.speaker_map,
            extra_metadata=transcription.extra_metadata,
            is_reviewed=transcription.is_reviewed,
            created_at=transcription.created_at,
            updated_at=transcription.updated_at,
            last_modified_at=transcription.last_modified_at,
            current_diff_id=transcription.current_diff_id
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summaries", response_model=List[TranscriptionSummary])
async def list_transcription_summaries(
    db: AsyncSession = Depends(get_db),
):
    """
    List all transcriptions in summary format (for dropdown)

    Returns:
        List of transcription summaries with dates and modification counts
    """
    try:
        # Query transcriptions with modification count and content preview
        query = select(
            Transcription.id,
            Transcription.title,
            Transcription.current_content_md,
            Transcription.created_at,
            Transcription.last_modified_at,
            func.count(TranscriptionDiff.id).label('modification_count')
        ).outerjoin(
            TranscriptionDiff,
            Transcription.id == TranscriptionDiff.transcription_id
        ).group_by(
            Transcription.id
        ).order_by(
            desc(func.coalesce(Transcription.last_modified_at, Transcription.created_at))
        )

        result = await db.execute(query)
        rows = result.all()

        summaries = [
            TranscriptionSummary(
                id=row.id,
                title=row.title,
                content_preview=row.current_content_md[:100] if row.current_content_md else None,
                created_at=row.created_at,
                last_modified_at=row.last_modified_at,
                modification_count=row.modification_count
            )
            for row in rows
        ]

        return summaries

    except Exception as e:
        logger.error(f"Error listing transcription summaries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=TranscriptionListResponse)
async def list_transcriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    reviewed_only: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List transcriptions with pagination

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page
        reviewed_only: Filter by review status
        db: Database session

    Returns:
        List of transcriptions with pagination metadata
    """
    try:
        # Build query
        query = select(Transcription)

        if reviewed_only is not None:
            query = query.where(Transcription.is_reviewed == reviewed_only)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        # Apply pagination and ordering
        query = query.order_by(desc(Transcription.created_at))
        query = query.offset((page - 1) * page_size).limit(page_size)

        # Execute query
        result = await db.execute(query)
        transcriptions = result.scalars().all()

        # Map current_content_md to content_md for each transcription
        transcription_responses = [
            TranscriptionResponse(
                id=t.id,
                title=t.title,
                content_md=t.current_content_md,  # Map current to content_md
                audio_file_path=t.audio_file_path,
                duration_seconds=t.duration_seconds,
                speaker_map=t.speaker_map,
                extra_metadata=t.extra_metadata,
                is_reviewed=t.is_reviewed,
                created_at=t.created_at,
                updated_at=t.updated_at,
                last_modified_at=t.last_modified_at,
                current_diff_id=t.current_diff_id
            )
            for t in transcriptions
        ]

        return TranscriptionListResponse(
            transcriptions=transcription_responses,
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"Error listing transcriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ollama-models")
async def list_ollama_models(
    ollama_client: OllamaClient = Depends(get_ollama_client),
):
    """
    List available Ollama models

    Returns:
        List of available models with name and size
    """
    try:
        import asyncio

        # Get list of models from Ollama
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, ollama_client.client.list)

        models = []
        # Response is a Pydantic ListResponse with .models attribute
        model_list = response.models if hasattr(response, 'models') else response.get('models', [])

        # Filter out thinking/reasoning models - they're too slow for quick text review
        # These models do extended chain-of-thought which isn't needed for grammar fixes
        thinking_model_patterns = [
            'deepseek-r1',  # DeepSeek reasoning models
            'qwen3:',       # Qwen3 models have thinking by default (use qwen2.5 instead)
            'qwq',          # Qwen QwQ reasoning models
            'o1',           # OpenAI-style reasoning models
        ]

        for model in model_list:
            # Model objects have .model attribute for the name
            name = model.model if hasattr(model, 'model') else model.get('name', '')

            # Skip thinking models
            name_lower = name.lower()
            is_thinking_model = any(pattern in name_lower for pattern in thinking_model_patterns)
            if is_thinking_model:
                logger.debug(f"Filtering out thinking model: {name}")
                continue

            # Format size to human readable
            size_bytes = model.size if hasattr(model, 'size') else model.get('size', 0)
            if size_bytes > 1e9:
                size_str = f"{size_bytes / 1e9:.1f}GB"
            elif size_bytes > 1e6:
                size_str = f"{size_bytes / 1e6:.0f}MB"
            else:
                size_str = ""

            models.append({
                'name': name,
                'size': size_str,
            })

        logger.info(f"Listed {len(models)} Ollama models")
        return models

    except Exception as e:
        logger.error(f"Error listing Ollama models: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to list Ollama models: {str(e)}")


@router.get("/ollama-model-info/{model_name:path}")
async def get_ollama_model_info(
    model_name: str,
    ollama_client: OllamaClient = Depends(get_ollama_client),
):
    """
    Get information about an Ollama model including context window size

    Args:
        model_name: Name of the model to query

    Returns:
        Model info including context_length
    """
    try:
        import asyncio

        # Get model info from Ollama
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: ollama_client.client.show(model_name)
        )

        # Extract relevant info
        # Ollama returns modelinfo with context_length in the parameters or modelfile
        model_info = {
            'name': model_name,
            'context_length': 4096,  # Default fallback
        }

        # Try to get context_length from model parameters
        if hasattr(response, 'modelinfo'):
            modelinfo = response.modelinfo
            if isinstance(modelinfo, dict):
                # Check for num_ctx in modelinfo
                if 'general.context_length' in modelinfo:
                    model_info['context_length'] = modelinfo['general.context_length']
        elif isinstance(response, dict):
            # Try model_info dict
            if 'modelinfo' in response and isinstance(response['modelinfo'], dict):
                if 'general.context_length' in response['modelinfo']:
                    model_info['context_length'] = response['modelinfo']['general.context_length']
            # Also check parameters (Ollama >= 0.1.30)
            if 'parameters' in response:
                params_str = response.get('parameters', '')
                if isinstance(params_str, str):
                    # Parse num_ctx from parameters string
                    import re
                    match = re.search(r'num_ctx\s+(\d+)', params_str)
                    if match:
                        model_info['context_length'] = int(match.group(1))

        logger.info(f"Got model info for {model_name}: context_length={model_info['context_length']}")
        return model_info

    except Exception as e:
        logger.error(f"Error getting Ollama model info for {model_name}: {e}")
        # Return default context length on error
        return {
            'name': model_name,
            'context_length': 4096,
            'error': str(e)
        }


class TranscribePathRequest(BaseModel):
    """Request body for transcribing by file path"""
    audio_path: str
    language: Optional[str] = None
    diarize: bool = False


async def get_audio_duration(audio_path: str) -> float:
    """Get audio duration using ffprobe - tries fast methods first, falls back to slower ones"""
    import subprocess

    # Method 1: Try reading duration from format metadata (fastest, but often missing in WebM)
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error',
             '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            capture_output=True, text=True, timeout=2
        )
        duration = result.stdout.strip()
        if duration and duration != 'N/A' and float(duration) > 0:
            return float(duration)
    except Exception as e:
        logger.debug(f"Format duration method failed: {e}")

    # Method 2: Read last packet timestamp (fast for WebM files without header duration)
    # Reads from near end of file to get the last timestamp
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error',
             '-read_intervals', '99999%+#1000',  # Read last 1000 packets from near end
             '-show_entries', 'packet=pts_time',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            capture_output=True, text=True, timeout=5
        )
        # Get the last non-empty line (last packet timestamp)
        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip() and l.strip() != 'N/A']
        if lines:
            return float(lines[-1])
    except Exception as e:
        logger.debug(f"Packet timestamp method failed: {e}")

    # Method 3: Fall back to full stream analysis (slower but reliable)
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error',
             '-show_entries', 'stream=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            capture_output=True, text=True, timeout=30
        )
        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip() and l.strip() != 'N/A']
        if lines:
            return float(lines[0])
    except Exception as e:
        logger.warning(f"Could not get audio duration: {e}")

    return 0.0


@router.get("/audio-duration")
async def get_audio_file_duration(audio_path: str):
    """
    Get the duration of an audio file.
    Used by frontend to estimate transcription time.
    """
    from pathlib import Path

    # Convert API path to filesystem path
    if audio_path.startswith('/api/audio/'):
        filename = audio_path.replace('/api/audio/', '')
        audio_dir = Path.home() / "projects" / "python" / "mlx_whisper" / "audio"
        audio_path = str(audio_dir / filename)

    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    duration = await get_audio_duration(audio_path)
    # Estimate transcription time: roughly 1 second of processing per 10 seconds of audio
    estimated_seconds = max(5, duration / 10)

    return {
        "duration": duration,
        "estimated_transcription_seconds": estimated_seconds
    }


@router.post("/transcribe-path", response_model=dict)
async def transcribe_audio_by_path(
    request: TranscribePathRequest,
    whisper_service: MLXWhisperService = Depends(get_whisper_service),
):
    """
    Transcribe an audio file by its server path.
    Used for re-transcribing existing recordings.

    Args:
        request: Contains audio_path (API path like /api/audio/filename.webm) and optional language
        whisper_service: MLX-Whisper service instance

    Returns:
        Transcription segments and text
    """
    from pathlib import Path

    try:
        # Convert API path to filesystem path
        audio_path = request.audio_path
        if audio_path.startswith('/api/audio/'):
            filename = audio_path.replace('/api/audio/', '')
            audio_dir = Path.home() / "projects" / "python" / "mlx_whisper" / "audio"
            audio_path = str(audio_dir / filename)

        # Verify file exists
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail=f"Audio file not found: {request.audio_path}")

        # Transcribe with optional language
        logger.info(f"Re-transcribing file: {audio_path}, language: {request.language}, diarize: {request.diarize}")
        segments = await whisper_service.transcribe_audio(
            audio_path,
            language=request.language if request.language and request.language != 'auto' else None
        )

        # Apply speaker diarization if requested
        if request.diarize:
            speaker_turns = await whisper_service.run_diarization(audio_path)
            for segment in segments:
                # Find speaker at segment midpoint
                midpoint = (segment.start + segment.end) / 2
                for start, end, speaker in speaker_turns:
                    if start <= midpoint <= end:
                        segment.speaker = speaker
                        break

        # Build full text from segments
        full_text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())

        # Format as markdown
        markdown = whisper_service.format_as_markdown(segments)

        return {
            "segments": [seg.model_dump() for seg in segments],
            "text": full_text,
            "markdown": markdown,
            "duration": segments[-1].end if segments else 0.0,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error re-transcribing audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{transcription_id}", response_model=TranscriptionResponse)
async def get_transcription(
    transcription_id: int,
    validate: bool = Query(True, description="Validate patch chain integrity"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific transcription by ID with optional patch chain validation

    Args:
        transcription_id: Transcription ID
        validate: Whether to validate patch chain integrity
        db: Database session

    Returns:
        Transcription data
    """
    try:
        result = await db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        # Validate patch chain if requested
        if validate and transcription.current_diff_id:
            # Get all diffs for this transcription
            diffs_result = await db.execute(
                select(TranscriptionDiff)
                .where(TranscriptionDiff.transcription_id == transcription_id)
                .order_by(TranscriptionDiff.sequence_number)
            )
            diffs = diffs_result.scalars().all()

            if diffs:
                # Validate patch chain
                patches = [diff.diff_patch for diff in diffs]
                is_valid, error_msg = DiffService.validate_patch_chain(
                    transcription.content_md,
                    patches,
                    transcription.current_content_md
                )

                if not is_valid:
                    logger.warning(
                        f"Patch chain validation failed for transcription {transcription_id}: {error_msg}"
                    )
                    # Log the error but still return the transcription (using current_content_md as fallback)

        # Return current_content_md as content_md (frontend expects current version)
        return TranscriptionResponse(
            id=transcription.id,
            title=transcription.title,
            content_md=transcription.current_content_md,  # Map current to content_md
            audio_file_path=transcription.audio_file_path,
            duration_seconds=transcription.duration_seconds,
            speaker_map=transcription.speaker_map,
            extra_metadata=transcription.extra_metadata,
            is_reviewed=transcription.is_reviewed,
            created_at=transcription.created_at,
            updated_at=transcription.updated_at,
            last_modified_at=transcription.last_modified_at,
            current_diff_id=transcription.current_diff_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{transcription_id}", response_model=TranscriptionResponse)
async def update_transcription(
    transcription_id: int,
    data: TranscriptionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update a transcription with diff tracking

    If content_md is updated, creates a diff and validates the patch chain.

    Args:
        transcription_id: Transcription ID
        data: Updated transcription data
        db: Database session

    Returns:
        Updated transcription
    """
    try:
        # Get existing transcription
        result = await db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        update_data = data.model_dump(exclude_unset=True)

        # Check if content is being updated
        if 'content_md' in update_data:
            new_content = update_data['content_md']
            old_content = transcription.current_content_md

            # Only create diff if content actually changed
            if new_content != old_content:
                # Generate diff patch
                diff_patch = DiffService.generate_diff(old_content, new_content)
                summary = DiffService.generate_summary(old_content, new_content)

                # Get next sequence number
                max_seq_result = await db.execute(
                    select(func.max(TranscriptionDiff.sequence_number))
                    .where(TranscriptionDiff.transcription_id == transcription_id)
                )
                max_seq = max_seq_result.scalar_one_or_none() or 0
                next_seq = max_seq + 1

                # Create new diff record
                new_diff = TranscriptionDiff(
                    transcription_id=transcription_id,
                    diff_patch=diff_patch,
                    sequence_number=next_seq,
                    summary=summary
                )
                db.add(new_diff)
                await db.flush()  # Get the diff ID

                # Update transcription
                transcription.current_content_md = new_content
                transcription.current_diff_id = new_diff.id
                transcription.last_modified_at = datetime.utcnow()

                # Validate patch chain (non-blocking - log warning only)
                diffs_result = await db.execute(
                    select(TranscriptionDiff)
                    .where(TranscriptionDiff.transcription_id == transcription_id)
                    .order_by(TranscriptionDiff.sequence_number)
                )
                all_diffs = diffs_result.scalars().all()
                patches = [d.diff_patch for d in all_diffs]

                is_valid, error_msg = DiffService.validate_patch_chain(
                    transcription.content_md,
                    patches,
                    transcription.current_content_md
                )

                if not is_valid:
                    # Log warning but don't block - we have current_content_md as fallback
                    logger.warning(
                        f"Patch chain validation warning for transcription {transcription_id}: {error_msg}. "
                        f"This is typically due to whitespace/formatting differences. "
                        f"Using cached current_content_md as source of truth."
                    )
                else:
                    logger.info(f"Patch chain validated successfully for transcription {transcription_id}")

                logger.info(f"Created diff {new_diff.id} for transcription {transcription_id}")

            # Remove content_md from update_data (we handled it above)
            del update_data['content_md']

        # Update other fields
        for field, value in update_data.items():
            setattr(transcription, field, value)

        await db.commit()
        await db.refresh(transcription)

        logger.info(f"Updated transcription: {transcription_id}")

        # Return current_content_md as content_md (frontend expects current version)
        return TranscriptionResponse(
            id=transcription.id,
            title=transcription.title,
            content_md=transcription.current_content_md,  # Map current to content_md
            audio_file_path=transcription.audio_file_path,
            duration_seconds=transcription.duration_seconds,
            speaker_map=transcription.speaker_map,
            extra_metadata=transcription.extra_metadata,
            is_reviewed=transcription.is_reviewed,
            created_at=transcription.created_at,
            updated_at=transcription.updated_at,
            last_modified_at=transcription.last_modified_at,
            current_diff_id=transcription.current_diff_id
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{transcription_id}", status_code=204)
async def delete_transcription(
    transcription_id: int,
    reason: Optional[str] = Query(None, description="Reason for deletion"),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft delete a transcription (move to deleted_transcriptions table)

    Args:
        transcription_id: Transcription ID
        reason: Optional reason for deletion
        db: Database session
    """
    try:
        result = await db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        # Copy to deleted_transcriptions table (only keep current content, not history)
        deleted = DeletedTranscription(
            id=transcription.id,
            created_at=transcription.created_at,
            updated_at=transcription.updated_at,
            title=transcription.title,
            content_md=transcription.current_content_md,  # Save latest version as original
            current_content_md=transcription.current_content_md,  # Save latest version
            current_diff_id=None,  # Don't keep diff reference
            last_modified_at=transcription.last_modified_at,
            audio_file_path=transcription.audio_file_path,
            duration_seconds=transcription.duration_seconds,
            speaker_map=transcription.speaker_map,
            extra_metadata=transcription.extra_metadata,
            is_reviewed=transcription.is_reviewed,
            deleted_at=datetime.utcnow(),
            deleted_reason=reason
        )
        db.add(deleted)

        # Clear current_diff_id to avoid circular foreign key constraint
        transcription.current_diff_id = None
        await db.flush()

        # Explicitly delete all diffs first (CASCADE not working as expected)
        result = await db.execute(
            select(TranscriptionDiff).where(TranscriptionDiff.transcription_id == transcription_id)
        )
        diffs = result.scalars().all()
        for diff in diffs:
            await db.delete(diff)
        await db.flush()

        # Now delete the transcription
        await db.delete(transcription)

        await db.commit()

        logger.info(f"Soft deleted transcription: {transcription_id}")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{transcription_id}/history", response_model=List[DiffResponse])
async def get_transcription_history(
    transcription_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get modification history (diffs) for a transcription

    Args:
        transcription_id: Transcription ID
        db: Database session

    Returns:
        List of diffs ordered by sequence number
    """
    try:
        # Check if transcription exists
        result = await db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        # Get all diffs
        diffs_result = await db.execute(
            select(TranscriptionDiff)
            .where(TranscriptionDiff.transcription_id == transcription_id)
            .order_by(TranscriptionDiff.sequence_number)
        )
        diffs = diffs_result.scalars().all()

        return diffs

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcription history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcribe", response_model=dict)
async def transcribe_audio_file(
    file: UploadFile = File(...),
    whisper_service: MLXWhisperService = Depends(get_whisper_service),
):
    """
    Transcribe an uploaded audio file

    Args:
        file: Audio file upload
        whisper_service: MLX-Whisper service instance

    Returns:
        Transcription segments (no speaker diarization in MLX-Whisper)
    """
    try:
        # Save uploaded file
        import uuid
        filename = f"{uuid.uuid4()}.{file.filename.split('.')[-1]}"
        audio_data = await file.read()
        audio_path = await whisper_service.save_audio_chunk(audio_data, filename)

        # Transcribe
        logger.info(f"Transcribing file: {filename}")
        segments = await whisper_service.transcribe_audio(audio_path)

        # Format as markdown
        markdown = whisper_service.format_as_markdown(segments)

        return {
            "segments": [seg.model_dump() for seg in segments],
            "markdown": markdown,
            "audio_path": audio_path,
            "duration": segments[-1].end if segments else 0.0,
        }

    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_ai_job(job_id: str, action: str, text: str, model: Optional[str], context_words: Optional[int], ollama_client: OllamaClient):
    """Background task to process AI job"""
    try:
        ai_job_store.update_job(job_id, status=JobStatus.PROCESSING)
        logger.info(f"Processing AI job {job_id}: {action} (context_words: {context_words})")

        # Perform requested action
        if action == "fix_grammar":
            result = await ollama_client.fix_grammar(text, model=model, context_words=context_words)
        elif action == "rephrase":
            result = await ollama_client.rephrase_professionally(text, model=model, context_words=context_words)
        elif action == "summarize":
            result = await ollama_client.summarize(text, model=model, context_words=context_words)
        elif action == "improve":
            result = await ollama_client.improve_text(text, model=model, context_words=context_words)
        elif action == "extract_actions":
            result = await ollama_client.extract_action_items(text, model=model, context_words=context_words)
        else:
            raise ValueError(f"Unknown action: {action}")

        ai_job_store.update_job(
            job_id,
            status=JobStatus.COMPLETED,
            result=result,
            completed_at=datetime.utcnow().isoformat()
        )
        logger.info(f"AI job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"AI job {job_id} failed: {e}")
        ai_job_store.update_job(
            job_id,
            status=JobStatus.FAILED,
            error=str(e),
            completed_at=datetime.utcnow().isoformat()
        )


@router.post("/ai-review-async", response_model=dict)
async def ai_review_text_async(
    request: AIReviewRequest,
    background_tasks: BackgroundTasks = None,
    ollama_client: OllamaClient = Depends(get_ollama_client),
):
    """
    Start an async AI review job (returns immediately with job ID)

    Use this for longer texts that may timeout with the synchronous endpoint.
    Poll /ai-review-status/{job_id} to check progress and get results.

    Args:
        request: AIReviewRequest with text, action, and optional model

    Returns:
        Job ID to poll for status
    """
    try:
        text = request.text
        action = request.action
        model = request.model
        context_words = request.context_words

        # Check if Ollama is available
        if not await ollama_client.is_available():
            raise HTTPException(
                status_code=503,
                detail="Ollama AI service is not available"
            )

        # Validate action
        valid_actions = ["fix_grammar", "rephrase", "summarize", "improve", "extract_actions"]
        if action not in valid_actions:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action: {action}. Valid actions: {valid_actions}"
            )

        # Cleanup old jobs periodically
        ai_job_store.cleanup_old_jobs(max_age_hours=1)

        # Create job
        job_id = ai_job_store.create_job(action, text, model, context_words)

        # Start background processing
        # Note: We use asyncio.create_task instead of BackgroundTasks for true async
        asyncio.create_task(process_ai_job(job_id, action, text, model, context_words, ollama_client))

        word_count = len(text.split())
        logger.info(f"Started async AI job {job_id}: {action} ({word_count} words, context_words: {context_words})")

        return {
            "job_id": job_id,
            "status": JobStatus.PENDING,
            "action": action,
            "word_count": word_count,
            "message": "Job started. Poll /ai-review-status/{job_id} for results."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting async AI review: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-review-status/{job_id}", response_model=dict)
async def get_ai_review_status(job_id: str):
    """
    Get the status of an async AI review job

    Args:
        job_id: Job ID returned from /ai-review-async

    Returns:
        Job status and result (if completed)
    """
    job = ai_job_store.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Return different response based on status
    response = {
        "job_id": job["id"],
        "status": job["status"],
        "action": job["action"],
        "created_at": job["created_at"],
    }

    if job["status"] == JobStatus.COMPLETED:
        response["result"] = job["result"]
        response["completed_at"] = job["completed_at"]
    elif job["status"] == JobStatus.FAILED:
        response["error"] = job["error"]
        response["completed_at"] = job["completed_at"]

    return response


@router.post("/ai-review", response_model=dict)
async def ai_review_text(
    request: AIReviewRequest,
    ollama_client: OllamaClient = Depends(get_ollama_client),
):
    """
    Use Ollama AI to review/rewrite text (synchronous - may timeout for large texts)

    For large texts (500+ words), use /ai-review-async instead.

    Args:
        request: AIReviewRequest with text, action, and optional model

    Returns:
        Reviewed/rewritten text
    """
    try:
        text = request.text
        action = request.action
        model = request.model
        context_words = request.context_words

        # Check if Ollama is available
        if not await ollama_client.is_available():
            raise HTTPException(
                status_code=503,
                detail="Ollama AI service is not available"
            )

        # Perform requested action with optional model override
        if action == "fix_grammar":
            result = await ollama_client.fix_grammar(text, model=model, context_words=context_words)
        elif action == "rephrase":
            result = await ollama_client.rephrase_professionally(text, model=model, context_words=context_words)
        elif action == "summarize":
            result = await ollama_client.summarize(text, model=model, context_words=context_words)
        elif action == "improve":
            result = await ollama_client.improve_text(text, model=model, context_words=context_words)
        elif action == "extract_actions":
            result = await ollama_client.extract_action_items(text, model=model, context_words=context_words)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action: {action}"
            )

        logger.info(f"AI review completed: {action} (model: {model or 'default'}, context_words: {context_words})")
        return {"original": text, "result": result, "action": action}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during AI review: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai-review-stream")
async def ai_review_text_stream(
    request: AIReviewRequest,
    ollama_client: OllamaClient = Depends(get_ollama_client),
):
    """
    Stream AI review results using Server-Sent Events (SSE).

    Processes text in chunks and streams each chunk's result as it completes.
    This allows the frontend to receive partial results without waiting for the
    entire text to be processed.

    SSE Events:
    - start: {total_chunks, action, model}
    - progress: {chunk_index, total_chunks, chunk_result}
    - complete: {total_chunks, action}
    - error: {message}

    Args:
        request: AIReviewRequest with text, action, and optional model/context_words

    Returns:
        StreamingResponse with SSE events
    """
    import json

    async def generate_events():
        try:
            text = request.text
            action = request.action
            model = request.model or ollama_client.default_model
            context_words = request.context_words or ollama_client.max_context_words

            # Check if Ollama is available
            if not await ollama_client.is_available():
                yield f"event: error\ndata: {json.dumps({'message': 'Ollama AI service is not available'})}\n\n"
                return

            # Validate action
            valid_actions = ["fix_grammar", "rephrase", "summarize", "improve", "extract_actions"]
            if action not in valid_actions:
                yield f"event: error\ndata: {json.dumps({'message': f'Unknown action: {action}'})}\n\n"
                return

            # Get the instruction for this action
            instructions = {
                "fix_grammar": (
                    "Fix all grammar, spelling, and punctuation errors in the following text. "
                    "Preserve the original meaning and style. Only output the corrected text, "
                    "nothing else."
                ),
                "rephrase": (
                    "Rephrase the following text in a more professional and formal tone. "
                    "Maintain the key information but improve clarity and professionalism. "
                    "Only output the rephrased text, nothing else."
                ),
                "improve": (
                    "Improve the following text by fixing grammar, enhancing clarity, "
                    "and improving flow. Preserve the original meaning and style. "
                    "Only output the improved text, nothing else."
                ),
                "summarize": (
                    "Create a very concise summary of the following text in maximum 100 characters. "
                    "Capture the key points and main ideas in a single phrase or sentence. "
                    "Only output the summary, nothing else."
                ),
                "extract_actions": (
                    "Extract all action items from the following text. "
                    "Format as a bulleted list. Only output the action items, nothing else."
                ),
            }
            instruction = instructions[action]

            # Chunk the text
            chunks = ollama_client._chunk_text_at_sentences(text, context_words)
            total_chunks = len(chunks)

            logger.info(f"SSE AI review starting: {action}, {total_chunks} chunks, model: {model}")

            # Send start event
            yield f"event: start\ndata: {json.dumps({'total_chunks': total_chunks, 'action': action, 'model': model})}\n\n"

            # Process each chunk
            for i, chunk in enumerate(chunks):
                chunk_words = len(chunk.split())
                logger.info(f"SSE processing chunk {i+1}/{total_chunks} ({chunk_words} words)")

                # Send processing event
                yield f"event: processing\ndata: {json.dumps({'chunk_index': i, 'total_chunks': total_chunks, 'chunk_words': chunk_words})}\n\n"

                # Process the chunk
                try:
                    chunk_result = await ollama_client.rewrite_text(chunk, instruction, model)

                    # Send progress event with result
                    yield f"event: progress\ndata: {json.dumps({'chunk_index': i, 'total_chunks': total_chunks, 'chunk_result': chunk_result})}\n\n"

                except Exception as chunk_error:
                    logger.error(f"Error processing chunk {i+1}: {chunk_error}")
                    yield f"event: error\ndata: {json.dumps({'message': f'Error processing chunk {i+1}: {str(chunk_error)}'})}\n\n"
                    return

            # Send complete event
            logger.info(f"SSE AI review completed: {action}, {total_chunks} chunks")
            yield f"event: complete\ndata: {json.dumps({'total_chunks': total_chunks, 'action': action})}\n\n"

        except Exception as e:
            logger.error(f"SSE AI review error: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
