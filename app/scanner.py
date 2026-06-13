from pathlib import Path

from .config import IGNORED_DIRS, IGNORED_FILE_SUFFIXES
from .parser import detect_language, extract_definitions, first_meaningful_line, is_probably_binary, read_text
from .utils import to_posix


def should_skip(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in IGNORED_DIRS for part in relative.parts):
        return True
    return path.suffix.lower() in IGNORED_FILE_SUFFIXES


def scan_project(root: Path) -> list[dict]:
    entries: list[dict] = []
    if not root.exists():
        return entries

    for path in sorted(root.rglob("*")):
        if not path.is_file() or should_skip(path, root):
            continue
        if is_probably_binary(path):
            continue

        relative = to_posix(path.relative_to(root))
        try:
            text, truncated = read_text(path)
        except OSError:
            continue

        language = detect_language(path)
        entries.append(
            {
                "path": relative,
                "name": path.name,
                "extension": path.suffix.lower(),
                "language": language,
                "size": path.stat().st_size,
                "lines": text.count("\n") + (1 if text else 0),
                "summary": first_meaningful_line(text),
                "definitions": extract_definitions(language, text),
                "content": text,
                "truncated": truncated,
            }
        )

    return entries
