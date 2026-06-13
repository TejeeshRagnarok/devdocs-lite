from .config import MAX_PREVIEW_CHARS


def preview_file(path: str, entries: list[dict]) -> dict | None:
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
            }
    return None
