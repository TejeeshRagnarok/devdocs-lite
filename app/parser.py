"""AST-based Python parser.

Responsibilities:
- Parse Python source with the ``ast`` module
- Extract top-level functions, classes, imports, and module docstrings
- Produce a normalised metadata dict for every Python file (even empty ones)
- Never raise; log and return an empty-metadata shape on any error
"""

import ast
import logging
from pathlib import PurePosixPath
from typing import Any


logger = logging.getLogger(__name__)


def module_name_from_path(path: str) -> str:
    """Return a dotted Python module name for a repository-relative path."""
    pure_path = PurePosixPath(path)
    without_suffix = pure_path.with_suffix("")
    parts = list(without_suffix.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _decorator_name(node: ast.AST) -> str:
    """Return a readable decorator name from an AST decorator node."""
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = _decorator_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        if isinstance(node, ast.Call):
            return _decorator_name(node.func)
    return ""


def _decorators(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    values: list[str] = []
    for decorator in node.decorator_list:
        name = _decorator_name(decorator).strip()
        if name:
            values.append(name)
    return values


def _function_metadata(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    return {
        "name": node.name,
        "async": isinstance(node, ast.AsyncFunctionDef),
        "decorators": _decorators(node),
        "docstring": ast.get_docstring(node) or "",
        "line": node.lineno,
    }


def _class_metadata(node: ast.ClassDef) -> dict[str, Any]:
    methods = [
        _function_metadata(child)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return {
        "name": node.name,
        "methods": methods,
        "decorators": _decorators(node),
        "docstring": ast.get_docstring(node) or "",
        "line": node.lineno,
    }


def _imports(tree: ast.AST) -> list[str]:
    """Return a deduplicated list of imported names from an AST tree."""
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                values.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            for alias in node.names:
                if alias.name == "*":
                    # e.g. "from os import *" → "os.*"
                    values.append(f"{module}.*" if module else "*")
                else:
                    values.append(alias.name)

    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value and value not in seen:
            unique_values.append(value)
            seen.add(value)
    return unique_values


def empty_python_metadata(path: str, error: str = "") -> dict[str, Any]:
    """Return the metadata shape used when a Python file cannot be parsed or is empty."""
    return {
        "file": path,
        "module": module_name_from_path(path),
        "language": "Python",
        "imports": [],
        "functions": [],
        "classes": [],
        "docstring": None,
        "error": error,
    }


def parse_python_source(source: str, path: str) -> dict[str, Any]:
    """Parse Python source with ast and return structured repository metadata.

    Always returns a valid dict — never raises.  Empty source produces
    ``empty_python_metadata`` with no error field set.
    """
    if not source or not source.strip():
        return empty_python_metadata(path)

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        logger.warning("SyntaxError parsing %s: %s", path, exc)
        return empty_python_metadata(path, str(exc))
    except Exception as exc:  # pragma: no cover
        logger.warning("Unexpected error parsing %s: %s", path, exc)
        return empty_python_metadata(path, str(exc))

    functions = [
        _function_metadata(node)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    classes = [
        _class_metadata(node)
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    ]

    return {
        "file": path,
        "module": module_name_from_path(path),
        "language": "Python",
        "imports": _imports(tree),
        "functions": functions,
        "classes": classes,
        "docstring": ast.get_docstring(tree),
        "error": "",
    }


def parsed_definitions(parsed: dict[str, Any]) -> list[str]:
    """Flatten parsed Python symbols into the legacy definitions shape."""
    names: list[str] = []
    for function in parsed.get("functions", []):
        names.append(function["name"])
    for class_info in parsed.get("classes", []):
        names.append(class_info["name"])
        names.extend(method["name"] for method in class_info.get("methods", []))
    return names
