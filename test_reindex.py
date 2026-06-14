"""Upload the devdocs-lite-main.zip to the running server and verify results."""
import json
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8001"
zip_path = Path(__file__).parent / "uploads" / "devdocs-lite-main.zip"

boundary = "FormBoundaryXYZ123"
CRLF = b"\r\n"

with open(zip_path, "rb") as f:
    zip_data = f.read()

body = b""
body += b"--" + boundary.encode() + CRLF
body += b'Content-Disposition: form-data; name="file"; filename="devdocs-lite-main.zip"' + CRLF
body += b"Content-Type: application/zip" + CRLF + CRLF
body += zip_data + CRLF
body += b"--" + boundary.encode() + b"--" + CRLF

req = urllib.request.Request(
    BASE + "/upload",
    data=body,
    headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
    method="POST",
)
r = urllib.request.urlopen(req)
result = json.loads(r.read())
print("Upload result:", result)

# Now verify summary
r = urllib.request.urlopen(BASE + "/summary")
data = json.loads(r.read())
print("\n=== /summary after re-index ===")
for k in ["file_count", "python_files", "function_count", "class_count", "import_count", "average_loc"]:
    print(f"  {k}: {data.get(k)}")
print("  largest_file:", data.get("largest_file"))
print("  smallest_file:", data.get("smallest_file"))

# Verify Q&A acceptance tests
print("\n=== Q&A Acceptance Tests ===")


def ask(question):
    payload = json.dumps({"question": question}).encode()
    req2 = urllib.request.Request(
        BASE + "/ask",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req2)
    return json.loads(resp.read())


tests = [
    "What does ingest.py contain?",
    "Which file defines upload?",
    "How many functions exist?",
    "Which modules import FastAPI?",
    "Show every class.",
    "Explain main.py.",
    "What is the purpose of rag.py?",
]

for q in tests:
    ans = ask(q)
    print(f"\nQ: {q}")
    print("A:", ans["answer"][:400])
    print("Sources:", [s["path"] for s in ans.get("sources", [])][:3])
