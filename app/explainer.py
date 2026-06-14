"""Repository Explainer.

Responsibilities:
- Translate parsed AST metadata into developer-friendly explanations
- Explain individual files, functions, classes, and full projects
- Generate project flow diagrams and repository summaries
- Handle edge cases: empty files, missing docstrings, syntax errors, non-Python files

Design:
- Uses parsed metadata first (AST functions, classes, imports, decorators, docstrings)
- Falls back to content heuristics for non-Python files
- Never crashes — returns graceful explanations for every input
"""

import logging
import re
from typing import Any

from .insights import python_entries
from .parser import parse_python_source


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_entry_by_path(path: str, entries: list[dict]) -> dict | None:
    """Locate an entry by file path, filename, or partial suffix match."""
    needle = path.lower().replace("\\", "/")
    # Exact path match
    for entry in entries:
        if entry["path"].lower() == needle:
            return entry
    # Suffix / basename match
    for entry in entries:
        if entry["path"].lower().endswith(needle) or entry["name"].lower() == needle:
            return entry
    return None


def _find_function_in_entries(
    name: str, entries: list[dict],
) -> list[dict]:
    """Find all occurrences of a function/method name across parsed entries.

    Returns a list of dicts with keys: entry, function, class_name (if method).
    """
    clean_name = name.strip().rstrip("()")
    results: list[dict] = []

    for entry in python_entries(entries):
        parsed = entry.get("parsed") or {}

        for func in parsed.get("functions", []):
            if func["name"].lower() == clean_name.lower():
                results.append({"entry": entry, "function": func, "class_name": None})

        for cls in parsed.get("classes", []):
            for method in cls.get("methods", []):
                if method["name"].lower() == clean_name.lower():
                    results.append({"entry": entry, "function": method, "class_name": cls["name"]})

    return results


def _find_class_in_entries(
    name: str, entries: list[dict],
) -> list[dict]:
    """Find all occurrences of a class name across parsed entries.

    Returns a list of dicts with keys: entry, class_info.
    """
    clean_name = name.strip()
    results: list[dict] = []

    for entry in python_entries(entries):
        parsed = entry.get("parsed") or {}
        for cls in parsed.get("classes", []):
            if cls["name"].lower() == clean_name.lower():
                results.append({"entry": entry, "class_info": cls})

    return results


def _infer_file_purpose(entry: dict) -> str:
    """Infer the purpose of a file from its name, path, and content patterns."""
    name = entry.get("name", "").lower()
    path = entry.get("path", "").lower()
    language = entry.get("language", "")
    content = entry.get("content", "")

    # Well-known filenames
    purposes = {
        "main.py": "the application entry point",
        "app.py": "the application entry point",
        "__init__.py": "a Python package initialiser that marks this directory as importable",
        "setup.py": "the package build and installation configuration",
        "pyproject.toml": "the modern Python project configuration (PEP 621)",
        "conftest.py": "shared pytest fixtures and test configuration",
        "config.py": "application configuration and settings",
        "settings.py": "application settings and environment configuration",
        "models.py": "data models and schemas",
        "views.py": "request handlers / view functions",
        "urls.py": "URL routing configuration",
        "forms.py": "form definitions and validation",
        "admin.py": "admin interface registration",
        "serializers.py": "data serialisation and deserialisation logic",
        "utils.py": "shared utility functions used across the project",
        "helpers.py": "shared helper functions",
        "constants.py": "project-wide constant values",
        "exceptions.py": "custom exception classes",
        "middleware.py": "request/response middleware",
        "tasks.py": "background task definitions",
        "tests.py": "test suite for the module",
        "requirements.txt": "Python dependency declarations",
        "readme.md": "project documentation and overview",
        "changelog.md": "release history and change log",
        "dockerfile": "container build instructions",
        "makefile": "build automation recipes",
        "package.json": "Node.js project configuration and dependency declarations",
        "tsconfig.json": "TypeScript compiler configuration",
        ".gitignore": "Git ignore rules that exclude files from version control",
        ".env": "environment variable definitions (secrets and config)",
        "license": "software license terms",
    }

    for known_name, purpose in purposes.items():
        if name == known_name:
            return purpose

    path_parts = set(path.replace("/", " ").replace("\\", " ").split())
    if name.startswith("test_") or "tests" in path_parts or "test" in path_parts:
        return "a test module"
    if "/api/" in path or "routes" in name:
        return "an API route handler module"
    if "/migrations/" in path:
        return "a database migration"

    # Language-based inference
    lang_purposes = {
        "CSS": "a stylesheet that defines visual presentation rules",
        "SCSS": "a Sass stylesheet with variables and nesting for visual presentation",
        "HTML": "a markup template that defines page structure",
        "JavaScript": "a script that implements client-side interactivity and logic",
        "TypeScript": "a typed script that implements client-side logic with type safety",
        "JSON": "a data/configuration file",
        "YAML": "a configuration file",
        "XML": "a data or configuration file",
        "Markdown": "a documentation file",
        "Shell": "a shell script for automation or environment setup",
        "SQL": "database queries or schema definitions",
    }

    if language in lang_purposes:
        return lang_purposes[language]

    # Content-based inference for Python
    if language == "Python" and content:
        if "FastAPI" in content or "Flask" in content or "Django" in content:
            return "a web application module"
        if "def test_" in content or "class Test" in content:
            return "a test module"
        if "click" in content or "argparse" in content:
            return "a CLI command module"

    return "a project source file"


def _describe_decorator(decorator: str) -> str:
    """Produce a human-readable note about a decorator."""
    if "app.get" in decorator or "router.get" in decorator:
        route = re.search(r"""['"](.*?)['"]""", decorator)
        return f"registered as a GET endpoint at `{route.group(1)}`" if route else "registered as a GET endpoint"
    if "app.post" in decorator or "router.post" in decorator:
        route = re.search(r"""['"](.*?)['"]""", decorator)
        return f"registered as a POST endpoint at `{route.group(1)}`" if route else "registered as a POST endpoint"
    if "app.put" in decorator or "router.put" in decorator:
        route = re.search(r"""['"](.*?)['"]""", decorator)
        return f"registered as a PUT endpoint at `{route.group(1)}`" if route else "registered as a PUT endpoint"
    if "app.delete" in decorator or "router.delete" in decorator:
        route = re.search(r"""['"](.*?)['"]""", decorator)
        return f"registered as a DELETE endpoint at `{route.group(1)}`" if route else "registered as a DELETE endpoint"
    if "staticmethod" in decorator:
        return "a static method"
    if "classmethod" in decorator:
        return "a class method"
    if "property" in decorator:
        return "a property accessor"
    if "abstractmethod" in decorator:
        return "an abstract method that subclasses must implement"
    if "app.on_event" in decorator:
        event = re.search(r"""['"](.*?)['"]""", decorator)
        return f"an application lifecycle hook ({event.group(1)})" if event else "an application lifecycle hook"
    return f"decorated with @{decorator}"


def _explain_function_detail(func: dict, class_name: str | None = None) -> str:
    """Generate a detailed explanation paragraph for a single function or method."""
    name = func["name"]
    is_async = func.get("async", False)
    docstring = func.get("docstring", "")
    decorators = func.get("decorators", [])
    line = func.get("line", 0)

    prefix = f"{class_name}.{name}" if class_name else name
    kind = "coroutine" if is_async else "function"
    if class_name:
        kind = "async method" if is_async else "method"

    lines: list[str] = []
    lines.append(f"{prefix}()")
    lines.append("")

    # Decorator context
    for dec in decorators:
        desc = _describe_decorator(dec)
        lines.append(f"  • {desc}")

    if docstring:
        lines.append(f"  • Purpose: {docstring.split(chr(10))[0].strip()}")
    else:
        # Infer purpose from name
        inferred = _infer_function_purpose(name)
        if inferred:
            lines.append(f"  • Purpose: {inferred}")

    lines.append(f"  • Type: {kind}")
    if line:
        lines.append(f"  • Defined at line {line}")

    return "\n".join(lines)


def _infer_function_purpose(name: str) -> str:
    """Infer purpose from common function naming patterns."""
    patterns = {
        r"^(get|fetch|load|read|retrieve)_": "retrieves or loads data",
        r"^(set|update|save|write|store)_": "persists or updates data",
        r"^(create|build|make|generate|init)_": "creates or constructs a resource",
        r"^(delete|remove|destroy|drop)_": "removes or cleans up a resource",
        r"^(check|is_|has_|can_|should_|validate)": "performs a validation or boolean check",
        r"^(parse|extract|transform|convert)_": "transforms or parses data from one form to another",
        r"^(render|display|show|format)_": "formats or renders output for display",
        r"^(handle|process|on_)": "handles an event or processes a request",
        r"^(test_|assert)": "verifies expected behavior in a test",
        r"^(setup|teardown|configure)": "configures or initialises the environment",
        r"^(scan|walk|discover|find)_": "searches or discovers resources",
        r"^(send|emit|dispatch|publish)_": "sends or dispatches a message or event",
        r"^(log|debug|warn|error)_": "logs or reports information",
        r"^(ensure|require|assert)_": "ensures a precondition is met",
        r"^(upload|download)_": "transfers data to/from an external system",
        r"^_": "an internal helper (private by convention)",
    }
    for pattern, purpose in patterns.items():
        if re.match(pattern, name.lower()):
            return purpose
    return ""


def _explain_non_python_file(entry: dict) -> str:
    """Generate an explanation for non-Python files using content heuristics."""
    name = entry.get("name", "")
    language = entry.get("language", "")
    lines_count = entry.get("lines", 0)
    content = entry.get("content", "")
    purpose = _infer_file_purpose(entry)

    parts: list[str] = []
    parts.append(f"{name} is {purpose}.")
    parts.append("")

    if language == "HTML":
        parts.extend(_analyze_html(content))
    elif language in ("CSS", "SCSS"):
        parts.extend(_analyze_css(content))
    elif language in ("JavaScript", "TypeScript", "JavaScript React", "TypeScript React"):
        parts.extend(_analyze_javascript(content))
    elif language == "Markdown":
        parts.extend(_analyze_markdown(content))
    elif language == "JSON":
        parts.extend(_analyze_json(content, name))
    else:
        if content.strip():
            parts.append(f"Contains {lines_count} lines of {language} content.")
        else:
            parts.append("This file is currently empty.")

    return "\n".join(parts)


def _analyze_html(content: str) -> list[str]:
    """Extract structural information from HTML content."""
    lines: list[str] = []

    title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
    if title_match:
        lines.append(f"Page Title: {title_match.group(1).strip()}")

    headings = re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", content, re.IGNORECASE)
    if headings:
        lines.append("")
        lines.append("Headings:")
        for heading in headings[:10]:
            clean = re.sub(r"<[^>]+>", "", heading).strip()
            if clean:
                lines.append(f"  • {clean}")

    forms = re.findall(r'<form[^>]*id=["\']([^"\']+)["\']', content, re.IGNORECASE)
    if forms:
        lines.append("")
        lines.append("Forms:")
        for form_id in forms:
            lines.append(f"  • #{form_id}")

    sections = re.findall(r'<section[^>]*class=["\']([^"\']+)["\']', content, re.IGNORECASE)
    if sections:
        lines.append("")
        lines.append("Sections:")
        for section_class in sections[:10]:
            lines.append(f"  • .{section_class}")

    scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', content, re.IGNORECASE)
    stylesheets = re.findall(r'<link[^>]*href=["\']([^"\']+\.css)["\']', content, re.IGNORECASE)
    if scripts or stylesheets:
        lines.append("")
        lines.append("External Resources:")
        for src in stylesheets:
            lines.append(f"  • Stylesheet: {src}")
        for src in scripts:
            lines.append(f"  • Script: {src}")

    return lines


def _analyze_css(content: str) -> list[str]:
    """Extract structural information from CSS content."""
    lines: list[str] = []

    selectors = re.findall(r"^([.#:@][^\s{]+)", content, re.MULTILINE)
    if selectors:
        # Group by type
        classes = [s for s in selectors if s.startswith(".")]
        ids = [s for s in selectors if s.startswith("#")]
        at_rules = [s for s in selectors if s.startswith("@")]

        if classes:
            lines.append(f"Defines {len(classes)} CSS class rule(s).")
        if ids:
            lines.append(f"Defines {len(ids)} ID-based rule(s).")
        if at_rules:
            lines.append(f"Contains {len(at_rules)} at-rule(s) (media queries, keyframes, etc.).")

    variables = re.findall(r"--[\w-]+", content)
    if variables:
        unique_vars = sorted(set(variables))
        lines.append("")
        lines.append(f"CSS Custom Properties ({len(unique_vars)}):")
        for var in unique_vars[:12]:
            lines.append(f"  • {var}")
        if len(unique_vars) > 12:
            lines.append(f"  ... and {len(unique_vars) - 12} more")

    return lines


def _analyze_javascript(content: str) -> list[str]:
    """Extract structural information from JavaScript content."""
    lines: list[str] = []

    functions = re.findall(r"(?:function|const|let|var)\s+(\w+)\s*(?:=\s*(?:async\s*)?(?:\([^)]*\)\s*=>|\([^)]*\)\s*{|function)|\s*\()", content)
    if functions:
        lines.append(f"Functions/Variables ({len(functions)}):")
        for func in functions[:15]:
            lines.append(f"  • {func}")
        if len(functions) > 15:
            lines.append(f"  ... and {len(functions) - 15} more")

    event_listeners = re.findall(r'addEventListener\(\s*["\'](\w+)["\']', content)
    if event_listeners:
        lines.append("")
        lines.append("Event Listeners:")
        for event in sorted(set(event_listeners)):
            lines.append(f"  • {event}")

    api_calls = re.findall(r'(?:fetch|requestJson)\(\s*["`\']([^"`\']+)["`\']', content)
    if api_calls:
        lines.append("")
        lines.append("API Calls:")
        for url in sorted(set(api_calls)):
            lines.append(f"  • {url}")

    return lines


def _analyze_markdown(content: str) -> list[str]:
    """Extract structural information from Markdown content."""
    lines: list[str] = []

    headings = re.findall(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)
    if headings:
        lines.append("Document Structure:")
        for level, title in headings[:15]:
            indent = "  " * (len(level) - 1)
            lines.append(f"{indent}• {title.strip()}")

    code_blocks = re.findall(r"```(\w+)?", content)
    if code_blocks:
        languages = [lang for lang in code_blocks if lang]
        if languages:
            lines.append("")
            lines.append(f"Code examples in: {', '.join(sorted(set(languages)))}")

    return lines


def _analyze_json(content: str, name: str) -> list[str]:
    """Extract structural information from JSON content."""
    lines: list[str] = []

    if name == "package.json":
        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', content)
        version_match = re.search(r'"version"\s*:\s*"([^"]+)"', content)
        if name_match:
            lines.append(f"Package: {name_match.group(1)}")
        if version_match:
            lines.append(f"Version: {version_match.group(1)}")

    # Count top-level keys
    top_keys = re.findall(r'^\s{2}"(\w+)"', content, re.MULTILINE)
    if top_keys:
        lines.append("")
        lines.append(f"Top-level keys ({len(top_keys)}):")
        for key in top_keys[:12]:
            lines.append(f"  • {key}")
        if len(top_keys) > 12:
            lines.append(f"  ... and {len(top_keys) - 12} more")

    return lines


def _collect_project_modules(entries: list[dict]) -> list[dict]:
    """Group entries into logical modules/directories for project explanation."""
    modules: dict[str, list[dict]] = {}
    for entry in entries:
        path = entry.get("path", "")
        parts = path.split("/")
        if len(parts) > 1:
            module_name = parts[0] if len(parts) == 2 else "/".join(parts[:2])
        else:
            module_name = "(root)"
        modules.setdefault(module_name, []).append(entry)
    return [
        {"module": name, "files": files}
        for name, files in sorted(modules.items())
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain_file(path: str, entries: list[dict]) -> dict[str, Any]:
    """Generate a natural-language explanation of a file.

    For Python files: uses AST-parsed metadata (functions, classes, imports,
    decorators, docstrings) to build a rich explanation.

    For non-Python files: uses content heuristics to produce meaningful
    explanations.

    Returns a dict with ``explanation`` (str) and ``metadata`` (dict).
    """
    entry = _find_entry_by_path(path, entries)
    if entry is None:
        return {
            "explanation": f"File '{path}' was not found in the current index.",
            "metadata": {"found": False},
        }

    file_path = entry["path"]
    name = entry["name"]
    language = entry.get("language", "")
    lines_count = entry.get("lines", 0)
    size = entry.get("size", 0)
    content = entry.get("content", "")

    # Handle empty files
    if not content or not content.strip():
        purpose = _infer_file_purpose(entry)
        return {
            "explanation": (
                f"{name} is {purpose}.\n\n"
                f"This file is currently empty ({size} bytes)."
            ),
            "metadata": {"found": True, "path": file_path, "language": language, "empty": True},
        }

    # Non-Python files
    if language != "Python":
        explanation = _explain_non_python_file(entry)
        return {
            "explanation": explanation,
            "metadata": {"found": True, "path": file_path, "language": language, "lines": lines_count},
        }

    # Python files: use parsed metadata
    parsed = entry.get("parsed") or {}
    if not parsed or "language" not in parsed:
        parsed = parse_python_source(content, file_path)

    purpose = _infer_file_purpose(entry)
    module_name = parsed.get("module", "")
    docstring = parsed.get("docstring")
    functions = parsed.get("functions", [])
    classes = parsed.get("classes", [])
    imports = parsed.get("imports", [])
    error = parsed.get("error", "")

    parts: list[str] = []

    # Opening description
    parts.append(f"{name} is {purpose}.")
    if module_name:
        parts.append(f"Module: {module_name}")
    parts.append("")

    # Module docstring
    if docstring:
        parts.append("Description:")
        for doc_line in docstring.strip().splitlines():
            parts.append(f"  {doc_line}")
        parts.append("")

    # Responsibilities (inferred from functions and decorators)
    responsibilities = _infer_responsibilities(entry, functions, classes, imports)
    if responsibilities:
        parts.append("Responsibilities:")
        for resp in responsibilities:
            parts.append(f"  • {resp}")
        parts.append("")

    # Functions
    if functions:
        parts.append(f"Functions ({len(functions)}):")
        parts.append("")
        for func in functions:
            parts.append(_explain_function_detail(func))
            parts.append("")
    else:
        parts.append("This file defines no top-level functions.")
        parts.append("")

    # Classes
    if classes:
        parts.append(f"Classes ({len(classes)}):")
        parts.append("")
        for cls in classes:
            cls_doc = cls.get("docstring", "")
            methods = cls.get("methods", [])
            parts.append(f"  {cls['name']}")
            if cls_doc:
                parts.append(f"    {cls_doc.split(chr(10))[0].strip()}")
            if methods:
                parts.append(f"    Methods: {', '.join(m['name'] + '()' for m in methods)}")
            parts.append("")

    # Imports
    if imports:
        parts.append(f"Dependencies ({len(imports)} imports):")
        for imp in imports:
            parts.append(f"  • {imp}")
        parts.append("")

    # Parse errors
    if error:
        parts.append(f"⚠ Parse warning: {error}")
        parts.append("")

    metadata = {
        "found": True,
        "path": file_path,
        "language": language,
        "lines": lines_count,
        "function_count": len(functions),
        "class_count": len(classes),
        "import_count": len(imports),
    }

    return {"explanation": "\n".join(parts).rstrip(), "metadata": metadata}


def _infer_responsibilities(
    entry: dict,
    functions: list[dict],
    classes: list[dict],
    imports: list[Any],
) -> list[str]:
    """Infer high-level responsibilities from parsed metadata."""
    responsibilities: list[str] = []
    content = entry.get("content", "")
    name = entry.get("name", "").lower()

    # Detect from decorators
    has_routes = False
    for func in functions:
        for dec in func.get("decorators", []):
            if "app.get" in dec or "app.post" in dec or "app.put" in dec or "app.delete" in dec:
                has_routes = True
                break
            if "app.on_event" in dec:
                responsibilities.append("Manages application lifecycle events")

    if has_routes:
        responsibilities.append("Registers and handles HTTP routes")

    # Detect from imports and content patterns
    if any("FastAPI" in str(imp) for imp in imports):
        responsibilities.append("Creates the FastAPI application instance")
    if any("Jinja2" in str(imp) or "templates" in str(imp).lower() for imp in imports):
        responsibilities.append("Serves templated HTML pages")
    if any("StaticFiles" in str(imp) for imp in imports):
        responsibilities.append("Mounts static file serving")
    if "UploadFile" in content or "upload" in name:
        responsibilities.append("Handles file uploads")
    if "zipfile" in content or "ZipFile" in content:
        responsibilities.append("Processes ZIP archives")
    if "ast.parse" in content or "ast.walk" in content:
        responsibilities.append("Parses Python source code via the AST module")
    if "rglob" in content or re.search(r"\bwalk\b", content):
        responsibilities.append("Scans directory trees")
    if "json.dump" in content or "write_json" in content:
        responsibilities.append("Persists data to JSON files")
    if "logging" in content and "getLogger" in content:
        responsibilities.append("Uses structured logging")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for resp in responsibilities:
        if resp not in seen:
            unique.append(resp)
            seen.add(resp)
    return unique


def explain_function(name: str, entries: list[dict]) -> dict[str, Any]:
    """Explain a specific function's purpose, workflow, inputs, outputs, and side effects.

    Uses AST metadata — does NOT fall back to keyword search.

    Returns a dict with ``explanation`` (str) and ``metadata`` (dict).
    """
    matches = _find_function_in_entries(name, entries)

    if not matches:
        return {
            "explanation": (
                f"Function '{name}' was not found in the parsed metadata.\n\n"
                "This may mean:\n"
                "  • The function is defined inside another function (nested)\n"
                "  • The file has a syntax error preventing parsing\n"
                "  • The function exists in a non-Python file"
            ),
            "metadata": {"found": False},
        }

    parts: list[str] = []

    for match in matches:
        entry = match["entry"]
        func = match["function"]
        class_name = match["class_name"]
        file_path = entry["path"]

        func_name = func["name"]
        is_async = func.get("async", False)
        docstring = func.get("docstring", "")
        decorators = func.get("decorators", [])
        line = func.get("line", 0)

        qualified_name = f"{class_name}.{func_name}" if class_name else func_name
        kind = "async method" if class_name and is_async else "method" if class_name else "coroutine" if is_async else "function"

        parts.append(f"{qualified_name}()")
        parts.append(f"  Defined in: {file_path} (line {line})")
        parts.append(f"  Type: {kind}")
        parts.append("")

        # Purpose
        parts.append("Purpose:")
        if docstring:
            for doc_line in docstring.strip().splitlines():
                parts.append(f"  {doc_line}")
        else:
            inferred = _infer_function_purpose(func_name)
            parts.append(f"  {inferred}" if inferred else "  (no docstring available)")
        parts.append("")

        # Decorator context
        if decorators:
            parts.append("Route / Decorator Context:")
            for dec in decorators:
                desc = _describe_decorator(dec)
                parts.append(f"  • {desc}")
            parts.append("")

        # Workflow — infer from content if available
        workflow = _infer_function_workflow(func_name, entry)
        if workflow:
            parts.append("Workflow:")
            for step_index, step in enumerate(workflow, 1):
                parts.append(f"  {step_index}. {step}")
            parts.append("")

        parts.append("─" * 40)
        parts.append("")

    metadata = {
        "found": True,
        "count": len(matches),
        "locations": [
            {"path": m["entry"]["path"], "line": m["function"].get("line", 0)}
            for m in matches
        ],
    }

    return {"explanation": "\n".join(parts).rstrip(), "metadata": metadata}


def _infer_function_workflow(name: str, entry: dict) -> list[str]:
    """Infer a function's workflow steps from content analysis."""
    content = entry.get("content", "")
    if not content:
        return []

    # Find the function body (simple heuristic: from def to next def/class or end)
    pattern = rf"(?:async\s+)?def\s+{re.escape(name)}\s*\("
    match = re.search(pattern, content)
    if not match:
        return []

    start = match.start()
    # Find next top-level def/class or end of content
    next_def = re.search(r"\n(?:async\s+)?(?:def|class)\s+", content[start + 1:])
    end = start + 1 + next_def.start() if next_def else len(content)
    body = content[start:end]

    steps: list[str] = []

    # Detect common operations in order
    checks = [
        (r"(?:validate|check|verify|assert|if not)", "Validate input"),
        (r"(?:read|load|open|fetch|get)\b", "Read / retrieve data"),
        (r"(?:await\s+\w+\.read|UploadFile|file\.read)", "Receive uploaded data"),
        (r"(?:\.write|save|dump)\b", "Write data to disk"),
        (r"(?:ZipFile|extract|unzip)", "Extract archive contents"),
        (r"(?:scan|walk|rglob|glob)", "Scan files"),
        (r"(?:parse|ast\.parse)", "Parse source code"),
        (r"(?:build_metadata|metadata)", "Build metadata"),
        (r"(?:write_json|json\.dump)", "Persist results"),
        (r"(?:return|Response|JSONResponse)", "Return response"),
        (r"(?:raise\s+HTTP|HTTPException)", "Raise error on failure"),
    ]

    for pattern_str, step_desc in checks:
        if re.search(pattern_str, body, re.IGNORECASE):
            if step_desc not in steps:
                steps.append(step_desc)

    return steps


def explain_class(name: str, entries: list[dict]) -> dict[str, Any]:
    """Explain a class: purpose, responsibilities, relationships, public methods.

    Returns a dict with ``explanation`` (str) and ``metadata`` (dict).
    """
    matches = _find_class_in_entries(name, entries)

    if not matches:
        return {
            "explanation": (
                f"Class '{name}' was not found in the parsed metadata.\n\n"
                "The class may exist in a non-Python file or the file may have a syntax error."
            ),
            "metadata": {"found": False},
        }

    parts: list[str] = []

    for match in matches:
        entry = match["entry"]
        cls = match["class_info"]
        file_path = entry["path"]

        cls_name = cls["name"]
        docstring = cls.get("docstring", "")
        decorators = cls.get("decorators", [])
        methods = cls.get("methods", [])
        line = cls.get("line", 0)

        parts.append(f"class {cls_name}")
        parts.append(f"  Defined in: {file_path} (line {line})")
        parts.append("")

        # Purpose
        if docstring:
            parts.append("Purpose:")
            for doc_line in docstring.strip().splitlines():
                parts.append(f"  {doc_line}")
            parts.append("")

        # Decorators
        if decorators:
            parts.append("Decorators:")
            for dec in decorators:
                parts.append(f"  • @{dec}")
            parts.append("")

        # Public methods
        public_methods = [m for m in methods if not m["name"].startswith("_")]
        private_methods = [m for m in methods if m["name"].startswith("_") and m["name"] != "__init__"]
        init = next((m for m in methods if m["name"] == "__init__"), None)

        if init:
            parts.append("Constructor:")
            init_doc = init.get("docstring", "")
            parts.append(f"  __init__() — {init_doc.split(chr(10))[0].strip() if init_doc else 'initialises the instance'}")
            parts.append("")

        if public_methods:
            parts.append(f"Public Methods ({len(public_methods)}):")
            for method in public_methods:
                method_doc = method.get("docstring", "")
                desc = method_doc.split("\n")[0].strip() if method_doc else _infer_function_purpose(method["name"]) or "—"
                is_async = " (async)" if method.get("async") else ""
                parts.append(f"  • {method['name']}(){is_async} — {desc}")
            parts.append("")

        if private_methods:
            parts.append(f"Internal Methods ({len(private_methods)}):")
            for method in private_methods:
                parts.append(f"  • {method['name']}()")
            parts.append("")

        if not methods:
            parts.append("This class defines no methods.")
            parts.append("")

    metadata = {
        "found": True,
        "count": len(matches),
        "locations": [
            {"path": m["entry"]["path"], "line": m["class_info"].get("line", 0)}
            for m in matches
        ],
    }

    return {"explanation": "\n".join(parts).rstrip(), "metadata": metadata}


def explain_project(entries: list[dict], metadata: dict) -> dict[str, Any]:
    """Generate a full project explanation: purpose, architecture, workflows, entry points.

    Written like a senior engineer explaining the codebase to a new developer.

    Returns a dict with ``explanation`` (str) and ``metadata`` (dict).
    """
    if not entries:
        return {
            "explanation": "No repository has been indexed yet. Upload a ZIP codebase first.",
            "metadata": {"indexed": False},
        }

    project_name = metadata.get("project_name", "this project")
    file_count = metadata.get("file_count", len(entries))
    languages = metadata.get("languages", {})
    total_lines = metadata.get("total_lines", 0)
    function_count = metadata.get("function_count", 0)
    class_count = metadata.get("class_count", 0)
    important_files = metadata.get("important_files", [])

    parts: list[str] = []

    # --- Project Overview ---
    parts.append(f"Project: {project_name}")
    parts.append("=" * (len(f"Project: {project_name}")))
    parts.append("")

    # Purpose
    purpose = _infer_project_purpose(entries, metadata)
    parts.append("Purpose:")
    parts.append(f"  {purpose}")
    parts.append("")

    # At a Glance
    lang_summary = ", ".join(f"{lang} ({count})" for lang, count in languages.items())
    parts.append("At a Glance:")
    parts.append(f"  • {file_count} files, {total_lines} lines of code")
    parts.append(f"  • Languages: {lang_summary}")
    parts.append(f"  • {function_count} functions, {class_count} classes")
    parts.append("")

    # --- Architecture ---
    parts.append("Architecture:")
    parts.append("─" * 40)
    modules = _collect_project_modules(entries)
    for mod in modules:
        mod_name = mod["module"]
        files = mod["files"]
        file_names = ", ".join(f["name"] for f in files[:8])
        if len(files) > 8:
            file_names += f", ... (+{len(files) - 8} more)"
        parts.append(f"  {mod_name}/")
        parts.append(f"    {file_names}")
    parts.append("")

    # --- Entry Points ---
    entry_points = _find_entry_points(entries)
    if entry_points:
        parts.append("Entry Points:")
        for ep in entry_points:
            parts.append(f"  • {ep}")
        parts.append("")

    # --- Key Workflows ---
    workflows = _infer_project_workflows(entries)
    if workflows:
        parts.append("Key Workflows:")
        for workflow_name, steps in workflows.items():
            parts.append(f"  {workflow_name}:")
            for i, step in enumerate(steps):
                connector = "↓" if i < len(steps) - 1 else ""
                parts.append(f"    {step}")
                if connector:
                    parts.append(f"    {connector}")
        parts.append("")

    # --- Important Files ---
    if important_files:
        parts.append("Important Files:")
        for imp_file in important_files[:12]:
            # Find and explain each
            imp_entry = _find_entry_by_path(imp_file, entries)
            if imp_entry:
                purpose_text = _infer_file_purpose(imp_entry)
                parts.append(f"  • {imp_file} — {purpose_text}")
            else:
                parts.append(f"  • {imp_file}")
        parts.append("")

    # --- Project Flow ---
    parts.append("Project Flow:")
    parts.append("─" * 40)
    flow = generate_project_flow(entries)
    parts.append(flow)
    parts.append("")

    proj_metadata = {
        "indexed": True,
        "project_name": project_name,
        "file_count": file_count,
        "languages": languages,
    }

    return {"explanation": "\n".join(parts).rstrip(), "metadata": proj_metadata}


def _infer_project_purpose(entries: list[dict], metadata: dict) -> str:
    """Infer the project purpose from README, docstrings, and file patterns."""
    # Check README first
    for entry in entries:
        if entry["name"].lower() in ("readme.md", "readme.txt", "readme"):
            content = entry.get("content", "")
            # Extract first paragraph after the title
            lines = content.strip().splitlines()
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("="):
                    return stripped[:300]

    # Check for framework indicators
    content_blob = " ".join(e.get("content", "")[:200] for e in entries[:20])
    if "FastAPI" in content_blob:
        return "A FastAPI web application that provides a REST API backend."
    if "Flask" in content_blob:
        return "A Flask web application."
    if "Django" in content_blob:
        return "A Django web application."
    if "React" in content_blob or "jsx" in content_blob:
        return "A React frontend application."

    project_name = metadata.get("project_name", "Unknown")
    return f"{project_name} is a software project."


def _find_entry_points(entries: list[dict]) -> list[str]:
    """Identify likely application entry points."""
    entry_points: list[str] = []

    for entry in entries:
        name = entry.get("name", "").lower()
        content = entry.get("content", "")

        if name in ("main.py", "app.py", "manage.py", "server.py"):
            entry_points.append(f"{entry['path']} — application entry point")
        elif name == "index.html":
            entry_points.append(f"{entry['path']} — web frontend entry point")
        elif name == "index.js" or name == "index.ts":
            entry_points.append(f"{entry['path']} — JavaScript entry point")
        elif "__main__" in content and entry.get("language") == "Python":
            entry_points.append(f"{entry['path']} — CLI entry point (__main__)")

    return entry_points[:8]


def _infer_project_workflows(entries: list[dict]) -> dict[str, list[str]]:
    """Infer key workflows from the project structure and content."""
    workflows: dict[str, list[str]] = {}
    file_names = {e["name"].lower() for e in entries}
    content_blob = " ".join(e.get("content", "")[:500] for e in entries[:20])

    if "upload" in content_blob.lower() or "UploadFile" in content_blob:
        workflows["Upload Flow"] = [
            "User uploads a file",
            "Server validates the upload",
            "File is saved to disk",
            "Processing is triggered",
        ]

    if "ingest" in file_names or "ingest.py" in file_names:
        workflows["Ingestion Flow"] = [
            "Receive upload",
            "Extract contents",
            "Scan repository files",
            "Parse source code",
            "Build metadata",
            "Persist index to disk",
        ]

    if "scanner.py" in file_names or "scan" in content_blob.lower():
        workflows["Scanning Flow"] = [
            "Walk directory tree",
            "Filter ignored files",
            "Detect language per file",
            "Read bounded text content",
            "Invoke parser for Python files",
            "Build index entries",
        ]

    return workflows


def generate_project_flow(entries: list[dict]) -> str:
    """Generate the project processing flow as readable text.

    Shows the pipeline: Upload → Extract → Scan → Parse → Metadata →
    Insights → Search → Explainer
    """
    file_names = {e["name"].lower() for e in entries}

    steps: list[str] = []
    steps.append("  Upload ZIP")

    if "ingest.py" in file_names:
        steps.append("  Extract repository")

    if "scanner.py" in file_names:
        steps.append("  Scan files")

    if "parser.py" in file_names:
        steps.append("  Parse source code (AST)")

    if "metadata.py" in file_names:
        steps.append("  Build metadata")

    if "insights.py" in file_names:
        steps.append("  Generate repository insights")

    if "search.py" in file_names:
        steps.append("  Index for search")

    steps.append("  Repository Explainer")
    steps.append("  Developer explores and understands the codebase")

    flow_lines: list[str] = []
    for i, step in enumerate(steps):
        flow_lines.append(step)
        if i < len(steps) - 1:
            flow_lines.append("    ↓")

    return "\n".join(flow_lines)


def generate_repository_summary(entries: list[dict], metadata: dict) -> dict[str, Any]:
    """Generate a structured repository summary.

    Includes: project name, purpose, languages, file count, main modules,
    important entry points, overall architecture.
    """
    project_name = metadata.get("project_name", "Unknown")
    purpose = _infer_project_purpose(entries, metadata)
    languages = metadata.get("languages", {})
    file_count = metadata.get("file_count", len(entries))
    total_lines = metadata.get("total_lines", 0)

    # Main modules
    modules = _collect_project_modules(entries)
    main_modules = [
        {"name": mod["module"], "file_count": len(mod["files"])}
        for mod in modules
    ]

    # Entry points
    entry_points = _find_entry_points(entries)

    summary = {
        "project_name": project_name,
        "purpose": purpose,
        "languages": languages,
        "file_count": file_count,
        "total_lines": total_lines,
        "main_modules": main_modules,
        "entry_points": entry_points,
        "architecture": "Monolithic application" if len(modules) <= 3 else "Multi-module application",
    }

    # Text version
    parts: list[str] = []
    parts.append(f"Project: {project_name}")
    parts.append(f"Purpose: {purpose}")
    parts.append(f"Files: {file_count} ({total_lines} lines)")
    parts.append(f"Languages: {', '.join(languages.keys())}")
    parts.append("")
    parts.append("Main Modules:")
    for mod in main_modules:
        parts.append(f"  • {mod['name']} ({mod['file_count']} files)")
    parts.append("")
    if entry_points:
        parts.append("Entry Points:")
        for ep in entry_points:
            parts.append(f"  • {ep}")
    parts.append("")
    parts.append(f"Architecture: {summary['architecture']}")

    return {
        "explanation": "\n".join(parts),
        "metadata": summary,
    }
