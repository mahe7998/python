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
from app.whisper_service import get_whisper_service, CUDAWhisperService
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
    """
    try:
        transcription_data = data.model_dump()
        transcription = Transcription(
            **transcription_data,
            current_content_md=transcription_data['content_md']
        )
        db.add(transcription)
        await db.commit()
        await db.refresh(transcription)

        logger.info(f"Created transcription: {transcription.id}")

        return TranscriptionResponse(
            id=transcription.id,
            title=transcription.title,
            content_md=transcription.current_content_md,
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
    """
    try:
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
    """
    try:
        query = select(Transcription)

        if reviewed_only is not None:
            query = query.where(Transcription.is_reviewed == reviewed_only)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(desc(Transcription.created_at))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        transcriptions = result.scalars().all()

        transcription_responses = [
            TranscriptionResponse(
                id=t.id,
                title=t.title,
                content_md=t.current_content_md,
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
    """
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, ollama_client.client.list)

        models = []
        model_list = response.models if hasattr(response, 'models') else response.get('models', [])

        thinking_model_patterns = [
            'deepseek-r1',
            'qwen3:',
            'qwq',
            'o1',
        ]

        for model in model_list:
            name = model.model if hasattr(model, 'model') else model.get('name', '')

            name_lower = name.lower()
            is_thinking_model = any(pattern in name_lower for pattern in thinking_model_patterns)
            if is_thinking_model:
                logger.debug(f"Filtering out thinking model: {name}")
                continue

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
    """
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: ollama_client.client.show(model_name)
        )

        model_info = {
            'name': model_name,
            'context_length': 4096,
        }

        if hasattr(response, 'modelinfo'):
            modelinfo = response.modelinfo
            if isinstance(modelinfo, dict):
                if 'general.context_length' in modelinfo:
                    model_info['context_length'] = modelinfo['general.context_length']
        elif isinstance(response, dict):
            if 'modelinfo' in response and isinstance(response['modelinfo'], dict):
                if 'general.context_length' in response['modelinfo']:
                    model_info['context_length'] = response['modelinfo']['general.context_length']
            if 'parameters' in response:
                params_str = response.get('parameters', '')
                if isinstance(params_str, str):
                    import re
                    match = re.search(r'num_ctx\s+(\d+)', params_str)
                    if match:
                        model_info['context_length'] = int(match.group(1))

        logger.info(f"Got model info for {model_name}: context_length={model_info['context_length']}")
        return model_info

    except Exception as e:
        logger.error(f"Error getting Ollama model info for {model_name}: {e}")
        return {
            'name': model_name,
            'context_length': 4096,
            'error': str(e)
        }


class TranscribePathRequest(BaseModel):
    """Request body for transcribing by file path"""
    audio_path: str
    language: Optional[str] = None


async def get_audio_duration(audio_path: str) -> float:
    """Get audio duration using ffprobe"""
    import subprocess

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

    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error',
             '-read_intervals', '99999%+#1000',
             '-show_entries', 'packet=pts_time',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            capture_output=True, text=True, timeout=5
        )
        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip() and l.strip() != 'N/A']
        if lines:
            return float(lines[-1])
    except Exception as e:
        logger.debug(f"Packet timestamp method failed: {e}")

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
    """
    from pathlib import Path

    if audio_path.startswith('/api/audio/'):
        filename = audio_path.replace('/api/audio/', '')
        audio_dir = Path.home() / "projects" / "python" / "cuda_whisper" / "audio"
        audio_path = str(audio_dir / filename)

    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    duration = await get_audio_duration(audio_path)
    estimated_seconds = max(5, duration / 10)

    return {
        "duration": duration,
        "estimated_transcription_seconds": estimated_seconds
    }


@router.post("/transcribe-path", response_model=dict)
async def transcribe_audio_by_path(
    request: TranscribePathRequest,
    whisper_service: CUDAWhisperService = Depends(get_whisper_service),
):
    """
    Transcribe an audio file by its server path.
    """
    from pathlib import Path

    try:
        audio_path = request.audio_path
        if audio_path.startswith('/api/audio/'):
            filename = audio_path.replace('/api/audio/', '')
            audio_dir = Path.home() / "projects" / "python" / "cuda_whisper" / "audio"
            audio_path = str(audio_dir / filename)

        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail=f"Audio file not found: {request.audio_path}")

        logger.info(f"Re-transcribing file: {audio_path}, language: {request.language}")
        segments = await whisper_service.transcribe_audio(
            audio_path,
            language=request.language if request.language and request.language != 'auto' else None
        )

        full_text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
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
    Get a specific transcription by ID
    """
    try:
        result = await db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        if validate and transcription.current_diff_id:
            diffs_result = await db.execute(
                select(TranscriptionDiff)
                .where(TranscriptionDiff.transcription_id == transcription_id)
                .order_by(TranscriptionDiff.sequence_number)
            )
            diffs = diffs_result.scalars().all()

            if diffs:
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

        return TranscriptionResponse(
            id=transcription.id,
            title=transcription.title,
            content_md=transcription.current_content_md,
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
    """
    try:
        result = await db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        update_data = data.model_dump(exclude_unset=True)

        if 'content_md' in update_data:
            new_content = update_data['content_md']
            old_content = transcription.current_content_md

            if new_content != old_content:
                diff_patch = DiffService.generate_diff(old_content, new_content)
                summary = DiffService.generate_summary(old_content, new_content)

                max_seq_result = await db.execute(
                    select(func.max(TranscriptionDiff.sequence_number))
                    .where(TranscriptionDiff.transcription_id == transcription_id)
                )
                max_seq = max_seq_result.scalar_one_or_none() or 0
                next_seq = max_seq + 1

                new_diff = TranscriptionDiff(
                    transcription_id=transcription_id,
                    diff_patch=diff_patch,
                    sequence_number=next_seq,
                    summary=summary
                )
                db.add(new_diff)
                await db.flush()

                transcription.current_content_md = new_content
                transcription.current_diff_id = new_diff.id
                transcription.last_modified_at = datetime.utcnow()

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
                    logger.warning(
                        f"Patch chain validation warning for transcription {transcription_id}: {error_msg}."
                    )
                else:
                    logger.info(f"Patch chain validated successfully for transcription {transcription_id}")

                logger.info(f"Created diff {new_diff.id} for transcription {transcription_id}")

            del update_data['content_md']

        for field, value in update_data.items():
            setattr(transcription, field, value)

        await db.commit()
        await db.refresh(transcription)

        logger.info(f"Updated transcription: {transcription_id}")

        return TranscriptionResponse(
            id=transcription.id,
            title=transcription.title,
            content_md=transcription.current_content_md,
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
    Soft delete a transcription
    """
    try:
        result = await db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        deleted = DeletedTranscription(
            id=transcription.id,
            created_at=transcription.created_at,
            updated_at=transcription.updated_at,
            title=transcription.title,
            content_md=transcription.current_content_md,
            current_content_md=transcription.current_content_md,
            current_diff_id=None,
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

        transcription.current_diff_id = None
        await db.flush()

        result = await db.execute(
            select(TranscriptionDiff).where(TranscriptionDiff.transcription_id == transcription_id)
        )
        diffs = result.scalars().all()
        for diff in diffs:
            await db.delete(diff)
        await db.flush()

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
    Get modification history for a transcription
    """
    try:
        result = await db.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

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
    whisper_service: CUDAWhisperService = Depends(get_whisper_service),
):
    """
    Transcribe an uploaded audio file
    """
    try:
        import uuid
        filename = f"{uuid.uuid4()}.{file.filename.split('.')[-1]}"
        audio_data = await file.read()
        audio_path = await whisper_service.save_audio_chunk(audio_data, filename)

        logger.info(f"Transcribing file: {filename}")
        segments = await whisper_service.transcribe_audio(audio_path)

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
    Start an async AI review job
    """
    try:
        text = request.text
        action = request.action
        model = request.model
        context_words = request.context_words

        if not await ollama_client.is_available():
            raise HTTPException(
                status_code=503,
                detail="Ollama AI service is not available"
            )

        valid_actions = ["fix_grammar", "rephrase", "summarize", "improve", "extract_actions"]
        if action not in valid_actions:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action: {action}. Valid actions: {valid_actions}"
            )

        ai_job_store.cleanup_old_jobs(max_age_hours=1)

        job_id = ai_job_store.create_job(action, text, model, context_words)

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
    """
    job = ai_job_store.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

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
    Use Ollama AI to review/rewrite text (synchronous)
    """
    try:
        text = request.text
        action = request.action
        model = request.model
        context_words = request.context_words

        if not await ollama_client.is_available():
            raise HTTPException(
                status_code=503,
                detail="Ollama AI service is not available"
            )

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
    Stream AI review results using Server-Sent Events (SSE)
    """
    import json

    async def generate_events():
        try:
            text = request.text
            action = request.action
            model = request.model or ollama_client.default_model
            context_words = request.context_words or ollama_client.max_context_words

            if not await ollama_client.is_available():
                yield f"event: error\ndata: {json.dumps({'message': 'Ollama AI service is not available'})}\n\n"
                return

            valid_actions = ["fix_grammar", "rephrase", "summarize", "improve", "extract_actions"]
            if action not in valid_actions:
                yield f"event: error\ndata: {json.dumps({'message': f'Unknown action: {action}'})}\n\n"
                return

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

            chunks = ollama_client._chunk_text_at_sentences(text, context_words)
            total_chunks = len(chunks)

            logger.info(f"SSE AI review starting: {action}, {total_chunks} chunks, model: {model}")

            yield f"event: start\ndata: {json.dumps({'total_chunks': total_chunks, 'action': action, 'model': model})}\n\n"

            for i, chunk in enumerate(chunks):
                chunk_words = len(chunk.split())
                logger.info(f"SSE processing chunk {i+1}/{total_chunks} ({chunk_words} words)")

                yield f"event: processing\ndata: {json.dumps({'chunk_index': i, 'total_chunks': total_chunks, 'chunk_words': chunk_words})}\n\n"

                try:
                    chunk_result = await ollama_client.rewrite_text(chunk, instruction, model)

                    yield f"event: progress\ndata: {json.dumps({'chunk_index': i, 'total_chunks': total_chunks, 'chunk_result': chunk_result})}\n\n"

                except Exception as chunk_error:
                    logger.error(f"Error processing chunk {i+1}: {chunk_error}")
                    yield f"event: error\ndata: {json.dumps({'message': f'Error processing chunk {i+1}: {str(chunk_error)}'})}\n\n"
                    return

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
            "X-Accel-Buffering": "no",
        }
    )
