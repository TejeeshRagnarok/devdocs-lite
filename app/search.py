import re

from .config import MAX_SEARCH_RESULTS


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")


def tokenize(value: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(value)]


def make_snippet(text: str, terms: list[str], limit: int = 420) -> str:
    lower = text.lower()
    positions = [lower.find(term) for term in terms if term and lower.find(term) >= 0]
    start = max(min(positions) - 120, 0) if positions else 0
    snippet = text[start : start + limit].strip()
    snippet = re.sub(r"\s+", " ", snippet)
    prefix = "... " if start > 0 else ""
    suffix = " ..." if start + limit < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def search_entries(query: str, entries: list[dict], limit: int = MAX_SEARCH_RESULTS) -> list[dict]:
    terms = tokenize(query)
    if not terms:
        return []

    results: list[dict] = []
    for entry in entries:
        searchable = " ".join(
            [
                entry.get("path", ""),
                entry.get("language", ""),
                entry.get("summary", ""),
                " ".join(entry.get("definitions", [])),
                entry.get("content", ""),
            ]
        ).lower()

        score = 0.0
        for term in terms:
            if term in entry.get("path", "").lower():
                score += 8
            if term in " ".join(entry.get("definitions", [])).lower():
                score += 6
            score += min(searchable.count(term), 12)

        if score:
            results.append(
                {
                    "path": entry["path"],
                    "score": score,
                    "language": entry["language"],
                    "snippet": make_snippet(entry.get("content", ""), terms),
                }
            )

    return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]
