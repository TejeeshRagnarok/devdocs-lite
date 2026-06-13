<<<<<<< HEAD
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
=======
import os
import shutil
import zipfile

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.cache = {}

# ✅ Use /tmp — completely avoids the corrupt data/raw file
RAW_DIR = "/tmp/devdocs/raw"
EXTRACT_DIR = "/tmp/devdocs/extracted"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        context={"request": request}
    )


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")

    # Clean old extracted data
    if os.path.exists(EXTRACT_DIR):
        shutil.rmtree(EXTRACT_DIR)

    os.makedirs(EXTRACT_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)

    zip_path = os.path.join(RAW_DIR, file.filename)
    with open(zip_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(EXTRACT_DIR)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    return {"message": "Upload successful. Codebase extracted."}


@app.post("/ask")
async def ask_question(data: dict):
    question = data.get("question")
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    return {"answer": f"You asked: {question}"}
>>>>>>> f89bf6497d40f4c8bc15e288c50ea09198ca8a27
