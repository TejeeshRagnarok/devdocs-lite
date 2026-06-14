from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .config import BASE_DIR, FILES_INDEX_PATH, METADATA_PATH
from .explainer import explain_class, explain_file, explain_function, explain_project
from .ingest import ingest_upload
from .insights import classes_by_file, functions_by_file, imports_by_file
from .metadata import ensure_insight_metadata
from .models import AskRequest, PreviewResponse, UploadResponse
from .preview import preview_file
from .rag import answer_question
from .search import search_entries
from .tree import build_tree
from .utils import ensure_workspace, read_json


app = FastAPI(title="DevDocs Lite", version="0.3.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def startup() -> None:
    ensure_workspace()


def get_entries() -> list[dict]:
    """Read the current file index from disk."""
    return read_json(FILES_INDEX_PATH, [])


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> dict:
    return await ingest_upload(file)


@app.get("/summary")
def summary() -> dict:
    metadata = read_json(METADATA_PATH, {"file_count": 0, "languages": {}, "important_files": []})
    return ensure_insight_metadata(metadata, get_entries())


@app.get("/tree")
def tree() -> list[dict]:
    return build_tree(get_entries())


@app.get("/files")
def files() -> list[dict]:
    _STRIP = {"content", "parsed"}
    return [
        {key: value for key, value in entry.items() if key not in _STRIP}
        for entry in get_entries()
    ]


@app.get("/functions")
def functions() -> list[dict]:
    return functions_by_file(get_entries())


@app.get("/classes")
def classes() -> list[dict]:
    return classes_by_file(get_entries())


@app.get("/imports")
def imports() -> list[dict]:
    return imports_by_file(get_entries())


@app.get("/preview", response_model=PreviewResponse)
def preview(path: str = Query(..., min_length=1)) -> dict:
    result = preview_file(path, get_entries())
    if not result:
        raise HTTPException(status_code=404, detail="File not found in the current index.")
    return result


@app.get("/search")
def search(q: str = Query(..., min_length=1)) -> list[dict]:
    return search_entries(q, get_entries())


@app.post("/ask")
def ask(payload: AskRequest) -> dict:
    return answer_question(payload.question, get_entries())


@app.get("/explain/file")
def explain_file_endpoint(path: str = Query(..., min_length=1)) -> dict:
    """Return a natural-language explanation of a specific file."""
    return explain_file(path, get_entries())


@app.get("/explain/project")
def explain_project_endpoint() -> dict:
    """Return a full project explanation with architecture and workflows."""
    entries = get_entries()
    metadata = read_json(METADATA_PATH, {"file_count": 0, "languages": {}, "important_files": []})
    metadata = ensure_insight_metadata(metadata, entries)
    return explain_project(entries, metadata)


@app.get("/explain/function")
def explain_function_endpoint(name: str = Query(..., min_length=1)) -> dict:
    """Return an explanation of a specific function or method."""
    return explain_function(name, get_entries())


@app.get("/explain/class")
def explain_class_endpoint(name: str = Query(..., min_length=1)) -> dict:
    """Return an explanation of a specific class."""
    return explain_class(name, get_entries())
