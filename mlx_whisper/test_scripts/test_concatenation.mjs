#!/usr/bin/env node
/**
 * Test script for audio concatenation using Playwright with real MediaRecorder API.
 *
 * This script replicates the EXACT frontend behavior by running a headless browser
 * with the same MediaRecorder API that the frontend uses.
 *
 * Prerequisites:
 *   npm install playwright ws
 *   npx playwright install chromium
 *
 * Usage:
 *   node test_concatenation.mjs
 */

import { chromium } from 'playwright';
import WebSocket from 'ws';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { spawn, execSync } from 'child_process';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Configuration
const WEBSOCKET_URL = 'ws://localhost:8000/ws/transcribe';
const MODEL = 'mlx-community/whisper-medium-mlx';
const RECORD_DURATION = 30; // seconds per segment
const CHUNK_INTERVAL = 3000; // ms - same as frontend
const AUDIO_DIR = path.join(__dirname, '..', 'audio');
const RESULTS_DIR = path.join(AUDIO_DIR, 'test_results');

// Ensure results directory exists
if (!fs.existsSync(RESULTS_DIR)) {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
}

/**
 * Capture audio from BlackHole to a WAV file using ffmpeg
 */
async function captureAudioFromBlackHole(outputPath, duration) {
  console.log(`  Capturing ${duration}s of audio from BlackHole to ${outputPath}...`);

  return new Promise((resolve, reject) => {
    // Capture at 16kHz to match frontend's getUserMedia sampleRate constraint
    // (We're using Web Audio API now, not Chrome's fake audio capture which required 44.1kHz)
    const ffmpeg = spawn('ffmpeg', [
      '-y',
      '-f', 'avfoundation',
      '-i', ':BlackHole 2ch',
      '-t', String(duration),
      '-ar', '16000',  // 16kHz to match frontend
      '-ac', '2',      // Stereo
      '-c:a', 'pcm_s16le',  // 16-bit signed
      outputPath
    ], { stdio: ['pipe', 'pipe', 'pipe'] });

    let stderr = '';
    ffmpeg.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    ffmpeg.on('close', (code) => {
      if (code === 0) {
        console.log(`  Audio captured successfully: ${outputPath}`);
        resolve(outputPath);
      } else {
        console.error(`  ffmpeg error:`, stderr);
        reject(new Error(`ffmpeg exited with code ${code}`));
      }
    });

    ffmpeg.on('error', reject);
  });
}

/**
 * Simple WebSocket client matching frontend behavior
 */
class TestWebSocket {
  constructor() {
    this.ws = null;
    this.listeners = {};
  }

  async connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(WEBSOCKET_URL);

      this.ws.on('open', () => {
        console.log('  WebSocket connected');
        resolve();
      });

      this.ws.on('error', (err) => {
        console.error('  WebSocket error:', err.message);
        reject(err);
      });

      this.ws.on('message', (data) => {
        try {
          const msg = JSON.parse(data.toString());
          this._emit(msg.type, msg);
        } catch (e) {
          console.error('  Error parsing message:', e);
        }
      });

      this.ws.on('close', () => {
        console.log('  WebSocket disconnected');
      });
    });
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  sendAudioChunk(base64Data, duration) {
    this.send({
      type: 'audio_chunk',
      data: base64Data,
      duration: duration
    });
  }

  on(event, callback) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);
  }

  off(event, callback) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }
  }

  _emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(cb => cb(data));
    }
  }
}

/**
 * Wait for model to be ready
 */
async function waitForModelReady(wsClient, timeout = 120000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error('Model loading timeout'));
    }, timeout);

    const handler = (data) => {
      console.log(`  Server: ${data.type} - ${data.message || ''}`);
      if (data.type === 'model_ready') {
        clearTimeout(timer);
        wsClient.off('model_ready', handler);
        resolve();
      }
    };

    wsClient.on('model_ready', handler);
    wsClient.on('status', (data) => {
      console.log(`  Status: ${data.message || ''}`);
    });
    wsClient.on('download_progress', (data) => {
      console.log(`  Download: ${data.message || ''}`);
    });
  });
}

/**
 * Serve audio file via a local HTTP server for the browser to fetch
 */
async function createAudioServer(audioFilePath) {
  const http = await import('http');
  const audioData = fs.readFileSync(audioFilePath);

  const server = http.createServer((req, res) => {
    if (req.url === '/audio.wav') {
      res.writeHead(200, {
        'Content-Type': 'audio/wav',
        'Content-Length': audioData.length,
        'Access-Control-Allow-Origin': '*',
      });
      res.end(audioData);
    } else {
      res.writeHead(404);
      res.end();
    }
  });

  await new Promise(resolve => server.listen(9999, resolve));
  return server;
}

/**
 * Record using Playwright with real MediaRecorder API
 * Uses Web Audio API to load audio file and route to MediaRecorder
 * (Chrome's --use-file-for-fake-audio-capture is broken on macOS)
 */
async function recordWithPlaywright(wsClient, sessionNum, duration, audioFilePath) {
  console.log(`  Starting Playwright with MediaRecorder...`);
  console.log(`  Audio source: ${audioFilePath}`);
  console.log(`  Recording duration: ${duration}s, chunk interval: ${CHUNK_INTERVAL/1000}s`);

  // Start local HTTP server to serve the audio file
  const audioServer = await createAudioServer(audioFilePath);
  console.log(`  Audio server started on http://localhost:9999/audio.wav`);

  // Launch browser - no fake audio flags needed, we use Web Audio API instead
  const browser = await chromium.launch({
    headless: false,  // Web Audio API works better in headed mode
    args: [
      '--autoplay-policy=no-user-gesture-required',
      '--disable-web-security',  // Allow cross-origin audio fetch
    ]
  });

  const context = await browser.newContext();
  const page = await context.newPage();

  // Collect chunks and results from browser
  let totalBytes = 0;

  // Expose function for browser to send chunks to Node.js
  await page.exposeFunction('sendChunkToServer', (base64Data, chunkDuration, chunkNum, byteLen) => {
    wsClient.sendAudioChunk(base64Data, chunkDuration);
    totalBytes += byteLen;
    const elapsed = Math.floor(chunkNum * 3);
    console.log(`  Sent chunk ${chunkNum}: ${byteLen} bytes (${elapsed}/${duration}s)`);
  });

  await page.exposeFunction('logMessage', (msg) => {
    console.log(`  [Browser] ${msg}`);
  });

  // Navigate to a blank page first
  await page.goto('about:blank');

  // Run MediaRecorder in the browser using Web Audio API to load audio
  const result = await page.evaluate(async ({ durationMs, chunkIntervalMs }) => {
    return new Promise(async (resolve, reject) => {
      try {
        await window.logMessage('Fetching audio file from server...');

        // Fetch the audio file from our local server
        const response = await fetch('http://localhost:9999/audio.wav');
        const arrayBuffer = await response.arrayBuffer();

        await window.logMessage(`Audio fetched: ${arrayBuffer.byteLength} bytes`);

        // Decode the audio using Web Audio API at 16kHz (same as frontend getUserMedia constraint)
        const audioContext = new AudioContext({ sampleRate: 16000 });
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

        await window.logMessage(`Audio decoded: ${audioBuffer.duration.toFixed(2)}s, ${audioBuffer.numberOfChannels}ch`);

        // Create MediaStreamDestination - this gives us a stream we can record
        const destination = audioContext.createMediaStreamDestination();

        // Create a buffer source to play the audio
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(destination);

        // Get the stream from the destination - THIS is what MediaRecorder will record
        const stream = destination.stream;

        await window.logMessage('Created MediaStream from audio file');

        // Create MediaRecorder with EXACT same settings as frontend
        const mediaRecorder = new MediaRecorder(stream, {
          mimeType: 'audio/webm;codecs=opus',
        });

        const chunks = [];
        let chunkNum = 0;
        let pendingChunks = 0;
        let stopped = false;
        let resolveWhenDone = null;

        // Handle data available - EXACTLY like frontend
        mediaRecorder.ondataavailable = async (event) => {
          if (event.data.size > 0) {
            pendingChunks++;
            chunkNum++;
            const myChunkNum = chunkNum;
            const buffer = await event.data.arrayBuffer();
            const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));
            const dur = mediaRecorder.state === 'recording' ? 3.0 : 0;

            chunks.push(event.data);
            await window.sendChunkToServer(base64, dur, myChunkNum, buffer.byteLength);
            pendingChunks--;

            // If stopped and no more pending chunks, resolve
            if (stopped && pendingChunks === 0 && resolveWhenDone) {
              resolveWhenDone();
            }
          }
        };

        // Start playing audio and recording simultaneously
        await window.logMessage(`Starting MediaRecorder with ${chunkIntervalMs}ms timeslice...`);
        source.start(0);  // Start playing the audio
        mediaRecorder.start(chunkIntervalMs);  // Start recording

        // Stop after duration
        setTimeout(() => {
          window.logMessage('Stopping MediaRecorder...');
          mediaRecorder.stop();
          source.stop();
        }, durationMs);

        // Wait for stop event and all chunks to be processed
        mediaRecorder.onstop = async () => {
          stopped = true;

          // Wait for any pending chunk processing to complete
          if (pendingChunks > 0) {
            await new Promise(r => { resolveWhenDone = r; });
          }

          // Give a small delay to ensure last async operations complete
          await new Promise(r => setTimeout(r, 100));

          await window.logMessage(`Recording stopped. Total chunks: ${chunks.length}`);

          // Create full blob for local save
          const fullBlob = new Blob(chunks, { type: 'audio/webm;codecs=opus' });

          // Use FileReader for more efficient base64 encoding (avoids stack overflow on large buffers)
          const base64Full = await new Promise((resolveBase64) => {
            const reader = new FileReader();
            reader.onloadend = () => {
              // Result is "data:audio/webm;codecs=opus;base64,XXXX..."
              const base64 = reader.result.split(',')[1];
              resolveBase64(base64);
            };
            reader.readAsDataURL(fullBlob);
          });

          await window.logMessage(`Blob encoded: ${base64Full.length} chars`);

          // Don't close audioContext - let browser cleanup handle it

          resolve({
            chunkCount: chunks.length,
            totalSize: fullBlob.size,
            fullAudioBase64: base64Full
          });
        };

      } catch (error) {
        await window.logMessage(`Error: ${error.message}`);
        reject(error);
      }
    });
  }, { durationMs: duration * 1000, chunkIntervalMs: CHUNK_INTERVAL });

  // Stop the audio server
  audioServer.close();

  // Save the full recording locally
  const outputPath = path.join(AUDIO_DIR, `test_session_${sessionNum}_${Date.now()}.webm`);
  const fullAudio = Buffer.from(result.fullAudioBase64, 'base64');
  fs.writeFileSync(outputPath, fullAudio);

  console.log(`  Recording completed: ${outputPath}`);
  console.log(`  Total chunks sent: ${result.chunkCount}, ${totalBytes} bytes`);

  await browser.close();

  return { outputPath, duration, totalBytes, chunksSent: result.chunkCount };
}

/**
 * Create a transcription collector that listens for transcriptions throughout the session.
 * Matches frontend App.jsx handleTranscription logic exactly.
 * Must be started BEFORE recording begins to capture all transcriptions.
 */
function createTranscriptionCollector(wsClient, previousText = '') {
  let accumulatedText = previousText;
  let audioUrl = null;
  let duration = 0;
  let resolvePromise = null;
  let cleanedUp = false;

  const handleTranscription = (data) => {
    // Match frontend logic: simply append with space separator
    // Backend already deduplicates and sends only new portions
    const text = (data.text || '').trim();
    if (text) {
      // Append with space if we already have text, otherwise just use the new text
      if (accumulatedText) {
        accumulatedText = accumulatedText + ' ' + text;
      } else {
        accumulatedText = text;
      }
      console.log(`  Transcription: '${text.slice(0, 50)}...' (len=${text.length}, total=${accumulatedText.length})`);
    }
  };

  const handleStatus = (data) => {
    console.log(`  Status: ${data.message || ''}`);
    if (data.audio_url) {
      audioUrl = data.audio_url;
      duration = data.duration_seconds || 0;
      console.log(`  Audio URL: ${audioUrl}`);
      console.log(`  Duration: ${duration}s`);
      cleanup();
      if (resolvePromise) {
        resolvePromise({ text: accumulatedText, audioUrl, duration });
      }
    }
  };

  const cleanup = () => {
    if (!cleanedUp) {
      cleanedUp = true;
      wsClient.off('transcription', handleTranscription);
      wsClient.off('status', handleStatus);
    }
  };

  // Start listening immediately
  wsClient.on('transcription', handleTranscription);
  wsClient.on('status', handleStatus);

  return {
    // Wait for completion (audio_url received)
    waitForCompletion: (timeout = 60000) => {
      return new Promise((resolve) => {
        resolvePromise = resolve;

        // If already completed, resolve immediately
        if (audioUrl) {
          resolve({ text: accumulatedText, audioUrl, duration });
          return;
        }

        // Timeout fallback
        setTimeout(() => {
          if (!audioUrl) {
            cleanup();
            resolve({ text: accumulatedText, audioUrl, duration });
          }
        }, timeout);
      });
    },
    // Get current accumulated text
    getText: () => accumulatedText,
    // Clean up listeners
    cleanup
  };
}

/**
 * Run a recording session
 */
async function runSession(sessionNum, audioFilePath, resumeAudioPath = null, previousText = '') {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`Recording Session ${sessionNum}`);
  console.log(`${'='.repeat(60)}`);

  const wsClient = new TestWebSocket();

  try {
    await wsClient.connect();

    // Wait for connection confirmation
    await new Promise(resolve => setTimeout(resolve, 100));

    // Set model and wait for ready
    wsClient.send({ type: 'set_model', model: MODEL });
    await waitForModelReady(wsClient);

    // Set channel
    wsClient.send({ type: 'set_channel', channel: 'both' });

    // If resuming, send resume audio path
    if (resumeAudioPath) {
      console.log(`  Resuming from: ${resumeAudioPath}`);
      wsClient.send({ type: 'set_resume_audio', audio_path: resumeAudioPath });
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    // START COLLECTING TRANSCRIPTIONS BEFORE RECORDING
    // This is critical - transcriptions are sent DURING recording, not after
    const collector = createTranscriptionCollector(wsClient, previousText);

    // Record using Playwright with real MediaRecorder
    await recordWithPlaywright(wsClient, sessionNum, RECORD_DURATION, audioFilePath);

    // Signal end of recording
    wsClient.send({ type: 'end_recording' });

    // Wait for audio_url (completion signal) - collector has been listening throughout
    const result = await collector.waitForCompletion();

    console.log(`\n  Session ${sessionNum} complete:`);
    console.log(`    Audio: ${result.audioUrl}`);
    console.log(`    Duration: ${result.duration}s`);
    console.log(`    Transcript: ${(result.text || '').slice(0, 100)}...`);

    wsClient.disconnect();
    return result;

  } catch (error) {
    console.error(`  Error in session ${sessionNum}:`, error);
    wsClient.disconnect();
    throw error;
  }
}

/**
 * Transcribe audio file using the backend API (same as frontend transcribeFile)
 */
async function transcribeFullAudio(audioPath) {
  console.log(`\n${'='.repeat(60)}`);
  console.log('Transcribing full audio file (via backend API)');
  console.log(`${'='.repeat(60)}`);

  // Convert API path to filesystem path
  let fullPath = audioPath;
  if (audioPath.startsWith('/api/audio/')) {
    const filename = audioPath.replace('/api/audio/', '');
    fullPath = path.join(AUDIO_DIR, filename);
  }

  console.log(`  Audio file: ${fullPath}`);

  // Verify file exists
  if (!fs.existsSync(fullPath)) {
    console.error(`  ERROR: File does not exist: ${fullPath}`);
    return '';
  }

  // Get duration with ffprobe
  const duration = await new Promise((resolve) => {
    const ffprobe = spawn('ffprobe', [
      '-v', 'error',
      '-show_entries', 'format=duration',
      '-of', 'default=noprint_wrappers=1:nokey=1',
      fullPath
    ]);
    let output = '';
    ffprobe.stdout.on('data', (data) => { output += data; });
    ffprobe.on('close', () => {
      resolve(parseFloat(output.trim()) || 0);
    });
  });
  console.log(`  Duration: ${duration}s`);

  // Read file and send to backend API (like frontend does)
  const fileBuffer = fs.readFileSync(fullPath);
  const filename = path.basename(fullPath);
  console.log(`  File size: ${fileBuffer.length} bytes`);

  // Create multipart form data manually for Node.js
  const boundary = '----FormBoundary' + Date.now();
  const formData = Buffer.concat([
    Buffer.from(`--${boundary}\r\n`),
    Buffer.from(`Content-Disposition: form-data; name="file"; filename="${filename}"\r\n`),
    Buffer.from('Content-Type: audio/webm\r\n\r\n'),
    fileBuffer,
    Buffer.from(`\r\n--${boundary}--\r\n`)
  ]);

  console.log(`  Uploading to backend API /api/transcriptions/transcribe...`);

  const http = await import('http');
  const transcription = await new Promise((resolve, reject) => {
    const req = http.request({
      hostname: 'localhost',
      port: 8000,
      path: '/api/transcriptions/transcribe',
      method: 'POST',
      headers: {
        'Content-Type': `multipart/form-data; boundary=${boundary}`,
        'Content-Length': formData.length
      },
      timeout: 120000  // 2 minute timeout for transcription
    }, (res) => {
      let data = '';
      res.on('data', chunk => { data += chunk; });
      res.on('end', () => {
        console.log(`  API response status: ${res.statusCode}`);
        if (res.statusCode !== 200) {
          console.error(`  API error response: ${data}`);
          resolve('');
          return;
        }
        try {
          const result = JSON.parse(data);
          // API returns: {segments, markdown, audio_path, duration}
          // Join segment texts as plain text (no markdown)
          let text = '';
          if (result.segments && result.segments.length > 0) {
            text = result.segments.map(s => s.text.trim()).filter(t => t).join(' ');
          }
          console.log(`  API returned ${result.segments?.length || 0} segments`);
          console.log(`  Duration: ${result.duration?.toFixed(1) || 'unknown'}s`);
          resolve(text);
        } catch (e) {
          console.error('  Failed to parse API response:', data.slice(0, 200));
          resolve('');
        }
      });
    });
    req.on('error', (err) => {
      console.error('  API request error:', err.message);
      resolve('');
    });
    req.on('timeout', () => {
      console.error('  API request timed out');
      req.destroy();
      resolve('');
    });
    req.write(formData);
    req.end();
  });

  console.log(`  Transcription length: ${transcription.length} chars`);
  if (transcription.length > 0) {
    console.log(`  Preview: ${transcription.slice(0, 100)}...`);
  } else {
    console.log(`  WARNING: Empty transcription received from API`);
  }

  return transcription;
}

/**
 * Main test function
 */
async function main() {
  console.log('='.repeat(60));
  console.log('Audio Concatenation Test (Playwright + MediaRecorder)');
  console.log('='.repeat(60));
  console.log(`Recording duration: ${RECORD_DURATION}s per segment`);
  console.log(`Results directory: ${RESULTS_DIR}`);
  console.log('');

  // Total audio needed = 2 sessions * RECORD_DURATION
  const totalAudioDuration = RECORD_DURATION * 2 + 5; // Extra 5s buffer

  // Check for pre-captured WAV file first (blackhole_capture_test.wav)
  const preCapturedPath = path.join(AUDIO_DIR, 'blackhole_capture_test.wav');
  let capturedAudioPath;

  if (fs.existsSync(preCapturedPath)) {
    capturedAudioPath = preCapturedPath;
    console.log(`\n${'='.repeat(60)}`);
    console.log('Using pre-captured audio file');
    console.log(`${'='.repeat(60)}`);
    console.log(`  Found existing WAV file: ${preCapturedPath}`);
    console.log(`  Skipping BlackHole capture...`);
  } else {
    capturedAudioPath = path.join(AUDIO_DIR, `blackhole_capture_${Date.now()}.wav`);
    console.log(`\n${'='.repeat(60)}`);
    console.log('Capturing audio from BlackHole');
    console.log(`${'='.repeat(60)}`);
    await captureAudioFromBlackHole(capturedAudioPath, totalAudioDuration);
  }

  try {

    // Session 1: First recording
    const session1 = await runSession(1, capturedAudioPath);

    if (!session1.audioUrl) {
      console.error('ERROR: No audio URL from session 1');
      process.exit(1);
    }

    // Wait before session 2
    console.log('\n  Waiting 2 seconds before session 2...');
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Session 2: Resume recording
    const session2 = await runSession(2, capturedAudioPath, session1.audioUrl, session1.text);

    if (!session2.audioUrl) {
      console.error('ERROR: No audio URL from session 2');
      process.exit(1);
    }

    // Save streaming transcription
    const streamingPath = path.join(RESULTS_DIR, `test_001_${Date.now()}_streaming.txt`);
    fs.writeFileSync(streamingPath, session2.text);
    console.log(`  Saved: ${streamingPath}`);

    // Wait and transcribe full audio
    await new Promise(resolve => setTimeout(resolve, 2000));
    const fullTranscription = await transcribeFullAudio(session2.audioUrl);

    // Save full transcription
    const fullPath = path.join(RESULTS_DIR, `test_001_${Date.now()}_full.txt`);
    fs.writeFileSync(fullPath, fullTranscription);
    console.log(`  Saved: ${fullPath}`);

    // Keep WAV file for verification (don't clean up)
    // if (fs.existsSync(capturedAudioPath)) {
    //   fs.unlinkSync(capturedAudioPath);
    //   console.log(`  Cleaned up: ${capturedAudioPath}`);
    // }
    console.log(`  WAV file kept for verification: ${capturedAudioPath}`);

    // Check duration
    const expectedDuration = RECORD_DURATION * 2;
    if (session2.duration < expectedDuration * 0.8) {
      console.log(`\n  !!! BUG DETECTED !!!`);
      console.log(`  Expected duration: ~${expectedDuration}s`);
      console.log(`  Actual duration: ${session2.duration}s`);
      console.log(`  Concatenation likely failed!`);
      process.exit(1);
    }

    console.log(`\n=== TEST PASSED ===`);
    console.log(`Total duration: ${session2.duration}s (expected: ~${expectedDuration}s)`);

  } catch (error) {
    console.error('Test failed:', error);
    // Keep WAV file for verification even on error
    // if (fs.existsSync(capturedAudioPath)) {
    //   fs.unlinkSync(capturedAudioPath);
    // }
    console.log(`  WAV file kept for verification: ${capturedAudioPath}`);
    process.exit(1);
  }
}

main();
