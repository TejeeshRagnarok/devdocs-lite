"""Repository search.

Responsibilities:
- Tokenise a query
- Score index entries using path, definitions, parsed metadata and content
- Return ranked results with snippets
"""

import logging
import re

from .config import MAX_SEARCH_RESULTS


logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def tokenize(value: str) -> list[str]:
    """Return lower-cased word tokens from a string."""
    return [token.lower() for token in TOKEN_RE.findall(value)]


def make_snippet(text: str, terms: list[str], limit: int = 420) -> str:
    """Extract a context snippet from *text* around the first matched term."""
    lower = text.lower()
    positions = [lower.find(term) for term in terms if term and lower.find(term) >= 0]
    start = max(min(positions) - 120, 0) if positions else 0
    snippet = text[start : start + limit].strip()
    snippet = re.sub(r"\s+", " ", snippet)
    prefix = "... " if start > 0 else ""
    suffix = " ..." if start + limit < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def parsed_terms(entry: dict) -> list[str]:
    """Collect all symbol names and import names from a parsed entry."""
    parsed = entry.get("parsed") or {}
    values: list[str] = []
    values.extend(parsed.get("imports", []))
    values.extend(function["name"] for function in parsed.get("functions", []))
    for class_info in parsed.get("classes", []):
        values.append(class_info["name"])
        values.extend(method["name"] for method in class_info.get("methods", []))
    return values


def search_entries(query: str, entries: list[dict], limit: int = MAX_SEARCH_RESULTS) -> list[dict]:
    """Score and rank index entries against *query*; return the top results."""
    terms = tokenize(query)
    if not terms:
        return []

    results: list[dict] = []
    for entry in entries:
        path_lower = entry.get("path", "").lower()
        definitions_text = " ".join(entry.get("definitions", [])).lower()
        parsed_text = " ".join(parsed_terms(entry)).lower()
        content_lower = entry.get("content", "").lower()

        searchable = " ".join(
            [
                path_lower,
                entry.get("language", ""),
                entry.get("summary", ""),
                definitions_text,
                parsed_text,
                content_lower,
            ]
        )

        score = 0.0
        for term in terms:
            if term in path_lower:
                score += 8
            if term in definitions_text:
                score += 6
            if term in parsed_text:
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
