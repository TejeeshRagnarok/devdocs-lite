# DevDocs Lite

A lightweight local tool for understanding a codebase by uploading a ZIP file, browsing indexed files, searching source, and asking questions.

## Features

- Upload and extract a ZIP codebase
- Index text and source files while skipping common binary/build artifacts
- Browse project summary, language mix, file list, and previews
- Search across indexed code
- Ask codebase questions with retrieval-based answers and source matches

## Tech Stack

- FastAPI
- Python
- HTML, CSS, JavaScript

## Run

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and upload a ZIP file.
