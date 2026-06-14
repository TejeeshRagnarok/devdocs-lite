# DevDocs Lite

A lightweight local tool for understanding a codebase by uploading a ZIP file, browsing indexed files, searching source, and asking questions.

## Features

- Upload and extract a ZIP codebase
- Index text and source files while skipping common binary/build artifacts
- Parse Python files with `ast` for functions, classes, methods, imports, decorators, and docstrings
- Browse project summary, repository insights, language mix, file list, and previews
- Filter files by language
- Search across indexed code
- Ask codebase questions with metadata-aware retrieval and source matches

## API

- `POST /upload` uploads and indexes a ZIP repository
- `GET /summary` returns project statistics and repository insights
- `GET /tree` returns the indexed file tree
- `GET /files` returns indexed file metadata
- `GET /preview?path=...` returns file preview content and Python insights when available
- `GET /search?q=...` searches indexed code
- `POST /ask` answers repository questions using parsed metadata first, then text retrieval
- `GET /functions` returns Python functions grouped by file
- `GET /classes` returns Python classes grouped by file
- `GET /imports` returns Python imports grouped by file

## Generated Data

- `data/files.json` stores the searchable file index
- `data/metadata.json` stores project-level statistics
- `data/parsed.json` stores structured Python metadata

## Tech Stack

- FastAPI
- Python
- HTML, CSS, JavaScript

## Run

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and upload a ZIP file.
