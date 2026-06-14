"""Tests for DevDocs v0.3.0 — Repository Explainer.

Verifies:
- File explanation (Python, non-Python, empty)
- Function explanation
- Class explanation
- Project explanation
- Q&A routing through explainer
- Existing features (search, metadata answers) still work
"""

import sys
from pathlib import Path

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.explainer import (
    explain_class,
    explain_file,
    explain_function,
    explain_project,
    generate_project_flow,
    generate_repository_summary,
)
from app.rag import answer_question
from app.search import search_entries
from app.insights import answer_from_metadata


# ---------------------------------------------------------------------------
# Fixture: a minimal set of index entries that mimic a real indexed project
# ---------------------------------------------------------------------------

SAMPLE_ENTRIES = [
    {
        "path": "app/main.py",
        "name": "main.py",
        "extension": ".py",
        "language": "Python",
        "size": 2000,
        "lines": 80,
        "summary": "from fastapi import FastAPI",
        "definitions": ["home", "upload", "ask"],
        "parsed": {
            "file": "app/main.py",
            "module": "app.main",
            "language": "Python",
            "imports": ["FastAPI", "File", "HTTPException", "Query", "UploadFile", "HTMLResponse", "StaticFiles", "Jinja2Templates"],
            "functions": [
                {"name": "home", "async": False, "decorators": ["app.get('/', response_class=HTMLResponse)"], "docstring": "Displays the homepage.", "line": 34},
                {"name": "upload", "async": True, "decorators": ["app.post('/upload')"], "docstring": "Receives ZIP repositories. Extracts and indexes them.", "line": 40},
                {"name": "ask", "async": False, "decorators": ["app.post('/ask')"], "docstring": "Answers repository questions.", "line": 92},
            ],
            "classes": [],
            "docstring": None,
            "error": "",
        },
        "content": "from fastapi import FastAPI, File, HTTPException, Query, UploadFile\nfrom fastapi.responses import HTMLResponse\nfrom fastapi.staticfiles import StaticFiles\nfrom fastapi.templating import Jinja2Templates\napp = FastAPI(title='DevDocs Lite', version='0.3.0')\napp.mount('/static', StaticFiles(directory='static'), name='static')\ntemplates = Jinja2Templates(directory='templates')\n\ndef home():\n    return templates.TemplateResponse('index.html')\n\nasync def upload(file):\n    return await ingest_upload(file)\n\ndef ask(payload):\n    return answer_question(payload.question)\n",
        "truncated": False,
    },
    {
        "path": "app/ingest.py",
        "name": "ingest.py",
        "extension": ".py",
        "language": "Python",
        "size": 1500,
        "lines": 60,
        "summary": "import zipfile",
        "definitions": ["save_upload", "extract_zip", "ingest_upload"],
        "parsed": {
            "file": "app/ingest.py",
            "module": "app.ingest",
            "language": "Python",
            "imports": ["zipfile", "Path", "HTTPException", "UploadFile"],
            "functions": [
                {"name": "save_upload", "async": True, "decorators": [], "docstring": "Save an uploaded file to disk.", "line": 13},
                {"name": "extract_zip", "async": False, "decorators": [], "docstring": "", "line": 29},
                {"name": "ingest_upload", "async": True, "decorators": [], "docstring": "Receive, extract, and index an uploaded repository.", "line": 58},
            ],
            "classes": [],
            "docstring": None,
            "error": "",
        },
        "content": "import zipfile\nfrom pathlib import Path\nasync def save_upload(file):\n    pass\ndef extract_zip(zip_path):\n    pass\nasync def ingest_upload(file):\n    zip_path = await save_upload(file)\n    project_name = extract_zip(zip_path)\n    entries = scan_project()\n    metadata = build_metadata(entries, project_name)\n    write_json(FILES_INDEX_PATH, entries)\n    return {'message': 'Indexed'}\n",
        "truncated": False,
    },
    {
        "path": "app/parser.py",
        "name": "parser.py",
        "extension": ".py",
        "language": "Python",
        "size": 3000,
        "lines": 120,
        "summary": "import ast",
        "definitions": ["parse_python_source", "parsed_definitions"],
        "parsed": {
            "file": "app/parser.py",
            "module": "app.parser",
            "language": "Python",
            "imports": ["ast", "logging", "PurePosixPath"],
            "functions": [
                {"name": "module_name_from_path", "async": False, "decorators": [], "docstring": "Return a dotted Python module name.", "line": 19},
                {"name": "parse_python_source", "async": False, "decorators": [], "docstring": "Parse Python source with ast and return structured metadata.", "line": 117},
                {"name": "parsed_definitions", "async": False, "decorators": [], "docstring": "Flatten parsed symbols into definitions shape.", "line": 158},
            ],
            "classes": [],
            "docstring": "AST-based Python parser.",
            "error": "",
        },
        "content": '"""AST-based Python parser."""\nimport ast\nimport logging\ndef module_name_from_path(path):\n    pass\ndef parse_python_source(source, path):\n    tree = ast.parse(source, filename=path)\n    return {}\ndef parsed_definitions(parsed):\n    return []\n',
        "truncated": False,
    },
    {
        "path": "templates/index.html",
        "name": "index.html",
        "extension": ".html",
        "language": "HTML",
        "size": 3000,
        "lines": 90,
        "summary": "<!DOCTYPE html>",
        "definitions": [],
        "parsed": {},
        "content": '<!DOCTYPE html>\n<html lang="en">\n<head><meta charset="UTF-8"><title>DevDocs Lite</title></head>\n<body>\n<main class="shell">\n<header class="topbar"><h1>DevDocs Lite</h1></header>\n<form id="uploadForm" class="upload-form"><input type="file" id="fileInput" accept=".zip"></form>\n<section class="panel ask-panel"><form id="askForm"><input type="text" id="questionInput"></form></section>\n</main>\n<script src="/static/script.js"></script>\n</body>\n</html>',
        "truncated": False,
    },
    {
        "path": "static/style.css",
        "name": "style.css",
        "extension": ".css",
        "language": "CSS",
        "size": 4000,
        "lines": 280,
        "summary": "* {",
        "definitions": [],
        "parsed": {},
        "content": "* { margin: 0; padding: 0; box-sizing: border-box; }\n:root {\n  color-scheme: light;\n  --bg: #f5f7f8;\n  --surface: #ffffff;\n  --text: #172026;\n  --accent: #0f766e;\n}\nbody { font-family: Inter, sans-serif; background: var(--bg); }\n.shell { width: min(1440px, 100%); margin: 0 auto; }\n.topbar { display: flex; }\n.panel { background: var(--surface); border-radius: 8px; }\n",
        "truncated": False,
    },
    {
        "path": "README.md",
        "name": "README.md",
        "extension": ".md",
        "language": "Markdown",
        "size": 1200,
        "lines": 40,
        "summary": "# DevDocs Lite",
        "definitions": [],
        "parsed": {},
        "content": "# DevDocs Lite\n\nA lightweight documentation and code exploration tool for ZIP-uploaded repositories.\n\n## Features\n\n- Upload ZIP\n- File explorer\n- Search\n- Repository insights\n\n## Getting Started\n\n```bash\nuvicorn app.main:app --reload\n```\n",
        "truncated": False,
    },
    {
        "path": "app/empty_module.py",
        "name": "empty_module.py",
        "extension": ".py",
        "language": "Python",
        "size": 0,
        "lines": 0,
        "summary": "",
        "definitions": [],
        "parsed": {
            "file": "app/empty_module.py",
            "module": "app.empty_module",
            "language": "Python",
            "imports": [],
            "functions": [],
            "classes": [],
            "docstring": None,
            "error": "",
        },
        "content": "",
        "truncated": False,
    },
    {
        "path": "app/models.py",
        "name": "models.py",
        "extension": ".py",
        "language": "Python",
        "size": 500,
        "lines": 25,
        "summary": "from pydantic import BaseModel",
        "definitions": ["AskRequest", "PreviewResponse", "UploadResponse"],
        "parsed": {
            "file": "app/models.py",
            "module": "app.models",
            "language": "Python",
            "imports": ["BaseModel", "Field"],
            "functions": [],
            "classes": [
                {
                    "name": "AskRequest",
                    "methods": [],
                    "decorators": [],
                    "docstring": "Request model for the /ask endpoint.",
                    "line": 4,
                },
                {
                    "name": "PreviewResponse",
                    "methods": [],
                    "decorators": [],
                    "docstring": "",
                    "line": 15,
                },
                {
                    "name": "UploadResponse",
                    "methods": [],
                    "decorators": [],
                    "docstring": "",
                    "line": 23,
                },
            ],
            "docstring": None,
            "error": "",
        },
        "content": "from pydantic import BaseModel, Field\n\nclass AskRequest(BaseModel):\n    \"\"\"Request model for the /ask endpoint.\"\"\"\n    question: str = Field(..., min_length=1, max_length=600)\n\nclass PreviewResponse(BaseModel):\n    path: str\n    language: str\n    content: str\n    truncated: bool\n\nclass UploadResponse(BaseModel):\n    message: str\n    files_indexed: int\n    project_name: str\n",
        "truncated": False,
    },
]

SAMPLE_METADATA = {
    "project_name": "devdocs-lite",
    "file_count": len(SAMPLE_ENTRIES),
    "total_lines": sum(e["lines"] for e in SAMPLE_ENTRIES),
    "total_size": sum(e["size"] for e in SAMPLE_ENTRIES),
    "python_files": 5,
    "function_count": 9,
    "class_count": 3,
    "method_count": 0,
    "import_count": 17,
    "average_loc": 85,
    "languages": {"Python": 5, "HTML": 1, "CSS": 1, "Markdown": 1},
    "important_files": ["app/main.py", "app/ingest.py", "README.md"],
}


# ---------------------------------------------------------------------------
# Tests: File Explanation
# ---------------------------------------------------------------------------

def test_explain_python_file():
    """Explain main.py should return responsibilities, functions, non-empty."""
    result = explain_file("main.py", SAMPLE_ENTRIES)
    explanation = result["explanation"]
    metadata = result["metadata"]

    assert metadata["found"] is True
    assert metadata["language"] == "Python"
    assert "main.py" in explanation.lower() or "entry point" in explanation.lower()
    assert "home" in explanation
    assert "upload" in explanation
    assert "ask" in explanation
    assert len(explanation) > 100
    print("  ✓ explain_file(main.py) — rich Python explanation")


def test_explain_ingest():
    """Explain ingest.py should describe ingestion responsibilities."""
    result = explain_file("ingest.py", SAMPLE_ENTRIES)
    explanation = result["explanation"]

    assert result["metadata"]["found"] is True
    assert "save_upload" in explanation
    assert "extract_zip" in explanation
    assert "ingest_upload" in explanation
    print("  ✓ explain_file(ingest.py) — ingestion module explained")


def test_explain_parser():
    """Explain parser.py should show AST docstring and functions."""
    result = explain_file("parser.py", SAMPLE_ENTRIES)
    explanation = result["explanation"]

    assert result["metadata"]["found"] is True
    assert "AST" in explanation or "ast" in explanation.lower()
    assert "parse_python_source" in explanation
    print("  ✓ explain_file(parser.py) — parser with docstring explained")


def test_explain_empty_file():
    """Explain an empty Python file should not crash."""
    result = explain_file("empty_module.py", SAMPLE_ENTRIES)
    explanation = result["explanation"]

    assert result["metadata"]["found"] is True
    assert result["metadata"]["empty"] is True
    assert "empty" in explanation.lower()
    print("  ✓ explain_file(empty_module.py) — graceful empty file")


def test_explain_html_file():
    """Explain an HTML file should produce meaningful non-Python explanation."""
    result = explain_file("index.html", SAMPLE_ENTRIES)
    explanation = result["explanation"]

    assert result["metadata"]["found"] is True
    assert result["metadata"]["language"] == "HTML"
    assert len(explanation) > 20
    print("  ✓ explain_file(index.html) — HTML explained")


def test_explain_css_file():
    """Explain a CSS file should produce meaningful explanation."""
    result = explain_file("style.css", SAMPLE_ENTRIES)
    explanation = result["explanation"]

    assert result["metadata"]["found"] is True
    assert result["metadata"]["language"] == "CSS"
    assert len(explanation) > 20
    print("  ✓ explain_file(style.css) — CSS explained")


def test_explain_readme():
    """Explain README.md should produce markdown analysis."""
    result = explain_file("README.md", SAMPLE_ENTRIES)
    explanation = result["explanation"]

    assert result["metadata"]["found"] is True
    assert "documentation" in explanation.lower() or "markdown" in explanation.lower() or "readme" in explanation.lower()
    print("  ✓ explain_file(README.md) — Markdown explained")


def test_explain_missing_file():
    """Explain a non-existent file should return a graceful 'not found'."""
    result = explain_file("nonexistent.py", SAMPLE_ENTRIES)
    assert result["metadata"]["found"] is False
    assert "not found" in result["explanation"].lower()
    print("  ✓ explain_file(nonexistent.py) — graceful not-found")


# ---------------------------------------------------------------------------
# Tests: Function Explanation
# ---------------------------------------------------------------------------

def test_explain_function_upload():
    """Explain upload() should return purpose, workflow, location."""
    result = explain_function("upload", SAMPLE_ENTRIES)
    explanation = result["explanation"]
    metadata = result["metadata"]

    assert metadata["found"] is True
    assert metadata["count"] >= 1
    assert "upload" in explanation.lower()
    assert "Purpose" in explanation
    print("  ✓ explain_function(upload) — function explained")


def test_explain_function_with_parens():
    """Explain upload_file() with trailing parens should still work."""
    result = explain_function("home()", SAMPLE_ENTRIES)
    assert result["metadata"]["found"] is True
    assert "home" in result["explanation"].lower()
    print("  ✓ explain_function(home()) — parens stripped correctly")


def test_explain_function_not_found():
    """Explain a non-existent function should not crash."""
    result = explain_function("nonexistent_func", SAMPLE_ENTRIES)
    assert result["metadata"]["found"] is False
    assert "not found" in result["explanation"].lower()
    print("  ✓ explain_function(nonexistent_func) — graceful not-found")


# ---------------------------------------------------------------------------
# Tests: Class Explanation
# ---------------------------------------------------------------------------

def test_explain_class():
    """Explain AskRequest class should return its purpose."""
    result = explain_class("AskRequest", SAMPLE_ENTRIES)
    explanation = result["explanation"]
    metadata = result["metadata"]

    assert metadata["found"] is True
    assert "AskRequest" in explanation
    assert "Purpose" in explanation or "Request model" in explanation
    print("  ✓ explain_class(AskRequest) — class explained")


def test_explain_class_not_found():
    """Explain a non-existent class should not crash."""
    result = explain_class("NonexistentClass", SAMPLE_ENTRIES)
    assert result["metadata"]["found"] is False
    print("  ✓ explain_class(NonexistentClass) — graceful not-found")


# ---------------------------------------------------------------------------
# Tests: Project Explanation
# ---------------------------------------------------------------------------

def test_explain_project():
    """Explain the whole project should return architecture and workflows."""
    result = explain_project(SAMPLE_ENTRIES, SAMPLE_METADATA)
    explanation = result["explanation"]

    assert result["metadata"]["indexed"] is True
    assert "devdocs" in explanation.lower() or "project" in explanation.lower()
    assert "Architecture" in explanation
    assert "Entry Points" in explanation or "entry point" in explanation.lower()
    assert len(explanation) > 200
    print("  ✓ explain_project() — full project explanation")


def test_explain_empty_project():
    """Explain an empty project should not crash."""
    result = explain_project([], {})
    assert result["metadata"]["indexed"] is False
    assert "no repository" in result["explanation"].lower() or "upload" in result["explanation"].lower()
    print("  ✓ explain_project([]) — graceful empty project")


def test_project_flow():
    """Project flow should include the pipeline steps."""
    flow = generate_project_flow(SAMPLE_ENTRIES)
    assert "Upload" in flow
    assert "Explainer" in flow
    assert "↓" in flow
    print("  ✓ generate_project_flow() — pipeline rendered")


def test_repository_summary():
    """Repository summary should include name, purpose, languages."""
    result = generate_repository_summary(SAMPLE_ENTRIES, SAMPLE_METADATA)
    assert "devdocs" in result["explanation"].lower()
    assert result["metadata"]["project_name"] == "devdocs-lite"
    assert result["metadata"]["file_count"] == len(SAMPLE_ENTRIES)
    print("  ✓ generate_repository_summary() — structured summary")


# ---------------------------------------------------------------------------
# Tests: Q&A Routing (explainer-first)
# ---------------------------------------------------------------------------

def test_qa_explain_file():
    """'Explain main.py' via Q&A should route to explainer."""
    result = answer_question("Explain main.py", SAMPLE_ENTRIES)
    assert "entry point" in result["answer"].lower() or "main.py" in result["answer"].lower()
    print("  ✓ Q&A: 'Explain main.py' → explainer")


def test_qa_explain_function():
    """'Explain upload()' via Q&A should route to explainer."""
    result = answer_question("Explain upload()", SAMPLE_ENTRIES)
    assert "upload" in result["answer"].lower()
    assert "Purpose" in result["answer"] or "purpose" in result["answer"].lower()
    print("  ✓ Q&A: 'Explain upload()' → explainer")


def test_qa_explain_project():
    """'Explain this repository' via Q&A should route to project explainer."""
    result = answer_question("Explain this repository", SAMPLE_ENTRIES)
    assert "project" in result["answer"].lower() or "architecture" in result["answer"].lower() or "devdocs" in result["answer"].lower()
    print("  ✓ Q&A: 'Explain this repository' → project explainer")


def test_qa_explain_project_like_new_dev():
    """'Explain this project like I'm a new developer' should route to project explainer."""
    result = answer_question("Explain this project like I'm a new developer", SAMPLE_ENTRIES)
    assert len(result["answer"]) > 100
    print("  ✓ Q&A: 'Explain this project like I'm a new developer' → project explainer")


def test_qa_what_is_purpose_of_parser():
    """'What is the purpose of parser.py?' should route to explainer."""
    result = answer_question("What is the purpose of parser.py?", SAMPLE_ENTRIES)
    assert "parser" in result["answer"].lower()
    print("  ✓ Q&A: 'What is the purpose of parser.py?' → explainer")


def test_qa_what_is_ingest_for():
    """'What is ingest.py for?' should route to explainer."""
    result = answer_question("What is ingest.py for?", SAMPLE_ENTRIES)
    assert "ingest" in result["answer"].lower()
    print("  ✓ Q&A: 'What is ingest.py for?' → explainer")


def test_qa_how_does_upload_work():
    """'How does the upload process work?' should still give useful answer."""
    result = answer_question("How does the upload process work?", SAMPLE_ENTRIES)
    assert len(result["answer"]) > 20
    print("  ✓ Q&A: 'How does the upload process work?' → answer given")


def test_qa_project_architecture():
    """'What is the project architecture?' should route to project explainer."""
    result = answer_question("What is the project architecture?", SAMPLE_ENTRIES)
    assert len(result["answer"]) > 100
    print("  ✓ Q&A: 'What is the project architecture?' → project explainer")


# ---------------------------------------------------------------------------
# Tests: Existing Features Still Work
# ---------------------------------------------------------------------------

def test_existing_search():
    """Search should still work with the existing search engine."""
    results = search_entries("upload", SAMPLE_ENTRIES)
    assert len(results) > 0
    assert any("ingest" in r["path"] or "main" in r["path"] for r in results)
    print("  ✓ Existing search still works")


def test_existing_metadata_answer():
    """Metadata-based Q&A should still work for non-explain queries."""
    result = answer_from_metadata("How many functions are there?", SAMPLE_ENTRIES)
    assert result is not None
    assert "function" in result["answer"].lower()
    print("  ✓ Existing metadata Q&A still works")


def test_qa_non_explain_falls_through():
    """A non-explain question should still use metadata/search fallback."""
    result = answer_question("How many functions are there?", SAMPLE_ENTRIES)
    assert "function" in result["answer"].lower()
    print("  ✓ Non-explain questions fall through to metadata/search")


def test_qa_empty_index():
    """Q&A with no entries should return a helpful message."""
    result = answer_question("Explain main.py", [])
    assert "upload" in result["answer"].lower()
    print("  ✓ Q&A with empty index → 'upload first' message")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0

    print(f"\nRunning {len(tests)} tests for DevDocs v0.3.0...\n")

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as exc:
            failed += 1
            print(f"  ✗ {test.__name__}: {exc}")

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'=' * 50}")

    if failed:
        sys.exit(1)
    else:
        print("\n✅ All tests passed. DevDocs v0.3.0 is ready.")
