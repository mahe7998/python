#!/usr/bin/env python3
"""
Simple Flask API wrapper for YouTube scripts
Allows n8n to call these scripts via HTTP requests
"""

from flask import Flask, jsonify, request
import os
from get_channel_id import get_channel_id_by_username
from get_playlist_videos import get_all_playlist_videos, get_channel_uploads_playlist

app = Flask(__name__)

# Get API key from environment
API_KEY = os.getenv('GOOGLE_YOUTUBE_API_KEY')

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok"})

@app.route('/channel/<username>', methods=['GET'])
def get_channel(username):
    """
    Get channel information by username
    Example: GET /channel/@matthew_berman
    """
    api_key = request.args.get('api_key', API_KEY)

    if not api_key:
        return jsonify({"error": "API key required"}), 400

    channel_info = get_channel_id_by_username(api_key, username)

    if not channel_info:
        return jsonify({"error": f"Channel not found: {username}"}), 404

    return jsonify(channel_info)

@app.route('/videos/by-username/<username>', methods=['GET'])
def get_videos_by_username(username):
    """
    Get all videos from a channel by username
    Example: GET /videos/by-username/@matthew_berman?max_results=50
    """
    api_key = request.args.get('api_key', API_KEY)
    max_results = request.args.get('max_results', type=int)

    if not api_key:
        return jsonify({"error": "API key required"}), 400

    # First get the uploads playlist ID
    playlist_id = get_channel_uploads_playlist(api_key, username)
    if not playlist_id:
        return jsonify({"error": f"Channel not found: {username}"}), 404

    # Get videos
    videos = get_all_playlist_videos(api_key, playlist_id, max_results)

    if videos is None:
        return jsonify({"error": "Failed to retrieve videos"}), 500

    return jsonify({
        "channel": username,
        "playlist_id": playlist_id,
        "count": len(videos),
        "videos": videos
    })

@app.route('/videos/by-playlist/<playlist_id>', methods=['GET'])
def get_videos_by_playlist(playlist_id):
    """
    Get all videos from a playlist by ID
    Example: GET /videos/by-playlist/UUawZsQWqfGSbCI5yjkdVkTA?max_results=50
    """
    api_key = request.args.get('api_key', API_KEY)
    max_results = request.args.get('max_results', type=int)

    if not api_key:
        return jsonify({"error": "API key required"}), 400

    videos = get_all_playlist_videos(api_key, playlist_id, max_results)

    if videos is None:
        return jsonify({"error": "Failed to retrieve videos"}), 500

    return jsonify({
        "playlist_id": playlist_id,
        "count": len(videos),
        "videos": videos
    })

if __name__ == '__main__':
    if not API_KEY:
        print("Warning: GOOGLE_YOUTUBE_API_KEY not set")

    # Run on port 5001, accessible from localhost
    app.run(host='0.0.0.0', port=5001, debug=True)
