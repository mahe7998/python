#!/usr/bin/env python3
"""
Script to manage deleted transcriptions
- List all deleted transcriptions with summaries
- Restore transcriptions back to main database

Usage:
    export WHISPER_DB_PASSWORD='your_password_here'
    python manage_deleted.py list
    python manage_deleted.py restore <ID>
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models import Transcription, DeletedTranscription

# Get password from environment variable
DB_PASSWORD = os.environ.get('WHISPER_DB_PASSWORD')
if not DB_PASSWORD:
    print("Error: WHISPER_DB_PASSWORD environment variable not set")
    print("Please set it using: export WHISPER_DB_PASSWORD='your_password_here'")
    sys.exit(1)

# Use localhost for accessing DB from outside Docker
DATABASE_URL = f"postgresql+asyncpg://whisper:{DB_PASSWORD}@localhost:5432/whisper"


async def list_deleted_transcriptions():
    """List all deleted transcriptions with summaries"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(DeletedTranscription).order_by(desc(DeletedTranscription.deleted_at))
        )
        deleted_transcriptions = result.scalars().all()

        if not deleted_transcriptions:
            print("\nNo deleted transcriptions found.")
            return

        print("\n" + "="*80)
        print("DELETED TRANSCRIPTIONS")
        print("="*80)

        for dt in deleted_transcriptions:
            # Get content preview (first 100 chars)
            content_preview = dt.content_md[:100] if dt.content_md else ""
            if len(dt.content_md or "") > 100:
                content_preview += "..."

            print(f"\nID: {dt.id}")
            print(f"Title: {dt.title}")
            print(f"Content Preview: {content_preview}")
            print(f"Created: {dt.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Deleted: {dt.deleted_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if dt.deleted_reason:
                print(f"Reason: {dt.deleted_reason}")
            print("-" * 80)

        print(f"\nTotal deleted transcriptions: {len(deleted_transcriptions)}\n")

    await engine.dispose()


async def restore_transcription(transcription_id: int):
    """Restore a deleted transcription back to the main database"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Find the deleted transcription
        result = await session.execute(
            select(DeletedTranscription).where(DeletedTranscription.id == transcription_id)
        )
        deleted = result.scalar_one_or_none()

        if not deleted:
            print(f"\nError: No deleted transcription found with ID {transcription_id}")
            return False

        # Check if ID already exists in main table
        existing = await session.execute(
            select(Transcription).where(Transcription.id == transcription_id)
        )
        if existing.scalar_one_or_none():
            print(f"\nError: Transcription ID {transcription_id} already exists in main database")
            print("Choose a different ID or delete the existing one first.")
            return False

        # Create new transcription from deleted data
        restored = Transcription(
            id=deleted.id,
            created_at=deleted.created_at,
            updated_at=datetime.now(timezone.utc),
            title=deleted.title,
            content_md=deleted.content_md,
            current_content_md=deleted.current_content_md,
            current_diff_id=None,  # No diffs when restoring
            last_modified_at=deleted.last_modified_at,
            audio_file_path=deleted.audio_file_path,
            duration_seconds=deleted.duration_seconds,
            speaker_map=deleted.speaker_map,
            extra_metadata=deleted.extra_metadata,
            is_reviewed=deleted.is_reviewed,
        )

        session.add(restored)

        # Remove from deleted table
        await session.delete(deleted)

        await session.commit()

        print(f"\n✅ Successfully restored transcription ID {transcription_id}")
        print(f"   Title: {restored.title}")
        print(f"   Content length: {len(restored.content_md)} characters\n")

        return True

    await engine.dispose()


async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  List deleted transcriptions:    python manage_deleted.py list")
        print("  Restore a transcription:        python manage_deleted.py restore <ID>")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "list":
        await list_deleted_transcriptions()

    elif command == "restore":
        if len(sys.argv) < 3:
            print("Error: Please provide a transcription ID to restore")
            print("Usage: python manage_deleted.py restore <ID>")
            sys.exit(1)

        try:
            transcription_id = int(sys.argv[2])
            await restore_transcription(transcription_id)
        except ValueError:
            print(f"Error: Invalid ID '{sys.argv[2]}'. Must be an integer.")
            sys.exit(1)

    else:
        print(f"Error: Unknown command '{command}'")
        print("Valid commands: list, restore")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
