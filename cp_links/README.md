# cp_links

A utility to save and restore symbolic links across systems.

## Purpose

When copying files between systems (particularly over networks), symbolic links often cannot be preserved. This tool allows you to:

1. Save information about all symbolic links in a directory to a JSON file
2. Later restore those links on a target system after copying the files

## Usage

### Save symbolic links

```bash
python cp_links.py /path/to/source/directory links.json
```

This scans the specified directory recursively for symbolic links and saves their information to a JSON file.

### Restore symbolic links

```bash
python cp_links.py links.json
```

This reads the JSON file and recreates all the symbolic links in their relative locations.

## Notes

- The tool will not overwrite an existing JSON file when saving links
- When restoring, existing paths will be skipped (not overwritten)
- Relative paths in the JSON file are relative to the current directory when restoring

## Requirements

- Python 3.6+
- No external dependencies