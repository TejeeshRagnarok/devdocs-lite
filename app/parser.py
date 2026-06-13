import re
from pathlib import Path

from .config import MAX_TEXT_BYTES


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

DEFINITION_PATTERNS = {
    "Python": re.compile(r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][\w]*)", re.MULTILINE),
    "JavaScript": re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|const|let)\s+([A-Za-z_$][\w$]*)",
        re.MULTILINE,
    ),
    "TypeScript": re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|interface|type|const|let)\s+([A-Za-z_$][\w$]*)",
        re.MULTILINE,
    ),
}


def detect_language(path: Path) -> str:
    return LANGUAGES_BY_SUFFIX.get(path.suffix.lower(), path.suffix.lstrip(".").upper() or "Text")


def is_probably_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\x00" in chunk


def read_text(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    truncated = len(raw) > MAX_TEXT_BYTES
    raw = raw[:MAX_TEXT_BYTES]
    return raw.decode("utf-8", errors="replace"), truncated


def extract_definitions(language: str, text: str) -> list[str]:
    base_language = language.split()[0]
    pattern = DEFINITION_PATTERNS.get(base_language)
    if not pattern:
        return []
    seen: list[str] = []
    for match in pattern.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
        if len(seen) >= 30:
            break
    return seen


def first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "//", "/*", "*")):
            return stripped[:180]
    return ""
