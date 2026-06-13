from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .config import BASE_DIR, FILES_INDEX_PATH, METADATA_PATH
from .ingest import ingest_upload
from .models import AskRequest, PreviewResponse, UploadResponse
from .preview import preview_file
from .rag import answer_question
from .search import search_entries
from .tree import build_tree
from .utils import ensure_workspace, read_json


app = FastAPI(title="DevDocs Lite", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def startup() -> None:
    ensure_workspace()


def get_entries() -> list[dict]:
    return read_json(FILES_INDEX_PATH, [])


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> dict:
    return await ingest_upload(file)


@app.get("/summary")
def summary() -> dict:
    return read_json(METADATA_PATH, {"file_count": 0, "languages": {}, "important_files": []})


@app.get("/tree")
def tree() -> list[dict]:
    return build_tree(get_entries())


@app.get("/files")
def files() -> list[dict]:
    return [
        {key: value for key, value in entry.items() if key != "content"}
        for entry in get_entries()
    ]


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
