#!/usr/bin/env python3
"""
Script to translate a markdown file using Ollama.
This is a simple wrapper around the main.py script.
"""

import subprocess
import argparse
import sys
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Translate a markdown file using Ollama.")
    parser.add_argument("file", type=str, help="Path to the markdown file to translate")
    parser.add_argument("--language", type=str, default="French", help="Target language for translation")
    parser.add_argument("--model", type=str, default="granite3.2:8b", help="Ollama model to use")
    return parser.parse_args()

def main():
    # Check if any arguments were provided
    if len(sys.argv) == 1:
        print("Error: No file specified.")
        print("Usage: python translate_markdown.py <path_to_markdown_file> [--language <language>] [--model <model>]")
        print("\nExample: python translate_markdown.py output/document.md --language French --model granite3.2:8b")
        return
    
    try:
        args = parse_args()
    except SystemExit:
        # This catches the case where argparse exits due to invalid arguments
        return
    
    # Ensure the file exists
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File {file_path} does not exist.")
        return
    
    # Build the command
    cmd = [
        "python", "main.py",
        "--markdown-file", str(file_path),
        "--language", args.language,
        "--ollama-model", args.model
    ]
    
    # Run the command
    print(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
