"""
Adversarial audit script for DevDocs v0.2.0.
Tests every acceptance criterion, edge case, and potential bug.
"""
import ast
import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

BASE = "http://127.0.0.1:8001"
FAILURES = []
PASSES = []

def fail(label, detail=""):
    FAILURES.append(f"FAIL: {label}" + (f" — {detail}" if detail else ""))
    print(f"  ✗ FAIL: {label}" + (f"\n      {detail}" if detail else ""))

def ok(label):
    PASSES.append(f"PASS: {label}")
    print(f"  ✓ {label}")

def get(path):
    r = urllib.request.urlopen(BASE + path)
    return json.loads(r.read())

def post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    r = urllib.request.urlopen(req)
    return json.loads(r.read())

def ask(q):
    return post("/ask", {"question": q})

# ─────────────────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════")
print("  PHASE 1: Parser Unit Tests")
print("══════════════════════════════════════════════════")
sys.path.insert(0, str(Path(__file__).parent))
from app.parser import parse_python_source, empty_python_metadata, _imports, module_name_from_path

# 1a. Empty string
r = parse_python_source("", "test.py")
if r["functions"] == [] and r["classes"] == [] and r["imports"] == [] and r.get("error","") == "":
    ok("Empty source → valid empty metadata, no error")
else:
    fail("Empty source must produce valid empty metadata", str(r))

# 1b. Whitespace-only
r = parse_python_source("   \n\t  ", "test.py")
if r["functions"] == [] and r["imports"] == []:
    ok("Whitespace-only source → empty metadata")
else:
    fail("Whitespace-only source", str(r))

# 1c. SyntaxError file
r = parse_python_source("def foo(:\n    pass", "bad.py")
if r["error"] and r["functions"] == []:
    ok("SyntaxError file → error set, no crash")
else:
    fail("SyntaxError file must set error field", str(r))

# 1d. Valid file - correct function count
src = """
def foo(): pass
def bar(): pass
class MyClass:
    def method(self): pass
"""
r = parse_python_source(src, "test.py")
if len(r["functions"]) == 2:
    ok("Top-level functions correctly counted (methods excluded from top-level list)")
else:
    fail(f"Top-level function count should be 2, got {len(r['functions'])}", str(r["functions"]))

# 1e. Classes count
if len(r["classes"]) == 1:
    ok("Class count correct")
else:
    fail(f"Class count should be 1, got {len(r['classes'])}")

# 1f. Methods inside class
methods = r["classes"][0]["methods"]
if len(methods) == 1 and methods[0]["name"] == "method":
    ok("Method inside class captured correctly")
else:
    fail("Class methods incorrect", str(methods))

# 1g. Import deduplication
src2 = """
import os
import os
from pathlib import Path
from pathlib import Path
"""
r2 = parse_python_source(src2, "dup.py")
if len(r2["imports"]) == len(set(r2["imports"])):
    ok("Import deduplication works")
else:
    fail("Imports are not deduplicated", str(r2["imports"]))

# 1h. from-import captures name, not module
src3 = "from fastapi import FastAPI, HTTPException"
r3 = parse_python_source(src3, "x.py")
if "FastAPI" in r3["imports"] and "HTTPException" in r3["imports"]:
    ok("from-import captures names (FastAPI, HTTPException)")
else:
    fail("from-import should capture names not module", str(r3["imports"]))

# 1i. wildcard import
src4 = "from os import *"
r4 = parse_python_source(src4, "x.py")
if any("os.*" in imp for imp in r4["imports"]):
    ok("Wildcard import captured as 'os.*'")
else:
    fail("Wildcard import not captured correctly", str(r4["imports"]))

# 1j. module_name_from_path
m = module_name_from_path("devdocs-lite-main/app/main.py")
if m == "devdocs-lite-main.app.main":
    ok("module_name_from_path correct")
else:
    fail(f"module_name_from_path incorrect: {m}")

# 1k. __init__ stripped from module name
m2 = module_name_from_path("app/__init__.py")
if m2 == "app":
    ok("__init__ stripped from module name")
else:
    fail(f"__init__ should be stripped, got: {m2}")

# 1l. docstring from parse_python_source should be None for no-docstring file
src5 = "x = 1"
r5 = parse_python_source(src5, "x.py")
if r5["docstring"] is None:
    ok("No docstring → docstring is None (not empty string)")
else:
    fail(f"docstring should be None for files without docstring, got: {repr(r5['docstring'])}")

# 1m. actual docstring is captured
src6 = '"""This is the module doc."""\nx = 1'
r6 = parse_python_source(src6, "x.py")
if r6["docstring"] == "This is the module doc.":
    ok("Module docstring captured correctly")
else:
    fail(f"Module docstring wrong: {repr(r6['docstring'])}")

# 1n. async function marked correctly
src7 = "async def my_func(): pass"
r7 = parse_python_source(src7, "x.py")
if r7["functions"] and r7["functions"][0]["async"] is True:
    ok("Async function correctly marked")
else:
    fail("Async function not correctly marked", str(r7["functions"]))

# ─────────────────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════")
print("  PHASE 2: Scanner Tests")
print("══════════════════════════════════════════════════")
from app.scanner import detect_language, should_skip, first_meaningful_line, read_text
from pathlib import Path as P

# 2a. Language detection
cases = [(".py", "Python"), (".js", "JavaScript"), (".ts", "TypeScript"), (".md", "Markdown"), (".unknown", "UNKNOWN")]
all_ok = True
for ext, expected in cases:
    path = P(f"file{ext}")
    got = detect_language(path)
    if got != expected:
        fail(f"detect_language({ext}) expected {expected}, got {got}")
        all_ok = False
if all_ok:
    ok("Language detection correct for all tested extensions")

# 2b. first_meaningful_line skips comments
fml = first_meaningful_line("# comment\n// another\nx = 1")
if fml == "x = 1":
    ok("first_meaningful_line skips comments")
else:
    fail(f"first_meaningful_line: {repr(fml)}")

# 2c. first_meaningful_line on empty string
fml2 = first_meaningful_line("")
if fml2 == "":
    ok("first_meaningful_line on empty string returns empty")
else:
    fail(f"first_meaningful_line on empty: {repr(fml2)}")

# ─────────────────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════")
print("  PHASE 3: Live API Endpoint Tests")
print("══════════════════════════════════════════════════")

# 3a. GET /
try:
    r = urllib.request.urlopen(BASE + "/")
    if r.status == 200 and b"DevDocs" in r.read():
        ok("GET / returns 200 with HTML")
    else:
        fail("GET / did not return expected HTML")
except Exception as e:
    fail("GET / threw exception", str(e))

# 3b. GET /summary
try:
    s = get("/summary")
    required_keys = ["file_count","python_files","function_count","class_count","import_count","average_loc","largest_file","smallest_file","languages"]
    missing = [k for k in required_keys if k not in s]
    if missing:
        fail(f"GET /summary missing keys: {missing}")
    else:
        ok("GET /summary has all required keys")
    # average_loc must be an integer, not a float
    aloc = s.get("average_loc")
    if isinstance(aloc, float):
        fail(f"average_loc is float ({aloc}) — should be int")
    else:
        ok(f"average_loc is integer: {aloc}")
except Exception as e:
    fail("GET /summary threw exception", str(e))

# 3c. GET /tree
try:
    t = get("/tree")
    if isinstance(t, list) and len(t) > 0:
        ok(f"GET /tree returns non-empty list ({len(t)} nodes)")
    else:
        fail("GET /tree returned empty or wrong type")
except Exception as e:
    fail("GET /tree threw exception", str(e))

# 3d. GET /files - no content field
try:
    files = get("/files")
    has_content = any("content" in f for f in files)
    if has_content:
        fail("GET /files leaks 'content' field — wastes bandwidth")
    else:
        ok("GET /files correctly strips 'content' field")
    has_parsed = any("parsed" in f for f in files)
    if has_parsed:
        fail("GET /files leaks 'parsed' field — wastes bandwidth")
    else:
        ok("GET /files correctly strips 'parsed' field")
except Exception as e:
    fail("GET /files threw exception", str(e))

# 3e. GET /preview - valid path
try:
    files = get("/files")
    py_files = [f for f in files if f["language"] == "Python"]
    if py_files:
        path = py_files[0]["path"]
        pv = get(f"/preview?path={urllib.parse.quote(path)}")
        required = ["path","language","content","truncated","insights"]
        missing = [k for k in required if k not in pv]
        if missing:
            fail(f"GET /preview missing keys: {missing}")
        else:
            ok("GET /preview has all required keys")
        ins = pv.get("insights") or {}
        if "docstring" in ins and "functions" in ins and "classes" in ins and "imports" in ins:
            ok("Preview insights include docstring, functions, classes, imports")
        else:
            fail("Preview insights missing fields", str(list(ins.keys())))
    else:
        fail("No Python files indexed to test preview")
except Exception as e:
    fail("GET /preview threw exception", str(e))

# 3f. GET /preview - invalid path returns 404
try:
    req = urllib.request.Request(BASE + "/preview?path=nonexistent%2Ffile.py")
    try:
        urllib.request.urlopen(req)
        fail("GET /preview with bad path should return 404, got 200")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            ok("GET /preview with invalid path correctly returns 404")
        else:
            fail(f"Expected 404 for bad path, got {e.code}")
except Exception as e:
    fail("GET /preview 404 test threw unexpected exception", str(e))

# 3g. GET /search
try:
    results = get("/search?q=upload")
    if isinstance(results, list) and len(results) > 0:
        ok(f"GET /search returns results ({len(results)} hits for 'upload')")
        r0 = results[0]
        if all(k in r0 for k in ["path","score","language","snippet"]):
            ok("Search result has correct shape")
        else:
            fail("Search result missing keys", str(list(r0.keys())))
    else:
        fail("GET /search returned no results for 'upload'")
except Exception as e:
    fail("GET /search threw exception", str(e))

# 3h. GET /search - empty query must return 422 (FastAPI validation)
try:
    req = urllib.request.Request(BASE + "/search?q=")
    try:
        urllib.request.urlopen(req)
        fail("GET /search with empty q should fail validation")
    except urllib.error.HTTPError as e:
        if e.code == 422:
            ok("GET /search with empty q correctly returns 422")
        else:
            fail(f"Expected 422 for empty q, got {e.code}")
except Exception as e:
    fail("GET /search empty-q test threw unexpected exception", str(e))

# 3i. POST /upload - non-zip rejected
try:
    boundary = "TestBoundary"
    body = b"--TestBoundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"bad.txt\"\r\nContent-Type: text/plain\r\n\r\nhello\r\n--TestBoundary--\r\n"
    req = urllib.request.Request(BASE + "/upload", data=body,
        headers={"Content-Type": "multipart/form-data; boundary=TestBoundary"}, method="POST")
    try:
        urllib.request.urlopen(req)
        fail("POST /upload with non-zip should reject")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            ok("POST /upload with non-zip correctly returns 400")
        else:
            fail(f"Expected 400 for non-zip, got {e.code}")
except Exception as e:
    fail("POST /upload non-zip test failed", str(e))

# 3j. POST /ask - empty question rejected
try:
    req = urllib.request.Request(BASE + "/ask",
        data=json.dumps({"question":""}).encode(),
        headers={"Content-Type":"application/json"}, method="POST")
    try:
        urllib.request.urlopen(req)
        fail("POST /ask with empty question should return 422")
    except urllib.error.HTTPError as e:
        if e.code == 422:
            ok("POST /ask with empty question correctly returns 422")
        else:
            fail(f"Expected 422 for empty question, got {e.code}")
except Exception as e:
    fail("POST /ask empty question test failed", str(e))

# ─────────────────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════")
print("  PHASE 4: Q&A Acceptance Tests")
print("══════════════════════════════════════════════════")

qa_tests = [
    ("What does ingest.py contain?",
     ["ingest.py", "save_upload", "extract_zip", "ingest_upload"],
     "ingest.py description must mention its functions"),
    ("Which file defines upload?",
     ["main.py", "upload"],
     "upload() must be found in main.py"),
    ("How many functions exist?",
     ["function"],
     "Must report function count"),
    ("Which modules import FastAPI?",
     ["main.py", "FastAPI"],
     "Must identify main.py imports FastAPI"),
    ("Show every class.",
     ["AskRequest", "SearchResponseItem", "PreviewResponse", "UploadResponse"],
     "Must show all 4 classes from models.py"),
    ("Explain main.py.",
     ["main.py", "startup", "upload", "summary", "search"],
     "Explain main.py must describe its functions"),
    ("What is the purpose of rag.py?",
     ["rag.py"],
     "Must describe rag.py from metadata"),
]

for question, expected_terms, label in qa_tests:
    try:
        ans = ask(question)
        answer_text = ans.get("answer","").lower()
        sources = ans.get("sources",[])
        missing_terms = [t for t in expected_terms if t.lower() not in answer_text]
        if missing_terms:
            fail(f"Q&A: '{question}'", f"Missing in answer: {missing_terms}\nAnswer was: {ans['answer'][:300]}")
        else:
            ok(f"Q&A: '{question}'")
        # Answer must NOT be the old keyword-match fallback
        if "relevant file matched" in answer_text:
            fail(f"Q&A still using keyword fallback for: {question}")
    except Exception as e:
        fail(f"Q&A: '{question}' threw exception", str(e))

# ─────────────────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════")
print("  PHASE 5: Statistics Accuracy Tests")
print("══════════════════════════════════════════════════")

try:
    summary = get("/summary")
    functions_resp = get("/functions")
    classes_resp = get("/classes")
    imports_resp = get("/imports")

    # Count functions from /functions endpoint
    actual_fn_count = sum(len(g["functions"]) for g in functions_resp)
    reported_fn_count = summary["function_count"]
    if actual_fn_count == reported_fn_count:
        ok(f"function_count consistent: /summary={reported_fn_count}, /functions total={actual_fn_count}")
    else:
        fail(f"function_count mismatch: /summary={reported_fn_count} vs /functions total={actual_fn_count}")

    # Count classes from /classes endpoint
    actual_cls_count = sum(len(g["classes"]) for g in classes_resp)
    reported_cls_count = summary["class_count"]
    if actual_cls_count == reported_cls_count:
        ok(f"class_count consistent: /summary={reported_cls_count}, /classes total={actual_cls_count}")
    else:
        fail(f"class_count mismatch: /summary={reported_cls_count} vs /classes total={actual_cls_count}")

    # Count imports from /imports endpoint
    actual_imp_count = sum(len(g["imports"]) for g in imports_resp)
    reported_imp_count = summary["import_count"]
    if actual_imp_count == reported_imp_count:
        ok(f"import_count consistent: /summary={reported_imp_count}, /imports total={actual_imp_count}")
    else:
        fail(f"import_count mismatch: /summary={reported_imp_count} vs /imports total={actual_imp_count}")

    # Python files count
    files = get("/files")
    actual_py = sum(1 for f in files if f["language"] == "Python")
    if actual_py == summary["python_files"]:
        ok(f"python_files consistent: {actual_py}")
    else:
        fail(f"python_files mismatch: /summary={summary['python_files']} vs /files count={actual_py}")

    # average_loc must be integer
    aloc = summary["average_loc"]
    if isinstance(aloc, int):
        ok(f"average_loc is int: {aloc}")
    else:
        fail(f"average_loc should be int, got {type(aloc).__name__}: {aloc}")

    # function_count must be > 0 (we have many functions)
    if reported_fn_count > 0:
        ok(f"function_count is non-zero: {reported_fn_count}")
    else:
        fail("function_count is 0 — parser not running correctly")

    # class_count should exactly match models.py classes
    if reported_cls_count == 4:
        ok(f"class_count is correct (4 classes in models.py)")
    else:
        fail(f"class_count: expected 4 (models.py classes), got {reported_cls_count}")

except Exception as e:
    fail("Statistics accuracy test failed", str(e))

# ─────────────────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════")
print("  PHASE 6: Edge Cases & Hidden Bugs")
print("══════════════════════════════════════════════════")

# 6a. Preview of non-Python file shows no insights
try:
    files = get("/files")
    non_py = [f for f in files if f["language"] != "Python" and f["language"] != "Text"]
    if non_py:
        path = non_py[0]["path"]
        pv = get(f"/preview?path={urllib.parse.quote(path)}")
        if pv["insights"] is None:
            ok(f"Preview of non-Python file ({non_py[0]['language']}) correctly returns null insights")
        else:
            fail(f"Preview of non-Python file should have null insights, got: {pv['insights']}")
    else:
        ok("No non-Python non-text files to test (skip)")
except Exception as e:
    fail("Preview non-Python edge case failed", str(e))

# 6b. Files endpoint strips 'parsed' field (it's large and internal)
try:
    files = get("/files")
    if files and "parsed" in files[0]:
        fail("GET /files leaks 'parsed' field to client — this is large internal data")
    else:
        ok("GET /files does not leak 'parsed' field")
except Exception as e:
    fail("Parsed field leak test failed", str(e))

# 6c. Search - path matching should rank path matches higher than content
try:
    results = get("/search?q=main")
    if results and "main" in results[0]["path"].lower():
        ok("Search ranks path matches above content matches")
    else:
        fail("Search does not prioritize path matches", str([r["path"] for r in results[:3]]))
except Exception as e:
    fail("Search path ranking test failed", str(e))

# 6d. Q&A for completely unknown question → no crash
try:
    ans = ask("xyzzy nothing happens frobozz")
    if isinstance(ans.get("answer"), str) and isinstance(ans.get("sources"), list):
        ok("Unknown question returns valid dict without crash")
    else:
        fail("Unknown question returned invalid response", str(ans))
except Exception as e:
    fail("Unknown question crashed", str(e))

# 6e. Q&A ask about a file not in index
try:
    ans = ask("What does nonexistent_file.py contain?")
    # Should NOT crash. Either fall back to search or report not found.
    if isinstance(ans.get("answer"), str):
        ok("Q&A for non-indexed filename returns string answer without crash")
    else:
        fail("Q&A for non-indexed file returned invalid response")
except Exception as e:
    fail("Q&A for non-indexed file crashed", str(e))

# 6f. ensure_insight_metadata rebuilds when INSIGHT_KEYS missing
from app.metadata import ensure_insight_metadata, INSIGHT_KEYS
old_meta = {"file_count": 5, "languages": {"Python": 5}, "project_name": "test"}
entries_with_py = [{"language": "Python", "path": "a.py", "name": "a.py",
                    "lines": 10, "size": 100,
                    "parsed": {"language":"Python","functions":[],"classes":[],"imports":[],"docstring":None,"error":"","file":"a.py","module":"a"}}]
rebuilt = ensure_insight_metadata(old_meta, entries_with_py)
if INSIGHT_KEYS.issubset(rebuilt.keys()):
    ok("ensure_insight_metadata rebuilds stale v0.1 metadata")
else:
    fail("ensure_insight_metadata did not rebuild stale metadata", str(list(rebuilt.keys())))

# 6g. ensure_insight_metadata doesn't rebuild when all keys present
full_meta = {k: 0 for k in INSIGHT_KEYS}
full_meta.update({"file_count": 1, "languages": {}, "project_name": "x", "indexed_at": "t",
                   "total_lines": 0, "total_size": 0, "method_count": 0, "important_files": []})
result = ensure_insight_metadata(full_meta, entries_with_py)
if result is full_meta:
    ok("ensure_insight_metadata returns cached metadata when keys present")
else:
    fail("ensure_insight_metadata unnecessarily rebuilt existing metadata")

# 6h. /files endpoint also strips 'content' - verify with actual content size
try:
    files_resp = get("/files")
    if files_resp:
        # If content was included it would make this much larger; just check key absence
        if "content" not in files_resp[0]:
            ok("Content stripped from /files response (confirmed)")
        else:
            fail("Content field present in /files - wastes bandwidth")
except Exception as e:
    fail("/files content-strip test failed", str(e))

# 6i. Test that python_entries() handles entries with empty parsed={}
from app.insights import python_entries
test_entries = [
    {"language": "Python", "path": "empty.py", "name": "empty.py", "content": "", "parsed": {}},
    {"language": "Python", "path": "full.py", "name": "full.py", "content": "def foo(): pass",
     "parsed": {"language":"Python","functions":[{"name":"foo","async":False,"decorators":[],"docstring":"","line":1}],
                "classes":[],"imports":[],"docstring":None,"error":"","file":"full.py","module":"full"}},
    {"language": "Markdown", "path": "readme.md", "name": "readme.md", "content": "hello", "parsed": {}},
]
result_entries = python_entries(test_entries)
if len(result_entries) == 2:  # only Python files
    ok("python_entries returns both empty and non-empty Python files, excludes non-Python")
else:
    fail(f"python_entries returned {len(result_entries)} entries, expected 2", str([e["path"] for e in result_entries]))

fn_count = sum(len(e["parsed"].get("functions",[])) for e in result_entries)
if fn_count == 1:
    ok("Function count correct across mixed empty/non-empty Python entries")
else:
    fail(f"Function count across test entries should be 1, got {fn_count}")

# 6j. Dead code: _parsed_metadata in scanner is defined but parse_python_source is called directly
import inspect
from app import scanner
src_text = inspect.getsource(scanner)
if "_parsed_metadata" in src_text and "def _parsed_metadata" in src_text:
    # Check if it's actually called anywhere
    if "= _parsed_metadata(" not in src_text and "=_parsed_metadata(" not in src_text:
        fail("Dead code: _parsed_metadata() is defined in scanner.py but never called — should be removed")
    else:
        ok("_parsed_metadata helper is called in scanner")
else:
    ok("No dead _parsed_metadata function in scanner")

# ─────────────────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════")
print("  PHASE 7: Architecture Violations")
print("══════════════════════════════════════════════════")

import ast as ast_mod

def check_no_business_logic(filepath, allowed_imports):
    """Verify a file has no business logic beyond routing."""
    with open(filepath) as f:
        src = f.read()
    tree = ast_mod.parse(src)
    violations = []
    for node in ast_mod.walk(tree):
        if isinstance(node, ast_mod.FunctionDef):
            if node.name not in ("startup", "get_entries", "home", "upload", "summary",
                                  "tree", "files", "functions", "classes", "imports",
                                  "preview", "search", "ask"):
                violations.append(f"Non-route function in main.py: {node.name}")
    return violations

main_violations = check_no_business_logic(
    r"d:\devdocs-lite-main\devdocs-lite-main\app\main.py", [])
if not main_violations:
    ok("main.py contains only route functions and get_entries helper")
else:
    fail("main.py architecture violation", str(main_violations))

# Check parser.py has no FastAPI imports
with open(r"d:\devdocs-lite-main\devdocs-lite-main\app\parser.py") as f:
    parser_src = f.read()
if "fastapi" in parser_src.lower():
    fail("parser.py has FastAPI import — architecture violation")
else:
    ok("parser.py has no FastAPI imports")

# Check scanner.py has no FastAPI imports
with open(r"d:\devdocs-lite-main\devdocs-lite-main\app\scanner.py") as f:
    scanner_src = f.read()
if "fastapi" in scanner_src.lower():
    fail("scanner.py has FastAPI import — architecture violation")
else:
    ok("scanner.py has no FastAPI imports")

# ─────────────────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════")
print("  FINAL REPORT")
print("══════════════════════════════════════════════════")
print(f"\n  Total PASS: {len(PASSES)}")
print(f"  Total FAIL: {len(FAILURES)}")
if FAILURES:
    print("\n  Failures:")
    for f in FAILURES:
        print(f"    {f}")
else:
    print("\n  All checks passed.")
