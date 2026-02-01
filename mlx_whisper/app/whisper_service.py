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
        model_name: str = "mlx-community/whisper-base-mlx",
        path_or_hf_repo: str = "mlx-community/whisper-base-mlx",
    ):
        """
        Initialize MLX-Whisper service

        Args:
            model_name: MLX-Whisper model name (tiny, base, small, medium, large-v2, large-v3)
            path_or_hf_repo: HuggingFace repo or local path to model
        """
        self.model_name = model_name
        self.path_or_hf_repo = path_or_hf_repo

        # Device is always MPS (Metal Performance Shaders) for MLX on Apple Silicon
        self.device = "mps"

        # Speaker diarization not yet supported in MLX-Whisper (placeholder for future)
        self.diarize_model = None

        logger.info(f"Initialized MLX-Whisper service with model={model_name} (Apple Silicon GPU acceleration)")

    def load_models(self):
        """
        Pre-load MLX-Whisper model to avoid delays on first transcription.
        Downloads model from HuggingFace if not cached.
        """
        import numpy as np
        import tempfile
        import os

        # Set up HuggingFace authentication if HF_TOKEN is available
        hf_token = os.environ.get("HF_TOKEN")
        if hf_token:
            # Set the token in the environment for huggingface_hub to use
            os.environ["HUGGING_FACE_HUB_TOKEN"] = hf_token
            logger.info("HF_TOKEN found - authenticated access to HuggingFace enabled")
        else:
            logger.info("No HF_TOKEN set - using public model access only")

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
            logger.info(f"Transcribing audio with MLX (GPU-accelerated): {audio_path}")
            if language:
                logger.info(f"Forcing language: {language}")
            else:
                logger.info("Language: auto-detect")

            # Build transcription options
            transcribe_kwargs = {
                "path_or_hf_repo": self.path_or_hf_repo,
                "verbose": False,
                # Disable conditioning on previous text to prevent hallucination loops
                # When True, hallucinations from one window propagate to subsequent windows
                # causing repetition loops, especially on concatenated audio files
                "condition_on_previous_text": False,
            }

            # Add language option if specified (forces transcription in that language)
            if language:
                transcribe_kwargs["language"] = language

            # Transcribe with MLX-Whisper (runs on Apple Silicon GPU)
            result = mlx_whisper.transcribe(audio_path, **transcribe_kwargs)

            # MLX-Whisper returns: {'text': str, 'segments': List[Dict], 'language': str}
            # segments contain: {'id', 'seek', 'start', 'end', 'text', 'tokens', 'temperature', 'avg_logprob', 'compression_ratio', 'no_speech_prob'}

            logger.info(f"Transcription completed: {len(result.get('segments', []))} segments")
            logger.info(f"Detected language: {result.get('language', 'unknown')}")

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
                    - 'left': Transcribe left channel only
                    - 'right': Transcribe right channel only
                    - 'both' or None: Mix stereo to mono (default behavior)
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
                # Use partial to pass language parameter
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
            # Standard transcription (stereo will be mixed to mono by Whisper)
            if channels == 2:
                logger.info("Stereo audio: mixing both channels to mono for transcription")
            loop = asyncio.get_event_loop()
            transcribe_func = partial(self._transcribe_sync, audio_path, language=language)
            result = await loop.run_in_executor(executor, transcribe_func)

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

    async def run_diarization(self, audio_path: str) -> list:
        """
        Run speaker diarization on audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            List of (start, end, speaker_id) tuples
        """
        from pyannote.audio import Pipeline
        import torch
        import torchaudio

        hf_token = os.environ.get("HF_TOKEN")
        if not hf_token:
            raise ValueError("HF_TOKEN environment variable required for diarization")

        logger.info(f"Loading speaker diarization model...")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token
        )
        # Use CPU for accurate timestamps (MPS has known issues on Apple Silicon)
        pipeline.to(torch.device("cpu"))

        logger.info(f"Running speaker diarization on: {audio_path}")

        # Convert to WAV if needed (torchaudio doesn't support WebM)
        import subprocess
        import tempfile

        if audio_path.endswith('.webm'):
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                wav_path = tmp.name
            subprocess.run(['ffmpeg', '-y', '-i', audio_path, '-ar', '16000', '-ac', '1', wav_path],
                          capture_output=True, check=True)
            logger.info(f"Converted WebM to WAV: {wav_path}")
        else:
            wav_path = audio_path

        # Load audio with torchaudio to avoid torchcodec issues
        waveform, sample_rate = torchaudio.load(wav_path)
        audio_dict = {"waveform": waveform, "sample_rate": sample_rate}

        # Cleanup temp file after loading
        if audio_path.endswith('.webm'):
            import os as os_module
            os_module.unlink(wav_path)

        def run_pipeline():
            return pipeline(audio_dict)

        loop = asyncio.get_event_loop()
        diarization_output = await loop.run_in_executor(executor, run_pipeline)

        # Build list of speaker turns
        # pyannote 4.0+ returns DiarizeOutput dataclass, access .speaker_diarization for Annotation
        diarization = diarization_output.speaker_diarization
        speaker_turns = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_turns.append((turn.start, turn.end, speaker))

        logger.info(f"Diarization complete: found {len(set(s[2] for s in speaker_turns))} speakers")
        return speaker_turns

    async def get_word_alignments(self, audio_path: str, text: str, language: str = "eng") -> list:
        """
        Get word-level timestamps using CTC forced alignment (wav2vec2).
        This provides much more accurate timing than Whisper's segment-level timestamps.

        Args:
            audio_path: Path to audio file (WAV format preferred)
            text: Full transcription text
            language: ISO 639-3 language code (default: "eng" for English)

        Returns:
            List of dicts with 'start', 'end', 'text' for each word
        """
        from ctc_forced_aligner import (
            load_audio,
            generate_emissions,
            preprocess_text,
            get_alignments,
            get_spans,
            postprocess_results,
            AlignmentSingleton,
        )
        import subprocess
        import tempfile

        logger.info(f"Running word-level alignment on: {audio_path}")

        # Convert to WAV if needed
        if audio_path.endswith('.webm'):
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                wav_path = tmp.name
            subprocess.run(['ffmpeg', '-y', '-i', audio_path, '-ar', '16000', '-ac', '1', wav_path],
                          capture_output=True, check=True)
            logger.info(f"Converted WebM to WAV for alignment: {wav_path}")
        else:
            wav_path = audio_path

        def run_alignment():
            # Load the alignment model (singleton - loads once)
            aligner = AlignmentSingleton()

            # Load audio
            audio_waveform = load_audio(wav_path)

            # Generate emissions from alignment model
            emissions, stride = generate_emissions(aligner.model, audio_waveform, batch_size=4)

            # Preprocess text for alignment
            tokens_starred, text_starred = preprocess_text(
                text,
                romanize=True,
                language=language
            )

            # Get alignments
            segments, scores, blank_token = get_alignments(
                emissions,
                tokens_starred,
                aligner.tokenizer
            )

            # Get word spans
            spans = get_spans(tokens_starred, segments, blank_token)

            # Post-process to get word timestamps
            word_timestamps = postprocess_results(text_starred, spans, stride, scores)

            return word_timestamps

        loop = asyncio.get_event_loop()
        word_timestamps = await loop.run_in_executor(executor, run_alignment)

        # Cleanup temp file
        if audio_path.endswith('.webm'):
            import os as os_module
            os_module.unlink(wav_path)

        logger.info(f"Word alignment complete: {len(word_timestamps)} words aligned")
        return word_timestamps

    def assign_speakers_to_words(self, word_timestamps: list, speaker_turns: list) -> list:
        """
        Assign speakers to words based on diarization output.

        Args:
            word_timestamps: List of {'start', 'end', 'text'} for each word
            speaker_turns: List of (start, end, speaker_id) tuples from diarization

        Returns:
            List of {'start', 'end', 'text', 'speaker'} for each word
        """
        result = []
        for word in word_timestamps:
            word_mid = (word['start'] + word['end']) / 2
            speaker = None

            # Find which speaker turn contains this word's midpoint
            for turn_start, turn_end, turn_speaker in speaker_turns:
                if turn_start <= word_mid <= turn_end:
                    speaker = turn_speaker
                    break

            result.append({
                'start': word['start'],
                'end': word['end'],
                'text': word['text'],
                'speaker': speaker
            })

        return result

    def words_to_speaker_segments(self, words_with_speakers: list) -> List[TranscriptionSegment]:
        """
        Convert word-level speaker assignments to sentence-like segments.
        Groups consecutive words by same speaker.

        Args:
            words_with_speakers: List of {'start', 'end', 'text', 'speaker'} dicts

        Returns:
            List of TranscriptionSegment with speaker assignments
        """
        if not words_with_speakers:
            return []

        segments = []
        current_speaker = words_with_speakers[0].get('speaker')
        current_text = []
        segment_start = words_with_speakers[0]['start']
        segment_end = words_with_speakers[0]['end']

        for word in words_with_speakers:
            if word.get('speaker') == current_speaker:
                current_text.append(word['text'])
                segment_end = word['end']
            else:
                # Speaker changed - save current segment
                if current_text:
                    segments.append(TranscriptionSegment(
                        text=" ".join(current_text),
                        start=segment_start,
                        end=segment_end,
                        speaker=current_speaker
                    ))
                # Start new segment
                current_speaker = word.get('speaker')
                current_text = [word['text']]
                segment_start = word['start']
                segment_end = word['end']

        # Don't forget the last segment
        if current_text:
            segments.append(TranscriptionSegment(
                text=" ".join(current_text),
                start=segment_start,
                end=segment_end,
                speaker=current_speaker
            ))

        return segments

    async def extract_speaker_embedding(self, audio_path: str, start: float, end: float) -> bytes:
        """
        Extract 256-dim voice embedding for a speaker segment.

        Args:
            audio_path: Path to audio file
            start: Start time in seconds
            end: End time in seconds

        Returns:
            Embedding as bytes (256 float32 values, ~1KB)
        """
        import numpy as np
        import subprocess
        import tempfile
        import torch
        import torchaudio
        from pyannote.audio import Model, Inference

        hf_token = os.environ.get("HF_TOKEN")
        if not hf_token:
            raise ValueError("HF_TOKEN environment variable required for embedding extraction")

        logger.info(f"Extracting embedding for segment {start:.2f}-{end:.2f}s")

        # Convert to WAV if needed
        if audio_path.endswith('.webm'):
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                wav_path = tmp.name
            subprocess.run(['ffmpeg', '-y', '-i', audio_path, '-ar', '16000', '-ac', '1', wav_path],
                          capture_output=True, check=True)
        else:
            wav_path = audio_path

        def run_embedding():
            # Load audio manually using torchaudio to avoid pyannote's AudioDecoder issues
            waveform, sample_rate = torchaudio.load(wav_path)

            # Resample to 16kHz if needed
            if sample_rate != 16000:
                resampler = torchaudio.transforms.Resample(sample_rate, 16000)
                waveform = resampler(waveform)
                sample_rate = 16000

            # Convert to mono if stereo
            if waveform.shape[0] > 1:
                waveform = waveform.mean(dim=0, keepdim=True)

            # Extract the segment
            start_sample = int(start * sample_rate)
            end_sample = int(end * sample_rate)
            segment_waveform = waveform[:, start_sample:end_sample]

            # Create audio dict for pyannote
            audio_dict = {"waveform": segment_waveform, "sample_rate": sample_rate}

            # Load wespeaker model (same as used by diarization, already cached)
            model = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM", token=hf_token)
            inference = Inference(model, window="whole")

            # Get embedding
            embedding = inference(audio_dict)
            return embedding

        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(executor, run_embedding)

        # Cleanup temp file
        if audio_path.endswith('.webm'):
            import os as os_module
            os_module.unlink(wav_path)

        # Convert numpy array to bytes for storage
        embedding_bytes = np.array(embedding).astype(np.float32).tobytes()
        logger.info(f"Extracted embedding: {len(embedding_bytes)} bytes")
        return embedding_bytes

    def compare_embeddings(self, emb1: bytes, emb2: bytes, threshold: float = 0.6) -> tuple:
        """
        Compare two embeddings using cosine distance.

        Args:
            emb1: First embedding as bytes
            emb2: Second embedding as bytes
            threshold: Distance threshold (lower = more strict)

        Returns:
            (is_match: bool, confidence: float) - confidence is 0-1 where 1 = identical
        """
        import numpy as np
        from scipy.spatial.distance import cosine

        # Convert bytes to numpy arrays
        arr1 = np.frombuffer(emb1, dtype=np.float32)
        arr2 = np.frombuffer(emb2, dtype=np.float32)

        # Calculate cosine distance (0 = identical, 2 = opposite)
        distance = cosine(arr1, arr2)

        # Convert distance to confidence (0-1 where 1 = identical)
        confidence = float(1 - (distance / 2))

        is_match = bool(distance < threshold)
        return is_match, confidence

    async def extract_all_speaker_embeddings(
        self, audio_path: str, speaker_turns: list
    ) -> dict:
        """
        Extract embeddings for all speakers from diarization output.
        Uses the longest segment for each speaker for best embedding quality.

        Args:
            audio_path: Path to audio file
            speaker_turns: List of (start, end, speaker_id) tuples

        Returns:
            Dict mapping speaker_id to embedding bytes
        """
        import numpy as np

        # Find longest segment for each speaker
        speaker_best_segments = {}
        for start, end, speaker_id in speaker_turns:
            duration = end - start
            if speaker_id not in speaker_best_segments or duration > speaker_best_segments[speaker_id][1]:
                speaker_best_segments[speaker_id] = (start, end - start, end)

        # Extract embedding for each speaker's longest segment
        embeddings = {}
        for speaker_id, (start, duration, end) in speaker_best_segments.items():
            try:
                embedding = await self.extract_speaker_embedding(audio_path, start, end)
                embeddings[speaker_id] = embedding
                logger.info(f"Extracted embedding for {speaker_id} from {start:.2f}-{end:.2f}s")
            except Exception as e:
                logger.error(f"Failed to extract embedding for {speaker_id}: {e}")

        return embeddings

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
        markdown_parts = []

        current_speaker = None
        current_texts = []

        for segment in segments:
            speaker_id = segment.speaker
            speaker_name = speaker_map.get(speaker_id, speaker_id)

            if speaker_id != current_speaker:
                # Flush previous speaker's text
                if current_texts:
                    markdown_parts.append(" ".join(current_texts))
                    current_texts = []

                # Start new speaker section
                if speaker_id is not None:
                    # Add line break before speaker label (except first)
                    prefix = "\n\n" if markdown_parts else ""
                    markdown_parts.append(f"{prefix}**{speaker_name}**:")
                current_speaker = speaker_id

            current_texts.append(segment.text.strip())

        # Flush remaining text
        if current_texts:
            markdown_parts.append(" ".join(current_texts))

        return " ".join(markdown_parts)

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
        # Model options: mlx-community/whisper-tiny, whisper-base-mlx, whisper-small-mlx, whisper-medium-mlx, whisper-large-v3-mlx
        model_name = os.getenv("WHISPER_MODEL", "mlx-community/whisper-base-mlx")

        whisper_service = MLXWhisperService(
            model_name=model_name,
            path_or_hf_repo=model_name,
        )
        whisper_service.load_models()

    return whisper_service
