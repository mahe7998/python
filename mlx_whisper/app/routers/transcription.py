"""
REST API router for transcription CRUD operations
"""
from typing import List, Optional
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
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
)
from app.whisper_service import get_whisper_service, MLXWhisperService
from app.ollama_client import get_ollama_client, OllamaClient
from app.diff_service import DiffService

logger = logging.getLogger(__name__)

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


@router.post("/ai-review", response_model=dict)
async def ai_review_text(
    text: str,
    action: str = Query(..., description="Action: fix_grammar, rephrase, summarize, improve, extract_actions"),
    ollama_client: OllamaClient = Depends(get_ollama_client),
):
    """
    Use Ollama AI to review/rewrite text

    Args:
        text: Text to review
        action: Action to perform
        ollama_client: Ollama client instance

    Returns:
        Reviewed/rewritten text
    """
    try:
        # Check if Ollama is available
        if not await ollama_client.is_available():
            raise HTTPException(
                status_code=503,
                detail="Ollama AI service is not available"
            )

        # Perform requested action
        if action == "fix_grammar":
            result = await ollama_client.fix_grammar(text)
        elif action == "rephrase":
            result = await ollama_client.rephrase_professionally(text)
        elif action == "summarize":
            result = await ollama_client.summarize(text)
        elif action == "improve":
            result = await ollama_client.improve_text(text)
        elif action == "extract_actions":
            result = await ollama_client.extract_action_items(text)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action: {action}"
            )

        logger.info(f"AI review completed: {action}")
        return {"original": text, "result": result, "action": action}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during AI review: {e}")
        raise HTTPException(status_code=500, detail=str(e))
