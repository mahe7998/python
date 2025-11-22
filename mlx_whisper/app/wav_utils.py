"""
Utilities for WAV file operations
"""
import struct
import logging
import numpy as np
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


def create_wav_header(sample_rate: int = 16000, channels: int = 1, bits_per_sample: int = 16, data_size: int = 0) -> bytes:
    """
    Create WAV file header

    Args:
        sample_rate: Sample rate in Hz
        channels: Number of audio channels
        bits_per_sample: Bits per sample (16 for PCM)
        data_size: Size of audio data in bytes

    Returns:
        WAV header bytes
    """
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8

    # RIFF chunk
    riff_chunk = b'RIFF'
    file_size = 36 + data_size  # Total file size minus 8 bytes for RIFF header
    riff_chunk += struct.pack('<I', file_size)
    riff_chunk += b'WAVE'

    # fmt sub-chunk
    fmt_chunk = b'fmt '
    fmt_chunk += struct.pack('<I', 16)  # fmt chunk size
    fmt_chunk += struct.pack('<H', 1)   # Audio format (1 = PCM)
    fmt_chunk += struct.pack('<H', channels)
    fmt_chunk += struct.pack('<I', sample_rate)
    fmt_chunk += struct.pack('<I', byte_rate)
    fmt_chunk += struct.pack('<H', block_align)
    fmt_chunk += struct.pack('<H', bits_per_sample)

    # data sub-chunk
    data_chunk = b'data'
    data_chunk += struct.pack('<I', data_size)

    return riff_chunk + fmt_chunk + data_chunk


def update_wav_header(wav_path: Path, data_size: int):
    """
    Update WAV file header with new data size

    Args:
        wav_path: Path to WAV file
        data_size: New size of audio data in bytes
    """
    with open(wav_path, 'r+b') as f:
        # Update file size in RIFF header (offset 4)
        f.seek(4)
        file_size = 36 + data_size
        f.write(struct.pack('<I', file_size))

        # Update data chunk size (offset 40)
        f.seek(40)
        f.write(struct.pack('<I', data_size))


def get_wav_data_size(wav_path: Path) -> int:
    """
    Get the current data size from WAV file header

    Args:
        wav_path: Path to WAV file

    Returns:
        Data size in bytes
    """
    if not wav_path.exists():
        return 0

    with open(wav_path, 'rb') as f:
        # Read data chunk size (offset 40)
        f.seek(40)
        data_size = struct.unpack('<I', f.read(4))[0]
        return data_size


def get_wav_info(wav_path: Path) -> Tuple[int, int, int]:
    """
    Get WAV file information

    Args:
        wav_path: Path to WAV file

    Returns:
        Tuple of (sample_rate, channels, bits_per_sample)
    """
    with open(wav_path, 'rb') as f:
        # Skip RIFF header
        f.seek(20)

        # Read fmt chunk
        channels = struct.unpack('<H', f.read(2))[0]
        sample_rate = struct.unpack('<I', f.read(4))[0]
        f.read(6)  # Skip byte_rate and block_align
        bits_per_sample = struct.unpack('<H', f.read(2))[0]

        return sample_rate, channels, bits_per_sample


def split_stereo_to_mono(input_path: Path, output_left: Path, output_right: Path) -> bool:
    """
    Split a stereo WAV file into two mono files (left and right channels)

    Args:
        input_path: Path to stereo WAV file
        output_left: Path for left channel output
        output_right: Path for right channel output

    Returns:
        True if successful, False if not stereo
    """
    import wave

    # Read input file
    with wave.open(str(input_path), 'rb') as wav_in:
        if wav_in.getnchannels() != 2:
            logger.info(f"Audio file is not stereo ({wav_in.getnchannels()} channels), skipping split")
            return False

        sample_rate = wav_in.getframerate()
        n_frames = wav_in.getnframes()
        sample_width = wav_in.getsampwidth()

        # Read all frames
        frames = wav_in.readframes(n_frames)

    # Convert to numpy array (interleaved stereo data)
    if sample_width == 2:  # 16-bit
        audio_data = np.frombuffer(frames, dtype=np.int16)
    elif sample_width == 4:  # 32-bit
        audio_data = np.frombuffer(frames, dtype=np.int32)
    else:
        logger.error(f"Unsupported sample width: {sample_width}")
        return False

    # Reshape to (n_samples, 2) and split channels
    audio_data = audio_data.reshape(-1, 2)
    left_channel = audio_data[:, 0]
    right_channel = audio_data[:, 1]

    # Write left channel
    with wave.open(str(output_left), 'wb') as wav_out:
        wav_out.setnchannels(1)
        wav_out.setsampwidth(sample_width)
        wav_out.setframerate(sample_rate)
        wav_out.writeframes(left_channel.tobytes())

    # Write right channel
    with wave.open(str(output_right), 'wb') as wav_out:
        wav_out.setnchannels(1)
        wav_out.setsampwidth(sample_width)
        wav_out.setframerate(sample_rate)
        wav_out.writeframes(right_channel.tobytes())

    logger.info(f"Split stereo file into: {output_left.name} and {output_right.name}")
    return True
