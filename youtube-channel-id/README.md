# YouTube Channel Tools

Python scripts to retrieve YouTube channel information and all videos from a channel.

## Features

### get_channel_id.py
- Retrieve channel ID from username or @username handle
- Get comprehensive channel information including:
  - Channel ID
  - Title
  - Custom URL
  - Uploads playlist ID
  - Subscriber count
  - Video count
  - Total views
  - Channel description
- Output in human-readable format or JSON
- Supports multiple username formats (@username, username)

### get_playlist_videos.py
- Retrieve all videos from any YouTube playlist
- Get videos directly from a channel username (auto-fetches uploads playlist)
- Pagination support to retrieve unlimited videos
- Export in multiple formats: human-readable, JSON, or CSV
- Includes video metadata: title, description, published date, thumbnails, etc.

## Prerequisites

- Python 3.7+
- YouTube Data API v3 key

### Getting a YouTube API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **YouTube Data API v3**
4. Go to **Credentials** → **Create Credentials** → **API Key**
5. Copy your API key

## Installation

1. Clone or download this repository

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. **(Optional but recommended)** Set up environment variable for API key:

Add to your `~/.zshrc` or `~/.bashrc`:
```bash
export GOOGLE_YOUTUBE_API_KEY="YOUR_API_KEY_HERE"
```

Then reload:
```bash
source ~/.zshrc  # or source ~/.bashrc
```

With this setup, you won't need to pass `--api-key` every time!

## Usage

### Script 1: Get Channel Information

**Basic Usage:**
```bash
# With environment variable set:
python3 get_channel_id.py @matthew_berman

# Or with explicit API key:
python3 get_channel_id.py @matthew_berman --api-key YOUR_API_KEY
```

**JSON Output:**
```bash
python3 get_channel_id.py @matthew_berman --json
```

**Example Output:**
```
============================================================
Channel Information for: @matthew_berman
============================================================
Channel ID:          UCawZsQWqfGSbCI5yjkdVkTA
Title:               Matthew Berman
Custom URL:          @matthew_berman
Uploads Playlist ID: UUawZsQWqfGSbCI5yjkdVkTA
Subscribers:         524000
Total Videos:        766
Total Views:         64801239
Created:             2008-01-27T09:20:24Z

Description:
Artificial Intelligence (AI), Open Source, Generative Art...
============================================================
```

**Command Line Options:**
- `username` (required): YouTube username or @username handle
- `--api-key` (optional): Your YouTube Data API key (uses GOOGLE_YOUTUBE_API_KEY env var if not provided)
- `--json` (optional): Output results in JSON format

---

### Script 2: Get All Videos from a Channel/Playlist

**Get all videos from a channel (by username):**
```bash
# With environment variable set:
python3 get_playlist_videos.py --username @matthew_berman

# Or with explicit API key:
python3 get_playlist_videos.py --username @matthew_berman --api-key YOUR_API_KEY
```

**Get videos from a specific playlist ID:**
```bash
python3 get_playlist_videos.py --playlist-id UUawZsQWqfGSbCI5yjkdVkTA
```

**Limit number of results:**
```bash
python3 get_playlist_videos.py --username @matthew_berman --max-results 50
```

**JSON output (for use in other scripts/n8n):**
```bash
python3 get_playlist_videos.py --username @matthew_berman --json
```

**CSV output:**
```bash
python3 get_playlist_videos.py --username @matthew_berman --csv > videos.csv
```

**Command Line Options:**
- `--username` OR `--playlist-id` (one required): Channel username or playlist ID
- `--api-key` (optional): Your YouTube Data API key (uses GOOGLE_YOUTUBE_API_KEY env var if not provided)
- `--max-results` (optional): Maximum number of videos to retrieve
- `--json` (optional): Output as JSON
- `--csv` (optional): Output as CSV

## Using as Python Modules

You can also import and use these functions in your own Python scripts:

**Example 1: Get Channel Info**
```python
from get_channel_id import get_channel_id_by_username

api_key = "YOUR_API_KEY"
username = "@matthew_berman"

channel_info = get_channel_id_by_username(api_key, username)

if channel_info:
    print(f"Channel ID: {channel_info['channel_id']}")
    print(f"Uploads Playlist: {channel_info['uploads_playlist_id']}")
```

**Example 2: Get All Videos**
```python
from get_playlist_videos import get_all_playlist_videos

api_key = "YOUR_API_KEY"
playlist_id = "UUawZsQWqfGSbCI5yjkdVkTA"

videos = get_all_playlist_videos(api_key, playlist_id)

if videos:
    for video in videos:
        print(f"{video['title']} - {video['video_id']}")
```

## n8n Integration

### Option 1: Execute Command Node (Direct)

Use n8n's **Execute Command** node to run the Python scripts directly:

**Get Channel Info:**
- Command: `python3`
- Arguments: `/full/path/to/get_channel_id.py @matthew_berman --json`

**Get Videos:**
- Command: `python3`
- Arguments: `/full/path/to/get_playlist_videos.py --username @matthew_berman --json`

Then use a **Code** node to parse the JSON output from `stdout`.

### Option 2: Flask API Server (Recommended for n8n)

Run the included Flask API server for easier HTTP integration:

**1. Start the API server:**
```bash
cd ~/projects/python/youtube-channel-id
python3 api_server.py
```

The server runs on `http://localhost:5001`

**2. Use HTTP Request nodes in n8n:**

**Get Channel Info:**
- Method: `GET`
- URL: `http://localhost:5001/channel/@matthew_berman`

**Get Videos:**
- Method: `GET`
- URL: `http://localhost:5001/videos/by-username/@matthew_berman`
- Query Parameters: `max_results=50` (optional)

**Get Videos by Playlist ID:**
- Method: `GET`
- URL: `http://localhost:5001/videos/by-playlist/UUawZsQWqfGSbCI5yjkdVkTA`

**API Endpoints:**
- `GET /health` - Health check
- `GET /channel/<username>` - Get channel info
- `GET /videos/by-username/<username>?max_results=N` - Get videos by username
- `GET /videos/by-playlist/<playlist_id>?max_results=N` - Get videos by playlist ID

The API automatically uses your `GOOGLE_YOUTUBE_API_KEY` environment variable.

## Tips & Notes

- The **Uploads Playlist ID** starts with `UU` instead of `UC` (channel ID)
- Both scripts try multiple methods to find channels (forHandle, forUsername, search)
- Subscriber count may show as "Hidden" if the channel has disabled it
- To get ALL videos from a channel, use `--username` without `--max-results`
- Videos are returned in reverse chronological order (newest first)
- API quota: ~100 units per channel lookup, ~1 unit per 50 videos retrieved

## Error Handling

The script will exit with an error message if:
- The channel cannot be found
- The API key is invalid
- API quota is exceeded
- Network errors occur

## License

MIT License

## Author

Created for n8n YouTube integration
