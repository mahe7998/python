"""
Diff service for transcription version control
Handles patch generation, application, and validation
"""
import difflib
from typing import List, Tuple, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DiffService:
    """Service for managing text diffs and patches"""

    @staticmethod
    def generate_diff(old_text: str, new_text: str) -> str:
        """
        Generate a unified diff patch between two text versions.

        Args:
            old_text: Original text content
            new_text: Modified text content

        Returns:
            Unified diff patch as string
        """
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile='original',
            tofile='modified',
            lineterm=''
        )

        return ''.join(diff)

    @staticmethod
    def apply_patch(original_text: str, patch: str) -> str:
        """
        Apply a unified diff patch to original text.

        Args:
            original_text: Original text content
            patch: Unified diff patch string

        Returns:
            Patched text content

        Raises:
            ValueError: If patch cannot be applied
        """
        if not patch.strip():
            return original_text

        original_lines = original_text.splitlines(keepends=True)
        patch_lines = patch.splitlines(keepends=True)

        # Parse the patch
        hunks = DiffService._parse_unified_diff(patch_lines)

        # Apply hunks to original text
        result_lines = original_lines.copy()
        offset = 0  # Track line number offset as we modify

        for hunk_start, hunk_old_count, hunk_new_count, hunk_lines in hunks:
            # Apply this hunk
            actual_start = hunk_start + offset - 1  # Convert to 0-based index

            # Remove old lines and insert new lines
            removed_lines = []
            added_lines = []

            for line in hunk_lines:
                if line.startswith('-'):
                    removed_lines.append(line[1:])
                elif line.startswith('+'):
                    added_lines.append(line[1:])

            # Replace the section
            end_idx = actual_start + len(removed_lines)
            result_lines[actual_start:end_idx] = added_lines

            # Update offset
            offset += len(added_lines) - len(removed_lines)

        return ''.join(result_lines)

    @staticmethod
    def _parse_unified_diff(patch_lines: List[str]) -> List[Tuple[int, int, int, List[str]]]:
        """
        Parse unified diff format into hunks.

        Returns:
            List of tuples: (start_line, old_count, new_count, hunk_lines)
        """
        hunks = []
        current_hunk = None

        for line in patch_lines:
            if line.startswith('@@'):
                # Parse hunk header: @@ -start,count +start,count @@
                parts = line.split('@@')[1].strip().split()
                old_part = parts[0]  # -start,count
                new_part = parts[1]  # +start,count

                old_start = int(old_part.split(',')[0][1:])  # Remove '-' prefix
                old_count = int(old_part.split(',')[1]) if ',' in old_part else 1

                new_start = int(new_part.split(',')[0][1:])  # Remove '+' prefix
                new_count = int(new_part.split(',')[1]) if ',' in new_part else 1

                if current_hunk:
                    hunks.append(current_hunk)

                current_hunk = (old_start, old_count, new_count, [])

            elif current_hunk and (line.startswith('-') or line.startswith('+') or line.startswith(' ')):
                current_hunk[3].append(line)

        if current_hunk:
            hunks.append(current_hunk)

        return hunks

    @staticmethod
    def apply_patches(original_text: str, patches: List[str]) -> str:
        """
        Apply multiple patches sequentially to reconstruct a version.

        Args:
            original_text: Original text content
            patches: List of patches to apply in order

        Returns:
            Final text after applying all patches
        """
        current_text = original_text

        for i, patch in enumerate(patches):
            try:
                current_text = DiffService.apply_patch(current_text, patch)
            except Exception as e:
                logger.error(f"Failed to apply patch {i+1}/{len(patches)}: {e}")
                raise ValueError(f"Failed to apply patch {i+1}: {e}")

        return current_text

    @staticmethod
    def validate_patch_chain(
        original_text: str,
        patches: List[str],
        expected_final: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that applying patches to original produces expected result.

        Args:
            original_text: Original text content
            patches: List of patches to apply
            expected_final: Expected final text after all patches

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            reconstructed = DiffService.apply_patches(original_text, patches)

            if reconstructed == expected_final:
                return True, None
            else:
                # Calculate diff for debugging
                diff_lines = list(difflib.unified_diff(
                    expected_final.splitlines(),
                    reconstructed.splitlines(),
                    lineterm=''
                ))
                error_msg = f"Validation failed: reconstructed text differs from expected. Diff:\n" + \
                           '\n'.join(diff_lines[:20])  # First 20 lines of diff
                return False, error_msg

        except Exception as e:
            return False, f"Validation failed with exception: {e}"

    @staticmethod
    def generate_summary(old_text: str, new_text: str, max_length: int = 100) -> str:
        """
        Generate a human-readable summary of changes.

        Args:
            old_text: Original text
            new_text: Modified text
            max_length: Maximum summary length

        Returns:
            Summary string
        """
        old_len = len(old_text)
        new_len = len(new_text)
        diff = new_len - old_len

        # Count line changes
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        opcodes = matcher.get_opcodes()

        added = sum(1 for op, _, _, j1, j2 in opcodes if op == 'insert' for _ in range(j1, j2))
        deleted = sum(1 for op, i1, i2, _, _ in opcodes if op == 'delete' for _ in range(i1, i2))
        modified = sum(1 for op in opcodes if op == 'replace')

        parts = []
        if added > 0:
            parts.append(f"+{added} lines")
        if deleted > 0:
            parts.append(f"-{deleted} lines")
        if modified > 0:
            parts.append(f"~{modified} changed")

        summary = ", ".join(parts) if parts else "No changes"

        if diff > 0:
            summary += f" (+{diff} chars)"
        elif diff < 0:
            summary += f" ({diff} chars)"

        return summary[:max_length]
