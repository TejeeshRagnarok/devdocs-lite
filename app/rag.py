"""Repository Q&A.

Responsibilities:
- Prefer parsed metadata answers (via ``answer_from_metadata``)
- Fall back to text retrieval only when metadata cannot answer
"""

import logging

from .insights import answer_from_metadata
from .search import search_entries


logger = logging.getLogger(__name__)


def answer_question(question: str, entries: list[dict]) -> dict:
    """Answer a question about the indexed repository.

    Strategy:
    1. Try to answer from parsed AST metadata (functions, classes, imports,
       file descriptions).
    2. Fall back to scored text retrieval when metadata is not enough.
    """
    if not entries:
        return {
            "answer": "Upload a ZIP codebase first, then ask a question about it.",
            "sources": [],
        }

    # Attempt metadata-first answer
    metadata_answer = answer_from_metadata(question, entries)
    if metadata_answer:
        return metadata_answer

    # Fallback: text retrieval
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
