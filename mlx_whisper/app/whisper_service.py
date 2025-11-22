"""
MLX-Whisper service for audio transcription with Apple Silicon acceleration
"""
import os
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

import mlx_whisper

from app.models import TranscriptionSegment

logger = logging.getLogger(__name__)

# Global executor for running CPU/GPU bound tasks
executor = ThreadPoolExecutor(max_workers=2)


class MLXWhisperService:
    """
    Service for handling MLX-Whisper transcription with Apple Silicon acceleration
    """

    def __init__(
        self,
        model_name: str = "mlx-community/whisper-base",
        path_or_hf_repo: str = "mlx-community/whisper-base",
    ):
        """
        Initialize MLX-Whisper service

        Args:
            model_name: MLX-Whisper model name (tiny, base, small, medium, large-v2, large-v3)
            path_or_hf_repo: HuggingFace repo or local path to model
        """
        self.model_name = model_name
        self.path_or_hf_repo = path_or_hf_repo

        logger.info(f"Initialized MLX-Whisper service with model={model_name} (Apple Silicon GPU acceleration)")

    def load_models(self):
        """
        Pre-load MLX-Whisper model to avoid delays on first transcription.
        Downloads model from HuggingFace if not cached.
        """
        import numpy as np
        import tempfile
        import os

        logger.info("Pre-loading MLX-Whisper model (downloading if needed)...")
        logger.info("This may take 1-2 minutes on first run...")

        try:
            # Create a short silent audio file to trigger model loading
            # 1 second of silence at 16kHz
            silent_audio = np.zeros(16000, dtype=np.float32)

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name

            # Write WAV file manually (simple 16kHz mono format)
            import wave
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(16000)  # 16kHz
                # Convert float32 to int16
                audio_int16 = (silent_audio * 32767).astype(np.int16)
                wav_file.writeframes(audio_int16.tobytes())

            # Transcribe silent audio to trigger model download and loading
            _ = mlx_whisper.transcribe(
                temp_path,
                path_or_hf_repo=self.path_or_hf_repo,
                verbose=False
            )

            # Clean up temp file
            os.unlink(temp_path)

            logger.info("MLX-Whisper model loaded successfully!")
            logger.info("Models will run with Apple Silicon GPU acceleration via MLX")

        except Exception as e:
            logger.error(f"Error pre-loading model: {e}")
            logger.info("Will fall back to lazy loading on first transcription")

    def _transcribe_sync(self, audio_path: str) -> Dict[str, Any]:
        """
        Synchronous transcription (runs in thread pool)

        Args:
            audio_path: Path to audio file

        Returns:
            Transcription result dictionary
        """
        try:
            logger.info(f"Transcribing audio with MLX (GPU-accelerated): {audio_path}")

            # Transcribe with MLX-Whisper (runs on Apple Silicon GPU)
            result = mlx_whisper.transcribe(
                audio_path,
                path_or_hf_repo=self.path_or_hf_repo,
                verbose=False
            )

            # MLX-Whisper returns: {'text': str, 'segments': List[Dict], 'language': str}
            # segments contain: {'id', 'seek', 'start', 'end', 'text', 'tokens', 'temperature', 'avg_logprob', 'compression_ratio', 'no_speech_prob'}

            logger.info(f"Transcription completed: {len(result.get('segments', []))} segments")
            logger.info(f"Detected language: {result.get('language', 'unknown')}")

            return result

        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            raise

    async def transcribe_audio(self, audio_path: str, channel: Optional[str] = None) -> List[TranscriptionSegment]:
        """
        Transcribe audio file with optional channel selection for stereo

        Args:
            audio_path: Path to audio file
            channel: Optional channel selection ('left', 'right', 'both', or None for auto/mono)
                    - 'left': Transcribe left channel only
                    - 'right': Transcribe right channel only
                    - 'both' or None: Mix stereo to mono (default behavior)

        Returns:
            List of transcription segments
        """
        from app.wav_utils import get_wav_info, split_stereo_to_mono

        audio_path_obj = Path(audio_path)

        # Check if file is stereo
        try:
            sample_rate, channels, bits = get_wav_info(audio_path_obj)
            logger.info(f"Audio info: {channels} channel(s), {sample_rate}Hz, {bits}-bit")
        except Exception as e:
            logger.warning(f"Could not read WAV info: {e}, proceeding with standard transcription")
            channels = 1

        # Handle stereo audio with specific channel selection
        if channels == 2 and channel in ['left', 'right']:
            logger.info(f"Stereo audio detected, transcribing {channel} channel only")

            # Split stereo into mono channels
            audio_dir = audio_path_obj.parent
            left_path = audio_dir / f"{audio_path_obj.stem}_left.wav"
            right_path = audio_dir / f"{audio_path_obj.stem}_right.wav"

            if split_stereo_to_mono(audio_path_obj, left_path, right_path):
                # Transcribe selected channel
                selected_path = left_path if channel == 'left' else right_path
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(executor, self._transcribe_sync, str(selected_path))

                # Clean up temporary files
                try:
                    left_path.unlink(missing_ok=True)
                    right_path.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Could not clean up temp files: {e}")
            else:
                # Fallback to standard transcription if split fails
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(executor, self._transcribe_sync, audio_path)
        else:
            # Mono audio, 'both' selected, or no channel selection
            # Standard transcription (stereo will be mixed to mono by Whisper)
            if channels == 2:
                logger.info("Stereo audio: mixing both channels to mono for transcription")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(executor, self._transcribe_sync, audio_path)

        # Convert to TranscriptionSegment objects
        # MLX-Whisper doesn't include speaker diarization, so we don't set speaker field
        segments = []
        for seg in result.get("segments", []):
            segment = TranscriptionSegment(
                text=seg.get("text", "").strip(),
                start=seg.get("start", 0.0),
                end=seg.get("end", 0.0),
            )
            segments.append(segment)

        return segments

    def format_as_markdown(
        self,
        segments: List[TranscriptionSegment],
        speaker_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Format transcription segments as markdown

        Args:
            segments: List of transcription segments
            speaker_map: Optional mapping of speaker IDs to names

        Returns:
            Formatted markdown text
        """
        if not segments:
            return ""

        speaker_map = speaker_map or {}
        markdown_lines = []

        current_speaker = None
        for segment in segments:
            speaker_id = segment.speaker
            speaker_name = speaker_map.get(speaker_id, speaker_id)

            # Add speaker label if changed
            if speaker_id != current_speaker:
                if current_speaker is not None:
                    markdown_lines.append("")  # Blank line between speakers
                markdown_lines.append(f"**{speaker_name}**: {segment.text}")
                current_speaker = speaker_id
            else:
                # Continue same speaker
                markdown_lines.append(segment.text)

        return "\n".join(markdown_lines)

    async def save_audio_chunk(self, audio_data: bytes, filename: str) -> str:
        """
        Save audio chunk to file

        Args:
            audio_data: Audio data bytes
            filename: Output filename

        Returns:
            Path to saved file
        """
        # Save to ~/projects/python/mlx_whisper/audio instead of /audio
        audio_dir = Path.home() / "projects" / "python" / "mlx_whisper" / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        file_path = audio_dir / filename
        with open(file_path, "wb") as f:
            f.write(audio_data)

        logger.info(f"Saved audio file: {file_path}")
        return str(file_path)


# Global service instance
whisper_service: Optional[MLXWhisperService] = None


def get_whisper_service() -> MLXWhisperService:
    """
    Get or create MLX-Whisper service instance

    Returns:
        MLXWhisperService instance
    """
    global whisper_service
    if whisper_service is None:
        # Initialize with default settings
        # Model options: mlx-community/whisper-tiny, whisper-base, whisper-small, whisper-medium, whisper-large-v3
        model_name = os.getenv("WHISPER_MODEL", "mlx-community/whisper-base")

        whisper_service = MLXWhisperService(
            model_name=model_name,
            path_or_hf_repo=model_name,
        )
        whisper_service.load_models()

    return whisper_service
