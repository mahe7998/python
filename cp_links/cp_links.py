#!/usr/bin/env python3
import os
import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Union


def find_symlinks(path: str) -> Dict[str, str]:
    """
    Find all symbolic links in the given path recursively.
    
    Args:
        path: Directory to search for symlinks
        
    Returns:
        Dictionary mapping relative paths to their link targets
    """
    path = Path(path).resolve()
    links = {}
    
    for root, _, files in os.walk(path):
        root_path = Path(root)
        
        # Check for symlinks in directories
        for item in os.scandir(root):
            if item.is_symlink():
                link_path = Path(item.path)
                # Get the target of the symlink
                target = os.readlink(item.path)
                # Store the path relative to the base path
                rel_path = str(link_path.relative_to(path))
                links[rel_path] = target
                
    return links


def save_symlinks(path: str, output_file: str) -> None:
    """
    Find all symlinks in the path and save them to a JSON file.
    
    Args:
        path: Directory to search for symlinks
        output_file: JSON file to save the symlinks
    """
    if os.path.exists(output_file):
        print(f"Output file {output_file} already exists. Will not overwrite.")
        return
        
    links = find_symlinks(path)
    
    with open(output_file, 'w') as f:
        json.dump(links, f, indent=2)
    
    print(f"Found {len(links)} symlinks and saved to {output_file}")


def restore_symlinks(json_file: str) -> None:
    """
    Restore symlinks from a JSON file.
    
    Args:
        json_file: JSON file containing symlink information
    """
    if not os.path.exists(json_file):
        print(f"JSON file {json_file} does not exist.")
        return
        
    with open(json_file, 'r') as f:
        links = json.load(f)
    
    success_count = 0
    error_count = 0
    
    for rel_path, target in links.items():
        try:
            # Create parent directories if they don't exist
            link_path = Path(rel_path)
            os.makedirs(os.path.dirname(link_path), exist_ok=True)
            
            # Create the symlink if it doesn't already exist
            if not os.path.lexists(rel_path):
                os.symlink(target, rel_path)
                success_count += 1
            else:
                print(f"Skipping existing path: {rel_path}")
        except Exception as e:
            print(f"Error restoring symlink {rel_path} -> {target}: {e}")
            error_count += 1
    
    print(f"Restored {success_count} symlinks with {error_count} errors")


def main():
    parser = argparse.ArgumentParser(
        description="Save and restore symbolic links. "
                    "If the first argument is a directory, symlinks are saved to a JSON file. "
                    "If the first argument is a JSON file, symlinks are restored from it."
    )
    parser.add_argument("source", help="Directory to scan for symlinks or JSON file to restore from")
    parser.add_argument("destination", help="JSON file to save to (when source is a directory)")
    
    args = parser.parse_args()
    
    # Check if source is a directory or a JSON file
    if os.path.isdir(args.source):
        save_symlinks(args.source, args.destination)
    elif os.path.isfile(args.source) and args.source.lower().endswith('.json'):
        restore_symlinks(args.source)
    else:
        print(f"Error: {args.source} is not a valid directory or JSON file")
        sys.exit(1)


if __name__ == "__main__":
    main()