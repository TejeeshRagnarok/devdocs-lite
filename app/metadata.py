"""Metadata builder.

Responsibilities:
- Compute project-level statistics from scanned file entries
- Provide ``ensure_insight_metadata`` to upgrade v0.1 cached summaries
"""

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .insights import python_entries


IMPORTANT_NAMES = {
    "dockerfile",
    "makefile",
    "package.json",
    "pyproject.toml",
    "readme.md",
    "requirements.txt",
    "tsconfig.json",
}

# Keys that v0.2.0 adds; if any are absent the metadata must be rebuilt.
INSIGHT_KEYS = {
    "python_files",
    "function_count",
    "class_count",
    "import_count",
    "average_loc",
    "largest_file",
    "smallest_file",
}


def _parsed_count(entry: dict[str, Any], key: str) -> int:
    """Return the length of a list field inside ``entry["parsed"]``."""
    parsed = entry.get("parsed") or {}
    return len(parsed.get(key, []))


def _method_count(entry: dict[str, Any]) -> int:
    """Return the total number of methods across all classes in a parsed entry."""
    parsed = entry.get("parsed") or {}
    return sum(len(class_info.get("methods", [])) for class_info in parsed.get("classes", []))


def _file_stat(entries: list[dict], reverse: bool) -> dict[str, Any] | None:
    """Return path/language/lines/size for the largest or smallest file."""
    if not entries:
        return None
    entry = sorted(
        entries,
        key=lambda item: (item.get("lines", 0), item.get("path", "")),
        reverse=reverse,
    )[0]
    return {
        "path": entry["path"],
        "language": entry["language"],
        "lines": entry.get("lines", 0),
        "size": entry.get("size", 0),
    }


def build_metadata(entries: list[dict], project_name: str) -> dict:
    """Build project-level statistics for the indexed repository."""
    language_counts = Counter(entry["language"] for entry in entries)
    total_lines = sum(entry.get("lines", 0) for entry in entries)
    total_size = sum(entry.get("size", 0) for entry in entries)

    parsed_python = python_entries(entries)
    function_count = sum(_parsed_count(entry, "functions") for entry in parsed_python)
    class_count = sum(_parsed_count(entry, "classes") for entry in parsed_python)
    method_count = sum(_method_count(entry) for entry in parsed_python)
    import_count = sum(_parsed_count(entry, "imports") for entry in parsed_python)

    important_files = [
        entry["path"]
        for entry in entries
        if entry["name"].lower() in IMPORTANT_NAMES or entry["path"].startswith(("app/", "src/"))
    ][:25]

    return {
        "project_name": project_name,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(entries),
        "total_lines": total_lines,
        "total_size": total_size,
        "python_files": len(parsed_python),
        "function_count": function_count,
        "class_count": class_count,
        "method_count": method_count,
        "import_count": import_count,
        # Round to nearest integer so the UI never shows a decimal
        "average_loc": round(total_lines / len(entries)) if entries else 0,
        "largest_file": _file_stat(entries, reverse=True),
        "smallest_file": _file_stat(entries, reverse=False),
        "languages": dict(language_counts.most_common()),
        "important_files": important_files,
    }


def ensure_insight_metadata(metadata: dict, entries: list[dict]) -> dict:
    """Return metadata with v0.2.0 insight fields, rebuilding old summaries if needed."""
    if not entries:
        return metadata
    if INSIGHT_KEYS.issubset(metadata.keys()):
        return metadata
    return build_metadata(entries, metadata.get("project_name", "Current project"))
