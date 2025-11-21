"""
WebSocket router for real-time audio streaming and transcription
"""
import logging
import asyncio
import json
from typing import List
import uuid
from pathlib import Path
import subprocess
import os
import glob

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydub import AudioSegment
import io

from app.whisper_service import get_whisper_service
from app.models import TranscriptionSegment
from app.wav_utils import create_wav_header, update_wav_header, get_wav_data_size

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def preload_model_with_resume(model_name: str, websocket: WebSocket) -> bool:
    """
    Pre-download model using huggingface_hub.snapshot_download with resume support.

    This ensures large files can resume if interrupted and provides better error handling.

    Args:
        model_name: HuggingFace model name (e.g., 'mlx-community/whisper-medium-mlx')
        websocket: WebSocket connection for sending status updates

    Returns:
        True if download successful, False otherwise
    """
    try:
        from huggingface_hub import snapshot_download
        import os

        # Disable XET download system to avoid "CAS service error" issues
        # XET can cause downloads to fail at 99% with incomplete files
        # See: https://github.com/huggingface/xet-core/issues/311
        os.environ["HF_HUB_DISABLE_XET"] = "1"

        # Enable hf_transfer for multi-threaded downloads (8 threads by default)
        # This significantly speeds up large file downloads (can achieve ~2 Gbps)
        os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

        logger.info(f"Pre-downloading model {model_name} with resume support (XET disabled, hf_transfer enabled)...")

        await websocket.send_json({
            "type": "status",
            "message": "Preparing model download..."
        })

        # Get event loop for async execution
        loop = asyncio.get_event_loop()

        # Download model in background thread
        def download_snapshot():
            """Download model files with automatic resume support"""
            return snapshot_download(
                repo_id=model_name,
                resume_download=True,  # Automatic resume for interrupted downloads
                local_files_only=False,
                ignore_patterns=["*.md", "*.txt", ".gitattributes"]  # Skip unnecessary files
            )

        # Run download with progress monitoring
        download_task = loop.run_in_executor(None, download_snapshot)

        # Monitor progress while downloading
        progress_counter = 0
        start_time = asyncio.get_event_loop().time()

        while not download_task.done():
            await asyncio.sleep(3)  # Check every 3 seconds
            progress_counter += 1
            elapsed = int(asyncio.get_event_loop().time() - start_time)

            # Check for incomplete files to show progress
            incomplete_info = get_incomplete_download_info(model_name)

            if incomplete_info:
                await websocket.send_json({
                    "type": "download_progress",
                    "message": f"Downloading model... ({incomplete_info}, {elapsed}s elapsed)",
                    "elapsed_seconds": elapsed,
                })
                logger.info(f"Download progress: {incomplete_info}, {elapsed}s elapsed")
            else:
                await websocket.send_json({
                    "type": "download_progress",
                    "message": f"Downloading model... ({elapsed}s elapsed)",
                    "elapsed_seconds": elapsed,
                })
                logger.info(f"Download progress: {elapsed}s elapsed")

        # Wait for completion
        model_path = await download_task
        logger.info(f"Model {model_name} pre-downloaded successfully to {model_path}")

        return True

    except Exception as e:
        logger.error(f"Error pre-downloading model {model_name}: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "message": f"Failed to download model: {str(e)}"
        })
        return False


def get_incomplete_download_info(model_name: str) -> str:
    """
    Check for incomplete downloads and return progress info.

    Args:
        model_name: HuggingFace model name

    Returns:
        Progress string like "942MB downloaded" or empty string if no incomplete files
    """
    try:
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        model_dir_name = f"models--{model_name.replace('/', '--')}"
        blobs_dir = cache_dir / model_dir_name / "blobs"

        if not blobs_dir.exists():
            return ""

        # Find incomplete files
        incomplete_files = list(blobs_dir.glob("*.incomplete"))

        if incomplete_files:
            # Get size of largest incomplete file
            total_size = 0
            for incomplete_file in incomplete_files:
                total_size += incomplete_file.stat().st_size

            size_mb = total_size / (1024 * 1024)
            return f"{size_mb:.0f}MB downloaded"

        return ""

    except Exception as e:
        logger.debug(f"Error checking incomplete downloads: {e}")
        return ""


def verify_model_download_complete(model_name: str) -> bool:
    """
    Verify that all required model files have been downloaded.

    Args:
        model_name: HuggingFace model name (e.g., 'mlx-community/whisper-medium-mlx')

    Returns:
        True if all required files exist, False otherwise
    """
    # Convert model name to cache directory path
    # HuggingFace caches models at: ~/.cache/huggingface/hub/models--{org}--{model}
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    model_cache_name = f"models--{model_name.replace('/', '--')}"
    model_path = cache_dir / model_cache_name

    if not model_path.exists():
        logger.warning(f"Model cache directory does not exist: {model_path}")
        return False

    # Check for required files in the blobs directory
    blobs_dir = model_path / "blobs"
    if not blobs_dir.exists():
        logger.warning(f"Model blobs directory does not exist: {blobs_dir}")
        return False

    # Required files for a Whisper model:
    # - config.json
    # - weights.npz or weights.safetensors
    # Note: Files are stored as content-addressed blobs, so we check by scanning

    required_extensions = {'.json', '.npz'}  # We need at least config.json and weights.npz
    found_extensions = set()

    # Check all files in blobs directory
    blob_files = list(blobs_dir.iterdir())
    if not blob_files:
        logger.warning(f"No blob files found in {blobs_dir}")
        return False

    total_size = 0
    for blob_file in blob_files:
        if blob_file.is_file():
            file_size = blob_file.stat().st_size
            total_size += file_size

            # Try to guess file type by reading header or extension
            # JSON files typically start with '{'
            # NPZ files have a ZIP signature
            try:
                with open(blob_file, 'rb') as f:
                    header = f.read(512)
                    if header.startswith(b'{'):
                        found_extensions.add('.json')
                        logger.info(f"Found JSON config file: {blob_file.name} ({file_size} bytes)")
                    elif header.startswith(b'PK'):  # ZIP/NPZ signature
                        found_extensions.add('.npz')
                        logger.info(f"Found NPZ weights file: {blob_file.name} ({file_size / 1024 / 1024:.1f} MB)")
            except Exception as e:
                logger.debug(f"Could not read blob file {blob_file}: {e}")

    logger.info(f"Total model size: {total_size / 1024 / 1024:.1f} MB")
    logger.info(f"Found file types: {found_extensions}")

    # Verify we have both required file types
    has_required = required_extensions.issubset(found_extensions)

    if not has_required:
        missing = required_extensions - found_extensions
        logger.warning(f"Model download incomplete. Missing file types: {missing}")
        return False

    # Check minimum size (Tiny model is ~75MB, Medium is ~1.5GB)
    # If model has <10MB, something is wrong
    if total_size < 10 * 1024 * 1024:
        logger.warning(f"Model total size is suspiciously small: {total_size / 1024 / 1024:.1f} MB")
        return False

    logger.info(f"Model download verification passed for {model_name}")
    return True


def align_and_deduplicate_text(previous_text: str, new_text: str, overlap_threshold: int = 10) -> str:
    """
    Align new transcription with previous text and remove duplicates

    Args:
        previous_text: Previously transcribed text
        new_text: Newly transcribed text (may overlap with previous)
        overlap_threshold: Minimum word overlap to consider for alignment

    Returns:
        Only the new portion of text that doesn't duplicate previous text
    """
    if not previous_text:
        logger.info(f"No previous text, returning all new text: '{new_text[:50]}...'")
        return new_text

    if not new_text:
        return ""

    # Split into words for comparison
    prev_words = previous_text.strip().split()
    new_words = new_text.strip().split()

    if not prev_words or not new_words:
        return new_text

    # Look for the longest matching suffix of previous text in new text
    # This handles cases where the new transcription starts partway through previous text
    best_match_idx = 0  # Default: no overlap found, use all new text (start from index 0)
    best_similarity = 0.0
    best_lookback = 0

    # Check last N words of previous text against beginning of new text
    # Require at least 3 words to match to avoid false positives
    for lookback in range(min(overlap_threshold, len(prev_words)), 2, -1):
        prev_suffix = prev_words[-lookback:]

        # Try to find this suffix at the start of new text
        for new_start_idx in range(min(overlap_threshold, len(new_words) - lookback + 1)):
            new_prefix = new_words[new_start_idx:new_start_idx + lookback]

            # Calculate similarity (allow some variation due to transcription differences)
            matches = sum(1 for a, b in zip(prev_suffix, new_prefix) if a.lower() == b.lower())
            similarity = matches / lookback if lookback > 0 else 0

            # If we find a good match (>70% similar), use this as the split point
            if similarity > 0.7:
                best_match_idx = new_start_idx + lookback
                best_similarity = similarity
                best_lookback = lookback
                logger.info(f"Found text overlap: {lookback} words matched at position {new_start_idx}, similarity: {similarity:.2f}")
                logger.info(f"  Previous suffix: '{' '.join(prev_suffix)}'")
                logger.info(f"  New prefix: '{' '.join(new_prefix)}'")
                break

        if best_match_idx > 0:
            break

    # Return only the new portion
    new_portion = " ".join(new_words[best_match_idx:])

    if best_match_idx == 0:
        # No overlap found - return all new text
        logger.info(f"No overlap detected, returning all new text ({len(new_words)} words)")
        logger.info(f"  Previous: '{previous_text[-100:]}'")
        logger.info(f"  New: '{new_text[:100]}'")
    elif not new_portion.strip():
        # Complete duplicate
        logger.info(f"Complete duplicate detected, discarding ({len(new_words)} words matched)")
    else:
        logger.info(f"Removed {best_match_idx} overlapping words, returning {len(new_words) - best_match_idx} new words")
        logger.info(f"  New portion: '{new_portion[:100]}'")

    return new_portion


class AudioBuffer:
    """
    Buffer for accumulating audio chunks with ffmpeg-based sliding window transcription
    Accumulates WebM chunks into a single file, extracts time ranges for transcription
    """

    def __init__(self, sample_rate: int = 16000, audio_dir: Path = None, session_id: str = None):
        self.sample_rate = sample_rate
        self.total_duration = 0.0  # Duration since last transcription trigger
        self.absolute_duration = 0.0  # Total duration of all audio
        self.last_transcribed_position = 0.0  # Track the last position transcribed (for final extraction)
        self.chunk_duration_threshold = 6.0  # Transcribe every 6 seconds
        self.window_seconds = 9.0  # Only transcribe last 9 seconds (using ffmpeg)
        self.last_transcription_text = ""  # Store last transcription for deduplication
        self.audio_dir = audio_dir or Path.home() / "projects" / "python" / "mlx_whisper" / "audio"
        self._lock = asyncio.Lock()  # Prevent concurrent access to file
        self.session_id = session_id
        self.webm_path = None  # Path to the growing WebM file
        if session_id:
            self.webm_path = self.audio_dir / f"{session_id}_recording.webm"

    async def add_chunk(self, audio_data: bytes, duration: float):
        """
        Append WebM chunk bytes to growing WebM file

        Args:
            audio_data: WebM audio bytes (streaming format)
            duration: Duration of chunk in seconds
        """
        async with self._lock:
            # Append WebM bytes to the growing file
            with open(self.webm_path, 'ab') as f:
                f.write(audio_data)

            # Update duration tracking
            self.total_duration += duration
            self.absolute_duration += duration

            logger.info(f"Appended {len(audio_data)} bytes WebM, total duration: {self.absolute_duration:.1f}s")

    def should_transcribe(self) -> bool:
        """
        Check if buffer has enough audio since last transcription

        Returns:
            True if ready to transcribe
        """
        return self.total_duration >= self.chunk_duration_threshold

    async def get_sliding_window_audio(self, session_id: str, chunk_counter: int) -> str:
        """
        Extract last N seconds of audio using ffmpeg for sliding window transcription

        Args:
            session_id: Session identifier
            chunk_counter: Chunk counter for unique filenames

        Returns:
            Path to the extracted audio file (last window_seconds only)
        """
        async with self._lock:
            # Check if WebM file exists
            if not self.webm_path or not self.webm_path.exists():
                return None

            total_duration = self.absolute_duration

        # Output will be WAV format (convert from WebM)
        output_path = self.audio_dir / f"{session_id}_chunk{chunk_counter}.wav"

        # If total duration is less than window, extract all
        if total_duration <= self.window_seconds:
            start_time = 0
            duration = total_duration
        else:
            # Extract last window_seconds
            start_time = max(0, total_duration - self.window_seconds)
            duration = self.window_seconds

        try:
            # Use ffmpeg to extract the sliding window from WebM and convert to WAV
            result = subprocess.run([
                'ffmpeg', '-y',  # Overwrite output file
                '-i', str(self.webm_path),
                '-ss', str(start_time),  # Start time
                '-t', str(duration),  # Duration
                '-ar', str(self.sample_rate),  # Sample rate
                '-ac', '1',  # Mono
                '-loglevel', 'error',  # Only show errors
                str(output_path)
            ], capture_output=True, timeout=10)

            if result.returncode != 0:
                logger.error(f"ffmpeg extraction failed: {result.stderr.decode()}")
                return None

            logger.info(f"Extracted sliding window: {start_time:.1f}s to {start_time + duration:.1f}s from WebM")
            return str(output_path)

        except subprocess.TimeoutExpired:
            logger.error("ffmpeg extraction timeout")
            return None
        except Exception as e:
            logger.error(f"ffmpeg extraction error: {e}")
            return None

    async def extract_complete_audio(self, session_id: str) -> str:
        """
        Extract only the remaining untranscribed audio from WebM to WAV for final transcription.
        This ensures we only transcribe the end portion that wasn't covered by sliding window.

        Args:
            session_id: Session identifier

        Returns:
            Path to the extracted remaining audio file, or None if extraction fails
        """
        async with self._lock:
            # Check if WebM file exists
            if not self.webm_path or not self.webm_path.exists():
                logger.error(f"WebM file not found for session {session_id}")
                return None

            total_duration = self.absolute_duration
            start_position = self.last_transcribed_position

        # Calculate the remaining duration to transcribe
        remaining_duration = total_duration - start_position

        # If there's less than 0.5 seconds remaining, skip it
        if remaining_duration < 0.5:
            logger.info(f"Only {remaining_duration:.1f}s remaining, skipping final transcription")
            return None

        # Output will be WAV format (convert from WebM)
        output_path = self.audio_dir / f"{session_id}_final.wav"

        try:
            # Use ffmpeg to extract only the remaining portion from WebM and convert to WAV
            result = subprocess.run([
                'ffmpeg', '-y',  # Overwrite output file
                '-i', str(self.webm_path),
                '-ss', str(start_position),  # Start from last transcribed position
                '-t', str(remaining_duration),  # Extract only remaining duration
                '-ar', str(self.sample_rate),  # Sample rate
                '-ac', '1',  # Mono
                '-loglevel', 'error',  # Only show errors
                str(output_path)
            ], capture_output=True, timeout=30)

            if result.returncode != 0:
                logger.error(f"ffmpeg final extraction failed: {result.stderr.decode()}")
                return None

            logger.info(f"Extracted final audio: {remaining_duration:.1f}s (from {start_position:.1f}s to {total_duration:.1f}s)")
            return str(output_path)

        except subprocess.TimeoutExpired:
            logger.error("ffmpeg final extraction timeout")
            return None
        except Exception as e:
            logger.error(f"ffmpeg final extraction error: {e}")
            return None

    async def fix_webm_duration(self):
        """
        Fix WebM file duration metadata using ffmpeg

        MediaRecorder creates WebM files without duration metadata,
        which prevents browsers from determining file length for seeking.
        This decodes and re-encodes the file to add proper duration metadata.
        """
        if not self.webm_path or not self.webm_path.exists():
            logger.warning("No WebM file to fix")
            return

        try:
            # Create temporary output file
            temp_output = self.webm_path.parent / f"{self.webm_path.stem}_fixed.webm"

            # Decode and re-encode to add duration metadata
            # We need to re-encode because simple remuxing doesn't work with MediaRecorder WebM files
            result = subprocess.run([
                'ffmpeg', '-y',
                '-i', str(self.webm_path),
                '-c:a', 'libopus',  # Re-encode audio as Opus
                '-b:a', '128k',     # Audio bitrate
                '-f', 'webm',       # Force WebM output format
                '-loglevel', 'error',
                str(temp_output)
            ], capture_output=True, timeout=60)

            if result.returncode != 0:
                logger.error(f"ffmpeg WebM fix failed: {result.stderr.decode()}")
                # Don't fail silently - keep original file
                return

            # Only replace if output file was created and has content
            if temp_output.exists() and temp_output.stat().st_size > 0:
                temp_output.replace(self.webm_path)
                logger.info(f"Fixed WebM duration metadata: {self.webm_path}")
            else:
                logger.error(f"ffmpeg produced empty output file")

        except subprocess.TimeoutExpired:
            logger.error("ffmpeg WebM fix timeout")
        except Exception as e:
            logger.error(f"ffmpeg WebM fix error: {e}")

    def mark_transcribed(self, transcription_text: str):
        """
        Mark transcription as complete and reset trigger timer

        Args:
            transcription_text: The transcribed text from this segment (for deduplication)
        """
        self.last_transcription_text = transcription_text
        # Track the last position we transcribed, minus 2s overlap to capture partial words
        # This ensures we don't miss word boundaries at the end
        self.last_transcribed_position = max(0, self.absolute_duration - 2.0)
        # Reset the trigger timer to transcribe again after 5 more seconds
        self.total_duration = 0.0

    def clear(self):
        """Clear buffer for new recording session"""
        self.total_duration = 0.0
        self.absolute_duration = 0.0
        self.last_transcribed_position = 0.0
        self.last_transcription_text = ""

        # Keep WebM file for audio playback
        # if self.webm_path and self.webm_path.exists():
        #     self.webm_path.unlink()
        #     logger.info(f"Deleted WebM file: {self.webm_path}")


@router.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """
    WebSocket endpoint for real-time audio transcription

    Protocol:
    - Client sends: {"type": "set_model", "model": <model_name>}
    - Client sends: {"type": "audio_chunk", "data": <base64_audio>, "duration": <seconds>}
    - Client sends: {"type": "end_recording"}
    - Server sends: {"type": "transcription", "segments": [...]}
    - Server sends: {"type": "status", "message": "..."}
    - Server sends: {"type": "error", "message": "..."}
    """
    await websocket.accept()
    logger.info("WebSocket connection established")

    # Will be set when client sends model selection
    whisper_service = None
    selected_model = None
    selected_channel = None  # Will be set when client sends channel selection ('left', 'right', 'both', or None)
    # Use host-based audio directory (same as whisper_service.py)
    audio_dir = Path.home() / "projects" / "python" / "mlx_whisper" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    audio_buffer = AudioBuffer(audio_dir=audio_dir, session_id=session_id)
    chunk_counter = 0  # Track unique filenames for each transcription

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "status",
            "message": "Connected. Ready to receive audio.",
            "session_id": session_id,
        })

        while True:
            # Receive message from client
            try:
                data = await websocket.receive_json()
            except Exception as e:
                logger.error(f"Error receiving WebSocket message: {e}")
                break

            message_type = data.get("type")

            if message_type == "set_model":
                # Set the model for this session
                model_name = data.get("model", "mlx-community/whisper-base")
                selected_model = model_name

                logger.info(f"Client selected model: {model_name}")

                # Import here to avoid circular dependency
                from app.whisper_service import MLXWhisperService

                # Create a new whisper service instance with the selected model
                whisper_service = MLXWhisperService(
                    model_name=model_name,
                    path_or_hf_repo=model_name
                )

                # Load the model with user feedback
                model_display_name = model_name.split('/')[-1].replace('whisper-', '').title()
                await websocket.send_json({
                    "type": "status",
                    "message": f"Loading {model_display_name} model..."
                })

                # Load model and verify with test transcription
                try:
                    import asyncio
                    import numpy as np
                    import tempfile
                    import wave
                    import os
                    import time

                    # Step 1: Pre-download model with resume support
                    logger.info(f"Step 1: Pre-downloading {model_name} with resume support")
                    download_success = await preload_model_with_resume(model_name, websocket)

                    if not download_success:
                        raise Exception("Model pre-download failed")

                    # Step 2: Load and verify model with test transcription
                    logger.info(f"Step 2: Loading and verifying {model_name}")

                    await websocket.send_json({
                        "type": "status",
                        "message": f"Verifying {model_display_name} model..."
                    })

                    loop = asyncio.get_event_loop()

                    # Create a short silent audio file for model verification
                    async def load_and_test_model_with_progress():
                        logger.info(f"Loading model {model_name} with test transcription...")

                        # Create 1 second of silence at 16kHz
                        silent_audio = np.zeros(16000, dtype=np.float32)

                        # Save to temp file
                        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                            temp_path = f.name

                        try:
                            # Write WAV file
                            with wave.open(temp_path, 'wb') as wav_file:
                                wav_file.setnchannels(1)  # Mono
                                wav_file.setsampwidth(2)  # 16-bit
                                wav_file.setframerate(16000)  # 16kHz
                                # Convert float32 to int16
                                audio_int16 = (silent_audio * 32767).astype(np.int16)
                                wav_file.writeframes(audio_int16.tobytes())

                            # Run model verification (model already downloaded by preload_model_with_resume)
                            result = await loop.run_in_executor(
                                None,
                                whisper_service._transcribe_sync,
                                temp_path
                            )
                            logger.info(f"Model {model_name} verified successfully via test transcription")

                            return True
                        finally:
                            # Clean up temp file
                            if os.path.exists(temp_path):
                                os.unlink(temp_path)

                    # Run the model loading with progress tracking
                    success = await load_and_test_model_with_progress()
                    logger.info(f"[DEBUG] 4. Model load complete!")

                    # Verify download is complete by checking files
                    logger.info(f"[DEBUG] 4.5. Verifying model download completeness...")
                    is_complete = verify_model_download_complete(model_name)

                    if not is_complete:
                        raise Exception(
                            f"Model download incomplete. This may be due to a timeout. "
                            f"Please try again or use a smaller model. "
                            f"Check backend logs for details."
                        )

                    logger.info(f"[DEBUG] 4.6. Model download verified complete!")

                    # Send explicit model_ready event FIRST
                    logger.info(f"[DEBUG] 5. Sending model_ready event")
                    await websocket.send_json({
                        "type": "model_ready",
                        "message": f"{model_display_name} model loaded and verified"
                    })

                    # Then send "Ready to record" status
                    logger.info(f"[DEBUG] 6. Sending status: Ready to record")
                    await websocket.send_json({
                        "type": "status",
                        "message": "Ready to record"
                    })

                except Exception as e:
                    logger.error(f"Error loading model: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to load model: {str(e)}"
                    })

            elif message_type == "set_channel":
                # Set the audio channel for this session
                channel = data.get("channel", "both")

                # Validate channel selection
                valid_channels = ["left", "right", "both"]
                if channel not in valid_channels:
                    logger.warning(f"Invalid channel selection: {channel}, defaulting to 'both'")
                    channel = "both"

                selected_channel = channel
                logger.info(f"Client selected channel: {channel}")

                await websocket.send_json({
                    "type": "status",
                    "message": f"Channel set to: {channel}"
                })

            elif message_type == "audio_chunk":
                # Ensure model is selected
                if whisper_service is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No model selected. Please reconnect."
                    })
                    continue

                # Process audio chunk
                try:
                    import base64

                    # Decode base64 audio data
                    audio_b64 = data.get("data", "")
                    audio_bytes = base64.b64decode(audio_b64)
                    duration = data.get("duration", 0.0)

                    # Add to buffer
                    await audio_buffer.add_chunk(audio_bytes, duration)

                    logger.info(f"Received audio chunk: {len(audio_bytes)} bytes, {duration}s")

                    # Check if we should transcribe
                    # Skip first transcription until we have at least window_seconds of audio
                    # to avoid duplication at the beginning
                    if audio_buffer.should_transcribe() and audio_buffer.absolute_duration >= audio_buffer.window_seconds:
                        await websocket.send_json({
                            "type": "status",
                            "message": "Transcribing..."
                        })

                        # Extract sliding window audio using ffmpeg (last 6 seconds only)
                        audio_path = await audio_buffer.get_sliding_window_audio(session_id, chunk_counter)
                        chunk_counter += 1

                        if not audio_path:
                            logger.error("Failed to extract sliding window audio")
                            continue

                        # Transcribe the sliding window
                        try:
                            segments = await whisper_service.transcribe_audio(audio_path, channel=selected_channel)

                            # Extract full text from all segments
                            full_text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())

                            # Remove any trailing punctuation
                            full_text_trimmed = full_text.rstrip('.,;:!?-')

                            # Deduplicate against previous transcription
                            new_text = align_and_deduplicate_text(
                                audio_buffer.last_transcription_text,
                                full_text_trimmed,
                                overlap_threshold=15
                            )

                            # Only send if there's actually new text
                            if new_text.strip():
                                # Clean trailing punctuation (remove last char if not alphanumeric or space)
                                cleaned_text = new_text.strip()
                                if cleaned_text and not (cleaned_text[-1].isalnum() or cleaned_text[-1].isspace()):
                                    cleaned_text = cleaned_text[:-1]

                                # Create simplified segments without speaker info
                                # Find which original segments contain the new text
                                new_segments = []
                                for seg in segments:
                                    seg_text = seg.text.strip()
                                    # Clean trailing punctuation from segment text too
                                    if seg_text and not (seg_text[-1].isalnum() or seg_text[-1].isspace()):
                                        seg_text = seg_text[:-1]

                                    if seg_text and seg_text in cleaned_text:
                                        new_segments.append({
                                            "text": seg_text,
                                            "start": seg.start,
                                            "end": seg.end,
                                        })

                                # If no segments matched, send the new text as a single segment
                                if not new_segments:
                                    new_segments = [{
                                        "text": cleaned_text,
                                        "start": max(0, audio_buffer.absolute_duration - audio_buffer.total_duration),
                                        "end": audio_buffer.absolute_duration,
                                    }]

                                await websocket.send_json({
                                    "type": "transcription",
                                    "segments": new_segments,
                                    "streaming": True,
                                    "text": cleaned_text,
                                })

                                logger.info(f"Sent streaming transcription: {len(new_segments)} segments, new text: '{new_text[:50]}...'")
                            else:
                                logger.info("No new text after deduplication, skipping send")

                            # Always mark as transcribed (even if no new text) to avoid re-transcribing
                            # the same audio repeatedly
                            audio_buffer.mark_transcribed(full_text)

                        except Exception as e:
                            logger.error(f"Transcription error: {e}")
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Transcription failed: {str(e)}"
                            })
                        finally:
                            # Clean up temporary WAV extraction files (keep WebM)
                            if audio_path and Path(audio_path).exists():
                                Path(audio_path).unlink()
                                logger.info(f"Deleted temporary WAV extraction file: {audio_path}")

                except Exception as e:
                    logger.error(f"Error processing audio chunk: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Error processing audio: {str(e)}"
                    })

            elif message_type == "end_recording":
                # Ensure model is selected
                if whisper_service is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No model selected. Please reconnect."
                    })
                    continue

                # Process any remaining audio in buffer
                logger.info("End recording signal received")

                if audio_buffer.webm_path and audio_buffer.webm_path.exists():
                    # Fix WebM duration metadata for proper seeking in browser
                    await audio_buffer.fix_webm_duration()

                    await websocket.send_json({
                        "type": "status",
                        "message": "Processing final audio..."
                    })

                    # Extract COMPLETE audio for final transcription (not sliding window)
                    # This ensures we capture all audio from the entire recording
                    audio_path = await audio_buffer.extract_complete_audio(session_id)

                    if not audio_path:
                        logger.error("Failed to extract complete audio for final transcription")
                        # Send empty final message
                        await websocket.send_json({
                            "type": "transcription",
                            "segments": [],
                            "final": True,
                            "streaming": False,
                            "text": "",
                        })
                    else:
                        try:
                            segments = await whisper_service.transcribe_audio(audio_path, channel=selected_channel)

                            # Extract full text from all segments
                            full_text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())

                            # Remove any trailing punctuation
                            full_text_trimmed = full_text.rstrip('.,;:!?-')

                            # Deduplicate against previous transcription
                            new_text = align_and_deduplicate_text(
                                audio_buffer.last_transcription_text,
                                full_text_trimmed,
                                overlap_threshold=15
                            )

                            # Send final transcription message (with new text if any)
                            if new_text.strip():
                                # Clean trailing punctuation (remove last char if not alphanumeric or space)
                                cleaned_text = new_text.strip()
                                if cleaned_text and not (cleaned_text[-1].isalnum() or cleaned_text[-1].isspace()):
                                    cleaned_text = cleaned_text[:-1]

                                # Create simplified segments without speaker info
                                new_segments = []
                                for seg in segments:
                                    seg_text = seg.text.strip()
                                    # Clean trailing punctuation from segment text too
                                    if seg_text and not (seg_text[-1].isalnum() or seg_text[-1].isspace()):
                                        seg_text = seg_text[:-1]

                                    if seg_text and seg_text in cleaned_text:
                                        new_segments.append({
                                            "text": seg_text,
                                            "start": seg.start,
                                            "end": seg.end,
                                        })

                                # If no segments matched, send the new text as a single segment
                                if not new_segments:
                                    new_segments = [{
                                        "text": cleaned_text,
                                        "start": max(0, audio_buffer.absolute_duration - audio_buffer.total_duration),
                                        "end": audio_buffer.absolute_duration,
                                    }]

                                await websocket.send_json({
                                    "type": "transcription",
                                    "segments": new_segments,
                                    "final": True,
                                    "streaming": False,
                                    "text": cleaned_text,
                                })

                                logger.info(f"Sent final transcription: {len(new_segments)} segments, new text: '{new_text[:50]}...'")
                            else:
                                logger.info("No new text in final transcription, already sent everything")
                                # Still send final message to signal completion
                                await websocket.send_json({
                                    "type": "transcription",
                                    "segments": [],
                                    "final": True,
                                    "streaming": False,
                                    "text": "",
                                })

                        except Exception as e:
                            logger.error(f"Final transcription error: {e}")
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Final transcription failed: {str(e)}"
                            })
                        finally:
                            # Clean up temporary WAV extraction files (keep WebM)
                            if audio_path and Path(audio_path).exists():
                                Path(audio_path).unlink()
                                logger.info(f"Deleted temporary WAV extraction file: {audio_path}")

                # Send completion message with audio file URL
                final_audio_url = None
                if audio_buffer.webm_path and audio_buffer.webm_path.exists():
                    # Keep the WebM file and send its path to frontend
                    final_audio_url = f"/api/audio/{audio_buffer.webm_path.name}"
                    logger.info(f"Final audio file available at: {final_audio_url}")

                await websocket.send_json({
                    "type": "status",
                    "message": "Recording completed. Transcription finished.",
                    "audio_url": final_audio_url
                })

                # Clear buffer for next recording session (but keep WebM file)
                # audio_buffer.clear()

            elif message_type == "ping":
                # Keepalive ping
                await websocket.send_json({"type": "pong"})

            else:
                logger.warning(f"Unknown message type: {message_type}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {message_type}"
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Server error: {str(e)}"
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
        logger.info("WebSocket connection closed")
