"""File preview.

Responsibilities:
- Locate a file by path in the current index
- Return bounded source content
- Return parsed Python insights (functions, classes, imports, docstring)
"""

import logging

from .config import MAX_PREVIEW_CHARS
from .parser import parse_python_source


logger = logging.getLogger(__name__)


def _python_insights(entry: dict) -> dict | None:
    """Return structured parser metadata for a Python file.

    Includes functions, classes, imports and the module docstring.
    Returns ``None`` for non-Python files.
    """
    if entry.get("language") != "Python":
        return None

    parsed = entry.get("parsed") or {}

    # If parsed dict is missing or empty, attempt a fresh parse from content.
    if not parsed or "language" not in parsed:
        content = entry.get("content", "")
        parsed = parse_python_source(content, entry.get("path", ""))

    return {
        "module": parsed.get("module", ""),
        "functions": [f["name"] for f in parsed.get("functions", [])],
        "classes": [c["name"] for c in parsed.get("classes", [])],
        "imports": parsed.get("imports", []),
        "docstring": parsed.get("docstring"),
    }


def preview_file(path: str, entries: list[dict]) -> dict | None:
    """Return preview content and parsed Python insights for an indexed file."""
    normalized = path.replace("\\", "/").lstrip("/")
    for entry in entries:
        if entry["path"] == normalized:
            content = entry.get("content", "")
            truncated = entry.get("truncated", False) or len(content) > MAX_PREVIEW_CHARS
            return {
                "path": entry["path"],
                "language": entry["language"],
                "content": content[:MAX_PREVIEW_CHARS],
                "truncated": truncated,
                "insights": _python_insights(entry),
            }
    return None
