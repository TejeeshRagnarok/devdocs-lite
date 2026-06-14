"""Repository Q&A.

Responsibilities:
- Detect explanation intent and route to the Explainer module
- Prefer parsed metadata answers (via ``answer_from_metadata``)
- Fall back to text retrieval only when metadata cannot answer
"""

import logging
import re

from .config import METADATA_PATH
from .explainer import explain_file, explain_function, explain_project
from .insights import answer_from_metadata
from .search import search_entries
from .utils import read_json


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Explanation-intent detection
# ---------------------------------------------------------------------------

_EXPLAIN_WORDS = {"explain", "describe", "what is", "what does", "purpose of", "tell me about"}

_FUNCTION_RE = re.compile(r"(\w+)\(\)")
_FILE_RE = re.compile(r"([A-Za-z][\w.-]*\.\w{2,})")

_PROJECT_PHRASES = {
    "explain this repository",
    "explain the repository",
    "explain this project",
    "explain the project",
    "explain project",
    "what is the project architecture",
    "what is this project",
    "project architecture",
    "how does this project work",
    "explain this project like",
    "repository overview",
    "project overview",
    "describe this project",
    "describe this repository",
}


def _has_explain_intent(question: str) -> bool:
    """Return whether the question expresses an 'explain' intent."""
    lower = question.lower().strip()
    return any(lower.startswith(word) or word in lower for word in _EXPLAIN_WORDS)


def _try_explain_routing(question: str, entries: list[dict]) -> dict | None:
    """Route explanation questions to the Explainer module.

    Returns a Q&A-shaped dict (``answer`` + ``sources``) or ``None`` if
    the question is not an explanation request.
    """
    lower = question.lower().strip()

    if not _has_explain_intent(lower):
        return None

    # 1. Project-level explanation
    for phrase in _PROJECT_PHRASES:
        if phrase in lower:
            metadata = read_json(METADATA_PATH, {"file_count": 0, "languages": {}, "important_files": []})
            result = explain_project(entries, metadata)
            return {
                "answer": result["explanation"],
                "sources": [],
            }

    # 2. Function-level explanation: "Explain upload_file()"
    func_match = _FUNCTION_RE.search(question)
    if func_match:
        result = explain_function(func_match.group(1), entries)
        return {
            "answer": result["explanation"],
            "sources": [
                {"path": loc["path"], "score": 100, "language": "Python", "snippet": f"Line {loc['line']}"}
                for loc in result["metadata"].get("locations", [])
            ],
        }

    # 3. File-level explanation: "Explain main.py"
    file_match = _FILE_RE.search(question)
    if file_match:
        result = explain_file(file_match.group(1), entries)
        meta = result.get("metadata", {})
        sources = []
        if meta.get("found"):
            sources.append({
                "path": meta.get("path", ""),
                "score": 100,
                "language": meta.get("language", ""),
                "snippet": "File explanation",
            })
        return {
            "answer": result["explanation"],
            "sources": sources,
        }

    return None


def answer_question(question: str, entries: list[dict]) -> dict:
    """Answer a question about the indexed repository.

    Strategy:
    1. Detect explanation intent → route to the Explainer module.
    2. Try to answer from parsed AST metadata (functions, classes, imports,
       file descriptions).
    3. Fall back to scored text retrieval when metadata is not enough.
    """
    if not entries:
        return {
            "answer": "Upload a ZIP codebase first, then ask a question about it.",
            "sources": [],
        }

    # 1. Explainer-first routing
    explain_answer = _try_explain_routing(question, entries)
    if explain_answer:
        return explain_answer

    # 2. Attempt metadata-first answer
    metadata_answer = answer_from_metadata(question, entries)
    if metadata_answer:
        return metadata_answer

    # 3. Fallback: text retrieval
    matches = search_entries(question, entries, limit=5)
    if not matches:
        return {
            "answer": (
                "I could not find a strong match in the indexed files.\n"
                "Try naming a file, feature, function, or error message."
            ),
            "sources": [],
        }

    lines = ["Here is what I found from the indexed codebase:", ""]
    for index, match in enumerate(matches[:3], start=1):
        snippet = match["snippet"] or "Relevant file matched the question terms."
        lines.append(f"{index}. {match['path']} ({match['language']})")
        lines.append(f"   {snippet}")

    lines.extend(
        [
            "",
            "This answer is based on local retrieval. For deeper reasoning, ask a "
            "more specific follow-up or mention the file/function you want inspected.",
        ]
    )

    return {
        "answer": "\n".join(lines),
        "sources": matches,
    }
