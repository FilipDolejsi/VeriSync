from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path


@dataclass
class PRChunk:
    """Represents a single chunk from a PR diff with file and hunk information."""

    file: str
    hunk: str  # e.g., "@@ -10,5 +10,7 @@"
    lines: List[str]
    detected_language: Optional[str]


# Language detection map based on file extensions
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "jsx",
    ".tsx": "tsx",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".sql": "sql",
    ".r": "r",
    ".R": "r",
    ".m": "matlab",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".groovy": "groovy",
    ".gradle": "gradle",
    ".xml": "xml",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "conf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "rst",
    ".tex": "latex",
}


def detect_language(filepath: str) -> Optional[str]:
    """
    Detect programming language based on file extension.

    Args:
        filepath: The file path to detect language for

    Returns:
        Language name or None if not detected
    """
    ext = Path(filepath).suffix.lower()
    return LANGUAGE_MAP.get(ext)


def parse_unified_diff(diff_content: str) -> List[PRChunk]:
    """
    Parse unified diff format into PRChunk objects.

    Unified diff format:
    --- a/path/to/file
    +++ b/path/to/file
    @@ -start,count +start,count @@
    context line
    -removed line
    +added line

    Args:
        diff_content: The unified diff content as a string

    Returns:
        List of PRChunk objects representing each change
    """
    chunks = []
    lines = diff_content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip until we find a file header
        if line.startswith("--- a/") or line.startswith("--- /"):
            # Parse file path from the --- line
            file_path = line[6:]  # Remove '--- a/' or '--- /'

            # Skip the +++ line
            i += 1
            if i < len(lines) and (
                lines[i].startswith("+++ b/") or lines[i].startswith("+++ ")
            ):
                i += 1
            else:
                i += 1
                continue

            # Now parse hunks for this file
            while i < len(lines):
                hunk_line = lines[i]

                # Check if this is a hunk header
                if hunk_line.startswith("@@"):
                    # Extract hunk header (e.g., "@@ -10,5 +10,7 @@")
                    hunk_end = hunk_line.find("@@", 2)
                    if hunk_end != -1:
                        hunk_header = hunk_line[: hunk_end + 2].strip()
                    else:
                        hunk_header = hunk_line.strip()

                    i += 1

                    # Collect lines for this hunk
                    chunk_lines = []
                    while i < len(lines):
                        current_line = lines[i]

                        # Stop if we hit another hunk or file header
                        if (
                            current_line.startswith("@@")
                            or current_line.startswith("--- ")
                            or current_line.startswith("diff --git")
                        ):
                            break

                        # Include diff lines (context, additions, deletions)
                        if current_line.startswith(("+", "-", " ")):
                            chunk_lines.append(current_line)
                            i += 1
                        elif current_line == "" or current_line.startswith("\\"):
                            # Empty lines or "\ No newline at end of file"
                            if current_line != "":
                                chunk_lines.append(current_line)
                            i += 1
                        else:
                            # Other content (shouldn't happen in well-formed diffs)
                            i += 1
                            break

                    # Create chunk if we have lines
                    if chunk_lines:
                        detected_lang = detect_language(file_path)
                        chunk = PRChunk(
                            file=file_path,
                            hunk=hunk_header,
                            lines=chunk_lines,
                            detected_language=detected_lang,
                        )
                        chunks.append(chunk)
                else:
                    # Not a hunk header, might be another file or end
                    break
        else:
            i += 1

    return chunks

