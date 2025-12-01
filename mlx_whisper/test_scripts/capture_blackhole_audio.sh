#!/bin/bash
# Capture audio from BlackHole 2ch at 16kHz stereo using sox
# Usage: ./capture_blackhole_audio.sh [duration_seconds]
# Note: Using sox instead of ffmpeg to avoid crackling/corruption issues

DURATION=${1:-65}
AUDIO_DIR="$(dirname "$0")/../audio"
OUTPUT_FILE="$AUDIO_DIR/blackhole_capture_test.wav"

# Delete existing file if it exists
if [ -f "$OUTPUT_FILE" ]; then
    echo "Removing existing file: $OUTPUT_FILE"
    rm -f "$OUTPUT_FILE"
fi

echo "Capturing ${DURATION}s of audio from BlackHole at 16kHz stereo (using sox)..."
echo "Output: $OUTPUT_FILE"
echo ""

# Use sox for reliable BlackHole capture (ffmpeg has known issues)
# -t coreaudio: use macOS CoreAudio driver
# -r 16000: resample to 16kHz
# -c 2: stereo output
# trim 0 $DURATION: capture for specified duration
sox -t coreaudio "BlackHole 2ch" -r 16000 -c 2 "$OUTPUT_FILE" trim 0 "$DURATION"

if [ $? -eq 0 ]; then
    echo ""
    echo "Capture complete!"
    echo ""
    # Use soxi (sox info) or ffprobe for file info
    if command -v soxi &> /dev/null; then
        soxi "$OUTPUT_FILE"
    else
        ffprobe -v error -show_entries stream=sample_rate,channels,duration -of default=noprint_wrappers=1 "$OUTPUT_FILE"
    fi
    ls -lh "$OUTPUT_FILE"
else
    echo "Capture failed!"
    echo "Make sure sox is installed: brew install sox"
    exit 1
fi
