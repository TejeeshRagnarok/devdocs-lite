from .search import search_entries


def answer_question(question: str, entries: list[dict]) -> dict:
    matches = search_entries(question, entries, limit=5)
    if not entries:
        return {
            "answer": "Upload a ZIP codebase first, then ask a question about it.",
            "sources": [],
        }

    if not matches:
        return {
            "answer": "I could not find a strong match in the indexed files. Try naming a file, feature, function, or error message.",
            "sources": [],
        }

    lines = [
        "Here is what I found from the indexed codebase:",
        "",
    ]
    for index, match in enumerate(matches[:3], start=1):
        lines.append(f"{index}. {match['path']} ({match['language']})")
        lines.append(f"   {match['snippet'] or 'Relevant file matched the question terms.'}")

    lines.extend(
        [
            "",
            "This answer is based on local retrieval. For deeper reasoning, ask a more specific follow-up or mention the file/function you want inspected.",
        ]
    )

    return {
        "answer": "\n".join(lines),
        "sources": matches,
    }
