#!/usr/bin/env python3
"""
YouTube Channel ID Retriever
Retrieves YouTube channel ID from @username or username
"""

import argparse
import os
import sys
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def get_channel_id_by_username(api_key, username):
    """
    Get YouTube channel ID from username or @username handle

    Args:
        api_key (str): YouTube Data API key
        username (str): YouTube username or @username handle

    Returns:
        dict: Channel information including ID, title, description, etc.
    """
    # Remove @ if present
    username = username.lstrip('@')

    try:
        # Build YouTube API client
        youtube = build('youtube', 'v3', developerKey=api_key)

        # Try forHandle first (for @username handles)
        request = youtube.channels().list(
            part='snippet,contentDetails,statistics',
            forHandle=username
        )

        response = request.execute()

        # If forHandle didn't work, try forUsername
        if not response.get('items'):
            request = youtube.channels().list(
                part='snippet,contentDetails,statistics',
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

                # Get full channel details
                request = youtube.channels().list(
                    part='snippet,contentDetails,statistics',
                    id=channel_id
                )
                response = request.execute()

        if not response.get('items'):
            return None

        channel = response['items'][0]

        # Extract relevant information
        channel_info = {
            'channel_id': channel['id'],
            'title': channel['snippet']['title'],
            'description': channel['snippet']['description'][:200] + '...' if len(channel['snippet']['description']) > 200 else channel['snippet']['description'],
            'custom_url': channel['snippet'].get('customUrl', 'N/A'),
            'published_at': channel['snippet']['publishedAt'],
            'subscriber_count': channel['statistics'].get('subscriberCount', 'Hidden'),
            'video_count': channel['statistics']['videoCount'],
            'view_count': channel['statistics']['viewCount'],
            'uploads_playlist_id': channel['contentDetails']['relatedPlaylists']['uploads']
        }

        return channel_info

    except HttpError as e:
        print(f"An HTTP error occurred: {e}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Retrieve YouTube channel ID from username or @username handle'
    )
    parser.add_argument(
        'username',
        help='YouTube username or @username handle (e.g., @matthew_berman or matthew_berman)'
    )
    parser.add_argument(
        '--api-key',
        default=os.getenv('GOOGLE_YOUTUBE_API_KEY'),
        help='YouTube Data API key (defaults to GOOGLE_YOUTUBE_API_KEY environment variable)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON format'
    )

    args = parser.parse_args()

    # Check if API key is provided
    if not args.api_key:
        print("Error: API key is required. Provide it via --api-key or set GOOGLE_YOUTUBE_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)

    # Get channel information
    channel_info = get_channel_id_by_username(args.api_key, args.username)

    if not channel_info:
        print(f"Could not find channel for username: {args.username}", file=sys.stderr)
        sys.exit(1)

    # Output results
    if args.json:
        import json
        print(json.dumps(channel_info, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"Channel Information for: {args.username}")
        print(f"{'='*60}")
        print(f"Channel ID:          {channel_info['channel_id']}")
        print(f"Title:               {channel_info['title']}")
        print(f"Custom URL:          {channel_info['custom_url']}")
        print(f"Uploads Playlist ID: {channel_info['uploads_playlist_id']}")
        print(f"Subscribers:         {channel_info['subscriber_count']}")
        print(f"Total Videos:        {channel_info['video_count']}")
        print(f"Total Views:         {channel_info['view_count']}")
        print(f"Created:             {channel_info['published_at']}")
        print(f"\nDescription:\n{channel_info['description']}")
        print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
