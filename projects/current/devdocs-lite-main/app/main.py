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