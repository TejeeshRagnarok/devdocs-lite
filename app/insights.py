"""Repository insights and Q&A from parsed metadata.

Responsibilities:
- Provide helpers that group parsed metadata by file (functions, classes, imports)
- Build the persisted parsed index
- Answer structural questions directly from parsed metadata
"""

import logging
from collections.abc import Iterable
from typing import Any

from .parser import parse_python_source
from .search import tokenize


logger = logging.getLogger(__name__)


STRUCTURE_WORDS = {
    "class",
    "classes",
    "define",
    "defines",
    "defined",
    "explain",
    "function",
    "functions",
    "implemented",
    "implementation",
    "import",
    "imports",
    "method",
    "methods",
    "module",
    "modules",
    "purpose",
    "where",
    "which",
}

STOP_WORDS = STRUCTURE_WORDS | {
    "all",
    "are",
    "contain",
    "contains",
    "does",
    "every",
    "exist",
    "file",
    "files",
    "for",
    "how",
    "is",
    "list",
    "many",
    "me",
    "show",
    "the",
    "what",
}


def _with_parsed_metadata(entry: dict) -> dict | None:
    """Return the entry (with ``parsed`` populated) if it is a Python file.

    Empty Python files still produce a valid parsed dict so they appear in
    statistics.  Returns ``None`` for non-Python files.
    """
    if entry.get("language") != "Python":
        return None

    parsed = entry.get("parsed")

    # Already has a valid parsed dict (even an empty-metadata one is valid)
    if isinstance(parsed, dict) and "language" in parsed:
        return entry

    # Needs parsing from content
    content = entry.get("content", "")
    parsed_result = parse_python_source(content, entry.get("path", ""))
    return {**entry, "parsed": parsed_result}


def python_entries(entries: list[dict]) -> list[dict]:
    """Return indexed Python files with parsed metadata (including empty files)."""
    parsed_entries: list[dict] = []
    for entry in entries:
        parsed_entry = _with_parsed_metadata(entry)
        if parsed_entry is not None:
            parsed_entries.append(parsed_entry)
    return parsed_entries


def build_parsed_index(entries: list[dict]) -> list[dict]:
    """Build the persisted structured metadata document for parsed source files."""
    return [entry["parsed"] for entry in python_entries(entries)]


def functions_by_file(entries: list[dict]) -> list[dict]:
    """Return top-level Python functions grouped by file."""
    return [
        {
            "file": entry["path"],
            "module": entry["parsed"].get("module", ""),
            "functions": [function["name"] for function in entry["parsed"].get("functions", [])],
        }
        for entry in python_entries(entries)
    ]


def classes_by_file(entries: list[dict]) -> list[dict]:
    """Return parsed Python classes grouped by file."""
    return [
        {
            "file": entry["path"],
            "module": entry["parsed"].get("module", ""),
            "classes": entry["parsed"].get("classes", []),
        }
        for entry in python_entries(entries)
    ]


def imports_by_file(entries: list[dict]) -> list[dict]:
    """Return Python imports grouped by file."""
    return [
        {
            "file": entry["path"],
            "module": entry["parsed"].get("module", ""),
            "imports": entry["parsed"].get("imports", []),
        }
        for entry in python_entries(entries)
    ]


def _source(path: str, language: str, score: float, snippet: str) -> dict:
    return {
        "path": path,
        "score": score,
        "language": language,
        "snippet": snippet,
    }


def _names(values: Iterable[dict]) -> list[str]:
    return [value["name"] for value in values]


def _query_terms(question: str) -> set[str]:
    return {term for term in tokenize(question) if term not in STOP_WORDS}


def _has_structure_intent(question: str) -> bool:
    terms = set(tokenize(question))
    return bool(terms & STRUCTURE_WORDS)


def _format_grouped(title: str, groups: list[dict], key: str, limit: int = 20) -> str:
    lines = [title, ""]
    shown = 0
    for group in groups:
        values = group.get(key, [])
        if not values:
            continue
        lines.append(f"- {group['file']}: {', '.join(values)}")
        shown += 1
        if shown >= limit:
            break
    if shown == 0:
        lines.append("No parsed metadata found.")
    return "\n".join(lines)


def _function_matches(question_terms: set[str], entries: list[dict]) -> list[dict]:
    matches: list[dict] = []
    for entry in python_entries(entries):
        parsed = entry["parsed"]
        for function in parsed.get("functions", []):
            if function["name"].lower() in question_terms:
                matches.append(
                    _source(entry["path"], entry["language"], 100, f"Function {function['name']}()")
                )
        for class_info in parsed.get("classes", []):
            for method in class_info.get("methods", []):
                if method["name"].lower() in question_terms:
                    matches.append(
                        _source(
                            entry["path"],
                            entry["language"],
                            95,
                            f"Method {class_info['name']}.{method['name']}()",
                        )
                    )
    return matches


def _class_matches(question_terms: set[str], entries: list[dict]) -> list[dict]:
    matches: list[dict] = []
    for entry in python_entries(entries):
        for class_info in entry["parsed"].get("classes", []):
            if class_info["name"].lower() in question_terms:
                method_names = _names(class_info.get("methods", []))
                suffix = f" Methods: {', '.join(method_names)}" if method_names else ""
                matches.append(
                    _source(entry["path"], entry["language"], 100, f"Class {class_info['name']}.{suffix}")
                )
    return matches


def _import_matches(question_terms: set[str], entries: list[dict]) -> list[dict]:
    matches: list[dict] = []
    for entry in python_entries(entries):
        imports = entry["parsed"].get("imports", [])
        for imported in imports:
            parts = {part.lower() for part in imported.replace(".", " ").split()}
            if imported.lower() in question_terms or parts & question_terms:
                matches.append(
                    _source(entry["path"], entry["language"], 90, f"Imports {imported}")
                )
                break
    return matches


def _count_answer(entries: list[dict]) -> dict[str, Any]:
    groups = functions_by_file(entries)
    count = sum(len(group["functions"]) for group in groups)
    return {
        "answer": f"The parsed Python metadata contains {count} top-level function(s).",
        "sources": [
            _source(group["file"], "Python", len(group["functions"]), ", ".join(group["functions"]))
            for group in groups
            if group["functions"]
        ],
    }


def _describe_file(entry: dict) -> dict[str, Any]:
    """Produce a human-readable description of a single file from its parsed metadata."""
    parsed = entry.get("parsed") or {}
    path = entry.get("path", "")
    language = entry.get("language", "")
    lines = entry.get("lines", 0)

    functions = [f["name"] for f in parsed.get("functions", [])]
    classes = [c["name"] for c in parsed.get("classes", [])]
    imports = parsed.get("imports", [])
    docstring = parsed.get("docstring") or None
    error = parsed.get("error", "")

    description_lines = [f"File: {path}", f"Language: {language}", f"Lines: {lines}", ""]

    if docstring:
        description_lines += [f"Module docstring: {docstring}", ""]

    if functions:
        description_lines += [f"Functions ({len(functions)}):", *[f"  - {fn}()" for fn in functions], ""]
    else:
        description_lines.append("Functions: none")

    if classes:
        description_lines += [f"Classes ({len(classes)}):", *[f"  - {cls}" for cls in classes], ""]
    else:
        description_lines.append("Classes: none")

    if imports:
        description_lines += [f"Imports ({len(imports)}):", *[f"  - {imp}" for imp in imports], ""]
    else:
        description_lines.append("Imports: none")

    if error:
        description_lines += ["", f"Parse error: {error}"]

    sources = [_source(path, language, 100, f"{len(functions)} function(s), {len(classes)} class(es)")]
    return {
        "answer": "\n".join(description_lines),
        "sources": sources,
    }


def _find_file_entry(name_or_path: str, entries: list[dict]) -> dict | None:
    """Locate an entry by file name or partial path, case-insensitively."""
    needle = name_or_path.lower().replace("\\", "/")
    # Exact path match first
    for entry in entries:
        if entry["path"].lower() == needle:
            return entry
    # Suffix / filename match
    for entry in entries:
        if entry["path"].lower().endswith(needle) or entry["name"].lower() == needle:
            return entry
    return None


def _extract_filename(question: str) -> str | None:
    """Try to pull a filename token from the question (e.g. 'ingest.py')."""
    for token in question.split():
        cleaned = token.strip("?\"'.,;:")
        if "." in cleaned and not cleaned.startswith("."):
            return cleaned
    return None


def answer_from_metadata(question: str, entries: list[dict]) -> dict[str, Any] | None:
    """Answer source-structure questions from parsed metadata when possible.

    Returns a dict with ``answer`` and ``sources`` if metadata can answer the
    question, or ``None`` to signal the caller to fall back to text retrieval.
    """
    if not entries:
        return None

    lower_question = question.lower()
    terms = _query_terms(question)
    has_intent = _has_structure_intent(question)

    # ------------------------------------------------------------------ #
    # 1. File-specific questions: "What does ingest.py contain?"          #
    # ------------------------------------------------------------------ #
    filename = _extract_filename(question)
    if filename:
        entry = _find_file_entry(filename, entries)
        if entry is not None:
            return _describe_file(entry)

    # ------------------------------------------------------------------ #
    # 2. Function count                                                    #
    # ------------------------------------------------------------------ #
    if "how many" in lower_question and "function" in lower_question:
        return _count_answer(entries)

    # ------------------------------------------------------------------ #
    # 3. List all classes                                                  #
    # ------------------------------------------------------------------ #
    if ("show" in lower_question or "list" in lower_question or "every" in lower_question) and "class" in lower_question:
        groups: list[dict] = []
        sources: list[dict] = []
        for group in classes_by_file(entries):
            names = _names(group["classes"])
            if names:
                groups.append({"file": group["file"], "classes": names})
                sources.append(_source(group["file"], "Python", len(names), ", ".join(names)))
        return {
            "answer": _format_grouped("Parsed classes:", groups, "classes"),
            "sources": sources,
        }

    # ------------------------------------------------------------------ #
    # 4. List all imports                                                  #
    # ------------------------------------------------------------------ #
    if ("show" in lower_question or "list" in lower_question) and "import" in lower_question:
        groups_imp = imports_by_file(entries)
        return {
            "answer": _format_grouped("Parsed imports:", groups_imp, "imports"),
            "sources": [
                _source(group["file"], "Python", len(group["imports"]), ", ".join(group["imports"]))
                for group in groups_imp
                if group["imports"]
            ],
        }

    # ------------------------------------------------------------------ #
    # 5. List all functions                                                #
    # ------------------------------------------------------------------ #
    if ("show" in lower_question or "list" in lower_question) and "function" in lower_question:
        return _count_answer(entries)

    # ------------------------------------------------------------------ #
    # 6. Symbol-level lookups                                              #
    # ------------------------------------------------------------------ #
    if not has_intent or not terms:
        return None

    matches: list[dict] = []
    if "class" in lower_question:
        matches.extend(_class_matches(terms, entries))
    elif "import" in lower_question or "module" in lower_question:
        matches.extend(_import_matches(terms, entries))
    else:
        matches.extend(_function_matches(terms, entries))
        matches.extend(_class_matches(terms, entries))
        matches.extend(_import_matches(terms, entries))

    if not matches:
        return None

    lines = ["Parsed metadata found these matches:", ""]
    for index, match in enumerate(matches[:8], start=1):
        lines.append(f"{index}. {match['path']} - {match['snippet']}")

    return {
        "answer": "\n".join(lines),
        "sources": matches[:8],
    }
