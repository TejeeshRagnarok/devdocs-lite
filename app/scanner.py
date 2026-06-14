"""File scanner.

Responsibilities:
- Walk repository directory tree
- Detect language per file suffix
- Read bounded text content
- Invoke parser for Python files
- Build index entries
"""

import logging
from pathlib import Path

from .config import IGNORED_DIRS, IGNORED_FILE_SUFFIXES, MAX_TEXT_BYTES
from .parser import parse_python_source, parsed_definitions
from .utils import to_posix


logger = logging.getLogger(__name__)


LANGUAGES_BY_SUFFIX = {
    ".c": "C",
    ".cpp": "C++",
    ".cs": "C#",
    ".css": "CSS",
    ".go": "Go",
    ".html": "HTML",
    ".java": "Java",
    ".js": "JavaScript",
    ".jsx": "JavaScript React",
    ".json": "JSON",
    ".md": "Markdown",
    ".php": "PHP",
    ".py": "Python",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".scss": "SCSS",
    ".sh": "Shell",
    ".sql": "SQL",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".txt": "Text",
    ".vue": "Vue",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
}


def detect_language(path: Path) -> str:
    """Detect a file language from its suffix."""
    return LANGUAGES_BY_SUFFIX.get(path.suffix.lower(), path.suffix.lstrip(".").upper() or "Text")


def should_skip(path: Path, root: Path) -> bool:
    """Return whether a file should be excluded from the project index."""
    relative = path.relative_to(root)
    if any(part in IGNORED_DIRS for part in relative.parts):
        return True
    return path.suffix.lower() in IGNORED_FILE_SUFFIXES


def is_probably_binary(path: Path) -> bool:
    """Return whether a file appears to contain binary data."""
    try:
        chunk = path.read_bytes()[:4096]
    except OSError:
        logger.warning("Could not inspect file for binary content: %s", path)
        return True
    return b"\x00" in chunk


def read_text(path: Path) -> tuple[str, bool]:
    """Read bounded text content from a repository file.

    Returns ``(text, truncated)``.  Handles ``UnicodeDecodeError`` by
    replacing undecodable bytes so indexing always continues.
    """
    try:
        raw = path.read_bytes()
    except PermissionError:
        logger.warning("Permission denied reading file: %s", path)
        return "", False
    truncated = len(raw) > MAX_TEXT_BYTES
    raw = raw[:MAX_TEXT_BYTES]
    return raw.decode("utf-8", errors="replace"), truncated


def first_meaningful_line(text: str) -> str:
    """Return the first non-comment line for lightweight file summaries."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "//", "/*", "*")):
            return stripped[:180]
    return ""


def scan_project(root: Path) -> list[dict]:
    """Scan repository files and return index entries."""
    entries: list[dict] = []
    if not root.exists():
        return entries

    for path in sorted(root.rglob("*")):
        if not path.is_file() or should_skip(path, root):
            continue
        if is_probably_binary(path):
            continue

        relative = to_posix(path.relative_to(root))
        language = detect_language(path)

        try:
            text, truncated = read_text(path)
        except OSError:
            logger.warning("Could not read file during scan: %s", path)
            continue

        # Always produce parsed metadata for Python files, even if empty.
        if language == "Python":
            parsed = parse_python_source(text, relative)
        else:
            parsed = {}

        definitions = parsed_definitions(parsed) if parsed else []

        entries.append(
            {
                "path": relative,
                "name": path.name,
                "extension": path.suffix.lower(),
                "language": language,
                "size": path.stat().st_size,
                "lines": text.count("\n") + (1 if text else 0),
                "summary": first_meaningful_line(text),
                "definitions": definitions,
                "parsed": parsed,
                "content": text,
                "truncated": truncated,
            }
        )

    return entries
