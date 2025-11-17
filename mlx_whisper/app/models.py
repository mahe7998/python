"""
SQLAlchemy models for WhisperX transcription system
"""
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

from app.database import Base


class Transcription(Base):
    """
    SQLAlchemy model for transcriptions table
    """
    __tablename__ = "transcriptions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    title = Column(String(255), nullable=False, index=True)
    content_md = Column(Text, nullable=False)  # Original content - never modified
    current_content_md = Column(Text, nullable=False)  # Current content - cached for performance
    current_diff_id = Column(Integer, ForeignKey('transcription_diffs.id', ondelete='SET NULL'), nullable=True)
    last_modified_at = Column(DateTime(timezone=True), nullable=True)
    audio_file_path = Column(String(500), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    speaker_map = Column(JSONB, default={}, nullable=False)
    extra_metadata = Column(JSONB, default={}, nullable=False)
    is_reviewed = Column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    diffs = relationship("TranscriptionDiff", back_populates="transcription", foreign_keys="TranscriptionDiff.transcription_id")
    current_diff = relationship("TranscriptionDiff", foreign_keys=[current_diff_id], post_update=True)


class TranscriptionDiff(Base):
    """
    SQLAlchemy model for transcription_diffs table
    Stores incremental diffs for version control
    """
    __tablename__ = "transcription_diffs"

    id = Column(Integer, primary_key=True, index=True)
    transcription_id = Column(Integer, ForeignKey('transcriptions.id', ondelete='CASCADE'), nullable=False, index=True)
    diff_patch = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    summary = Column(Text, nullable=True)

    # Relationships
    transcription = relationship("Transcription", back_populates="diffs", foreign_keys=[transcription_id])


class DeletedTranscription(Base):
    """
    SQLAlchemy model for deleted_transcriptions table
    Soft-deleted transcriptions for recovery
    """
    __tablename__ = "deleted_transcriptions"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    title = Column(String(255), nullable=False)
    content_md = Column(Text, nullable=False)
    current_content_md = Column(Text, nullable=False)
    current_diff_id = Column(Integer, nullable=True)
    last_modified_at = Column(DateTime(timezone=True), nullable=True)
    audio_file_path = Column(String(500), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    speaker_map = Column(JSONB, default={}, nullable=False)
    extra_metadata = Column(JSONB, default={}, nullable=False)
    is_reviewed = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    deleted_reason = Column(Text, nullable=True)


# Pydantic schemas for API request/response validation

class TranscriptionBase(BaseModel):
    """Base schema for transcription data"""
    title: str = Field(..., min_length=1, max_length=255)
    content_md: str = Field(..., min_length=1)
    audio_file_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    speaker_map: Dict[str, str] = Field(default_factory=dict)
    extra_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        serialization_alias='metadata'
    )
    is_reviewed: bool = False

    model_config = {
        "populate_by_name": True,  # Allow both 'metadata' and 'extra_metadata'
        "from_attributes": True
    }


class TranscriptionCreate(TranscriptionBase):
    """Schema for creating a new transcription"""
    pass


class TranscriptionUpdate(BaseModel):
    """Schema for updating an existing transcription"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content_md: Optional[str] = Field(None, min_length=1)
    speaker_map: Optional[Dict[str, str]] = None
    extra_metadata: Optional[Dict[str, Any]] = Field(None, serialization_alias='metadata')
    is_reviewed: Optional[bool] = None

    model_config = {
        "populate_by_name": True,  # Allow both 'metadata' and 'extra_metadata'
        "from_attributes": True
    }


class TranscriptionResponse(BaseModel):
    """Schema for transcription response - returns current content, not original"""
    id: int
    title: str
    content_md: str  # Will be populated from current_content_md
    audio_file_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    speaker_map: Dict[str, str] = Field(default_factory=dict)
    extra_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        serialization_alias='metadata'
    )
    is_reviewed: bool = False
    created_at: datetime
    updated_at: datetime
    last_modified_at: Optional[datetime] = None
    current_diff_id: Optional[int] = None

    model_config = {
        "populate_by_name": True,
        "from_attributes": True
    }


class TranscriptionSummary(BaseModel):
    """Schema for transcription list items (summary view)"""
    id: int
    title: str
    content_preview: Optional[str] = None  # First 100 chars of content
    created_at: datetime
    last_modified_at: Optional[datetime] = None
    modification_count: int = 0

    class Config:
        from_attributes = True


class DiffResponse(BaseModel):
    """Schema for diff response"""
    id: int
    transcription_id: int
    sequence_number: int
    created_at: datetime
    summary: Optional[str] = None

    class Config:
        from_attributes = True


class TranscriptionListResponse(BaseModel):
    """Schema for list of transcriptions"""
    transcriptions: list[TranscriptionResponse]
    total: int
    page: int
    page_size: int


class WebSocketMessage(BaseModel):
    """Schema for WebSocket messages"""
    type: str  # "audio_chunk", "transcription", "status", "error"
    data: Any


class TranscriptionSegment(BaseModel):
    """Schema for a single transcription segment"""
    text: str
    start: float
    end: float
    speaker: Optional[str] = None  # Optional for backwards compatibility
