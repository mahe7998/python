"""
CUDA Whisper service for audio transcription with RTX 4090 GPU acceleration
Uses faster-whisper (CTranslate2) for optimized CUDA inference
"""
import os
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

from faster_whisper import WhisperModel

from app.models import TranscriptionSegment

logger = logging.getLogger(__name__)

# Global executor for running CPU/GPU bound tasks
executor = ThreadPoolExecutor(max_workers=2)

# Model size mapping for faster-whisper
# faster-whisper uses different model naming than mlx-whisper
MODEL_SIZE_MAP = {
    # MLX-style names to faster-whisper sizes
    "mlx-community/whisper-tiny-mlx": "tiny",
    "mlx-community/whisper-tiny": "tiny",
    "mlx-community/whisper-base-mlx": "base",
    "mlx-community/whisper-base": "base",
    "mlx-community/whisper-small-mlx": "small",
    "mlx-community/whisper-small": "small",
    "mlx-community/whisper-medium-mlx": "medium",
    "mlx-community/whisper-medium": "medium",
    "mlx-community/whisper-large-v3-mlx": "large-v3",
    "mlx-community/whisper-large-v3": "large-v3",
    # Direct size names
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
    "large": "large",
    "large-v2": "large-v2",
    "large-v3": "large-v3",
    # Distil-whisper models (faster, smaller)
    "distil-large-v2": "distil-large-v2",
    "distil-large-v3": "distil-large-v3",
    "distil-medium.en": "distil-medium.en",
    "distil-small.en": "distil-small.en",
}


class CUDAWhisperService:
    """
    Service for handling Whisper transcription with CUDA GPU acceleration
    Uses faster-whisper (CTranslate2) for optimized inference on NVIDIA GPUs
    """

    def __init__(
        self,
        model_name: str = "base",
        path_or_hf_repo: str = "base",
    ):
        """
        Initialize CUDA Whisper service

        Args:
            model_name: Whisper model name (tiny, base, small, medium, large-v3, etc.)
            path_or_hf_repo: HuggingFace repo or local path to model (for compatibility)
        """
        # Convert MLX-style model names to faster-whisper sizes
        self.original_model_name = model_name
        self.model_size = MODEL_SIZE_MAP.get(model_name, model_name)
        self.path_or_hf_repo = path_or_hf_repo

        # Device configuration for RTX 4090
        self.device = "cuda"
        self.compute_type = "float16"  # FP16 for optimal RTX 4090 performance

        # Model instance (lazy loaded)
        self._model: Optional[WhisperModel] = None

        # Speaker diarization placeholder (not supported in faster-whisper alone)
        self.diarize_model = None

        logger.info(f"Initialized CUDA Whisper service with model={self.model_size} (CUDA GPU acceleration)")

    @property
    def model_name(self) -> str:
        """Return the original model name for API compatibility"""
        return self.original_model_name

    def _get_model(self) -> WhisperModel:
        """Get or create the WhisperModel instance"""
        if self._model is None:
            logger.info(f"Loading faster-whisper model: {self.model_size}")
            logger.info(f"Device: {self.device}, Compute type: {self.compute_type}")

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                # Download models to standard HuggingFace cache
                download_root=None,
            )

            logger.info("faster-whisper model loaded successfully!")

        return self._model

    def load_models(self):
        """
        Pre-load Whisper model to avoid delays on first transcription.
        Downloads model from HuggingFace if not cached.
        """
        import numpy as np
        import tempfile
        import wave

        logger.info("Pre-loading faster-whisper model (downloading if needed)...")
        logger.info("This may take 1-2 minutes on first run...")

        try:
            # Load the model
            model = self._get_model()

            # Create a short silent audio file to test transcription
            silent_audio = np.zeros(16000, dtype=np.float32)

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name

            try:
                # Write WAV file
                with wave.open(temp_path, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(16000)
                    audio_int16 = (silent_audio * 32767).astype(np.int16)
                    wav_file.writeframes(audio_int16.tobytes())

                # Test transcription to ensure model is fully loaded
                segments, info = model.transcribe(temp_path, beam_size=5)
                # Consume the generator to trigger actual inference
                list(segments)

                logger.info("faster-whisper model loaded and verified successfully!")
                logger.info(f"Detected language probability: {info.language_probability:.2f}")

            finally:
                os.unlink(temp_path)

        except Exception as e:
            logger.error(f"Error pre-loading model: {e}")
            logger.info("Will fall back to lazy loading on first transcription")

    def _transcribe_sync(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronous transcription (runs in thread pool)

        Args:
            audio_path: Path to audio file
            language: Optional language code (e.g., 'en', 'fr'). If None, auto-detect.

        Returns:
            Transcription result dictionary
        """
        try:
            logger.info(f"Transcribing audio with CUDA (GPU-accelerated): {audio_path}")
            if language:
                logger.info(f"Forcing language: {language}")
            else:
                logger.info("Language: auto-detect")

            model = self._get_model()

            # Build transcription options
            transcribe_kwargs = {
                "beam_size": 5,
                "best_of": 5,
                "patience": 1,
                # Disable conditioning on previous text to prevent hallucination loops
                "condition_on_previous_text": False,
                # VAD filter to reduce hallucinations on silence
                "vad_filter": True,
                "vad_parameters": dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=400,
                ),
            }

            # Add language option if specified
            if language:
                transcribe_kwargs["language"] = language

            # Transcribe with faster-whisper
            segments_generator, info = model.transcribe(audio_path, **transcribe_kwargs)

            # Convert generator to list and format result
            segments = []
            full_text_parts = []

            for segment in segments_generator:
                seg_dict = {
                    "id": segment.id,
                    "seek": int(segment.seek),
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    "tokens": list(segment.tokens) if segment.tokens else [],
                    "temperature": segment.temperature,
                    "avg_logprob": segment.avg_logprob,
                    "compression_ratio": segment.compression_ratio,
                    "no_speech_prob": segment.no_speech_prob,
                }
                segments.append(seg_dict)
                full_text_parts.append(segment.text)

            result = {
                "text": "".join(full_text_parts),
                "segments": segments,
                "language": info.language,
            }

            logger.info(f"Transcription completed: {len(segments)} segments")
            logger.info(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")

            return result

        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            raise

    async def transcribe_audio(
        self,
        audio_path: str,
        channel: Optional[str] = None,
        language: Optional[str] = None
    ) -> List[TranscriptionSegment]:
        """
        Transcribe audio file with optional channel selection for stereo

        Args:
            audio_path: Path to audio file
            channel: Optional channel selection ('left', 'right', 'both', or None for auto/mono)
            language: Optional language code (e.g., 'en', 'fr'). If None, auto-detect.

        Returns:
            List of transcription segments
        """
        from app.wav_utils import get_wav_info, split_stereo_to_mono
        from functools import partial

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
                transcribe_func = partial(self._transcribe_sync, str(selected_path), language=language)
                result = await loop.run_in_executor(executor, transcribe_func)

                # Clean up temporary files
                try:
                    left_path.unlink(missing_ok=True)
                    right_path.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Could not clean up temp files: {e}")
            else:
                # Fallback to standard transcription if split fails
                loop = asyncio.get_event_loop()
                transcribe_func = partial(self._transcribe_sync, audio_path, language=language)
                result = await loop.run_in_executor(executor, transcribe_func)
        else:
            # Mono audio, 'both' selected, or no channel selection
            if channels == 2:
                logger.info("Stereo audio: mixing both channels to mono for transcription")
            loop = asyncio.get_event_loop()
            transcribe_func = partial(self._transcribe_sync, audio_path, language=language)
            result = await loop.run_in_executor(executor, transcribe_func)

        # Convert to TranscriptionSegment objects
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

        return " ".join(markdown_lines)

    async def save_audio_chunk(self, audio_data: bytes, filename: str) -> str:
        """
        Save audio chunk to file

        Args:
            audio_data: Audio data bytes
            filename: Output filename

        Returns:
            Path to saved file
        """
        # Save to ~/projects/python/cuda_whisper/audio
        audio_dir = Path.home() / "projects" / "python" / "cuda_whisper" / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        file_path = audio_dir / filename
        with open(file_path, "wb") as f:
            f.write(audio_data)

        logger.info(f"Saved audio file: {file_path}")
        return str(file_path)


# Alias for compatibility with MLX version
MLXWhisperService = CUDAWhisperService

# Global service instance
whisper_service: Optional[CUDAWhisperService] = None


def get_whisper_service() -> CUDAWhisperService:
    """
    Get or create CUDA Whisper service instance

    Returns:
        CUDAWhisperService instance
    """
    global whisper_service
    if whisper_service is None:
        # Get model from environment, defaulting to base
        model_name = os.getenv("WHISPER_MODEL", "base")

        whisper_service = CUDAWhisperService(
            model_name=model_name,
            path_or_hf_repo=model_name,
        )
        whisper_service.load_models()

    return whisper_service
