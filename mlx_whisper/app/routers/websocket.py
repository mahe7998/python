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

        # Get HuggingFace token for authenticated access to gated/private models
        hf_token = os.environ.get("HF_TOKEN")
        if hf_token:
            logger.info(f"Pre-downloading model {model_name} with HF_TOKEN authentication...")
        else:
            logger.info(f"Pre-downloading model {model_name} (no HF_TOKEN set - public models only)...")

        logger.info("Download options: XET disabled, hf_transfer enabled, resume support enabled")

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
                ignore_patterns=["*.md", "*.txt", ".gitattributes"],  # Skip unnecessary files
                token=hf_token  # Use HF_TOKEN for authenticated access
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


async def add_webm_cuepoints(input_path: Path, output_path: Path, cue_interval_ms: int = 5000) -> bool:
    """
    Re-encode WebM file with proper cue points (seek table) for fast seeking.

    MediaRecorder creates WebM files without cue points, which means browsers
    must scan through the file to seek. This re-encodes the file with cue points
    every N milliseconds, enabling instant seeking.

    Args:
        input_path: Path to input WebM file
        output_path: Path for output WebM file with cue points
        cue_interval_ms: Cue point interval in milliseconds (default 5000 = 5 seconds)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Use ffmpeg to re-encode with cue points
        # -cluster_time_limit: Controls how often cue points are written (in milliseconds)
        # -cues_to_front 1: Move cue points (seek table) to the front of the file for fast access
        # -reserve_index_space: Reserve space at start of file for the cues index
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', str(input_path),
            '-c:a', 'libopus',           # Re-encode audio as Opus (WebM standard codec)
            '-b:a', '128k',              # Audio bitrate
            '-f', 'webm',                # Force WebM output format
            '-cluster_time_limit', str(cue_interval_ms),  # Cue point interval (in milliseconds)
            '-cues_to_front', '1',       # Move seek table to front of file
            '-reserve_index_space', '50000',  # Reserve 50KB for cues index at file start
            '-loglevel', 'error',
            str(output_path)
        ]

        logger.info(f"Adding cue points to WebM: {input_path} -> {output_path}")
        logger.info(f"Cue interval: {cue_interval_ms}ms, command: {' '.join(ffmpeg_cmd)}")

        result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=120)

        if result.returncode != 0:
            logger.error(f"ffmpeg cue points failed: {result.stderr.decode()}")
            return False

        # Verify output file was created and has content
        if not output_path.exists() or output_path.stat().st_size == 0:
            logger.error("ffmpeg produced empty output file")
            return False

        logger.info(f"Successfully added cue points to WebM: {output_path}")
        return True

    except subprocess.TimeoutExpired:
        logger.error("ffmpeg cue points timeout")
        return False
    except Exception as e:
        logger.error(f"ffmpeg cue points error: {e}")
        return False


class AudioBuffer:
    """
    Buffer for accumulating audio chunks with ffmpeg-based sliding window transcription
    Accumulates WebM chunks into a single file, extracts time ranges for transcription
    """

    def __init__(self, sample_rate: int = 16000, audio_dir: Path = None, session_id: str = None, channel_selection: str = 'both'):
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
        self.channel_selection = channel_selection  # Audio channel selection ('left', 'right', or 'both')
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
            # Use single ffmpeg call: extract channel with pan filter, then resample
            # The order matters: pan filter extracts channel first, then -ar resamples
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', str(self.webm_path),
                '-ss', str(start_time),
                '-t', str(duration),
            ]

            # Add channel selection filter (applied before resampling)
            if self.channel_selection == 'left':
                # Extract left channel only
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=c0'])
            elif self.channel_selection == 'right':
                # Extract right channel only
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=c1'])
            else:
                # Mix both channels to mono
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=0.5*c0+0.5*c1'])

            # Add resampling (applied after channel extraction)
            ffmpeg_cmd.extend([
                '-ar', str(self.sample_rate),
                '-loglevel', 'error',
                str(output_path)
            ])

            logger.info(f"Channel selection: {self.channel_selection}")
            logger.info(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
            result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=10)

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

        Includes at least 2 seconds of overlap from previous transcription to ensure
        enough audio context for accurate transcription (deduplication handles overlap).

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

            webm_path = self.webm_path
            # Include at least 2 seconds of overlap from previous transcription
            # This ensures we have enough audio context even for short final chunks
            # The deduplication logic will handle any overlapping text
            overlap_seconds = 2.0
            start_position = max(0, self.last_transcribed_position - overlap_seconds)

        # Get actual file duration using ffprobe (more accurate than tracking chunks)
        try:
            probe_cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(webm_path)
            ]
            probe_result = subprocess.run(probe_cmd, capture_output=True, timeout=10)
            if probe_result.returncode == 0:
                actual_duration = float(probe_result.stdout.decode().strip())
                logger.info(f"FINAL - Actual file duration from ffprobe: {actual_duration:.2f}s")
            else:
                logger.warning(f"ffprobe failed, using tracked duration: {probe_result.stderr.decode()}")
                actual_duration = self.absolute_duration
        except Exception as e:
            logger.warning(f"ffprobe error, using tracked duration: {e}")
            actual_duration = self.absolute_duration

        # Calculate the remaining duration to transcribe
        remaining_duration = actual_duration - start_position

        # If there's less than 0.5 seconds remaining, skip it
        if remaining_duration < 0.5:
            logger.info(f"Only {remaining_duration:.1f}s remaining, skipping final transcription")
            return None

        # Output will be WAV format (convert from WebM)
        output_path = self.audio_dir / f"{session_id}_final.wav"

        try:
            # Use single ffmpeg call: extract channel with pan filter, then resample
            # Don't use -t (duration limit) - extract from start_position to END of file
            # This ensures we capture all audio even if duration tracking was slightly off
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', str(webm_path),
                '-ss', str(start_position),
                # No -t flag - extract to end of file
            ]

            # Add channel selection filter (applied before resampling)
            if self.channel_selection == 'left':
                # Extract left channel only
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=c0'])
            elif self.channel_selection == 'right':
                # Extract right channel only
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=c1'])
            else:
                # Mix both channels to mono
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=0.5*c0+0.5*c1'])

            # Add resampling (applied after channel extraction)
            ffmpeg_cmd.extend([
                '-ar', str(self.sample_rate),
                '-loglevel', 'error',
                str(output_path)
            ])

            logger.info(f"FINAL - Channel selection: {self.channel_selection}")
            logger.info(f"FINAL - FFmpeg command: {' '.join(ffmpeg_cmd)}")
            result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=30)

            if result.returncode != 0:
                logger.error(f"ffmpeg final extraction failed: {result.stderr.decode()}")
                return None

            logger.info(f"Extracted final audio: from {start_position:.1f}s to end of file ({actual_duration:.2f}s), with {overlap_seconds:.1f}s overlap")
            return str(output_path)

        except subprocess.TimeoutExpired:
            logger.error("ffmpeg final extraction timeout")
            return None
        except Exception as e:
            logger.error(f"ffmpeg final extraction error: {e}")
            return None

    async def fix_webm_duration(self):
        """
        Fix WebM file duration metadata and add cue points for seeking.

        MediaRecorder creates WebM files without duration metadata or cue points,
        which prevents browsers from determining file length and causes slow seeking.
        This re-encodes the file with:
        - Proper duration metadata
        - Cue points (seek table) every 5 seconds for instant seeking
        - Cues moved to front of file for fast access
        """
        if not self.webm_path or not self.webm_path.exists():
            logger.warning("No WebM file to fix")
            return

        # Create temporary output file
        temp_output = self.webm_path.parent / f"{self.webm_path.stem}_fixed.webm"

        # Use the helper function with 5-second cue interval
        success = await add_webm_cuepoints(self.webm_path, temp_output, cue_interval_ms=5000)

        if success and temp_output.exists() and temp_output.stat().st_size > 0:
            temp_output.replace(self.webm_path)
            logger.info(f"Fixed WebM with cue points: {self.webm_path}")
        else:
            logger.error("Failed to fix WebM file")
            # Clean up temp file if it exists
            if temp_output.exists():
                temp_output.unlink()

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
    - Client sends: {"type": "set_resume_transcription", "transcription_id": <id>}
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
    selected_language = None  # Will be set when client sends language selection (e.g., 'en', 'fr', or None for auto-detect)
    resume_transcription_id = None  # Will be set when client wants to resume an existing transcription
    existing_audio_path = None  # Path to existing audio file when resuming
    existing_duration = 0.0  # Duration of existing audio when resuming

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
                model_name = data.get("model", "mlx-community/whisper-base-mlx")
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
                # Update audio buffer's channel selection
                audio_buffer.channel_selection = channel
                logger.info(f"[CHANNEL DEBUG] Client selected channel: {channel}")
                logger.info(f"[CHANNEL DEBUG] selected_channel variable set to: {selected_channel}")
                logger.info(f"[CHANNEL DEBUG] audio_buffer.channel_selection set to: {audio_buffer.channel_selection}")

                await websocket.send_json({
                    "type": "status",
                    "message": f"Channel set to: {channel}"
                })

            elif message_type == "set_language":
                # Set the transcription language for this session
                language = data.get("language")  # None means auto-detect

                selected_language = language
                logger.info(f"[LANGUAGE DEBUG] Client selected language: {language if language else 'auto-detect'}")

                await websocket.send_json({
                    "type": "status",
                    "message": f"Language set to: {language if language else 'auto-detect'}"
                })

            elif message_type == "set_resume_transcription":
                # Set the transcription ID to resume from
                transcription_id = data.get("transcription_id")

                if transcription_id:
                    logger.info(f"Client wants to resume transcription ID: {transcription_id}")

                    try:
                        # Load transcription from database
                        from app.database import async_session_maker
                        from app.models import Transcription
                        from sqlalchemy import select

                        async with async_session_maker() as session:
                            result = await session.execute(
                                select(Transcription).where(Transcription.id == transcription_id)
                            )
                            transcription = result.scalar_one_or_none()

                            if transcription:
                                resume_transcription_id = transcription_id
                                existing_audio_path = transcription.audio_file_path
                                existing_duration = transcription.duration_seconds or 0.0
                                existing_content = transcription.content_md or ""

                                # IMPORTANT: Create a NEW session and audio buffer for the resumed recording
                                # This ensures new audio goes to a separate file and can be concatenated later
                                session_id = str(uuid.uuid4())
                                audio_buffer = AudioBuffer(audio_dir=audio_dir, session_id=session_id, channel_selection=selected_channel or 'both')
                                chunk_counter = 0

                                # Initialize last_transcription_text with existing content for deduplication
                                # This prevents the first chunk from duplicating text that was already transcribed
                                if existing_content:
                                    audio_buffer.last_transcription_text = existing_content
                                    logger.info(f"Initialized deduplication buffer with {len(existing_content)} chars of existing content")

                                logger.info(f"Created new session {session_id} for resumed transcription")
                                logger.info(f"Loaded transcription {transcription_id}: audio_path={existing_audio_path}, duration={existing_duration}s")

                                await websocket.send_json({
                                    "type": "status",
                                    "message": f"Resuming transcription: {transcription.title}"
                                })
                            else:
                                logger.warning(f"Transcription {transcription_id} not found")
                                await websocket.send_json({
                                    "type": "error",
                                    "message": f"Transcription not found: {transcription_id}"
                                })

                    except Exception as e:
                        logger.error(f"Error loading transcription {transcription_id}: {e}")
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Failed to load transcription: {str(e)}"
                        })

            elif message_type == "set_resume_audio":
                # Resume from an audio file path (without database record)
                audio_path = data.get("audio_path")

                if audio_path:
                    logger.info(f"[CONCAT DEBUG] set_resume_audio received: {audio_path}")
                    logger.info(f"[CONCAT DEBUG] Current existing_audio_path before set: {existing_audio_path}")

                    # Convert API path to filesystem path
                    if audio_path.startswith("/api/audio/"):
                        filename = audio_path.replace("/api/audio/", "")
                        audio_full_path = audio_dir / filename

                        if audio_full_path.exists():
                            existing_audio_path = str(audio_full_path)
                            # Duration will be auto-detected using ffprobe when needed
                            existing_duration = 0.0

                            # IMPORTANT: Create a NEW session and audio buffer for the resumed recording
                            # This ensures new audio goes to a separate file and can be concatenated later
                            session_id = str(uuid.uuid4())
                            audio_buffer = AudioBuffer(audio_dir=audio_dir, session_id=session_id, channel_selection=selected_channel or 'both')
                            chunk_counter = 0
                            logger.info(f"[CONCAT DEBUG] Created new session {session_id} for resumed recording")
                            logger.info(f"[CONCAT DEBUG] existing_audio_path set to: {existing_audio_path}")

                            logger.info(f"Resuming from audio file: {existing_audio_path}")

                            await websocket.send_json({
                                "type": "status",
                                "message": f"Resuming from previous recording"
                            })
                        else:
                            logger.warning(f"Audio file not found: {audio_full_path}")
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Audio file not found: {audio_path}"
                            })
                    else:
                        logger.warning(f"Invalid audio path format: {audio_path}")
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Invalid audio path format"
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
                            segments = await whisper_service.transcribe_audio(audio_path, channel=selected_channel, language=selected_language)

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
                    # Send status to disable recording button while processing
                    await websocket.send_json({
                        "type": "processing_audio",
                        "message": "Optimizing audio for playback..."
                    })

                    # Fix WebM duration metadata and add cue points for proper seeking in browser
                    # Skip this if we're resuming - the file will be concatenated and cues added to the final file
                    if not existing_audio_path:
                        await audio_buffer.fix_webm_duration()
                    else:
                        logger.info("Skipping cue points for intermediate file (will be concatenated)")

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
                            segments = await whisper_service.transcribe_audio(audio_path, channel=selected_channel, language=selected_language)

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

                # Handle audio concatenation if resuming an existing transcription
                final_audio_path = audio_buffer.webm_path
                total_duration = audio_buffer.absolute_duration

                logger.info(f"[CONCAT DEBUG] end_recording: existing_audio_path = {existing_audio_path}")
                logger.info(f"[CONCAT DEBUG] end_recording: audio_buffer.webm_path = {audio_buffer.webm_path}")

                if existing_audio_path:
                    if resume_transcription_id:
                        logger.info(f"Resuming transcription {resume_transcription_id}, concatenating audio files")
                    else:
                        logger.info(f"Concatenating audio files (resuming from audio without database record)")

                    # Convert existing audio path to full path
                    # Handle API paths like /api/audio/filename.webm
                    if existing_audio_path.startswith("/api/audio/"):
                        filename = existing_audio_path.replace("/api/audio/", "")
                        existing_full_path = audio_dir / filename
                    else:
                        existing_full_path = Path(existing_audio_path)
                        if not existing_full_path.is_absolute():
                            existing_full_path = audio_dir / existing_audio_path

                    # Only concatenate if existing file exists
                    if existing_full_path.exists():
                        try:
                            await websocket.send_json({
                                "type": "status",
                                "message": "Appending audio to existing recording..."
                            })

                            # If existing_duration is not set (not from database), get it from the file using ffprobe
                            if existing_duration == 0.0:
                                try:
                                    probe_cmd = [
                                        'ffprobe', '-v', 'error',
                                        '-show_entries', 'format=duration',
                                        '-of', 'default=noprint_wrappers=1:nokey=1',
                                        str(existing_full_path)
                                    ]
                                    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
                                    if probe_result.returncode == 0:
                                        existing_duration = float(probe_result.stdout.strip())
                                        logger.info(f"Detected existing audio duration from file: {existing_duration:.1f}s")
                                except (ValueError, subprocess.TimeoutExpired) as e:
                                    logger.warning(f"Could not detect existing audio duration: {e}")
                                    existing_duration = 0.0

                            # Create output path for concatenated audio
                            concat_output = audio_dir / f"{session_id}_concatenated.webm"

                            # Create temporary filelist for FFmpeg concat demuxer
                            filelist_path = audio_dir / f"{session_id}_filelist.txt"
                            with open(filelist_path, 'w') as f:
                                f.write(f"file '{existing_full_path}'\n")
                                f.write(f"file '{audio_buffer.webm_path}'\n")

                            # Use FFmpeg concat demuxer to combine files without re-encoding
                            concat_cmd = [
                                'ffmpeg', '-y',
                                '-f', 'concat',
                                '-safe', '0',
                                '-i', str(filelist_path),
                                '-c', 'copy',  # Copy streams without re-encoding (fast)
                                '-loglevel', 'error',
                                str(concat_output)
                            ]

                            logger.info(f"Concatenating audio: {' '.join(concat_cmd)}")
                            result = subprocess.run(concat_cmd, capture_output=True, timeout=60)

                            if result.returncode == 0:
                                # Delete old files and filelist
                                audio_buffer.webm_path.unlink()
                                filelist_path.unlink()

                                # Use concatenated file as the final audio
                                final_audio_path = concat_output
                                total_duration = existing_duration + audio_buffer.absolute_duration

                                logger.info(f"Audio concatenation successful: {total_duration:.1f}s total duration")

                                # Add cue points to concatenated WebM for fast seeking
                                # The concat demuxer with -c copy doesn't add cue points
                                temp_fixed = concat_output.parent / f"{concat_output.stem}_fixed.webm"
                                logger.info("Adding cue points to concatenated WebM for fast seeking...")
                                cue_success = await add_webm_cuepoints(concat_output, temp_fixed, cue_interval_ms=5000)

                                if cue_success and temp_fixed.exists() and temp_fixed.stat().st_size > 0:
                                    temp_fixed.replace(concat_output)
                                    logger.info(f"Added cue points to concatenated WebM: {concat_output}")
                                else:
                                    logger.warning("Could not add cue points to concatenated WebM")
                                    # Clean up temp file if it exists
                                    if temp_fixed.exists():
                                        temp_fixed.unlink()

                                # Rename concatenated file to the original first file name
                                # This keeps the audio path consistent with any saved transcription
                                try:
                                    concat_output.replace(existing_full_path)
                                    final_audio_path = existing_full_path
                                    logger.info(f"Renamed concatenated file to original: {existing_full_path}")
                                except Exception as e:
                                    logger.warning(f"Could not rename concatenated file: {e}, keeping as {concat_output}")
                                    final_audio_path = concat_output

                                await websocket.send_json({
                                    "type": "status",
                                    "message": f"Audio appended successfully ({total_duration:.1f}s total)"
                                })
                            else:
                                logger.error(f"FFmpeg concat failed: {result.stderr.decode()}")
                                await websocket.send_json({
                                    "type": "error",
                                    "message": "Failed to append audio files"
                                })
                                # Continue with new recording only
                                filelist_path.unlink()

                        except Exception as e:
                            logger.error(f"Error concatenating audio: {e}")
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Audio concatenation error: {str(e)}"
                            })
                            # Continue with new recording only
                    else:
                        logger.warning(f"Existing audio file not found: {existing_full_path}")

                # Send completion message with audio file URL
                final_audio_url = None
                if final_audio_path and final_audio_path.exists():
                    # Keep the WebM file and send its path to frontend
                    final_audio_url = f"/api/audio/{final_audio_path.name}"
                    logger.info(f"Final audio file available at: {final_audio_url}")

                    # Get accurate duration from ffprobe (more reliable than tracking chunks)
                    # This is especially important after concatenation and re-encoding
                    try:
                        probe_cmd = [
                            'ffprobe', '-v', 'error',
                            '-show_entries', 'format=duration',
                            '-of', 'default=noprint_wrappers=1:nokey=1',
                            str(final_audio_path)
                        ]
                        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
                        if probe_result.returncode == 0:
                            actual_duration = float(probe_result.stdout.strip())
                            logger.info(f"Accurate final duration from ffprobe: {actual_duration:.2f}s (tracked: {total_duration:.2f}s)")
                            total_duration = actual_duration
                        else:
                            logger.warning(f"ffprobe failed for final duration, using tracked: {probe_result.stderr}")
                    except (ValueError, subprocess.TimeoutExpired) as e:
                        logger.warning(f"Could not get accurate duration from ffprobe: {e}, using tracked: {total_duration:.2f}s")

                await websocket.send_json({
                    "type": "status",
                    "message": "Recording completed. Transcription finished.",
                    "audio_url": final_audio_url,
                    "duration_seconds": total_duration
                })

                # Reset for next recording in same session
                # Create new session_id and audio buffer for potential next recording
                session_id = str(uuid.uuid4())
                audio_buffer = AudioBuffer(audio_dir=audio_dir, session_id=session_id, channel_selection=selected_channel or 'both')
                chunk_counter = 0
                # Reset resume state for next recording
                existing_audio_path = None
                existing_duration = 0.0
                resume_transcription_id = None
                logger.info(f"Reset for next recording, new session: {session_id}")

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
        except Exception as send_error:
            logger.debug(f"Could not send error to client (likely disconnected): {send_error}")
    finally:
        try:
            await websocket.close()
        except Exception as close_error:
            logger.debug(f"Could not close WebSocket (likely already closed): {close_error}")
        logger.info("WebSocket connection closed")
