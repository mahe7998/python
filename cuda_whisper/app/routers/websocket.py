"""
WebSocket router for real-time audio streaming and transcription
Optimized for NVIDIA CUDA GPU acceleration
"""
import logging
import asyncio
import json
from typing import List
import uuid
from pathlib import Path
import subprocess
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydub import AudioSegment
import io

from app.whisper_service import get_whisper_service, CUDAWhisperService, MODEL_SIZE_MAP
from app.models import TranscriptionSegment
from app.wav_utils import create_wav_header, update_wav_header, get_wav_data_size

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def preload_model_with_progress(model_name: str, websocket: WebSocket) -> bool:
    """
    Pre-load the faster-whisper model with progress feedback.

    Args:
        model_name: Model name or size (e.g., 'base', 'medium', 'large-v3')
        websocket: WebSocket connection for sending status updates

    Returns:
        True if model loaded successfully, False otherwise
    """
    try:
        # Convert model name to faster-whisper size
        model_size = MODEL_SIZE_MAP.get(model_name, model_name)

        logger.info(f"Pre-loading faster-whisper model: {model_size}")

        await websocket.send_json({
            "type": "status",
            "message": f"Loading {model_size} model..."
        })

        # Get event loop for async execution
        loop = asyncio.get_event_loop()

        start_time = asyncio.get_event_loop().time()

        # Send periodic status updates while loading
        async def send_loading_status():
            while True:
                await asyncio.sleep(2)
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                await websocket.send_json({
                    "type": "download_progress",
                    "message": f"Loading model... ({elapsed}s elapsed)",
                    "elapsed_seconds": elapsed,
                })

        # Start status update task
        status_task = asyncio.create_task(send_loading_status())

        try:
            # Load model in background thread
            from faster_whisper import WhisperModel

            def load_model():
                return WhisperModel(
                    model_size,
                    device="cuda",
                    compute_type="float16",
                )

            model = await loop.run_in_executor(None, load_model)

            logger.info(f"Model {model_size} loaded successfully")
            return True

        finally:
            status_task.cancel()
            try:
                await status_task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error(f"Error loading model {model_name}: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "message": f"Failed to load model: {str(e)}"
        })
        return False


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

    prev_words = previous_text.strip().split()
    new_words = new_text.strip().split()

    if not prev_words or not new_words:
        return new_text

    best_match_idx = 0
    best_similarity = 0.0
    best_lookback = 0

    for lookback in range(min(overlap_threshold, len(prev_words)), 2, -1):
        prev_suffix = prev_words[-lookback:]

        for new_start_idx in range(min(overlap_threshold, len(new_words) - lookback + 1)):
            new_prefix = new_words[new_start_idx:new_start_idx + lookback]

            matches = sum(1 for a, b in zip(prev_suffix, new_prefix) if a.lower() == b.lower())
            similarity = matches / lookback if lookback > 0 else 0

            if similarity > 0.7:
                best_match_idx = new_start_idx + lookback
                best_similarity = similarity
                best_lookback = lookback
                logger.info(f"Found text overlap: {lookback} words matched at position {new_start_idx}, similarity: {similarity:.2f}")
                break

        if best_match_idx > 0:
            break

    new_portion = " ".join(new_words[best_match_idx:])

    if best_match_idx == 0:
        logger.info(f"No overlap detected, returning all new text ({len(new_words)} words)")
    elif not new_portion.strip():
        logger.info(f"Complete duplicate detected, discarding ({len(new_words)} words matched)")
    else:
        logger.info(f"Removed {best_match_idx} overlapping words, returning {len(new_words) - best_match_idx} new words")

    return new_portion


async def add_webm_cuepoints(input_path: Path, output_path: Path, cue_interval_ms: int = 5000) -> bool:
    """
    Re-encode WebM file with proper cue points for fast seeking.

    Args:
        input_path: Path to input WebM file
        output_path: Path for output WebM file with cue points
        cue_interval_ms: Cue point interval in milliseconds

    Returns:
        True if successful, False otherwise
    """
    try:
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', str(input_path),
            '-c:a', 'libopus',
            '-b:a', '128k',
            '-f', 'webm',
            '-cluster_time_limit', str(cue_interval_ms),
            '-cues_to_front', '1',
            '-reserve_index_space', '50000',
            '-loglevel', 'error',
            str(output_path)
        ]

        logger.info(f"Adding cue points to WebM: {input_path} -> {output_path}")

        result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=120)

        if result.returncode != 0:
            logger.error(f"ffmpeg cue points failed: {result.stderr.decode()}")
            return False

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
    """

    def __init__(self, sample_rate: int = 16000, audio_dir: Path = None, session_id: str = None, channel_selection: str = 'both'):
        self.sample_rate = sample_rate
        self.total_duration = 0.0
        self.absolute_duration = 0.0
        self.last_transcribed_position = 0.0
        self.chunk_duration_threshold = 6.0
        self.window_seconds = 9.0
        self.last_transcription_text = ""
        self.audio_dir = audio_dir or Path.home() / "projects" / "python" / "cuda_whisper" / "audio"
        self._lock = asyncio.Lock()
        self.session_id = session_id
        self.webm_path = None
        self.channel_selection = channel_selection
        if session_id:
            self.webm_path = self.audio_dir / f"{session_id}_recording.webm"

    async def add_chunk(self, audio_data: bytes, duration: float):
        """Append WebM chunk bytes to growing WebM file"""
        async with self._lock:
            with open(self.webm_path, 'ab') as f:
                f.write(audio_data)

            self.total_duration += duration
            self.absolute_duration += duration

            logger.info(f"Appended {len(audio_data)} bytes WebM, total duration: {self.absolute_duration:.1f}s")

    def should_transcribe(self) -> bool:
        """Check if buffer has enough audio since last transcription"""
        return self.total_duration >= self.chunk_duration_threshold

    async def get_sliding_window_audio(self, session_id: str, chunk_counter: int) -> str:
        """Extract last N seconds of audio using ffmpeg for sliding window transcription"""
        async with self._lock:
            if not self.webm_path or not self.webm_path.exists():
                return None

            total_duration = self.absolute_duration

        output_path = self.audio_dir / f"{session_id}_chunk{chunk_counter}.wav"

        if total_duration <= self.window_seconds:
            start_time = 0
            duration = total_duration
        else:
            start_time = max(0, total_duration - self.window_seconds)
            duration = self.window_seconds

        try:
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', str(self.webm_path),
                '-ss', str(start_time),
                '-t', str(duration),
            ]

            if self.channel_selection == 'left':
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=c0'])
            elif self.channel_selection == 'right':
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=c1'])
            else:
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=0.5*c0+0.5*c1'])

            ffmpeg_cmd.extend([
                '-ar', str(self.sample_rate),
                '-loglevel', 'error',
                str(output_path)
            ])

            logger.info(f"Channel selection: {self.channel_selection}")
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
        """Extract remaining untranscribed audio from WebM to WAV for final transcription"""
        async with self._lock:
            if not self.webm_path or not self.webm_path.exists():
                logger.error(f"WebM file not found for session {session_id}")
                return None

            webm_path = self.webm_path
            overlap_seconds = 2.0
            start_position = max(0, self.last_transcribed_position - overlap_seconds)

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
                actual_duration = self.absolute_duration
        except Exception as e:
            logger.warning(f"ffprobe error, using tracked duration: {e}")
            actual_duration = self.absolute_duration

        remaining_duration = actual_duration - start_position

        if remaining_duration < 0.5:
            logger.info(f"Only {remaining_duration:.1f}s remaining, skipping final transcription")
            return None

        output_path = self.audio_dir / f"{session_id}_final.wav"

        try:
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', str(webm_path),
                '-ss', str(start_position),
            ]

            if self.channel_selection == 'left':
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=c0'])
            elif self.channel_selection == 'right':
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=c1'])
            else:
                ffmpeg_cmd.extend(['-af', 'pan=1c|c0=0.5*c0+0.5*c1'])

            ffmpeg_cmd.extend([
                '-ar', str(self.sample_rate),
                '-loglevel', 'error',
                str(output_path)
            ])

            logger.info(f"FINAL - Channel selection: {self.channel_selection}")
            result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=30)

            if result.returncode != 0:
                logger.error(f"ffmpeg final extraction failed: {result.stderr.decode()}")
                return None

            logger.info(f"Extracted final audio: from {start_position:.1f}s to end of file ({actual_duration:.2f}s)")
            return str(output_path)

        except subprocess.TimeoutExpired:
            logger.error("ffmpeg final extraction timeout")
            return None
        except Exception as e:
            logger.error(f"ffmpeg final extraction error: {e}")
            return None

    async def fix_webm_duration(self):
        """Fix WebM file duration metadata and add cue points for seeking"""
        if not self.webm_path or not self.webm_path.exists():
            logger.warning("No WebM file to fix")
            return

        temp_output = self.webm_path.parent / f"{self.webm_path.stem}_fixed.webm"

        success = await add_webm_cuepoints(self.webm_path, temp_output, cue_interval_ms=5000)

        if success and temp_output.exists() and temp_output.stat().st_size > 0:
            temp_output.replace(self.webm_path)
            logger.info(f"Fixed WebM with cue points: {self.webm_path}")
        else:
            logger.error("Failed to fix WebM file")
            if temp_output.exists():
                temp_output.unlink()

    def mark_transcribed(self, transcription_text: str):
        """Mark transcription as complete and reset trigger timer"""
        self.last_transcription_text = transcription_text
        self.last_transcribed_position = max(0, self.absolute_duration - 2.0)
        self.total_duration = 0.0

    def clear(self):
        """Clear buffer for new recording session"""
        self.total_duration = 0.0
        self.absolute_duration = 0.0
        self.last_transcribed_position = 0.0
        self.last_transcription_text = ""


@router.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """
    WebSocket endpoint for real-time audio transcription with CUDA acceleration

    Protocol:
    - Client sends: {"type": "set_model", "model": <model_name>}
    - Client sends: {"type": "set_channel", "channel": "left|right|both"}
    - Client sends: {"type": "set_language", "language": "en|fr|null"}
    - Client sends: {"type": "audio_chunk", "data": <base64_audio>, "duration": <seconds>}
    - Client sends: {"type": "end_recording"}
    - Server sends: {"type": "transcription", "segments": [...]}
    - Server sends: {"type": "status", "message": "..."}
    - Server sends: {"type": "error", "message": "..."}
    """
    await websocket.accept()
    logger.info("WebSocket connection established")

    whisper_service = None
    selected_model = None
    selected_channel = None
    selected_language = None
    resume_transcription_id = None
    existing_audio_path = None
    existing_duration = 0.0

    audio_dir = Path.home() / "projects" / "python" / "cuda_whisper" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    audio_buffer = AudioBuffer(audio_dir=audio_dir, session_id=session_id)
    chunk_counter = 0

    try:
        await websocket.send_json({
            "type": "status",
            "message": "Connected. Ready to receive audio.",
            "session_id": session_id,
        })

        while True:
            try:
                data = await websocket.receive_json()
            except Exception as e:
                logger.error(f"Error receiving WebSocket message: {e}")
                break

            message_type = data.get("type")

            if message_type == "set_model":
                model_name = data.get("model", "base")
                selected_model = model_name

                logger.info(f"Client selected model: {model_name}")

                # Create a new whisper service instance with the selected model
                whisper_service = CUDAWhisperService(
                    model_name=model_name,
                    path_or_hf_repo=model_name
                )

                model_size = MODEL_SIZE_MAP.get(model_name, model_name)
                model_display_name = model_size.replace('-', ' ').title()

                await websocket.send_json({
                    "type": "status",
                    "message": f"Loading {model_display_name} model on CUDA..."
                })

                try:
                    import numpy as np
                    import tempfile
                    import wave
                    import time

                    logger.info(f"Loading faster-whisper model: {model_size}")

                    loop = asyncio.get_event_loop()

                    async def load_and_test_model():
                        logger.info(f"Loading model {model_size} with test transcription...")

                        silent_audio = np.zeros(16000, dtype=np.float32)

                        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                            temp_path = f.name

                        try:
                            with wave.open(temp_path, 'wb') as wav_file:
                                wav_file.setnchannels(1)
                                wav_file.setsampwidth(2)
                                wav_file.setframerate(16000)
                                audio_int16 = (silent_audio * 32767).astype(np.int16)
                                wav_file.writeframes(audio_int16.tobytes())

                            result = await loop.run_in_executor(
                                None,
                                whisper_service._transcribe_sync,
                                temp_path
                            )
                            logger.info(f"Model {model_size} verified successfully via test transcription")

                            return True
                        finally:
                            if os.path.exists(temp_path):
                                os.unlink(temp_path)

                    success = await load_and_test_model()

                    await websocket.send_json({
                        "type": "model_ready",
                        "message": f"{model_display_name} model loaded on CUDA"
                    })

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
                channel = data.get("channel", "both")

                valid_channels = ["left", "right", "both"]
                if channel not in valid_channels:
                    logger.warning(f"Invalid channel selection: {channel}, defaulting to 'both'")
                    channel = "both"

                selected_channel = channel
                audio_buffer.channel_selection = channel
                logger.info(f"Client selected channel: {channel}")

                await websocket.send_json({
                    "type": "status",
                    "message": f"Channel set to: {channel}"
                })

            elif message_type == "set_language":
                language = data.get("language")

                selected_language = language
                logger.info(f"Client selected language: {language if language else 'auto-detect'}")

                await websocket.send_json({
                    "type": "status",
                    "message": f"Language set to: {language if language else 'auto-detect'}"
                })

            elif message_type == "set_resume_transcription":
                transcription_id = data.get("transcription_id")

                if transcription_id:
                    logger.info(f"Client wants to resume transcription ID: {transcription_id}")

                    try:
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

                                session_id = str(uuid.uuid4())
                                audio_buffer = AudioBuffer(audio_dir=audio_dir, session_id=session_id, channel_selection=selected_channel or 'both')
                                chunk_counter = 0

                                logger.info(f"Created new session {session_id} for resumed transcription")

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
                audio_path = data.get("audio_path")

                if audio_path:
                    logger.info(f"set_resume_audio received: {audio_path}")

                    if audio_path.startswith("/api/audio/"):
                        filename = audio_path.replace("/api/audio/", "")
                        audio_full_path = audio_dir / filename

                        if audio_full_path.exists():
                            existing_audio_path = str(audio_full_path)
                            existing_duration = 0.0

                            session_id = str(uuid.uuid4())
                            audio_buffer = AudioBuffer(audio_dir=audio_dir, session_id=session_id, channel_selection=selected_channel or 'both')
                            chunk_counter = 0

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
                if whisper_service is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No model selected. Please reconnect."
                    })
                    continue

                try:
                    import base64

                    audio_b64 = data.get("data", "")
                    audio_bytes = base64.b64decode(audio_b64)
                    duration = data.get("duration", 0.0)

                    await audio_buffer.add_chunk(audio_bytes, duration)

                    logger.info(f"Received audio chunk: {len(audio_bytes)} bytes, {duration}s")

                    if audio_buffer.should_transcribe() and audio_buffer.absolute_duration >= audio_buffer.window_seconds:
                        await websocket.send_json({
                            "type": "status",
                            "message": "Transcribing..."
                        })

                        audio_path = await audio_buffer.get_sliding_window_audio(session_id, chunk_counter)
                        chunk_counter += 1

                        if not audio_path:
                            logger.error("Failed to extract sliding window audio")
                            continue

                        try:
                            segments = await whisper_service.transcribe_audio(audio_path, channel=selected_channel, language=selected_language)

                            full_text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
                            full_text_trimmed = full_text.rstrip('.,;:!?-')

                            new_text = align_and_deduplicate_text(
                                audio_buffer.last_transcription_text,
                                full_text_trimmed,
                                overlap_threshold=15
                            )

                            if new_text.strip():
                                cleaned_text = new_text.strip()
                                if cleaned_text and not (cleaned_text[-1].isalnum() or cleaned_text[-1].isspace()):
                                    cleaned_text = cleaned_text[:-1]

                                new_segments = []
                                for seg in segments:
                                    seg_text = seg.text.strip()
                                    if seg_text and not (seg_text[-1].isalnum() or seg_text[-1].isspace()):
                                        seg_text = seg_text[:-1]

                                    if seg_text and seg_text in cleaned_text:
                                        new_segments.append({
                                            "text": seg_text,
                                            "start": seg.start,
                                            "end": seg.end,
                                        })

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

                                logger.info(f"Sent streaming transcription: {len(new_segments)} segments")
                            else:
                                logger.info("No new text after deduplication, skipping send")

                            audio_buffer.mark_transcribed(full_text)

                        except Exception as e:
                            logger.error(f"Transcription error: {e}")
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Transcription failed: {str(e)}"
                            })
                        finally:
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
                if whisper_service is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No model selected. Please reconnect."
                    })
                    continue

                logger.info("End recording signal received")

                if audio_buffer.webm_path and audio_buffer.webm_path.exists():
                    await websocket.send_json({
                        "type": "processing_audio",
                        "message": "Optimizing audio for playback..."
                    })

                    if not existing_audio_path:
                        await audio_buffer.fix_webm_duration()
                    else:
                        logger.info("Skipping cue points for intermediate file (will be concatenated)")

                    await websocket.send_json({
                        "type": "status",
                        "message": "Processing final audio..."
                    })

                    audio_path = await audio_buffer.extract_complete_audio(session_id)

                    if not audio_path:
                        logger.error("Failed to extract complete audio for final transcription")
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

                            full_text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
                            full_text_trimmed = full_text.rstrip('.,;:!?-')

                            new_text = align_and_deduplicate_text(
                                audio_buffer.last_transcription_text,
                                full_text_trimmed,
                                overlap_threshold=15
                            )

                            if new_text.strip():
                                cleaned_text = new_text.strip()
                                if cleaned_text and not (cleaned_text[-1].isalnum() or cleaned_text[-1].isspace()):
                                    cleaned_text = cleaned_text[:-1]

                                new_segments = []
                                for seg in segments:
                                    seg_text = seg.text.strip()
                                    if seg_text and not (seg_text[-1].isalnum() or seg_text[-1].isspace()):
                                        seg_text = seg_text[:-1]

                                    if seg_text and seg_text in cleaned_text:
                                        new_segments.append({
                                            "text": seg_text,
                                            "start": seg.start,
                                            "end": seg.end,
                                        })

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

                                logger.info(f"Sent final transcription: {len(new_segments)} segments")
                            else:
                                logger.info("No new text in final transcription")
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
                            if audio_path and Path(audio_path).exists():
                                Path(audio_path).unlink()
                                logger.info(f"Deleted temporary WAV extraction file: {audio_path}")

                # Handle audio concatenation if resuming
                final_audio_path = audio_buffer.webm_path
                total_duration = audio_buffer.absolute_duration

                if existing_audio_path:
                    logger.info(f"Concatenating audio files")

                    existing_full_path = Path(existing_audio_path)
                    if not existing_full_path.is_absolute():
                        existing_full_path = audio_dir / existing_audio_path

                    if existing_full_path.exists():
                        try:
                            await websocket.send_json({
                                "type": "status",
                                "message": "Appending audio to existing recording..."
                            })

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
                                        logger.info(f"Detected existing audio duration: {existing_duration:.1f}s")
                                except (ValueError, subprocess.TimeoutExpired) as e:
                                    logger.warning(f"Could not detect existing audio duration: {e}")
                                    existing_duration = 0.0

                            concat_output = audio_dir / f"{session_id}_concatenated.webm"

                            filelist_path = audio_dir / f"{session_id}_filelist.txt"
                            with open(filelist_path, 'w') as f:
                                f.write(f"file '{existing_full_path}'\n")
                                f.write(f"file '{audio_buffer.webm_path}'\n")

                            concat_cmd = [
                                'ffmpeg', '-y',
                                '-f', 'concat',
                                '-safe', '0',
                                '-i', str(filelist_path),
                                '-c', 'copy',
                                '-loglevel', 'error',
                                str(concat_output)
                            ]

                            logger.info(f"Concatenating audio: {' '.join(concat_cmd)}")
                            result = subprocess.run(concat_cmd, capture_output=True, timeout=60)

                            if result.returncode == 0:
                                audio_buffer.webm_path.unlink()
                                filelist_path.unlink()

                                final_audio_path = concat_output
                                total_duration = existing_duration + audio_buffer.absolute_duration

                                logger.info(f"Audio concatenation successful: {total_duration:.1f}s total duration")

                                temp_fixed = concat_output.parent / f"{concat_output.stem}_fixed.webm"
                                cue_success = await add_webm_cuepoints(concat_output, temp_fixed, cue_interval_ms=5000)

                                if cue_success and temp_fixed.exists() and temp_fixed.stat().st_size > 0:
                                    temp_fixed.replace(concat_output)
                                    logger.info(f"Added cue points to concatenated WebM: {concat_output}")
                                else:
                                    logger.warning("Could not add cue points to concatenated WebM")
                                    if temp_fixed.exists():
                                        temp_fixed.unlink()

                                try:
                                    concat_output.replace(existing_full_path)
                                    final_audio_path = existing_full_path
                                    logger.info(f"Renamed concatenated file to original: {existing_full_path}")
                                except Exception as e:
                                    logger.warning(f"Could not rename concatenated file: {e}")
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
                                filelist_path.unlink()

                        except Exception as e:
                            logger.error(f"Error concatenating audio: {e}")
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Audio concatenation error: {str(e)}"
                            })
                    else:
                        logger.warning(f"Existing audio file not found: {existing_full_path}")

                # Send completion message
                final_audio_url = None
                if final_audio_path and final_audio_path.exists():
                    final_audio_url = f"/api/audio/{final_audio_path.name}"
                    logger.info(f"Final audio file available at: {final_audio_url}")

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
                            logger.info(f"Accurate final duration from ffprobe: {actual_duration:.2f}s")
                            total_duration = actual_duration
                    except (ValueError, subprocess.TimeoutExpired) as e:
                        logger.warning(f"Could not get accurate duration from ffprobe: {e}")

                await websocket.send_json({
                    "type": "status",
                    "message": "Recording completed. Transcription finished.",
                    "audio_url": final_audio_url,
                    "duration_seconds": total_duration
                })

                # Reset for next recording
                session_id = str(uuid.uuid4())
                audio_buffer = AudioBuffer(audio_dir=audio_dir, session_id=session_id, channel_selection=selected_channel or 'both')
                chunk_counter = 0
                existing_audio_path = None
                existing_duration = 0.0
                resume_transcription_id = None
                logger.info(f"Reset for next recording, new session: {session_id}")

            elif message_type == "ping":
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
            logger.debug(f"Could not send error to client: {send_error}")
    finally:
        try:
            await websocket.close()
        except Exception as close_error:
            logger.debug(f"Could not close WebSocket: {close_error}")
        logger.info("WebSocket connection closed")
