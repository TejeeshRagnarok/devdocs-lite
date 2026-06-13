from collections import Counter
from datetime import datetime, timezone


IMPORTANT_NAMES = {
    "dockerfile",
    "makefile",
    "package.json",
    "pyproject.toml",
    "readme.md",
    "requirements.txt",
    "tsconfig.json",
}


def build_metadata(entries: list[dict], project_name: str) -> dict:
    language_counts = Counter(entry["language"] for entry in entries)
    total_lines = sum(entry.get("lines", 0) for entry in entries)
    total_size = sum(entry.get("size", 0) for entry in entries)

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
        "languages": dict(language_counts.most_common()),
        "important_files": important_files,
    }
