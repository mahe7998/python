#!/usr/bin/env python3
"""
YouTube Playlist Videos Retriever
Retrieves all videos from a YouTube playlist (like a channel's uploads)
"""

import argparse
import os
import sys
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def get_all_playlist_videos(api_key, playlist_id, max_results=None):
    """
    Get all videos from a YouTube playlist with pagination

    Args:
        api_key (str): YouTube Data API key
        playlist_id (str): YouTube playlist ID (e.g., UUawZsQWqfGSbCI5yjkdVkTA)
        max_results (int): Maximum number of videos to retrieve (None for all)

    Returns:
        list: List of video information dictionaries
    """
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        videos = []
        next_page_token = None
        page_count = 0

        while True:
            # Request playlist items
            request = youtube.playlistItems().list(
                part='snippet,contentDetails',
                playlistId=playlist_id,
                maxResults=50,  # Max allowed per page
                pageToken=next_page_token
            )

            response = request.execute()
            page_count += 1

            # Extract video information
            for item in response.get('items', []):
                video_info = {
                    'video_id': item['contentDetails']['videoId'],
                    'title': item['snippet']['title'],
                    'description': item['snippet']['description'],
                    'published_at': item['snippet']['publishedAt'],
                    'channel_id': item['snippet']['channelId'],
                    'channel_title': item['snippet']['channelTitle'],
                    'thumbnail': item['snippet']['thumbnails'].get('high', {}).get('url', ''),
                    'position': item['snippet']['position']
                }
                videos.append(video_info)

                # Check if we've reached max_results
                if max_results and len(videos) >= max_results:
                    return videos[:max_results]

            # Check if there are more pages
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

            # Progress indicator
            if not max_results:
                print(f"Retrieved {len(videos)} videos so far (page {page_count})...", file=sys.stderr)

        return videos

    except HttpError as e:
        print(f"An HTTP error occurred: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        return None


def get_channel_uploads_playlist(api_key, username):
    """
    Get the uploads playlist ID from a channel username

    Args:
        api_key (str): YouTube Data API key
        username (str): YouTube username or @username handle

    Returns:
        str: Uploads playlist ID
    """
    username = username.lstrip('@')

    try:
        youtube = build('youtube', 'v3', developerKey=api_key)

        # Try forHandle first
        request = youtube.channels().list(
            part='contentDetails',
            forHandle=username
        )
        response = request.execute()

        # If forHandle didn't work, try forUsername
        if not response.get('items'):
            request = youtube.channels().list(
                part='contentDetails',
                forUsername=username
            )
            response = request.execute()

        # If still no results, try search
        if not response.get('items'):
            search_request = youtube.search().list(
                part='snippet',
                q=username,
                type='channel',
                maxResults=1
            )
            search_response = search_request.execute()

            if search_response.get('items'):
                channel_id = search_response['items'][0]['snippet']['channelId']
                request = youtube.channels().list(
                    part='contentDetails',
                    id=channel_id
                )
                response = request.execute()

        if not response.get('items'):
            return None

        return response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    except HttpError as e:
        print(f"An HTTP error occurred: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Retrieve all videos from a YouTube playlist or channel'
    )

    # Input method: either playlist ID or username
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--playlist-id',
        help='YouTube playlist ID (e.g., UUawZsQWqfGSbCI5yjkdVkTA)'
    )
    input_group.add_argument(
        '--username',
        help='YouTube username or @username handle (will fetch uploads playlist)'
    )

    parser.add_argument(
        '--api-key',
        default=os.getenv('GOOGLE_YOUTUBE_API_KEY'),
        help='YouTube Data API key (defaults to GOOGLE_YOUTUBE_API_KEY environment variable)'
    )
    parser.add_argument(
        '--max-results',
        type=int,
        help='Maximum number of videos to retrieve (default: all)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON format'
    )
    parser.add_argument(
        '--csv',
        action='store_true',
        help='Output as CSV format'
    )

    args = parser.parse_args()

    # Check if API key is provided
    if not args.api_key:
        print("Error: API key is required. Provide it via --api-key or set GOOGLE_YOUTUBE_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)

    # Get playlist ID
    if args.username:
        print(f"Looking up uploads playlist for {args.username}...", file=sys.stderr)
        playlist_id = get_channel_uploads_playlist(args.api_key, args.username)
        if not playlist_id:
            print(f"Could not find channel for username: {args.username}", file=sys.stderr)
            sys.exit(1)
        print(f"Found playlist ID: {playlist_id}", file=sys.stderr)
    else:
        playlist_id = args.playlist_id

    # Get all videos
    print(f"Retrieving videos from playlist {playlist_id}...", file=sys.stderr)
    videos = get_all_playlist_videos(args.api_key, playlist_id, args.max_results)

    if videos is None:
        print("Failed to retrieve videos", file=sys.stderr)
        sys.exit(1)

    if not videos:
        print("No videos found in playlist", file=sys.stderr)
        sys.exit(0)

    print(f"\nTotal videos retrieved: {len(videos)}", file=sys.stderr)
    print("", file=sys.stderr)  # Empty line before output

    # Output results
    if args.json:
        import json
        print(json.dumps(videos, indent=2))
    elif args.csv:
        import csv
        import io
        output = io.StringIO()
        if videos:
            writer = csv.DictWriter(output, fieldnames=videos[0].keys())
            writer.writeheader()
            writer.writerows(videos)
        print(output.getvalue())
    else:
        # Human-readable format
        print("="*80)
        for i, video in enumerate(videos, 1):
            print(f"\n{i}. {video['title']}")
            print(f"   Video ID: {video['video_id']}")
            print(f"   URL: https://youtube.com/watch?v={video['video_id']}")
            print(f"   Published: {video['published_at']}")
            if video['description']:
                desc = video['description'][:100] + '...' if len(video['description']) > 100 else video['description']
                print(f"   Description: {desc}")
        print("\n" + "="*80)


if __name__ == '__main__':
    main()
